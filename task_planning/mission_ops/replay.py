from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Union

from task_planning.mission_ops.artifacts import ARTIFACT_FILENAMES

OPTIONAL_JSON_ARTIFACTS = {
    "execution_events.json",
}

JSON_ARTIFACTS = {
    "environment_profile.json",
    "mission_input.json",
    "model_output.json",
    "task_schema.json",
    "validation_report.json",
    "blackboard_snapshot.json",
    "planner_output.json",
    "bt_artifact.json",
    "gateway_trace.json",
    "command_acks.json",
    "task_progress.json",
    "execution_events.json",
    "failure_report.json",
    "replan_decision.json",
}

REQUIRED_JSON_SCHEMAS = {
    "environment_profile.json": "EnvironmentProfile.v1",
    "mission_input.json": "MissionInput.v1",
    "model_output.json": "ModelOutput.v1",
    "task_schema.json": "TaskSchema.v1",
    "validation_report.json": "ValidationReport.v1",
    "blackboard_snapshot.json": "MissionBlackboard.v1",
    "planner_output.json": "PddlPlan.v1",
    "bt_artifact.json": "BehaviorTree.v1",
    "gateway_trace.json": "GatewayTrace.v1",
    "command_acks.json": "CommandAckSet.v1",
    "task_progress.json": "TaskProgressSet.v1",
    "execution_events.json": "ExecutionEventLog.v1",
    "failure_report.json": "FailureReport.v1",
    "replan_decision.json": "ReplanRequest.v1",
}


@dataclass(frozen=True)
class ArtifactBundleRead:
    root: Path
    data: Dict[str, Any]
    validation_errors: List[str]

    @property
    def ok(self) -> bool:
        return not self.validation_errors

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": "ArtifactBundleRead.v1",
            "root": str(self.root),
            "ok": self.ok,
            "validation_errors": list(self.validation_errors),
        }


@dataclass(frozen=True)
class ArtifactDiff:
    path: str
    left: Any
    right: Any
    severity: str = "changed"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactComparison:
    left_root: Path
    right_root: Path
    diffs: List[ArtifactDiff]
    validation_errors: List[str]

    @property
    def equivalent(self) -> bool:
        return not self.validation_errors and not self.diffs

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": "ArtifactComparison.v1",
            "left_root": str(self.left_root),
            "right_root": str(self.right_root),
            "equivalent": self.equivalent,
            "validation_errors": list(self.validation_errors),
            "diffs": [diff.as_dict() for diff in self.diffs],
        }


def load_artifact_bundle(root: Union[str, Path]) -> ArtifactBundleRead:
    bundle_root = Path(root)
    errors: List[str] = []
    data: Dict[str, Any] = {}
    if not bundle_root.exists():
        return ArtifactBundleRead(root=bundle_root, data={}, validation_errors=[f"artifact root does not exist: {bundle_root}"])
    for filename in ARTIFACT_FILENAMES:
        path = bundle_root / filename
        if not path.exists():
            if filename in OPTIONAL_JSON_ARTIFACTS:
                data[filename] = {"schema": REQUIRED_JSON_SCHEMAS[filename], "items": []}
                continue
            errors.append(f"missing artifact: {filename}")
            continue
        if filename in JSON_ARTIFACTS:
            try:
                data[filename] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"invalid JSON artifact {filename}: {exc}")
        else:
            data[filename] = path.read_text(encoding="utf-8")
    errors.extend(_validate_bundle_semantics(data))
    return ArtifactBundleRead(root=bundle_root, data=data, validation_errors=errors)


