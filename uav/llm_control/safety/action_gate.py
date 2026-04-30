from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from uav.llm_control.schemas.models import CommandResult, StateSnapshot


DEFAULT_ALLOWED_ACTION_TOPICS = (
    "/goal",
    "/move_base_simple/goal",
    "/back_trigger",
    "/px4ctrl/takeoff_land",
)


@dataclass(frozen=True)
class ActionGateConfig:
    profile_name: str = "a-stage-sim-dry-run"
    allowed_topics: Sequence[str] = DEFAULT_ALLOWED_ACTION_TOPICS
    allowed_intents: Sequence[str] = ("move_relative", "return_home", "takeoff", "land")
    allowed_fcu_modes: Sequence[str] = ("OFFBOARD",)
    allowed_localization_sources: Sequence[str] = ("lio", "vio", "sim")
    min_target_z_m: float = 0.5
    max_target_z_m: float = 3.0
    max_goal_distance_m: float = 1.0
    max_execution_timeout_s: float = 3.0


@dataclass(frozen=True)
class ActionApproval:
    operator_id: str
    confirmation_phrase: str
    approved_at: float
    expires_at: float
    sim_evidence_id: str
    rollback_plan_id: str
    action_summary: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionGateDecision:
    allowed: bool
    reasons: Sequence[str]
    topic: Optional[str]
    message_type: Optional[str]
    publish_attempted: bool
    audit: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_action_gate(
    command: Union[CommandResult, Mapping[str, Any]],
    snapshot: StateSnapshot,
    approval: Optional[ActionApproval],
    *,
    now: float,
    requested_timeout_s: float,
    config: Optional[ActionGateConfig] = None,
) -> ActionGateDecision:
    """Evaluate whether a dry-run action is eligible for a later publish step.

    This function is deliberately side-effect free. An allowed decision means the
    caller may proceed to a separate publisher implementation; this function
    itself never publishes and always reports publish_attempted=False.
    """

    cfg = config or ActionGateConfig()
    command_dict = command.as_dict() if isinstance(command, CommandResult) else dict(command)
    meta = dict(command_dict.get("meta") or {})
    intent = dict(command_dict.get("intent") or {})
    execution = dict(command_dict.get("execution") or {})
    payload = execution.get("ros_payload")
    payload = dict(payload) if isinstance(payload, Mapping) else None
    topic = payload.get("topic") if payload else None
    message_type = payload.get("message_type") if payload else None
    reasons: List[str] = []

    if command_dict.get("status") != "needs_confirmation":
        reasons.append("command_not_ready_for_action")
    if intent.get("name") not in set(cfg.allowed_intents):
        reasons.append("intent_not_allowlisted")
    if bool(execution.get("publish_attempted", False)):
        reasons.append("publish_already_attempted")
    if payload is None:
        reasons.append("ros_payload_missing")
    if topic not in set(cfg.allowed_topics):
        reasons.append("topic_not_allowlisted")
    if topic == "/setpoints_cmd":
        reasons.append("low_level_setpoint_topic_denied")
    if isinstance(topic, str) and topic.startswith("/mavros/"):
        reasons.append("low_level_mavros_endpoint_denied")

    reasons.extend(f"{field}_stale" for field in snapshot.stale_fields(now))
    if not snapshot.fcu.connected:
        reasons.append("fcu_not_connected")
    if snapshot.fcu.mode not in set(cfg.allowed_fcu_modes):
        reasons.append("fcu_mode_not_offboard")
    if snapshot.localization.source not in set(cfg.allowed_localization_sources):
        reasons.append("unsupported_localization_source")

    expected_phrase = _expected_confirmation_phrase(meta, intent, topic)
    if approval is None:
        reasons.append("operator_confirmation_missing")
        approval_audit = None
    else:
        approval_audit = approval.as_dict()
        if approval.expires_at < now:
            reasons.append("operator_confirmation_expired")
        if approval.approved_at > now:
            reasons.append("operator_confirmation_from_future")
        if approval.confirmation_phrase != expected_phrase:
            reasons.append("operator_confirmation_phrase_mismatch")
        if not approval.operator_id:
            reasons.append("operator_id_missing")
        if not approval.sim_evidence_id:
            reasons.append("sim_evidence_missing")
        if not approval.rollback_plan_id:
            reasons.append("rollback_plan_missing")
        if not approval.action_summary:
            reasons.append("action_summary_missing")

    if requested_timeout_s <= 0:
        reasons.append("execution_timeout_invalid")
    elif requested_timeout_s > cfg.max_execution_timeout_s:
        reasons.append("execution_timeout_too_long")

    if payload is not None:
        reasons.extend(_payload_limit_reasons(payload, cfg))
    reasons.extend(_resolution_limit_reasons(command_dict.get("resolution"), cfg))

    audit = {
        "request_id": meta.get("request_id"),
        "intent": intent.get("name"),
        "operator_id": approval.operator_id if approval else None,
        "approval": approval_audit,
        "expected_confirmation_phrase": expected_phrase,
        "requested_timeout_s": float(requested_timeout_s),
        "now": float(now),
        "allowed_topics": list(cfg.allowed_topics),
        "allowed_intents": list(cfg.allowed_intents),
        "allowed_fcu_modes": list(cfg.allowed_fcu_modes),
        "allowed_localization_sources": list(cfg.allowed_localization_sources),
        "profile_name": cfg.profile_name,
        "ready_flags": snapshot.ready_flags(now),
    }
    return ActionGateDecision(
        allowed=not reasons,
        reasons=reasons,
        topic=topic,
        message_type=message_type,
        publish_attempted=False,
        audit=audit,
    )


def _expected_confirmation_phrase(meta: Mapping[str, Any], intent: Mapping[str, Any], topic: Optional[str]) -> str:
    return f"CONFIRM {meta.get('request_id')} {intent.get('name')} {topic}"


def _payload_limit_reasons(payload: Mapping[str, Any], config: ActionGateConfig) -> List[str]:
    message = payload.get("message")
    if not isinstance(message, Mapping):
        return []
    pose = message.get("pose")
    if not isinstance(pose, Mapping):
        return []
    position = pose.get("position")
    if not isinstance(position, Mapping) or "z" not in position:
        return []

    try:
        z = float(position["z"])
    except (TypeError, ValueError):
        return ["target_z_invalid"]
    if z < config.min_target_z_m or z > config.max_target_z_m:
        return ["target_z_out_of_bounds"]
    return []


def _resolution_limit_reasons(resolution: Any, config: ActionGateConfig) -> List[str]:
    if not isinstance(resolution, Mapping):
        return []
    source = resolution.get("source_position")
    target = resolution.get("target_position")
    if not isinstance(source, Mapping) or not isinstance(target, Mapping):
        return []
    try:
        dx = float(target["x"]) - float(source["x"])
        dy = float(target["y"]) - float(source["y"])
        dz = float(target["z"]) - float(source["z"])
    except (KeyError, TypeError, ValueError):
        return ["target_distance_invalid"]

    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
    if distance > config.max_goal_distance_m:
        return ["target_distance_too_large"]
    return []
