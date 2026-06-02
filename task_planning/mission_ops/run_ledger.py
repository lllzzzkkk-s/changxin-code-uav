from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MissionRunEvent:
    run_id: str
    mission_id: str
    event_type: str
    task_id: str = ""
    platform_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)
    schema: str = "MissionRunEvent.v1"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MissionRunEvent":
        return cls(
            run_id=str(data.get("run_id", "")),
            mission_id=str(data.get("mission_id", "")),
            event_type=str(data.get("event_type", "")),
            task_id=str(data.get("task_id", "")),
            platform_id=str(data.get("platform_id", "")),
            payload=dict(data.get("payload") or {}),
            timestamp=str(data.get("timestamp", utc_timestamp())),
            schema=str(data.get("schema", "MissionRunEvent.v1")),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OperatorApprovalState:
    required: bool
    approved: bool = False
    source: Optional[str] = None
    mission_id: Optional[str] = None
    task_id: Optional[str] = None
    platform_id: Optional[str] = None
    target_id: Optional[str] = None
    approved_at: Optional[str] = None
    expires_at: Optional[str] = None
    operator_note: str = ""
    schema: str = "OperatorApprovalState.v1"

    @classmethod
    def not_required(cls) -> "OperatorApprovalState":
        return cls(required=False)

    @classmethod
    def required_unapproved(
        cls,
        *,
        mission_id: str = "",
        task_id: str = "",
        platform_id: str = "",
        target_id: str = "",
    ) -> "OperatorApprovalState":
        return cls(
            required=True,
            approved=False,
            mission_id=mission_id,
            task_id=task_id,
            platform_id=platform_id,
            target_id=target_id,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OperatorApprovalState":
        return cls(
            required=bool(data.get("required", False)),
            approved=bool(data.get("approved", False)),
            source=data.get("source"),
            mission_id=data.get("mission_id"),
            task_id=data.get("task_id"),
            platform_id=data.get("platform_id"),
            target_id=data.get("target_id"),
            approved_at=data.get("approved_at"),
            expires_at=data.get("expires_at"),
            operator_note=str(data.get("operator_note", "")),
            schema=str(data.get("schema", "OperatorApprovalState.v1")),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MissionRunRecord:
    run_id: str
    case_id: str
    mission_id: str
    profile: str
    model_provider: str
    platform_backend: str
    phase_baseline: str
    artifact_bundle_path: str
    current_state: str
    operator_approval: OperatorApprovalState = field(default_factory=OperatorApprovalState.not_required)
    events: List[MissionRunEvent] = field(default_factory=list)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)
    schema: str = "MissionRunRecord.v1"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MissionRunRecord":
        return cls(
            run_id=str(data.get("run_id", "")),
            case_id=str(data.get("case_id", "")),
            mission_id=str(data.get("mission_id", "")),
            profile=str(data.get("profile", "")),
            model_provider=str(data.get("model_provider", "")),
            platform_backend=str(data.get("platform_backend", "")),
            phase_baseline=str(data.get("phase_baseline", "")),
            artifact_bundle_path=str(data.get("artifact_bundle_path", "")),
            current_state=str(data.get("current_state", "")),
            operator_approval=OperatorApprovalState.from_dict(data.get("operator_approval") or {}),
            events=[MissionRunEvent.from_dict(item) for item in data.get("events") or []],
            created_at=str(data.get("created_at", utc_timestamp())),
            updated_at=str(data.get("updated_at", utc_timestamp())),
            schema=str(data.get("schema", "MissionRunRecord.v1")),
        )

    def with_event(self, event: MissionRunEvent) -> "MissionRunRecord":
        return replace(self, events=[*self.events, event], updated_at=utc_timestamp())

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["operator_approval"] = self.operator_approval.as_dict()
        data["events"] = [event.as_dict() for event in self.events]
        return data


class JsonMissionRunLedger:
    def __init__(self, root: Union[str, Path]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, record: MissionRunRecord) -> None:
        self._path(record.run_id).write_text(
            json.dumps(record.as_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def load(self, run_id: str) -> MissionRunRecord:
        return MissionRunRecord.from_dict(json.loads(self._path(run_id).read_text(encoding="utf-8")))

    def append_event(self, run_id: str, event: MissionRunEvent) -> MissionRunRecord:
        record = self.load(run_id).with_event(_event_from_any(event))
        self.save(record)
        return record

    def _path(self, run_id: str) -> Path:
        return self.root / f"{run_id}.ledger.json"


def validate_operator_approval(
    approval: OperatorApprovalState,
    *,
    mission_id: str,
    task_id: str,
    platform_id: str,
    target_id: str,
    now: Optional[datetime] = None,
) -> List[str]:
    if not approval.required:
        return []
    errors: List[str] = []
    if not approval.approved:
        errors.append("operator approval is required")
        return errors
    if not approval.source:
        errors.append("operator approval source is required")
    if approval.mission_id and approval.mission_id != mission_id:
        errors.append("mission scope mismatch")
    if approval.task_id and approval.task_id != task_id:
        errors.append("task scope mismatch")
    if approval.platform_id and approval.platform_id != platform_id:
        errors.append("platform scope mismatch")
    if approval.target_id and approval.target_id != target_id:
        errors.append("target scope mismatch")
    if approval.expires_at:
        expires_at = _parse_time(approval.expires_at)
        current_time = now or datetime.now(timezone.utc)
        if expires_at < current_time:
            errors.append("operator approval is stale")
    return errors


def _event_from_any(event: Any) -> MissionRunEvent:
    if isinstance(event, MissionRunEvent):
        return event
    if hasattr(event, "as_dict"):
        return MissionRunEvent.from_dict(event.as_dict())
    return MissionRunEvent.from_dict(event)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
