from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.config import EnvironmentProfile, load_profile
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore


MISSION_INTENT_RUN_SCHEMA = "MissionIntentRun.v1"


@dataclass(frozen=True)
class MissionIntentRunReport:
    ok: bool
    intent: str
    profile_path: str
    mission_profile: str
    model_provider: str
    platform_backend: str
    context_snapshot: Dict[str, Any]
    case_id: str
    mission_id: str = ""
    run_id: str = ""
    status: str = ""
    current_state: str = ""
    artifact_bundle_path: str = ""
    validation_errors: tuple[str, ...] = ()
    ros_connected: bool = False
    hardware_dispatch_performed: bool = False
    schema: str = MISSION_INTENT_RUN_SCHEMA

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "intent": self.intent,
            "profile_path": self.profile_path,
            "mission_profile": self.mission_profile,
            "model_provider": self.model_provider,
            "platform_backend": self.platform_backend,
            "context_snapshot": dict(self.context_snapshot),
            "case_id": self.case_id,
            "mission_id": self.mission_id,
            "run_id": self.run_id,
            "status": self.status,
            "current_state": self.current_state,
            "artifact_bundle_path": self.artifact_bundle_path,
            "validation_errors": list(self.validation_errors),
            "ros_connected": self.ros_connected,
            "hardware_dispatch_performed": self.hardware_dispatch_performed,
        }


def run_task_planning_intent(
    *,
    profile_path: Path,
    intent: str,
    context_snapshot: Optional[Mapping[str, Any]] = None,
    case_id: str = "",
    artifact_root: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> MissionIntentRunReport:
    profile = load_profile(profile_path)
    if artifact_root is not None:
        profile_data = profile.as_env_dict()
        profile_data["MISSION_ARTIFACT_ROOT"] = str(_resolve_artifact_root(artifact_root, repo_root=repo_root))
        profile = EnvironmentProfile.from_mapping(profile_data)
    else:
        profile = _normalize_artifact_root(profile, repo_root=repo_root)

    context = dict(context_snapshot or {})
    profile_path_text = str(profile_path.expanduser())
    base = {
        "intent": intent,
        "profile_path": profile_path_text,
        "mission_profile": profile.mission_profile,
        "model_provider": profile.model_provider,
        "platform_backend": profile.platform_backend,
        "context_snapshot": context,
        "case_id": case_id,
    }
    validation_errors = _preflight_errors(intent=intent, profile=profile)
    if validation_errors:
        return MissionIntentRunReport(ok=False, validation_errors=tuple(validation_errors), **base)

    run_input = {
        "intent": intent,
        "context_snapshot": context,
        "case_id": case_id,
    }
    state_root = Path(profile.mission_artifact_root) / "_state"
    runner = MissionManagerRunner(
        state_store=JsonMissionOpsStateStore(state_root),
        gateway=MockPlatformGateway(),
    )
    result = runner.run(run_input, profile.as_env_dict())
    errors = []
    if result.state.error:
        errors.append(result.state.error)
    return MissionIntentRunReport(
        ok=not errors,
        mission_id=result.state.mission_id,
        run_id=result.run_id,
        status=result.status,
        current_state=result.state.current_state,
        artifact_bundle_path=result.artifact_bundle_path or "",
        validation_errors=tuple(errors),
        **base,
    )


def _preflight_errors(*, intent: str, profile: EnvironmentProfile) -> list[str]:
    errors: list[str] = []
    if not intent.strip():
        errors.append("intent is required")
    if profile.platform_backend.strip().lower() == "ros1_gateway":
        errors.append("PLATFORM_BACKEND=ros1_gateway is not allowed")
    return errors


def _normalize_artifact_root(profile: EnvironmentProfile, *, repo_root: Optional[Path]) -> EnvironmentProfile:
    artifact_root = Path(profile.mission_artifact_root).expanduser()
    if artifact_root.is_absolute():
        return profile
    profile_data = profile.as_env_dict()
    profile_data["MISSION_ARTIFACT_ROOT"] = str(_resolve_artifact_root(artifact_root, repo_root=repo_root))
    return EnvironmentProfile.from_mapping(profile_data)


def _resolve_artifact_root(artifact_root: Path, *, repo_root: Optional[Path]) -> Path:
    expanded = artifact_root.expanduser()
    if expanded.is_absolute():
        return expanded
    root = repo_root or Path.cwd()
    return root / expanded
