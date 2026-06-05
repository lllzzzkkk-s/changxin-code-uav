from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol

from task_planning.contracts import CommandAck, TaskCommand, TaskProgress


TARGET_MAP_SCHEMA = "UnitUgvTargetMap.v1"


@dataclass(frozen=True)
class UnitUgvTarget:
    target_id: str
    capability: str
    action: str
    operator_confirmed_mapping: bool
    frame_id: str = "map"
    x: Optional[float] = None
    y: Optional[float] = None
    yaw: float = 0.0
    max_distance_m: Optional[float] = None
    description: str = ""

    @classmethod
    def from_mapping(cls, target_id: str, data: Mapping[str, Any]) -> "UnitUgvTarget":
        operator_confirmed_mapping = data.get("operator_confirmed_mapping", False)
        if not isinstance(operator_confirmed_mapping, bool):
            raise ValueError(f"target {target_id} operator_confirmed_mapping must be a JSON boolean")
        return cls(
            target_id=target_id,
            capability=str(data.get("capability", "confirm_target")),
            action=str(data.get("action", "")),
            operator_confirmed_mapping=operator_confirmed_mapping,
            frame_id=str(data.get("frame_id", "map")),
            x=_optional_float(data.get("x")),
            y=_optional_float(data.get("y")),
            yaw=float(data.get("yaw", 0.0)),
            max_distance_m=_optional_float(data.get("max_distance_m")),
            description=str(data.get("description", "")),
        )


