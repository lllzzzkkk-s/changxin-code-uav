from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Protocol

from task_planning.contracts import CapabilityRegistry, CommandAck, PlatformState, TaskCommand, validate_task_command


class LocalCapabilityExecutor(Protocol):
    def dry_run(self, command: TaskCommand) -> CommandAck:
        ...

    def dispatch(self, command: TaskCommand) -> CommandAck:
        ...


@dataclass(frozen=True)
class GatewayServiceResponse:
    ack: CommandAck
    mode: str
    platform_id: str
    motion_attempted: bool
    raw_ros_publish_attempted: bool = False
    schema: str = "GatewayServiceResponse.v1"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "mode": self.mode,
            "platform_id": self.platform_id,
            "motion_attempted": self.motion_attempted,
            "raw_ros_publish_attempted": self.raw_ros_publish_attempted,
            "ack": self.ack.as_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)


class SafeDryRunExecutor:
    def dry_run(self, command: TaskCommand) -> CommandAck:
        return CommandAck(
            mission_id=command.mission_id,
            task_id=command.task_id,
            platform_id=command.platform_id,
            accepted=True,
            reason="dry_run_only",
            local_check={
                "capability_known": True,
                "localization_ok": True,
                "battery_ok": True,
                "safety_ok": True,
                "motion_attempted": False,
            },
        )

    def dispatch(self, command: TaskCommand) -> CommandAck:
        return CommandAck(
            mission_id=command.mission_id,
            task_id=command.task_id,
            platform_id=command.platform_id,
            accepted=False,
            reason="no local dispatch executor configured",
            local_check={
                "capability_known": True,
                "localization_ok": True,
                "battery_ok": True,
                "safety_ok": False,
                "motion_attempted": False,
            },
        )


class PlatformGatewayServiceCore:
    """Platform-side service core for ROS1 gateway wrappers.

    ROS-specific service handlers should pass the received TaskCommand JSON to
    `handle_json`. This core validates capability-level commands and refuses raw
    ROS controls before any local executor is called.
    """

    def __init__(
        self,
        *,
        platform_state: PlatformState,
        registry: Optional[CapabilityRegistry] = None,
        executor: Optional[LocalCapabilityExecutor] = None,
    ) -> None:
        self.platform_state = platform_state
        self.registry = registry or CapabilityRegistry(platforms=[platform_state])
        self.executor = executor or SafeDryRunExecutor()

    def dry_run_json(self, task_command_json: str) -> str:
        return self.handle_json(task_command_json, mode="dry_run").to_json()

    def dispatch_json(self, task_command_json: str) -> str:
        return self.handle_json(task_command_json, mode="dispatch").to_json()

    def handle_json(self, task_command_json: str, *, mode: str) -> GatewayServiceResponse:
        if mode not in {"dry_run", "dispatch"}:
            return self._reject_empty(mode, f"unsupported gateway mode: {mode}")
        try:
            data = json.loads(task_command_json)
        except json.JSONDecodeError as exc:
            return self._reject_empty(mode, f"invalid TaskCommand JSON: {exc}")
        if not isinstance(data, Mapping):
            return self._reject_empty(mode, "TaskCommand JSON must be an object")
        command = TaskCommand.from_dict(data)
        validation_errors = self._validate(command)
        if validation_errors:
            return self._response(
                mode=mode,
                ack=self._rejected(command, validation_errors[0]),
                motion_attempted=False,
            )
        ack = self.executor.dry_run(command) if mode == "dry_run" else self.executor.dispatch(command)
        return self._response(
            mode=mode,
            ack=ack,
            motion_attempted=bool(ack.local_check.get("motion_attempted", False)),
        )

    def _validate(self, command: TaskCommand) -> list[str]:
        errors = validate_task_command(command, self.registry)
        if command.platform_id != self.platform_state.platform_id:
            errors.append(f"command platform_id does not match this gateway: {command.platform_id}")
        if self.platform_state.comm_status != "online":
            errors.append(f"platform comm_status is not online: {self.platform_state.comm_status}")
        if not self.platform_state.localization_ok:
            errors.append("platform localization is not ok")
        if self.platform_state.safety_state != "normal":
            errors.append(f"platform safety_state is not normal: {self.platform_state.safety_state}")
        if self.platform_state.battery_percentage < float(command.preconditions.get("min_battery_percentage", 0.0)):
            errors.append("platform battery is below command precondition")
        return errors

    def _response(self, *, mode: str, ack: CommandAck, motion_attempted: bool) -> GatewayServiceResponse:
        return GatewayServiceResponse(
            ack=ack,
            mode=mode,
            platform_id=self.platform_state.platform_id,
            motion_attempted=motion_attempted,
            raw_ros_publish_attempted=False,
        )

    def _reject_empty(self, mode: str, reason: str) -> GatewayServiceResponse:
        ack = CommandAck.rejected(
            mission_id="",
            task_id="",
            platform_id=self.platform_state.platform_id,
            reason=reason,
        )
        return self._response(mode=mode, ack=ack, motion_attempted=False)

    def _rejected(self, command: TaskCommand, reason: str) -> CommandAck:
        return CommandAck(
            mission_id=command.mission_id,
            task_id=command.task_id,
            platform_id=command.platform_id or self.platform_state.platform_id,
            accepted=False,
            reason=reason,
            local_check={
                "capability_known": command.capability in self.platform_state.capabilities,
                "localization_ok": self.platform_state.localization_ok,
                "battery_ok": self.platform_state.battery_percentage >= float(command.preconditions.get("min_battery_percentage", 0.0)),
                "safety_ok": self.platform_state.safety_state == "normal",
                "motion_attempted": False,
            },
        )
