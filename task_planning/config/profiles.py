from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Union


ALLOWED_MISSION_PROFILES = {"dev_mock", "home_model_lab", "server_sim", "work_hardware"}
ALLOWED_MODEL_PROVIDERS = {"mock", "local_http", "remote_http"}
ALLOWED_PLANNER_BACKENDS = {"mock", "pddl"}
ALLOWED_PLATFORM_BACKENDS = {"mock", "sim", "ros1_gateway"}
ALLOWED_STATE_STORES = {"json", "sqlite"}
ALLOWED_MODEL_LAB_EVIDENCE_KINDS = {"unspecified", "mock_endpoint", "home_5090_live"}


class ProfileValidationError(ValueError):
    pass


@dataclass(frozen=True)
class EnvironmentProfile:
    mission_profile: str
    model_provider: str
    model_base_url: str
    model_name: str
    planner_backend: str
    platform_backend: str
    mission_state_store: str
    mission_artifact_root: str
    ros_master_uri: str = ""
    ros_ip: str = ""
    hardware_approval_required: bool = False
    ros_gateway_dispatch_service_template: str = "/fleet/{platform_id}/gateway/dispatch"
    ros_gateway_dry_run_service_template: str = "/fleet/{platform_id}/gateway/dry_run"
    model_lab_evidence_kind: str = "unspecified"
    source_path: Optional[str] = None
    schema: str = "EnvironmentProfile.v1"

    @classmethod
    def from_env_file(cls, path: Union[str, Path]) -> "EnvironmentProfile":
        profile_path = Path(path)
        data = parse_env_file(profile_path)
        return cls.from_mapping(data, source_path=str(profile_path), require_complete=True)

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, object],
        *,
        source_path: Optional[str] = None,
        require_complete: bool = True,
    ) -> "EnvironmentProfile":
        profile = cls(
            mission_profile=_read_value(data, "MISSION_PROFILE", "mission_profile", "dev_mock"),
            model_provider=_read_value(data, "MODEL_PROVIDER", "model_provider", "mock"),
            model_base_url=_read_value(data, "MODEL_BASE_URL", "model_base_url", ""),
            model_name=_read_value(data, "MODEL_NAME", "model_name", ""),
            planner_backend=_read_value(data, "PLANNER_BACKEND", "planner_backend", "mock"),
            platform_backend=_read_value(data, "PLATFORM_BACKEND", "platform_backend", "mock"),
            mission_state_store=_read_value(data, "MISSION_STATE_STORE", "mission_state_store", "json"),
            mission_artifact_root=_read_value(data, "MISSION_ARTIFACT_ROOT", "mission_artifact_root", ""),
            ros_master_uri=_read_value(data, "ROS_MASTER_URI", "ros_master_uri", ""),
            ros_ip=_read_value(data, "ROS_IP", "ros_ip", ""),
            hardware_approval_required=_read_bool(data, "HARDWARE_APPROVAL_REQUIRED", "hardware_approval_required", False),
            ros_gateway_dispatch_service_template=_read_value(
                data,
                "ROS_GATEWAY_DISPATCH_SERVICE_TEMPLATE",
                "ros_gateway_dispatch_service_template",
                "/fleet/{platform_id}/gateway/dispatch",
            ),
            ros_gateway_dry_run_service_template=_read_value(
                data,
                "ROS_GATEWAY_DRY_RUN_SERVICE_TEMPLATE",
                "ros_gateway_dry_run_service_template",
                "/fleet/{platform_id}/gateway/dry_run",
            ),
            model_lab_evidence_kind=_read_value(
                data,
                "MODEL_LAB_EVIDENCE_KIND",
                "model_lab_evidence_kind",
                "unspecified",
            ),
            source_path=source_path,
        )
        errors = profile.validate(require_complete=require_complete)
        if errors:
            raise ProfileValidationError("; ".join(errors))
        return profile

    def validate(self, *, require_complete: bool = True) -> List[str]:
        errors: List[str] = []
        if self.mission_profile not in ALLOWED_MISSION_PROFILES:
            errors.append(f"unsupported MISSION_PROFILE: {self.mission_profile}")
        if self.model_provider not in ALLOWED_MODEL_PROVIDERS:
            errors.append(f"unsupported MODEL_PROVIDER: {self.model_provider}")
        if self.planner_backend not in ALLOWED_PLANNER_BACKENDS:
            errors.append(f"unsupported PLANNER_BACKEND: {self.planner_backend}")
        if self.platform_backend not in ALLOWED_PLATFORM_BACKENDS:
            errors.append(f"unsupported PLATFORM_BACKEND: {self.platform_backend}")
        if self.mission_state_store not in ALLOWED_STATE_STORES:
            errors.append(f"unsupported MISSION_STATE_STORE: {self.mission_state_store}")
        if self.model_lab_evidence_kind not in ALLOWED_MODEL_LAB_EVIDENCE_KINDS:
            errors.append(f"unsupported MODEL_LAB_EVIDENCE_KIND: {self.model_lab_evidence_kind}")
        if require_complete and not self.mission_artifact_root:
            errors.append("MISSION_ARTIFACT_ROOT is required for portable run artifacts")
        if self.model_provider in {"local_http", "remote_http"}:
            if not self.model_base_url:
                errors.append(f"MODEL_BASE_URL is required when MODEL_PROVIDER={self.model_provider}")
            if not self.model_name:
                errors.append(f"MODEL_NAME is required when MODEL_PROVIDER={self.model_provider}")
        if self.platform_backend == "ros1_gateway":
            if not self.ros_master_uri:
                errors.append("ROS_MASTER_URI is required when PLATFORM_BACKEND=ros1_gateway")
            if not self.ros_ip:
                errors.append("ROS_IP is required when PLATFORM_BACKEND=ros1_gateway")
            if _contains_placeholder(self.ros_master_uri):
                errors.append("ROS_MASTER_URI still contains a template placeholder")
            if _contains_placeholder(self.ros_ip):
                errors.append("ROS_IP still contains a template placeholder")
            if "{platform_id}" not in self.ros_gateway_dispatch_service_template:
                errors.append("ROS_GATEWAY_DISPATCH_SERVICE_TEMPLATE must include {platform_id}")
            if "{platform_id}" not in self.ros_gateway_dry_run_service_template:
                errors.append("ROS_GATEWAY_DRY_RUN_SERVICE_TEMPLATE must include {platform_id}")

        errors.extend(self._validate_lane_rules())
        return errors

    def _validate_lane_rules(self) -> List[str]:
        errors: List[str] = []
        if self.mission_profile == "dev_mock":
            if self.model_provider != "mock":
                errors.append("dev_mock must use MODEL_PROVIDER=mock")
            if self.platform_backend != "mock":
                errors.append("dev_mock must use PLATFORM_BACKEND=mock")
        elif self.mission_profile == "home_model_lab":
            if self.model_provider not in {"mock", "local_http"}:
                errors.append("home_model_lab may use only MODEL_PROVIDER=mock|local_http")
            if self.platform_backend != "mock":
                errors.append("home_model_lab must use PLATFORM_BACKEND=mock")
        elif self.mission_profile == "server_sim":
            if self.model_provider not in {"mock", "remote_http"}:
                errors.append("server_sim may use only MODEL_PROVIDER=mock|remote_http")
            if self.platform_backend != "sim":
                errors.append("server_sim must use PLATFORM_BACKEND=sim")
        elif self.mission_profile == "work_hardware":
            if self.model_provider not in {"mock", "remote_http"}:
                errors.append("work_hardware may use only MODEL_PROVIDER=mock|remote_http")
            if self.platform_backend not in {"mock", "ros1_gateway"}:
                errors.append("work_hardware may use only PLATFORM_BACKEND=mock|ros1_gateway")
            if self.platform_backend == "ros1_gateway" and not self.hardware_approval_required:
                errors.append("work_hardware ros1_gateway requires HARDWARE_APPROVAL_REQUIRED=true")
        return errors

    def as_dict(self) -> Dict[str, object]:
        data = asdict(self)
        if data["source_path"] is None:
            data.pop("source_path")
        return data

    def as_env_dict(self) -> Dict[str, str]:
        return {
            "MISSION_PROFILE": self.mission_profile,
            "MODEL_PROVIDER": self.model_provider,
            "MODEL_BASE_URL": self.model_base_url,
            "MODEL_NAME": self.model_name,
            "PLANNER_BACKEND": self.planner_backend,
            "PLATFORM_BACKEND": self.platform_backend,
            "MISSION_STATE_STORE": self.mission_state_store,
            "MISSION_ARTIFACT_ROOT": self.mission_artifact_root,
            "ROS_MASTER_URI": self.ros_master_uri,
            "ROS_IP": self.ros_ip,
            "HARDWARE_APPROVAL_REQUIRED": "true" if self.hardware_approval_required else "false",
            "ROS_GATEWAY_DISPATCH_SERVICE_TEMPLATE": self.ros_gateway_dispatch_service_template,
            "ROS_GATEWAY_DRY_RUN_SERVICE_TEMPLATE": self.ros_gateway_dry_run_service_template,
            "MODEL_LAB_EVIDENCE_KIND": self.model_lab_evidence_kind,
        }


def load_profile(path: Union[str, Path]) -> EnvironmentProfile:
    return EnvironmentProfile.from_env_file(path)


def parse_env_file(path: Union[str, Path]) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ProfileValidationError(f"invalid env line: {raw_line}")
        key, value = line.split("=", 1)
        data[key.strip()] = _strip_quotes(value.strip())
    return data


def _read_value(data: Mapping[str, object], upper_key: str, lower_key: str, default: str) -> str:
    value = data.get(upper_key, data.get(lower_key, default))
    return str(value)


def _read_bool(data: Mapping[str, object], upper_key: str, lower_key: str, default: bool) -> bool:
    value = data.get(upper_key, data.get(lower_key, default))
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    raise ProfileValidationError(f"{upper_key} must be true or false")


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _contains_placeholder(value: str) -> bool:
    return "<" in value or ">" in value