def compare_artifact_bundles(left_root: Union[str, Path], right_root: Union[str, Path]) -> ArtifactComparison:
    left = load_artifact_bundle(left_root)
    right = load_artifact_bundle(right_root)
    validation_errors = [f"left: {error}" for error in left.validation_errors]
    validation_errors.extend(f"right: {error}" for error in right.validation_errors)
    diffs: List[ArtifactDiff] = []
    if validation_errors:
        return ArtifactComparison(left_root=left.root, right_root=right.root, diffs=diffs, validation_errors=validation_errors)

    comparisons = {
        "mission_input.case_id": _path_value(left.data, ["mission_input.json", "run_input", "case_id"]),
        "task_schema.mission_request": _path_value(left.data, ["task_schema.json", "mission_request"]),
        "planner_output.steps": _canonical_plan_steps(_path_value(left.data, ["planner_output.json", "steps"], [])),
        "bt_artifact.commands": _canonical_commands(_path_value(left.data, ["bt_artifact.json", "task_commands"], [])),
        "gateway_trace.records": _canonical_gateway_records(_path_value(left.data, ["gateway_trace.json", "records"], [])),
        "execution_events.event_types": _canonical_event_types(_path_value(left.data, ["execution_events.json", "items"], [])),
        "validation_report.status": _path_value(left.data, ["validation_report.json", "status"]),
        "replan_decision": _path_value(left.data, ["replan_decision.json"]),
    }
    right_values = {
        "mission_input.case_id": _path_value(right.data, ["mission_input.json", "run_input", "case_id"]),
        "task_schema.mission_request": _path_value(right.data, ["task_schema.json", "mission_request"]),
        "planner_output.steps": _canonical_plan_steps(_path_value(right.data, ["planner_output.json", "steps"], [])),
        "bt_artifact.commands": _canonical_commands(_path_value(right.data, ["bt_artifact.json", "task_commands"], [])),
        "gateway_trace.records": _canonical_gateway_records(_path_value(right.data, ["gateway_trace.json", "records"], [])),
        "execution_events.event_types": _canonical_event_types(_path_value(right.data, ["execution_events.json", "items"], [])),
        "validation_report.status": _path_value(right.data, ["validation_report.json", "status"]),
        "replan_decision": _path_value(right.data, ["replan_decision.json"]),
    }
    for path, left_value in comparisons.items():
        right_value = right_values[path]
        if left_value != right_value:
            diffs.append(ArtifactDiff(path=path, left=left_value, right=right_value))
    return ArtifactComparison(left_root=left.root, right_root=right.root, diffs=diffs, validation_errors=[])


def _validate_bundle_semantics(data: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    documents: Dict[str, Mapping[str, Any]] = {}
    for filename, schema in REQUIRED_JSON_SCHEMAS.items():
        value = data.get(filename) or {}
        if not isinstance(value, Mapping):
            errors.append(f"{filename} must contain an object")
            value = {}
        documents[filename] = value
        if value.get("schema") != schema:
            errors.append(f"{filename} must be {schema}")

    validation = documents["validation_report.json"]
    gateway_trace = documents["gateway_trace.json"]
    bt = documents["bt_artifact.json"]
    if validation.get("status") not in {"passed", "failed"}:
        errors.append("validation_report.json status must be passed or failed")
    for index, record in enumerate(gateway_trace.get("records") or []):
        if record.get("publish_attempted") is not False:
            errors.append(f"gateway_trace record {index} must have publish_attempted=false")
    return errors


def _path_value(data: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _canonical_plan_steps(steps: Any) -> List[Dict[str, Any]]:
    if not isinstance(steps, list):
        return []
    return [
        {
            "index": step.get("index"),
            "action": step.get("action"),
            "arguments": list(step.get("arguments") or []),
        }
        for step in steps
        if isinstance(step, Mapping)
    ]


def _canonical_commands(commands: Any) -> List[Dict[str, Any]]:
    if not isinstance(commands, list):
        return []
    return [
        {
            "task_id": command.get("task_id"),
            "platform_id": command.get("platform_id"),
            "capability": command.get("capability"),
            "parameters": dict(command.get("parameters") or {}),
            "disconnect_policy": command.get("disconnect_policy"),
        }
        for command in commands
        if isinstance(command, Mapping)
    ]


def _canonical_gateway_records(records: Any) -> List[Dict[str, Any]]:
    if not isinstance(records, list):
        return []
    return [
        {
            "task_id": record.get("task_id"),
            "platform_id": record.get("platform_id"),
            "capability": record.get("capability"),
            "accepted": record.get("accepted"),
            "reason": record.get("reason"),
            "publish_attempted": record.get("publish_attempted"),
        }
        for record in records
        if isinstance(record, Mapping)
    ]


def _canonical_event_types(events: Any) -> List[str]:
    if not isinstance(events, list):
        return []
    return [
        str(event.get("event_type"))
        for event in events
        if isinstance(event, Mapping)
    ]
