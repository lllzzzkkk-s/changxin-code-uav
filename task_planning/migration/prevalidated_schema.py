from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.config import EnvironmentProfile, load_profile
from task_planning.contracts import CapabilityRegistry, TaskSchema
from task_planning.mission_ops.artifacts import write_artifact_bundle
from task_planning.mission_ops.state import MissionOpsState
from task_planning.mission_ops.tools import (
    compile_plan_to_bt_tool,
    dry_run_gateway_tool,
    generate_pddl_problem_tool,
    run_pddl_planner_tool,
    update_blackboard_tool,
    validate_pddl_problem_tool,
    validate_plan_tool,
    validate_task_schema_tool,
)


@dataclass(frozen=True)
class PrevalidatedSchemaRun:
    run_id: str
    status: str
    current_state: str
    artifact_bundle_path: Path
    validation_errors: List[str]
    case_id: str = ""
    schema: str = "PrevalidatedSchemaRun.v1"

    @property
    def ok(self) -> bool:
        return not self.validation_errors

    def as_dict(self) -> Dict[str, object]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "run_id": self.run_id,
            "status": self.status,
            "current_state": self.current_state,
            "artifact_bundle_path": str(self.artifact_bundle_path),
            "validation_errors": list(self.validation_errors),
            "case_id": self.case_id,
        }


def run_prevalidated_task_schema(
    *,
    profile_path: Path,
    task_schema_path: Path,
    artifact_root: Optional[Path] = None,
    case_id: Optional[str] = None,
) -> PrevalidatedSchemaRun:
    profile = load_profile(profile_path)
    if artifact_root is not None:
        data = profile.as_env_dict()
        data["MISSION_ARTIFACT_ROOT"] = str(artifact_root)
        profile = EnvironmentProfile.from_mapping(data)
    task_schema = TaskSchema.from_dict(json.loads(task_schema_path.read_text(encoding="utf-8")))
    resolved_case_id = _resolve_case_id(task_schema_path=task_schema_path, task_schema=task_schema, case_id=case_id)
    registry = CapabilityRegistry.scout_and_confirm_default()
    validation_errors = _profile_errors(profile)
    validation_errors.extend(_case_id_errors(resolved_case_id))

    outputs: Dict[str, Any] = {
        "task_schema": task_schema.as_dict(),
        "task_schema_source": {
            "schema": "TaskSchemaSource.v1",
            "path": str(task_schema_path),
            "mode": "prevalidated_schema",
            "case_id": resolved_case_id,
        },
    }
    state = MissionOpsState(
        run_id=str(uuid.uuid4()),
        mission_id=task_schema.mission_request.mission_id,
        current_state="VALIDATE_TASK_SCHEMA",
        input_artifact_refs={
            "task_schema_path": str(task_schema_path),
            "profile_path": str(profile_path),
        },
        output_artifact_refs=dict(outputs),
    )

    validation_errors.extend(validate_task_schema_tool(task_schema, registry))
    if validation_errors:
        outputs["validation_errors"] = validation_errors
        state = state.transition("NEEDS_CLARIFICATION", output_artifact_refs=outputs, approval_required=True, error=validation_errors[0])
        bundle = write_artifact_bundle(state=state, profile=profile, run_input=_run_input(task_schema, task_schema_path, resolved_case_id), gateway_trace=[])
        return PrevalidatedSchemaRun(
            run_id=state.run_id,
            status="failed",
            current_state=state.current_state,
            artifact_bundle_path=bundle.root,
            validation_errors=validation_errors,
            case_id=resolved_case_id,
        )

    blackboard = update_blackboard_tool(task_schema, registry)
    outputs["blackboard"] = blackboard.as_dict()
    problem = generate_pddl_problem_tool(task_schema)
    outputs["pddl_problem"] = problem.as_dict()
    problem_errors = validate_pddl_problem_tool(problem)
    if problem_errors:
        return _failed_result(state, profile, task_schema, task_schema_path, outputs, problem_errors, resolved_case_id)

    plan = run_pddl_planner_tool(problem)
    outputs["plan"] = plan.as_dict()
    plan_errors = validate_plan_tool(plan, registry)
    if plan_errors:
        return _failed_result(state, profile, task_schema, task_schema_path, outputs, plan_errors, resolved_case_id)

    behavior_tree = compile_plan_to_bt_tool(plan, task_schema.mission_request.mission_id)
    outputs["behavior_tree"] = behavior_tree.as_dict()

    if profile.mission_profile == "work_hardware" and profile.hardware_approval_required:
        state = state.transition("OPERATOR_APPROVAL", output_artifact_refs=outputs, approval_required=True)
        bundle = write_artifact_bundle(state=state, profile=profile, run_input=_run_input(task_schema, task_schema_path, resolved_case_id), gateway_trace=[])
        return PrevalidatedSchemaRun(
            run_id=state.run_id,
            status="approval_required",
            current_state=state.current_state,
            artifact_bundle_path=bundle.root,
            validation_errors=[],
            case_id=resolved_case_id,
        )

    gateway = MockPlatformGateway(registry)
    acks = dry_run_gateway_tool(gateway, behavior_tree)
    outputs["gateway_acks"] = [ack.as_dict() for ack in acks]
    rejected = [ack for ack in acks if not ack.accepted]
    if rejected:
        state = state.transition(
            "DISPATCH_OR_HOLD",
            output_artifact_refs=outputs,
            error=rejected[0].reason,
        )
        bundle = write_artifact_bundle(state=state, profile=profile, run_input=_run_input(task_schema, task_schema_path, resolved_case_id), gateway_trace=gateway.dispatch_log)
        return PrevalidatedSchemaRun(
            run_id=state.run_id,
            status="failed",
            current_state=state.current_state,
            artifact_bundle_path=bundle.root,
            validation_errors=[rejected[0].reason],
            case_id=resolved_case_id,
        )

    state = state.transition("DISPATCH_OR_HOLD", output_artifact_refs=outputs)
    bundle = write_artifact_bundle(state=state, profile=profile, run_input=_run_input(task_schema, task_schema_path, resolved_case_id), gateway_trace=gateway.dispatch_log)
    return PrevalidatedSchemaRun(
        run_id=state.run_id,
        status="dry_run_complete",
        current_state=state.current_state,
        artifact_bundle_path=bundle.root,
        validation_errors=[],
        case_id=resolved_case_id,
    )


