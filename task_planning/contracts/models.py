from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional


ALLOWED_CAPABILITIES = {
    "inspect_area",
    "move_to_region",
    "confirm_target",
    "relay_or_overwatch",
    "hold_position",
    "return_home",
    "land_or_stop",
}

ALLOWED_FAILURE_TYPES = {
    "localization_unstable",
    "battery_low",
    "path_blocked",
    "target_not_found",
    "task_timeout",
    "safety_gate_reject",
    "ros_bridge_error",
    "operator_interrupt",
    "comm_lost",
}

RAW_ROS_PREFIXES = ("/mavros/", "/cmd_vel", "/setpoints_cmd")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PlatformState:
    platform_id: str
    platform_type: str
    capabilities: List[str]
    comm_status: str = "online"
    task_status: str = "idle"
    localization_ok: bool = True
    safety_state: str = "normal"
    battery_percentage: float = 0.80
    timestamp: str = field(default_factory=utc_timestamp)
    schema: str = "PlatformState.v1"

    @classmethod
    def example(cls, platform_id: str, platform_type: str, capabilities: List[str]) -> "PlatformState":
        return cls(platform_id=platform_id, platform_type=platform_type, capabilities=list(capabilities))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlatformState":
        return cls(
            platform_id=str(data.get("platform_id", "")),
            platform_type=str(data.get("platform_type", "")),
            capabilities=list(data.get("capabilities") or []),
            comm_status=str(data.get("comm_status", "online")),
            task_status=str(data.get("task_status", "idle")),
            localization_ok=bool(_nested_get(data, ["localization", "ok"], data.get("localization_ok", True))),
            safety_state=str(_nested_get(data, ["safety", "state"], data.get("safety_state", "normal"))),
            battery_percentage=float(_nested_get(data, ["battery", "percentage"], data.get("battery_percentage", 0.8))),
            timestamp=str(data.get("timestamp", utc_timestamp())),
            schema=str(data.get("schema", "PlatformState.v1")),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityRegistry:
    platforms: List[PlatformState]
    schema: str = "CapabilityRegistry.v1"

    @classmethod
    def scout_and_confirm_default(cls) -> "CapabilityRegistry":
        return cls(platforms=[
            PlatformState.example(
                platform_id="uav_0",
                platform_type="uav",
                capabilities=["inspect_area", "relay_or_overwatch", "hold_position", "return_home"],
            ),
            PlatformState.example(
                platform_id="ugv_0",
                platform_type="ugv",
                capabilities=["move_to_region", "confirm_target", "hold_position", "return_home"],
            ),
        ])

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CapabilityRegistry":
        return cls(platforms=[PlatformState.from_dict(item) for item in data.get("platforms") or []])

    def platform_by_id(self, platform_id: str) -> Optional[PlatformState]:
        for platform in self.platforms:
            if platform.platform_id == platform_id:
                return platform
        return None

    def platforms_with_capability(self, capability: str) -> List[PlatformState]:
        return [platform for platform in self.platforms if capability in platform.capabilities]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "platforms": [platform.as_dict() for platform in self.platforms],
        }


