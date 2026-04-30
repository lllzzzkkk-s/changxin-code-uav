from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Optional

from uav.llm_control.core.pipeline import process_command
from uav.llm_control.schemas.models import CommandResult, StateSnapshot


@dataclass(frozen=True)
class DryRunReport:
    status: str
    request_id: Optional[str]
    publish_attempted: bool
    command: Dict[str, Any]
    trace: List[Dict[str, Any]]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_dry_run_report(envelope: Mapping[str, Any], snapshot: StateSnapshot, *, now: float) -> DryRunReport:
    result = process_command(envelope, snapshot, now=now)
    command = result.as_dict()
    return DryRunReport(
        status=result.status,
        request_id=result.meta.get("request_id"),
        publish_attempted=bool(result.execution.get("publish_attempted", False)),
        command=command,
        trace=_adapter_trace(result, snapshot, now),
    )


def _adapter_trace(result: CommandResult, snapshot: StateSnapshot, now: float) -> List[Dict[str, Any]]:
    payload = result.execution.get("ros_payload")
    trace: List[Dict[str, Any]] = [
        {
            "stage": "input",
            "request_id": result.meta.get("request_id"),
            "intent": result.intent.get("name"),
            "arguments": result.arguments,
        },
        _schema_validation_stage(result),
        {
            "stage": "state_snapshot",
            "ttl_s": snapshot.ttl_s,
            "ready_flags": snapshot.ready_flags(now),
            "fcu": {
                "connected": snapshot.fcu.connected,
                "armed": snapshot.fcu.armed,
                "mode": snapshot.fcu.mode,
                "age_s": snapshot.fcu.age_s(now),
            },
            "battery": {
                "voltage": snapshot.battery.voltage,
                "percentage": snapshot.battery.percentage,
                "age_s": snapshot.battery.age_s(now),
            },
            "rc": {
                "channels_count": len(snapshot.rc.channels),
                "age_s": snapshot.rc.age_s(now),
            },
            "localization": {
                "source": snapshot.localization.source,
                "position": dict(snapshot.localization.position),
                "velocity": dict(snapshot.localization.velocity),
                "yaw": snapshot.localization.yaw,
                "age_s": snapshot.localization.age_s(now),
            },
        },
        {
            "stage": "safety_policy",
            "risk_class": result.safety.get("risk_class"),
            "confirmation_policy": result.safety.get("confirmation_policy"),
            "reasons": list(result.safety.get("reasons") or []),
            "failure_code": result.failure_code,
        },
        {
            "stage": "target_point",
            "target_position": result.resolution.get("target_position"),
            "source_position": result.resolution.get("source_position"),
            "frame": result.resolution.get("frame"),
            "localization_source": result.resolution.get("localization_source"),
        },
        _ros_payload_stage(payload),
        {
            "stage": "confirmation_gate",
            "status": _confirmation_status(result),
            "publish_attempted": False,
            "dry_run": True,
        },
    ]
    return trace


def _schema_validation_stage(result: CommandResult) -> Dict[str, Any]:
    rejected = result.failure_code == "validation_failure"
    return {
        "stage": "schema_validation",
        "status": "rejected" if rejected else "accepted",
        "failure_code": result.failure_code if rejected else None,
        "message": result.message if rejected else "",
    }


def _ros_payload_stage(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if payload is None:
        return {
            "stage": "ros_payload",
            "payload": None,
            "topic": None,
            "message_type": None,
            "message": None,
        }
    return {
        "stage": "ros_payload",
        "payload": payload,
        "topic": payload.get("topic"),
        "message_type": payload.get("message_type"),
        "message": payload.get("message"),
    }


def _confirmation_status(result: CommandResult) -> str:
    if result.status == "needs_confirmation":
        return "blocked_for_confirmation"
    if result.status == "succeeded":
        return "not_required"
    return "not_reached"