def _profile_errors(profile: EnvironmentProfile) -> List[str]:
    errors: List[str] = []
    if profile.platform_backend == "ros1_gateway":
        errors.append("prevalidated schema replay must use PLATFORM_BACKEND=mock|sim before real ROS1 gateway dispatch")
    if profile.model_provider not in {"mock", "local_http", "remote_http"}:
        errors.append("unsupported model provider for prevalidated schema replay")
    return errors


def _failed_result(
    state: MissionOpsState,
    profile: EnvironmentProfile,
    task_schema: TaskSchema,
    task_schema_path: Path,
    outputs: Dict[str, Any],
    errors: List[str],
    case_id: str,
) -> PrevalidatedSchemaRun:
    outputs["validation_errors"] = errors
    state = state.transition("NEEDS_CLARIFICATION", output_artifact_refs=outputs, approval_required=True, error=errors[0])
    bundle = write_artifact_bundle(state=state, profile=profile, run_input=_run_input(task_schema, task_schema_path, case_id), gateway_trace=[])
    return PrevalidatedSchemaRun(
        run_id=state.run_id,
        status="failed",
        current_state=state.current_state,
        artifact_bundle_path=bundle.root,
        validation_errors=errors,
        case_id=case_id,
    )


def _run_input(task_schema: TaskSchema, task_schema_path: Path, case_id: str) -> Dict[str, Any]:
    return {
        "schema": "PrevalidatedTaskSchemaInput.v1",
        "case_id": case_id,
        "intent": task_schema.intent,
        "context_snapshot": dict(task_schema.context_snapshot),
        "task_schema_path": str(task_schema_path),
    }


def _resolve_case_id(*, task_schema_path: Path, task_schema: TaskSchema, case_id: Optional[str]) -> str:
    explicit = str(case_id or "").strip()
    if explicit:
        return explicit

    sibling_case_id = _case_id_from_sibling_model_lab_input(task_schema_path)
    if sibling_case_id:
        return sibling_case_id

    context_case_id = str(task_schema.context_snapshot.get("case_id") or "").strip()
    if context_case_id:
        return context_case_id
    return ""


def _case_id_from_sibling_model_lab_input(task_schema_path: Path) -> str:
    mission_input_path = task_schema_path.expanduser().resolve().parent / "mission_input.json"
    if not mission_input_path.exists() or not mission_input_path.is_file():
        return ""
    try:
        data = json.loads(mission_input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, Mapping):
        return ""
    if data.get("schema") == "ModelLabMissionInput.v1":
        return str(data.get("case_id") or "").strip()
    run_input = data.get("run_input")
    if isinstance(run_input, Mapping):
        return str(run_input.get("case_id") or "").strip()
    return ""


def _case_id_errors(case_id: str) -> List[str]:
    if case_id:
        return []
    return [
        "prevalidated schema replay requires case_id; pass --case or use a model_lab artifact directory with mission_input.json"
    ]
