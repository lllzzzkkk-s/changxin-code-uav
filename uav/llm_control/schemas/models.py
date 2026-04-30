from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional


SUPPORTED_LOCALIZATION_SOURCES = {"lio", "vio", "sim"}


def _copy_xyz(values: Mapping[str, Any], *, name: str) -> Dict[str, float]:
    required = ("x", "y", "z")
    missing = [key for key in required if key not in values]
    if missing:
        raise ValueError(f"{name} missing keys: {', '.join(missing)}")
    return {key: float(values[key]) for key in required}


@dataclass(frozen=True)
class FcuSnapshot:
    connected: bool
    armed: bool
    mode: str
    updated_at: float

    def age_s(self, now: float) -> float:
        return float(now) - float(self.updated_at)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BatterySnapshot:
    voltage: float
    percentage: float
    updated_at: float

    def age_s(self, now: float) -> float:
        return float(now) - float(self.updated_at)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RcSnapshot:
    channels: List[int]
    updated_at: float

    def age_s(self, now: float) -> float:
        return float(now) - float(self.updated_at)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalizationSnapshot:
    source: str
    position: Mapping[str, Any]
    velocity: Mapping[str, Any]
    yaw: float
    updated_at: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "position", _copy_xyz(self.position, name="position"))
        object.__setattr__(self, "velocity", _copy_xyz(self.velocity, name="velocity"))
        object.__setattr__(self, "yaw", float(self.yaw))

    def age_s(self, now: float) -> float:
        return float(now) - float(self.updated_at)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StateSnapshot:
    captured_at: float
    fcu: FcuSnapshot
    battery: BatterySnapshot
    rc: RcSnapshot
    localization: LocalizationSnapshot
    ttl_s: float = 1.0

    def stale_fields(self, now: float, fields: Optional[List[str]] = None) -> List[str]:
        selected = fields or ["fcu", "battery", "rc", "localization"]
        stale = []
        for field_name in selected:
            snapshot = getattr(self, field_name)
            if snapshot.age_s(now) > self.ttl_s:
                stale.append(field_name)
        return stale

    def ready_flags(self, now: float) -> Dict[str, bool]:
        stale = set(self.stale_fields(now))
        return {
            "fcu_fresh": "fcu" not in stale,
            "battery_fresh": "battery" not in stale,
            "rc_fresh": "rc" not in stale,
            "localization_fresh": "localization" not in stale,
            "fcu_connected": self.fcu.connected,
            "localization_source_supported": self.localization.source in SUPPORTED_LOCALIZATION_SOURCES,
            "rc_channels_present": len(self.rc.channels) >= 8,
        }

    def as_dict(self, now: Optional[float] = None) -> Dict[str, Any]:
        data = asdict(self)
        if now is not None:
            data["ready_flags"] = self.ready_flags(now)
        return data


@dataclass(frozen=True)
class ToolContract:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    risk_class: str
    preconditions: List[str]
    confirmation_policy: str
    executor_binding: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CommandResult:
    status: str
    meta: Dict[str, Any]
    intent: Dict[str, Any]
    arguments: Dict[str, Any]
    resolution: Dict[str, Any] = field(default_factory=dict)
    safety: Dict[str, Any] = field(default_factory=dict)
    execution: Dict[str, Any] = field(default_factory=dict)
    data: Optional[Dict[str, Any]] = None
    failure_code: Optional[str] = None
    message: str = ""
    trace: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "meta": self.meta,
            "intent": self.intent,
            "arguments": self.arguments,
            "resolution": self.resolution,
            "safety": self.safety,
            "execution": self.execution,
            "data": self.data,
            "failure_code": self.failure_code,
            "message": self.message,
            "trace": self.trace,
        }
