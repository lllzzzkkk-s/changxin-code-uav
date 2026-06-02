from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

from task_planning.contracts import CommandAck, FailureReport, TaskCommand, TaskProgress
from task_planning.contracts.models import utc_timestamp
from task_planning.execution.plan_to_bt import BehaviorTreeArtifact


@dataclass(frozen=True)
class MissionRunEvent:
    run_id: str
    mission_id: str
    event_type: str
    task_id: str = ""
    platform_id: str = ""
    payload: Dict[str, Any] = None
    timestamp: str = ""
    schema: str = "MissionRunEvent.v1"

    def __post_init__(self) -> None:
        if self.payload is None:
            object.__setattr__(self, "payload", {})
        if not self.timestamp:
            object.__setattr__(self, "timestamp", utc_timestamp())

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BehaviorTreeRunResult:
    run_id: str
    mission_id: str
    status: str
    task_commands: List[TaskCommand]
    command_acks: List[CommandAck]
    task_progress: List[TaskProgress]
    events: List[MissionRunEvent]
    failure_report: Optional[FailureReport] = None
    schema: str = "BehaviorTreeRunResult.v1"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "mission_id": self.mission_id,
            "status": self.status,
            "task_commands": [command.as_dict() for command in self.task_commands],
            "command_acks": [ack.as_dict() for ack in self.command_acks],
            "task_progress": [progress.as_dict() for progress in self.task_progress],
            "events": [event.as_dict() for event in self.events],
            "failure_report": self.failure_report.as_dict() if self.failure_report else None,
        }


class BehaviorTreeRuntime:
    def __init__(
        self,
        *,
        gateway: Any,
        heartbeat_events: Optional[Iterable[Any]] = None,
        platform_state_events: Optional[Iterable[Any]] = None,
    ) -> None:
        self.gateway = gateway
        self.heartbeat_events = list(heartbeat_events or [])
        self.platform_state_events = list(platform_state_events or [])

    def run(
        self,
        behavior_tree: Union[BehaviorTreeArtifact, Mapping[str, Any]],
        *,
        run_id: str,
    ) -> BehaviorTreeRunResult:
        mission_id, commands = _commands_from_behavior_tree(behavior_tree)
        events: List[MissionRunEvent] = []
        acks: List[CommandAck] = []
        progress_items: List[TaskProgress] = []
        failure_report: Optional[FailureReport] = None

        _append_event(events, run_id, mission_id, "bt_runtime_started", payload={"task_count": len(commands)})
        for command in commands:
            _append_event(events, run_id, mission_id, "task_dispatch_requested", command)
            ack = self.gateway.dispatch(command)
            acks.append(ack)
            if ack.accepted:
                _append_event(events, run_id, mission_id, "command_ack_accepted", command, ack.as_dict())
                progress = TaskProgress(
                    mission_id=command.mission_id,
                    task_id=command.task_id,
                    platform_id=command.platform_id,
                    status="completed",
                    progress_ratio=1.0,
                    message=f"mock gateway completed capability {command.capability}",
                )
                progress_items.append(progress)
                _append_event(events, run_id, mission_id, "task_progress_observed", command, progress.as_dict())
                continue

            _append_event(events, run_id, mission_id, "command_ack_rejected", command, ack.as_dict())
            failure_report = FailureReport(
                mission_id=command.mission_id,
                task_id=command.task_id,
                platform_id=command.platform_id,
                failure_type="safety_gate_reject",
                recoverable=True,
                reason=ack.reason,
                recommended_actions=["central_replan"],
            )
            _append_event(events, run_id, mission_id, "failure_report_recorded", command, failure_report.as_dict())
            _append_event(
                events,
                run_id,
                mission_id,
                "central_replan_requested",
                command,
                {"mode": "central_replan", "reason": ack.reason},
            )
            break

        for heartbeat in self.heartbeat_events:
            payload = _payload_dict(heartbeat)
            _append_event(
                events,
                run_id,
                mission_id,
                "heartbeat_observed",
                task_id=str(payload.get("last_task_id") or ""),
                platform_id=str(payload.get("platform_id") or ""),
                payload=payload,
            )
        for platform_state in self.platform_state_events:
            payload = _payload_dict(platform_state)
            _append_event(
                events,
                run_id,
                mission_id,
                "platform_state_observed",
                platform_id=str(payload.get("platform_id") or ""),
                payload=payload,
            )

        status = "failed" if failure_report is not None else "completed"
        _append_event(events, run_id, mission_id, "bt_runtime_completed", payload={"status": status})
        return BehaviorTreeRunResult(
            run_id=run_id,
            mission_id=mission_id,
            status=status,
            task_commands=commands,
            command_acks=acks,
            task_progress=progress_items,
            events=events,
            failure_report=failure_report,
        )


def _commands_from_behavior_tree(
    behavior_tree: Union[BehaviorTreeArtifact, Mapping[str, Any]]
) -> tuple[str, List[TaskCommand]]:
    if isinstance(behavior_tree, BehaviorTreeArtifact):
        return behavior_tree.mission_id, list(behavior_tree.task_commands)
    mission_id = str(behavior_tree.get("mission_id", ""))
    commands = [
        item if isinstance(item, TaskCommand) else TaskCommand.from_dict(item)
        for item in behavior_tree.get("task_commands", [])
    ]
    return mission_id, commands


def _append_event(
    events: List[MissionRunEvent],
    run_id: str,
    mission_id: str,
    event_type: str,
    command: Optional[TaskCommand] = None,
    payload: Optional[Dict[str, Any]] = None,
    *,
    task_id: str = "",
    platform_id: str = "",
) -> None:
    events.append(MissionRunEvent(
        run_id=run_id,
        mission_id=mission_id,
        event_type=event_type,
        task_id=command.task_id if command else task_id,
        platform_id=command.platform_id if command else platform_id,
        payload=dict(payload or {}),
    ))


def _payload_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, Mapping):
        return dict(value)
    return {"value": value}
