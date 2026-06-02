from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MissionOpsState:
    run_id: str
    mission_id: str
    current_state: str
    input_artifact_refs: Dict[str, Any] = field(default_factory=dict)
    output_artifact_refs: Dict[str, Any] = field(default_factory=dict)
    approval_required: bool = False
    approval_state: Dict[str, Any] = field(default_factory=dict)
    execution_event_refs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)
    schema: str = "MissionOpsState.v1"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MissionOpsState":
        return cls(
            run_id=str(data.get("run_id", "")),
            mission_id=str(data.get("mission_id", "")),
            current_state=str(data.get("current_state", "")),
            input_artifact_refs=dict(data.get("input_artifact_refs") or {}),
            output_artifact_refs=dict(data.get("output_artifact_refs") or {}),
            approval_required=bool(data.get("approval_required", False)),
            approval_state=dict(data.get("approval_state") or {"schema": "OperatorApprovalState.v1", "required": False, "approved": False}),
            execution_event_refs=dict(data.get("execution_event_refs") or {}),
            error=data.get("error"),
            created_at=str(data.get("created_at", utc_timestamp())),
            updated_at=str(data.get("updated_at", utc_timestamp())),
            schema=str(data.get("schema", "MissionOpsState.v1")),
        )

    def transition(
        self,
        current_state: str,
        *,
        mission_id: Optional[str] = None,
        input_artifact_refs: Optional[Dict[str, Any]] = None,
        output_artifact_refs: Optional[Dict[str, Any]] = None,
        approval_required: Optional[bool] = None,
        approval_state: Optional[Dict[str, Any]] = None,
        execution_event_refs: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> "MissionOpsState":
        return replace(
            self,
            mission_id=self.mission_id if mission_id is None else mission_id,
            current_state=current_state,
            input_artifact_refs=self.input_artifact_refs if input_artifact_refs is None else input_artifact_refs,
            output_artifact_refs=self.output_artifact_refs if output_artifact_refs is None else output_artifact_refs,
            approval_required=self.approval_required if approval_required is None else approval_required,
            approval_state=self.approval_state if approval_state is None else approval_state,
            execution_event_refs=self.execution_event_refs if execution_event_refs is None else execution_event_refs,
            error=error,
            updated_at=utc_timestamp(),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
