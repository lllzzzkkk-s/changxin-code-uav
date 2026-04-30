from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Optional

from uav.llm_control.ros_adapters.dry_run import build_dry_run_report
from uav.llm_control.safety.action_gate import (
    ActionApproval,
    ActionGateConfig,
    evaluate_action_gate,
)
from uav.llm_control.schemas.models import StateSnapshot


@dataclass(frozen=True)
class ActionGateDryRunReport:
    status: str
    request_id: Optional[str]
    profile_name: str
    dry_run_status: str
    gate_allowed: bool
    publish_attempted: bool
    command: Dict[str, Any]
    gate_decision: Dict[str, Any]
    trace: List[Dict[str, Any]]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_action_gate_dry_run_report(
    envelope: Mapping[str, Any],
    snapshot: StateSnapshot,
    approval: Optional[ActionApproval],
    *,
    now: float,
    requested_timeout_s: float,
    config: Optional[ActionGateConfig] = None,
) -> ActionGateDryRunReport:
    dry_run_report = build_dry_run_report(envelope, snapshot, now=now).as_dict()
    command = dry_run_report["command"]
    gate_decision = evaluate_action_gate(
        command,
        snapshot,
        approval,
        now=now,
        requested_timeout_s=requested_timeout_s,
        config=config,
    ).as_dict()

    trace = list(dry_run_report["trace"])
    trace.append(
        {
            "stage": "action_gate",
            "status": "allowed" if gate_decision["allowed"] else "rejected",
            "profile_name": gate_decision["audit"]["profile_name"],
            "reasons": list(gate_decision["reasons"]),
            "topic": gate_decision["topic"],
            "message_type": gate_decision["message_type"],
            "publish_attempted": False,
        }
    )

    gate_allowed = bool(gate_decision["allowed"])
    return ActionGateDryRunReport(
        status="gate_allowed" if gate_allowed else "gate_rejected",
        request_id=dry_run_report["request_id"],
        profile_name=gate_decision["audit"]["profile_name"],
        dry_run_status=dry_run_report["status"],
        gate_allowed=gate_allowed,
        publish_attempted=False,
        command=command,
        gate_decision=gate_decision,
        trace=trace,
    )