@dataclass(frozen=True)
class UnitUgvTargetMap:
    platform_id: str
    targets: Dict[str, UnitUgvTarget]
    schema: str = TARGET_MAP_SCHEMA

    @classmethod
    def from_path(cls, path: Path) -> "UnitUgvTargetMap":
        data = json.loads(path.expanduser().read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError("target map must be a JSON object")
        if data.get("schema") != TARGET_MAP_SCHEMA:
            raise ValueError(f"target map schema must be {TARGET_MAP_SCHEMA}")
        platform_id = str(data.get("platform_id", "")).strip()
        if not platform_id:
            raise ValueError("target map platform_id is required")
        raw_targets = data.get("targets")
        if not isinstance(raw_targets, Mapping) or not raw_targets:
            raise ValueError("target map requires a non-empty targets object")
        targets: Dict[str, UnitUgvTarget] = {}
        for target_id, target_data in raw_targets.items():
            if not isinstance(target_data, Mapping):
                raise ValueError(f"target map entry {target_id!r} must be an object")
            targets[str(target_id)] = UnitUgvTarget.from_mapping(str(target_id), target_data)
        return cls(platform_id=platform_id, targets=targets)


@dataclass(frozen=True)
class UnitUgvDispatchResult:
    accepted: bool
    reason: str
    motion_attempted: bool
    observations: Dict[str, Any]


class UnitUgvLocalBridge(Protocol):
    def confirm_without_motion(self, command: TaskCommand, target: UnitUgvTarget) -> UnitUgvDispatchResult:
        ...

    def move_base_confirm(self, command: TaskCommand, target: UnitUgvTarget, timeout_s: float) -> UnitUgvDispatchResult:
        ...


class RejectingUnitUgvBridge:
    def confirm_without_motion(self, command: TaskCommand, target: UnitUgvTarget) -> UnitUgvDispatchResult:
        return UnitUgvDispatchResult(
            accepted=True,
            reason="manual_confirm_completed",
            motion_attempted=False,
            observations={
                "target_id": target.target_id,
                "action": target.action,
                "description": target.description,
            },
        )

    def move_base_confirm(self, command: TaskCommand, target: UnitUgvTarget, timeout_s: float) -> UnitUgvDispatchResult:
        return UnitUgvDispatchResult(
            accepted=False,
            reason="move_base bridge is not enabled",
            motion_attempted=False,
            observations={"target_id": target.target_id, "action": target.action},
        )


class Ros1MoveBaseBridge(RejectingUnitUgvBridge):
    def __init__(
        self,
        *,
        rospy: Any,
        action_name: str = "/move_base",
        wait_for_server_s: float = 5.0,
    ) -> None:
        self.rospy = rospy
        self.action_name = action_name
        self.wait_for_server_s = wait_for_server_s
        self._actionlib = None
        self._MoveBaseAction = None
        self._MoveBaseGoal = None
        self._GoalStatus = None

    def move_base_confirm(self, command: TaskCommand, target: UnitUgvTarget, timeout_s: float) -> UnitUgvDispatchResult:
        errors = _move_base_target_errors(target)
        if errors:
            return UnitUgvDispatchResult(
                accepted=False,
                reason=errors[0],
                motion_attempted=False,
                observations={"target_id": target.target_id, "action": target.action},
            )
        self._load_ros_symbols()
        client = self._actionlib.SimpleActionClient(self.action_name, self._MoveBaseAction)
        if not client.wait_for_server(self.rospy.Duration(self.wait_for_server_s)):
            return UnitUgvDispatchResult(
                accepted=False,
                reason=f"move_base action server unavailable: {self.action_name}",
                motion_attempted=False,
                observations={"target_id": target.target_id, "action": target.action, "action_name": self.action_name},
            )

        goal = self._MoveBaseGoal()
        goal.target_pose.header.frame_id = target.frame_id
        goal.target_pose.header.stamp = self.rospy.Time.now()
        goal.target_pose.pose.position.x = float(target.x)
        goal.target_pose.pose.position.y = float(target.y)
        goal.target_pose.pose.position.z = 0.0
        goal.target_pose.pose.orientation.z = math.sin(float(target.yaw) / 2.0)
        goal.target_pose.pose.orientation.w = math.cos(float(target.yaw) / 2.0)

        client.send_goal(goal)
        finished = client.wait_for_result(self.rospy.Duration(timeout_s))
        if not finished:
            client.cancel_goal()
            return UnitUgvDispatchResult(
                accepted=False,
                reason="move_base goal timed out",
                motion_attempted=True,
                observations=self._move_base_observations(target, client),
            )
        state = client.get_state()
        if state == self._GoalStatus.SUCCEEDED:
            return UnitUgvDispatchResult(
                accepted=True,
                reason="move_base_goal_completed",
                motion_attempted=True,
                observations=self._move_base_observations(target, client),
            )
        return UnitUgvDispatchResult(
            accepted=False,
            reason=f"move_base goal failed with state {state}",
            motion_attempted=True,
            observations=self._move_base_observations(target, client),
        )

    def _load_ros_symbols(self) -> None:
        if self._actionlib is not None:
            return
        import actionlib  # type: ignore
        from actionlib_msgs.msg import GoalStatus  # type: ignore
        from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal  # type: ignore

        self._actionlib = actionlib
        self._GoalStatus = GoalStatus
        self._MoveBaseAction = MoveBaseAction
        self._MoveBaseGoal = MoveBaseGoal

    def _move_base_observations(self, target: UnitUgvTarget, client: Any) -> Dict[str, Any]:
        return {
            "target_id": target.target_id,
            "action": target.action,
            "action_name": self.action_name,
            "frame_id": target.frame_id,
            "x": target.x,
            "y": target.y,
            "yaw": target.yaw,
            "move_base_state": client.get_state(),
        }


class UnitUgvExecutor:
    """Local UGV executor for vetted TaskCommand.v1 confirm_target commands.

    This executor does not run a model and does not accept raw ROS references in
    TaskCommand. It only maps a validated capability-level command to a local,
    operator-confirmed target map.
    """

    def __init__(
        self,
        *,
        target_map: UnitUgvTargetMap,
        operator_approved: bool = False,
        bridge: Optional[UnitUgvLocalBridge] = None,
        progress_output: Optional[Path] = None,
        max_move_base_distance_m: Optional[float] = None,
    ) -> None:
        self.target_map = target_map
        self.operator_approved = operator_approved
        self.bridge = bridge or RejectingUnitUgvBridge()
        self.progress_output = progress_output
        self.max_move_base_distance_m = max_move_base_distance_m

    def dry_run(self, command: TaskCommand) -> CommandAck:
        target, errors = self._resolve_target(command)
        if errors:
            return self._reject(command, errors[0], target=target)
        return CommandAck(
            mission_id=command.mission_id,
            task_id=command.task_id,
            platform_id=command.platform_id,
            accepted=True,
            reason="unit_ugv_dry_run_ok",
            local_check=self._local_check(target=target, motion_attempted=False),
        )

    def dispatch(self, command: TaskCommand) -> CommandAck:
        target, errors = self._resolve_target(command)
        if errors:
            return self._reject(command, errors[0], target=target)
        if not self.operator_approved:
            return self._reject(command, "operator approval required for unit UGV dispatch", target=target)

        if target.action == "manual_confirm":
            result = self.bridge.confirm_without_motion(command, target)
        elif target.action == "move_base_goal":
            result = self.bridge.move_base_confirm(command, target, timeout_s=float(command.timeout_s))
        else:
            result = UnitUgvDispatchResult(
                accepted=False,
                reason=f"unsupported unit UGV target action: {target.action}",
                motion_attempted=False,
                observations={"target_id": target.target_id, "action": target.action},
            )
        progress = self._progress(command, target, result)
        self._write_progress([progress])
        return CommandAck(
            mission_id=command.mission_id,
            task_id=command.task_id,
            platform_id=command.platform_id,
            accepted=result.accepted,
            reason=result.reason,
            local_check=self._local_check(
                target=target,
                motion_attempted=result.motion_attempted,
                extra={
                    "dispatch_action": target.action,
                    "task_progress_output": str(self.progress_output) if self.progress_output else "",
                },
            ),
        )

    def _resolve_target(self, command: TaskCommand) -> tuple[Optional[UnitUgvTarget], List[str]]:
        errors: List[str] = []
        if command.platform_id != self.target_map.platform_id:
            errors.append(f"target map platform_id does not match command: {self.target_map.platform_id}")
        if command.capability != "confirm_target":
            errors.append(f"unit UGV executor supports confirm_target only, got {command.capability}")
        target_id = str(command.parameters.get("target_id") or "").strip()
        if not target_id:
            errors.append("confirm_target command requires parameters.target_id")
            return None, errors
        target = self.target_map.targets.get(target_id)
        if target is None:
            errors.append(f"target_id is not mapped on this unit UGV: {target_id}")
            return None, errors
        if target.capability != command.capability:
            errors.append(f"target mapping capability mismatch: {target.capability}")
        if not target.operator_confirmed_mapping:
            errors.append(f"target mapping is not operator-confirmed: {target_id}")
        if target.action == "move_base_goal":
            errors.extend(_move_base_target_errors(target))
            errors.extend(_move_base_distance_limit_errors(target, self.max_move_base_distance_m))
        elif target.action != "manual_confirm":
            errors.append(f"target action must be manual_confirm or move_base_goal: {target.action}")
        return target, errors

    def _reject(self, command: TaskCommand, reason: str, *, target: Optional[UnitUgvTarget]) -> CommandAck:
        return CommandAck(
            mission_id=command.mission_id,
            task_id=command.task_id,
            platform_id=command.platform_id,
            accepted=False,
            reason=reason,
            local_check=self._local_check(target=target, motion_attempted=False, safety_ok=False),
        )

    def _local_check(
        self,
        *,
        target: Optional[UnitUgvTarget],
        motion_attempted: bool,
        safety_ok: bool = True,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        check = {
            "capability_known": True,
            "localization_ok": True,
            "battery_ok": True,
            "safety_ok": safety_ok,
            "target_mapped": target is not None,
            "mapping_operator_confirmed": bool(target and target.operator_confirmed_mapping),
            "motion_attempted": motion_attempted,
            "raw_ros_publish_attempted": False,
        }
        check.update(dict(extra or {}))
        return check

    def _progress(self, command: TaskCommand, target: UnitUgvTarget, result: UnitUgvDispatchResult) -> Dict[str, Any]:
        status = "completed" if result.accepted else "failed"
        progress_ratio = 1.0 if result.accepted else 0.0
        return TaskProgress(
            mission_id=command.mission_id,
            task_id=command.task_id,
            platform_id=command.platform_id,
            status=status,
            progress_ratio=progress_ratio,
            message=result.reason,
            observations={
                "target_id": target.target_id,
                "capability": command.capability,
                "unit_ugv_action": target.action,
                "motion_attempted": result.motion_attempted,
                **dict(result.observations),
            },
        ).as_dict()

    def _write_progress(self, items: List[Mapping[str, Any]]) -> None:
        if self.progress_output is None:
            return
        self.progress_output.expanduser().parent.mkdir(parents=True, exist_ok=True)
        data = {"schema": "TaskProgressSet.v1", "items": [dict(item) for item in items]}
        self.progress_output.expanduser().write_text(
            json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)


def _move_base_target_errors(target: UnitUgvTarget) -> List[str]:
    errors = []
    if not target.frame_id:
        errors.append(f"move_base target {target.target_id} requires frame_id")
    if target.x is None or target.y is None:
        errors.append(f"move_base target {target.target_id} requires x and y")
    if target.max_distance_m is None or target.max_distance_m <= 0:
        errors.append(f"move_base target {target.target_id} requires positive max_distance_m")
    return errors


def _move_base_distance_limit_errors(
    target: UnitUgvTarget,
    max_move_base_distance_m: Optional[float],
) -> List[str]:
    if max_move_base_distance_m is None or max_move_base_distance_m <= 0:
        return ["move_base dispatch requires explicit max_move_base_distance_m limit"]
    if target.max_distance_m is not None and target.max_distance_m > max_move_base_distance_m:
        return [
            f"move_base target {target.target_id} max_distance_m {target.max_distance_m} "
            f"exceeds authorized limit {max_move_base_distance_m}"
        ]
    return []
