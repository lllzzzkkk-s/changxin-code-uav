from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Union

from task_planning.config import EnvironmentProfile
from task_planning.mission_ops.state import MissionOpsState


ARTIFACT_FILENAMES = (
    "environment_profile.json",
    "mission_input.json",
    "model_output.json",
    "task_schema.json",
    "validation_report.json",
    "blackboard_snapshot.json",
    "pddl_problem.pddl",
    "planner_output.json",
    "bt_artifact.json",
    "gateway_trace.json",
    "command_acks.json",
    "task_progress.json",
    "execution_events.json",
    "failure_report.json",
    "replan_decision.json",
    "run_summary.md",
)


@dataclass(frozen=True)
class MissionArtifactBundle:
    run_id: str
    root: Path
    files: Dict[str, Path]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": "MissionArtifactBundle.v1",
            "run_id": self.run_id,
            "root": str(self.root),
            "files": {name: str(path) for name, path in self.files.items()},
        }


def write_artifact_bundle(
    *,
    state: MissionOpsState,
    profile: EnvironmentProfile,
    run_input: Mapping[str, Any],
    gateway_trace: Optional[Iterable[Mapping[str, Any]]] = None,
    base_dir: Optional[Union[str, Path]] = None,
) -> MissionArtifactBundle:
    root = _resolve_root(profile.mission_artifact_root, base_dir=base_dir) / state.run_id
    root.mkdir(parents=True, exist_ok=True)

    outputs = dict(state.output_artifact_refs)
    task_schema = dict(outputs.get("task_schema") or {})
    pddl_problem = dict(outputs.get("pddl_problem") or {})
    plan = dict(outputs.get("plan") or {})
    behavior_tree = dict(outputs.get("behavior_tree") or {})
    gateway_acks = list(outputs.get("gateway_acks") or [])
    task_progress = list(outputs.get("task_progress") or [])
    execution_events = list(outputs.get("execution_events") or [])
    failure_report = dict(outputs.get("failure_report") or {})
    replan_decision = dict(outputs.get("replan_request") or {})

    files: Dict[str, Path] = {}
    _write_json(root / "environment_profile.json", profile.as_dict(), files)
    _write_json(root / "mission_input.json", {"schema": "MissionInput.v1", "run_input": dict(run_input)}, files)
    _write_json(root / "model_output.json", _model_output(profile, task_schema), files)
    _write_json(root / "task_schema.json", task_schema or {"schema": "TaskSchema.v1", "status": "not_generated"}, files)
    _write_json(root / "validation_report.json", _validation_report(state, outputs), files)
    _write_json(root / "blackboard_snapshot.json", outputs.get("blackboard") or {"schema": "MissionBlackboard.v1", "status": "not_generated"}, files)
    _write_text(root / "pddl_problem.pddl", str(pddl_problem.get("pddl", "")), files)
    _write_json(root / "planner_output.json", plan or {"schema": "PddlPlan.v1", "steps": []}, files)
    _write_json(root / "bt_artifact.json", behavior_tree or {"schema": "BehaviorTree.v1", "task_commands": []}, files)
    _write_json(root / "gateway_trace.json", {"schema": "GatewayTrace.v1", "records": list(gateway_trace or [])}, files)
    _write_json(root / "command_acks.json", {"schema": "CommandAckSet.v1", "items": gateway_acks}, files)
    _write_json(root / "task_progress.json", {"schema": "TaskProgressSet.v1", "items": task_progress}, files)
    _write_json(root / "execution_events.json", {"schema": "ExecutionEventLog.v1", "items": execution_events}, files)
    _write_json(root / "failure_report.json", failure_report or {"schema": "FailureReport.v1", "status": "not_reported"}, files)
    _write_json(root / "replan_decision.json", replan_decision or {"schema": "ReplanRequest.v1", "status": "not_requested"}, files)
    _write_text(root / "run_summary.md", _run_summary(state, profile, root), files)
    return MissionArtifactBundle(run_id=state.run_id, root=root, files=files)


def _model_output(profile: EnvironmentProfile, task_schema: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema": "ModelOutput.v1",
        "model_provider": profile.model_provider,
        "model_name": profile.model_name,
        "status": "generated" if task_schema else "not_generated",
        "output": dict(task_schema),
    }


def _validation_report(state: MissionOpsState, outputs: Mapping[str, Any]) -> Dict[str, Any]:
    validation_errors = list(outputs.get("validation_errors") or [])
    if state.error and state.error not in validation_errors:
        validation_errors.append(state.error)
    return {
        "schema": "ValidationReport.v1",
        "status": "failed" if validation_errors else "passed",
        "errors": validation_errors,
        "current_state": state.current_state,
    }


def _run_summary(state: MissionOpsState, profile: EnvironmentProfile, root: Path) -> str:
    return "\n".join([
        f"# Mission Run {state.run_id}",
        "",
        f"- mission_profile: `{profile.mission_profile}`",
        f"- model_provider: `{profile.model_provider}`",
        f"- platform_backend: `{profile.platform_backend}`",
        f"- current_state: `{state.current_state}`",
        f"- approval_required: `{str(state.approval_required).lower()}`",
        f"- approval_state: `{state.approval_state.get('schema', '')}`",
        f"- execution_event_count: `{len(state.output_artifact_refs.get('execution_events') or [])}`",
        f"- error: `{state.error or ''}`",
        f"- artifact_root: `{root}`",
        "",
    ])


def _resolve_root(root: str, *, base_dir: Optional[Union[str, Path]]) -> Path:
    path = Path(root).expanduser()
    if path.is_absolute():
        return path
    if base_dir is not None:
        return Path(base_dir).expanduser() / path
    return Path.cwd() / path


def _write_json(path: Path, data: Mapping[str, Any], files: Dict[str, Path]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    files[path.name] = path


def _write_text(path: Path, text: str, files: Dict[str, Path]) -> None:
    path.write_text(text, encoding="utf-8")
    files[path.name] = path
