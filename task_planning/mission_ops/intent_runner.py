from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.config import EnvironmentProfile, load_profile
from task_planning.contracts import CapabilityRegistry
from task_planning.mission_ops.agent_adapter import AgentTaskSchemaAdapter
from task_planning.mission_ops.model_client import ModelClient
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
    semantic_compiler: Dict[str, Any] = field(default_factory=dict)
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
            "semantic_compiler": dict(self.semantic_compiler),
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
    agent_name: str = "",
    agent_draft: Optional[Mapping[str, Any]] = None,
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
        "semantic_compiler": _semantic_compiler_metadata(
            profile=profile,
            agent_name=agent_name,
            agent_draft=agent_draft,
        ),
    }
    validation_errors = _preflight_errors(
        intent=intent,
        profile=profile,
        agent_name=agent_name,
        agent_draft=agent_draft,
    )
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
        model_client=_model_client_for_request(agent_name=agent_name, agent_draft=agent_draft),
        gateway=MockPlatformGateway(),
    )
    try:
        result = runner.run(run_input, profile.as_env_dict())
    except Exception as exc:
        return MissionIntentRunReport(ok=False, validation_errors=(str(exc),), **base)
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


def _preflight_errors(
    *,
    intent: str,
    profile: EnvironmentProfile,
    agent_name: str,
    agent_draft: Optional[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if not intent.strip():
        errors.append("intent is required")
    if profile.platform_backend.strip().lower() == "ros1_gateway":
        errors.append("PLATFORM_BACKEND=ros1_gateway is not allowed")
    if agent_name and agent_draft is None:
        errors.append("agent_draft is required when agent_name is set")
    if agent_draft is not None and not agent_name:
        errors.append("agent_name is required when agent_draft is set")
    return errors


def _model_client_for_request(*, agent_name: str, agent_draft: Optional[Mapping[str, Any]]) -> Optional[ModelClient]:
    if not agent_name and agent_draft is None:
        return None
    return AgentTaskSchemaAdapter(
        agent_name=agent_name,
        draft_fn=lambda payload: dict(agent_draft or {}),
        registry=CapabilityRegistry.scout_and_confirm_default(),
    )


def _semantic_compiler_metadata(
    *,
    profile: EnvironmentProfile,
    agent_name: str,
    agent_draft: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    if agent_name or agent_draft is not None:
        return {
            "schema": "SemanticCompilerBinding.v1",
            "kind": "agent_adapter",
            "agent_name": agent_name,
            "draft_schema": str((agent_draft or {}).get("schema", "")),
            "allowed_output_schema": "TaskSchema.v1",
        }
    return {
        "schema": "SemanticCompilerBinding.v1",
        "kind": "model_client",
        "model_provider": profile.model_provider,
    }


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