@dataclass(frozen=True)
class MissionRequest:
    mission_id: str
    mission_type: str
    areas: List[str]
    targets: List[str]
    required_capabilities: List[str]
    constraints: Dict[str, Any] = field(default_factory=dict)
    schema: str = "MissionRequest.v1"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MissionRequest":
        return cls(
            mission_id=str(data.get("mission_id", "")),
            mission_type=str(data.get("mission_type", "")),
            areas=list(data.get("areas") or []),
            targets=list(data.get("targets") or []),
            required_capabilities=list(data.get("required_capabilities") or []),
            constraints=dict(data.get("constraints") or {}),
            schema=str(data.get("schema", "MissionRequest.v1")),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskSchema:
    mission_request: MissionRequest
    intent: str
    context_snapshot: Dict[str, Any] = field(default_factory=dict)
    schema: str = "TaskSchema.v1"

    @classmethod
    def from_intent(
        cls,
        *,
        mission_id: str,
        intent: str,
        area_id: str,
        target_id: str,
        context_snapshot: Optional[Mapping[str, Any]] = None,
    ) -> "TaskSchema":
        return cls(
            intent=intent,
            context_snapshot=dict(context_snapshot or {}),
            mission_request=MissionRequest(
                mission_id=mission_id,
                mission_type="scout_and_confirm",
                areas=[area_id],
                targets=[target_id],
                required_capabilities=["inspect_area", "confirm_target", "relay_or_overwatch"],
                constraints={
                    "require_operator_before_motion": False,
                    "max_mission_duration_s": 600,
                },
            ),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskSchema":
        return cls(
            mission_request=MissionRequest.from_dict(data.get("mission_request") or {}),
            intent=str(data.get("intent", "")),
            context_snapshot=dict(data.get("context_snapshot") or {}),
            schema=str(data.get("schema", "TaskSchema.v1")),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "intent": self.intent,
            "context_snapshot": dict(self.context_snapshot),
            "mission_request": self.mission_request.as_dict(),
        }


@dataclass(frozen=True)
class MissionBlackboard:
    mission_id: str
    status: str = "running"
    open_tasks: List[str] = field(default_factory=list)
    in_progress: Dict[str, Any] = field(default_factory=dict)
    completed_tasks: List[str] = field(default_factory=list)
    failed_tasks: List[str] = field(default_factory=list)
    platform_states: Dict[str, Any] = field(default_factory=dict)
    targets: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    schema: str = "MissionBlackboard.v1"

    @classmethod
    def from_request(cls, request: MissionRequest, registry: CapabilityRegistry) -> "MissionBlackboard":
        return cls(
            mission_id=request.mission_id,
            open_tasks=list(request.required_capabilities),
            platform_states={platform.platform_id: platform.as_dict() for platform in registry.platforms},
            targets={target: {"status": "unknown", "position": None} for target in request.targets},
            events=[{"type": "mission_request_accepted", "mission_id": request.mission_id}],
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskCommand:
    mission_id: str
    task_id: str
    platform_id: str
    capability: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    preconditions: Dict[str, Any] = field(default_factory=lambda: {
        "localization_ok": True,
        "min_battery_percentage": 0.30,
    })
    abort_policy: str = "hold_position"
    disconnect_policy: str = "continue_current_task"
    timeout_s: int = 180
    requires_operator_confirm: bool = False
    schema: str = "TaskCommand.v1"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskCommand":
        return cls(
            mission_id=str(data.get("mission_id", "")),
            task_id=str(data.get("task_id", "")),
            platform_id=str(data.get("platform_id", "")),
            capability=str(data.get("capability", "")),
            parameters=dict(data.get("parameters") or {}),
            preconditions=dict(data.get("preconditions") or {}),
            abort_policy=str(data.get("abort_policy", "hold_position")),
            disconnect_policy=str(data.get("disconnect_policy", "continue_current_task")),
            timeout_s=int(data.get("timeout_s", 180)),
            requires_operator_confirm=bool(data.get("requires_operator_confirm", False)),
            schema=str(data.get("schema", "TaskCommand.v1")),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CommandAck:
    mission_id: str
    task_id: str
    platform_id: str
    accepted: bool
    reason: str = ""
    local_check: Dict[str, Any] = field(default_factory=lambda: {
        "capability_known": True,
        "localization_ok": True,
        "battery_ok": True,
        "safety_ok": True,
    })
    schema: str = "CommandAck.v1"

    @classmethod
    def accepted(cls, mission_id: str, task_id: str, platform_id: str) -> "CommandAck":
        return cls(mission_id=mission_id, task_id=task_id, platform_id=platform_id, accepted=True)

    @classmethod
    def rejected(cls, mission_id: str, task_id: str, platform_id: str, reason: str) -> "CommandAck":
        return cls(
            mission_id=mission_id,
            task_id=task_id,
            platform_id=platform_id,
            accepted=False,
            reason=reason,
            local_check={"capability_known": False, "localization_ok": True, "battery_ok": True, "safety_ok": False},
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskProgress:
    mission_id: str
    task_id: str
    platform_id: str
    status: str
    progress_ratio: float = 0.0
    message: str = ""
    observations: Dict[str, Any] = field(default_factory=dict)
    schema: str = "TaskProgress.v1"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FailureReport:
    mission_id: str
    task_id: str
    platform_id: str
    failure_type: str
    recoverable: bool
    reason: str
    recommended_actions: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)
    state_ref: str = ""
    schema: str = "FailureReport.v1"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FailureReport":
        return cls(
            mission_id=str(data.get("mission_id", "")),
            task_id=str(data.get("task_id", "")),
            platform_id=str(data.get("platform_id", "")),
            failure_type=str(data.get("failure_type", "")),
            recoverable=bool(data.get("recoverable", False)),
            reason=str(data.get("reason", "")),
            recommended_actions=list(data.get("recommended_actions") or []),
            evidence=dict(data.get("evidence") or {}),
            timestamp=str(data.get("timestamp", utc_timestamp())),
            state_ref=str(data.get("state_ref", "")),
            schema=str(data.get("schema", "FailureReport.v1")),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Heartbeat:
    platform_id: str
    gateway_status: str
    ros_master_ok: bool
    last_state_seq: int
    last_task_id: Optional[str] = None
    timestamp: str = field(default_factory=utc_timestamp)
    schema: str = "Heartbeat.v1"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def validate_mission_request(request: MissionRequest, registry: CapabilityRegistry) -> List[str]:
    errors = []
    if request.schema != "MissionRequest.v1":
        errors.append("schema must be MissionRequest.v1")
    if not request.mission_id:
        errors.append("mission_id is required")
    if request.mission_type != "scout_and_confirm":
        errors.append("mission_type must be scout_and_confirm")
    if not request.areas:
        errors.append("at least one area is required")
    if not request.targets:
        errors.append("at least one target is required")
    for capability in request.required_capabilities:
        if capability not in ALLOWED_CAPABILITIES:
            errors.append(f"capability is not allowed: {capability}")
        if not registry.platforms_with_capability(capability):
            errors.append(f"no platform can satisfy capability: {capability}")
    return errors


def validate_task_command(command: TaskCommand, registry: CapabilityRegistry) -> List[str]:
    errors = []
    if command.schema != "TaskCommand.v1":
        errors.append("schema must be TaskCommand.v1")
    if command.capability not in ALLOWED_CAPABILITIES:
        errors.append(f"capability is not allowed: {command.capability}")
    if _contains_raw_ros_reference(command.as_dict()):
        errors.append("raw ROS topic reference is forbidden in TaskCommand")

    platform = registry.platform_by_id(command.platform_id)
    if platform is None:
        errors.append(f"unknown platform_id: {command.platform_id}")
    elif command.capability not in platform.capabilities:
        errors.append(f"platform {command.platform_id} does not expose capability: {command.capability}")
    if command.disconnect_policy != "continue_current_task":
        errors.append("disconnect_policy must be continue_current_task in phase 1")
    return errors


def validate_command_ack(ack: CommandAck) -> List[str]:
    errors = []
    if ack.schema != "CommandAck.v1":
        errors.append("schema must be CommandAck.v1")
    if not ack.mission_id:
        errors.append("mission_id is required")
    if not ack.task_id:
        errors.append("task_id is required")
    if not ack.platform_id:
        errors.append("platform_id is required")
    if not isinstance(ack.accepted, bool):
        errors.append("accepted must be bool")
    if not ack.accepted and not ack.reason:
        errors.append("rejected ack must include reason")
    return errors


def validate_failure_report(report: FailureReport) -> List[str]:
    errors = []
    if report.schema != "FailureReport.v1":
        errors.append("schema must be FailureReport.v1")
    if report.failure_type not in ALLOWED_FAILURE_TYPES:
        errors.append(f"failure_type is not allowed: {report.failure_type}")
    if not report.reason:
        errors.append("reason is required")
    if not report.task_id:
        errors.append("task_id is required")
    if not report.platform_id:
        errors.append("platform_id is required")
    return errors


def _nested_get(data: Mapping[str, Any], path: List[str], default: Any) -> Any:
    current = data
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _contains_raw_ros_reference(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith(RAW_ROS_PREFIXES) or value in RAW_ROS_PREFIXES
    if isinstance(value, Mapping):
        return any(_contains_raw_ros_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_raw_ros_reference(item) for item in value)
    return False
