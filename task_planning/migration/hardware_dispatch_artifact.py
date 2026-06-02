from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from task_planning.config import ProfileValidationError, load_profile
from task_planning.contracts import CommandAck, TaskCommand
from task_planning.migration.hardware_evidence import inspect_hardware_execution_artifact
from task_planning.migration.machine_identity import current_machine_id
from task_planning.mission_ops.artifacts import ARTIFACT_FILENAMES
from task_planning.mission_ops.replay import load_artifact_bundle


HARDWARE_DISPATCH_ARTIFACT_SCHEMA = "UnitHardwareDispatchArtifactRecord.v1"
UNIT_HARDWARE_EXECUTION_CONTEXT = "unit_workplace_hardware"


@dataclass(frozen=True)
class UnitHardwareDispatchArtifactRecord:
    artifact_root: Path
    source_artifact: Path
    validation_errors: List[str]
    schema: str = HARDWARE_DISPATCH_ARTIFACT_SCHEMA

    @property
    def ok(self) -> bool:
        return not self.validation_errors

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["artifact_root"] = str(self.artifact_root)
        data["source_artifact"] = str(self.source_artifact)
        return data


def record_unit_hardware_dispatch_artifact(
    *,
    source_artifact: Path,
    profile_path: Path,
    output_dir: Path,
    platform_id: str,
    task_id: Optional[str] = None,
    dispatch_service: Optional[str] = None,
    dispatch_returncode: int = 0,
    dispatch_stdout: str = "",
    dispatch_stderr: str = "",
    command_ack: Optional[Mapping[str, Any]] = None,
    task_progress: Sequence[Mapping[str, Any]] = (),
    operator_approved: bool = False,
    execution_context: str = UNIT_HARDWARE_EXECUTION_CONTEXT,
    run_id: Optional[str] = None,
    overwrite: bool = False,
) -> UnitHardwareDispatchArtifactRecord:
    source_artifact = source_artifact.expanduser().resolve()
    profile_path = profile_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    errors: List[str] = []

    source_bundle = load_artifact_bundle(source_artifact)
    errors.extend(f"source_artifact:{error}" for error in source_bundle.validation_errors)
    errors.extend(_source_validation_errors(source_bundle.data))
    profile = None
    try:
        profile = load_profile(profile_path)
    except (OSError, ProfileValidationError) as exc:
        errors.append(f"profile cannot be loaded: {exc}")

    if profile is not None:
        if profile.mission_profile != "work_hardware":
            errors.append("hardware dispatch artifact profile must use MISSION_PROFILE=work_hardware")
        if profile.platform_backend != "ros1_gateway":
            errors.append("hardware dispatch artifact profile must use PLATFORM_BACKEND=ros1_gateway")
        if profile.hardware_approval_required is not True:
            errors.append("hardware dispatch artifact profile must preserve HARDWARE_APPROVAL_REQUIRED=true")

    if execution_context != UNIT_HARDWARE_EXECUTION_CONTEXT:
        errors.append(f"execution_context must be {UNIT_HARDWARE_EXECUTION_CONTEXT}")
    if not operator_approved:
        errors.append("operator_approved=true is required before recording real dispatch proof")

    command = _select_task_command(source_bundle.data, platform_id=platform_id, task_id=task_id, errors=errors)
    service = dispatch_service or _default_dispatch_service(profile, platform_id)
    if service:
        if not service.strip().endswith("/gateway/dispatch"):
            errors.append("dispatch_service must be a /gateway/dispatch service, not dry_run")
        if platform_id not in service:
            errors.append("dispatch_service should include the selected platform_id")
    else:
        errors.append("dispatch_service is required")

    ack = _resolve_ack(
        command=command,
        explicit_ack=command_ack,
        dispatch_stdout=dispatch_stdout,
        dispatch_stderr=dispatch_stderr,
        dispatch_returncode=dispatch_returncode,
        errors=errors,
    )
    progress_items = _normalize_progress(task_progress, command=command, errors=errors)
    _validate_dispatch_alignment(
        command=command,
        ack=ack,
        progress_items=progress_items,
        dispatch_returncode=dispatch_returncode,
        errors=errors,
    )

    artifact_root = output_dir / (run_id or f"{source_artifact.name}-hardware-dispatch")
    if errors:
        return UnitHardwareDispatchArtifactRecord(
            artifact_root=artifact_root,
            source_artifact=source_artifact,
            validation_errors=errors,
        )
    if artifact_root.exists():
        if not overwrite:
            return UnitHardwareDispatchArtifactRecord(
                artifact_root=artifact_root,
                source_artifact=source_artifact,
                validation_errors=[f"artifact_root already exists: {artifact_root}"],
            )
        shutil.rmtree(artifact_root)
    artifact_root.mkdir(parents=True)

    _copy_source_artifact_files(source_artifact, artifact_root)
    assert profile is not None
    assert command is not None
    assert ack is not None
    _write_json(
        artifact_root / "environment_profile.json",
        _hardware_profile(profile, source_artifact, execution_context, operator_approved),
    )
    _write_json(artifact_root / "validation_report.json", _hardware_validation_report(source_bundle.data))
    _write_json(artifact_root / "gateway_trace.json", {
        "schema": "GatewayTrace.v1",
        "records": [_dispatch_record(
            command=command,
            ack=ack,
            service=service,
            returncode=dispatch_returncode,
            stdout=dispatch_stdout,
            stderr=dispatch_stderr,
            execution_context=execution_context,
        )],
    })
    _write_json(artifact_root / "command_acks.json", {
        "schema": "CommandAckSet.v1",
        "items": [ack],
    })
    _write_json(artifact_root / "task_progress.json", {
        "schema": "TaskProgressSet.v1",
        "items": list(progress_items),
    })
    _write_text(artifact_root / "run_summary.md", _run_summary(
        source_artifact=source_artifact,
        profile_path=profile_path,
        service=service,
        command=command,
        dispatch_returncode=dispatch_returncode,
        execution_context=execution_context,
        operator_approved=operator_approved,
    ))

    inspection = inspect_hardware_execution_artifact(artifact_root)
    validation_errors = list(inspection.get("validation_errors") or [])
    return UnitHardwareDispatchArtifactRecord(
        artifact_root=artifact_root,
        source_artifact=source_artifact,
        validation_errors=validation_errors,
    )


def parse_command_ack_file(path: Path) -> Dict[str, Any]:
    data = _load_json_object(path)
    return _extract_ack_dict(data) or data


def parse_task_progress_file(path: Path) -> List[Dict[str, Any]]:
    data = _load_json_object(path)
    if data.get("schema") == "TaskProgressSet.v1":
        items = data.get("items")
        if not isinstance(items, list):
            raise ValueError("TaskProgressSet.v1 requires an items list")
        progress_items: List[Dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise ValueError(f"TaskProgressSet.v1 items[{index}] must be an object")
            progress_items.append(dict(item))
        return progress_items
    return [data]


def _select_task_command(
    data: Mapping[str, Any],
    *,
    platform_id: str,
    task_id: Optional[str],
    errors: List[str],
) -> Optional[Dict[str, Any]]:
    bt = data.get("bt_artifact.json") or {}
    raw_commands = bt.get("task_commands") if isinstance(bt, Mapping) else []
    if not isinstance(raw_commands, list):
        errors.append("source bt_artifact.json task_commands must be a list")
        return None
    matches = [
        command for command in raw_commands
        if isinstance(command, Mapping)
        and command.get("platform_id") == platform_id
        and (task_id is None or command.get("task_id") == task_id)
    ]
    if not matches:
        selector = f"platform_id={platform_id}" if task_id is None else f"platform_id={platform_id}, task_id={task_id}"
        errors.append(f"no TaskCommand found in source artifact for {selector}")
        return None
    if task_id is None and len(matches) > 1:
        errors.append("multiple TaskCommand entries match platform_id; provide --task-id")
        return None
    command = TaskCommand.from_dict(matches[0]).as_dict()
    return command


def _default_dispatch_service(profile, platform_id: str) -> str:
    if profile is None:
        return ""
    return profile.ros_gateway_dispatch_service_template.format(platform_id=platform_id)


def _resolve_ack(
    *,
    command: Optional[Mapping[str, Any]],
    explicit_ack: Optional[Mapping[str, Any]],
    dispatch_stdout: str,
    dispatch_stderr: str,
    dispatch_returncode: int,
    errors: List[str],
) -> Optional[Dict[str, Any]]:
    if command is None:
        return None
    if explicit_ack is not None:
        ack = dict(explicit_ack)
    else:
        ack = _extract_ack_from_text(dispatch_stdout)
    if not ack:
        errors.append("CommandAck evidence is required; provide --command-ack-file or a parsable dispatch stdout")
        return None
    if "schema" in ack and ack.get("schema") != "CommandAck.v1":
        errors.append("CommandAck schema must be CommandAck.v1")
    accepted = _required_bool_field(ack, "accepted", errors)
    local_check = ack.get("local_check") or {}
    if not isinstance(local_check, Mapping):
        errors.append("CommandAck local_check must be an object")
        local_check = {}
    normalized = CommandAck(
        mission_id=str(ack.get("mission_id", command.get("mission_id", ""))),
        task_id=str(ack.get("task_id", command.get("task_id", ""))),
        platform_id=str(ack.get("platform_id", command.get("platform_id", ""))),
        accepted=accepted is True,
        reason=str(ack.get("reason", "" if dispatch_returncode == 0 else dispatch_stderr)),
        local_check=dict(local_check),
        schema=str(ack.get("schema", "CommandAck.v1")),
    ).as_dict()
    return normalized


def _required_bool_field(data: Mapping[str, Any], field: str, errors: List[str]) -> Optional[bool]:
    value = data.get(field)
    if isinstance(value, bool):
        return value
    errors.append(f"CommandAck {field} must be a JSON boolean")
    return None


def _extract_ack_from_text(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    for candidate in _json_candidates(stripped):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, Mapping):
            extracted = _extract_ack_dict(data)
            if extracted:
                return extracted
    return {}


def _json_candidates(text: str) -> List[str]:
    candidates = [text]
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("response_json:"):
            value = stripped.split(":", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                try:
                    loaded = json.loads(value)
                except json.JSONDecodeError:
                    value = value[1:-1]
                else:
                    value = loaded if isinstance(loaded, str) else json.dumps(loaded, ensure_ascii=False)
            candidates.append(value)
    return candidates


def _extract_ack_dict(data: Mapping[str, Any]) -> Dict[str, Any]:
    if data.get("schema") == "CommandAck.v1":
        return dict(data)
    ack = data.get("ack")
    if isinstance(ack, Mapping):
        return dict(ack)
    response_json = data.get("response_json")
    if isinstance(response_json, str):
        try:
            nested = json.loads(response_json)
        except json.JSONDecodeError:
            return {}
        if isinstance(nested, Mapping):
            return _extract_ack_dict(nested)
    if "accepted" in data:
        return dict(data)
    return {}


def _normalize_progress(
    task_progress: Sequence[Mapping[str, Any]],
    *,
    command: Optional[Mapping[str, Any]],
    errors: List[str],
) -> List[Dict[str, Any]]:
    if command is None:
        return []
    if not task_progress:
        errors.append("at least one TaskProgress item is required for hardware execution proof")
        return []
    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(task_progress):
        if not isinstance(item, Mapping):
            errors.append(f"task_progress[{index}] must be an object")
            continue
        progress = dict(item)
        if progress.get("schema") != "TaskProgress.v1":
            errors.append(f"task_progress[{index}] must use schema TaskProgress.v1")
        if not progress.get("status"):
            errors.append(f"task_progress[{index}] must include status")
        normalized.append(progress)
    return normalized


def _validate_dispatch_alignment(
    *,
    command: Optional[Mapping[str, Any]],
    ack: Optional[Mapping[str, Any]],
    progress_items: Sequence[Mapping[str, Any]],
    dispatch_returncode: int,
    errors: List[str],
) -> None:
    if command is None or ack is None:
        return
    expected = (command.get("mission_id"), command.get("task_id"), command.get("platform_id"))
    observed_ack = (ack.get("mission_id"), ack.get("task_id"), ack.get("platform_id"))
    if observed_ack != expected:
        errors.append("CommandAck mission_id/task_id/platform_id must match selected TaskCommand")
    if ack.get("accepted") is not True:
        errors.append("CommandAck must be accepted=true for final hardware execution proof")
    if dispatch_returncode != 0:
        errors.append("dispatch_returncode must be 0 for final hardware execution proof")
    matching_progress = [
        item for item in progress_items
        if (
            item.get("mission_id"),
            item.get("task_id"),
            item.get("platform_id"),
        ) == expected
    ]
    if not matching_progress:
        errors.append("at least one TaskProgress item must match selected TaskCommand")


def _copy_source_artifact_files(source: Path, target: Path) -> None:
    for filename in ARTIFACT_FILENAMES:
        source_file = source / filename
        if not source_file.exists():
            continue
        shutil.copy2(source_file, target / filename)


def _source_validation_errors(data: Mapping[str, Any]) -> List[str]:
    profile = data.get("environment_profile.json")
    validation = data.get("validation_report.json")
    if not isinstance(profile, Mapping):
        profile = {}
    if not isinstance(validation, Mapping):
        return ["source_artifact validation_report.json is required before hardware dispatch recording"]
    errors: List[str] = []
    if profile.get("mission_profile") != "work_hardware":
        errors.append("source_artifact must use mission_profile=work_hardware before hardware dispatch recording")
    if profile.get("platform_backend") not in {"mock", "sim"}:
        errors.append("source_artifact must be a mock/sim pre-dispatch artifact before hardware dispatch recording")
    if profile.get("hardware_approval_required") is not True:
        errors.append("source_artifact must preserve hardware_approval_required=true before hardware dispatch recording")
    if validation.get("status") != "passed":
        errors.append("source_artifact validation_report.status must be passed before hardware dispatch recording")
    if validation.get("current_state") != "OPERATOR_APPROVAL":
        errors.append("source_artifact validation_report.current_state must be OPERATOR_APPROVAL before hardware dispatch recording")
    validation_errors = validation.get("errors")
    if not isinstance(validation_errors, list):
        errors.append("source_artifact validation_report.errors must be a list")
    elif validation_errors:
        errors.append("source_artifact validation_report.errors must be empty before hardware dispatch recording")
    return errors


def _hardware_profile(
    profile,
    source_artifact: Path,
    execution_context: str,
    operator_approved: bool,
) -> Dict[str, Any]:
    data = profile.as_dict()
    data["execution_context"] = execution_context
    data["operator_approved"] = operator_approved
    data["operator_approval_source"] = "local_unit_operator"
    data["machine_id"] = current_machine_id()
    data["source_artifact_root"] = str(source_artifact)
    return data


def _hardware_validation_report(data: Mapping[str, Any]) -> Dict[str, Any]:
    source_validation = data.get("validation_report.json") or {}
    return {
        "schema": "ValidationReport.v1",
        "status": "passed",
        "errors": [],
        "current_state": "HARDWARE_DISPATCH_RECORDED",
        "source_validation_report": source_validation,
    }


def _dispatch_record(
    *,
    command: Mapping[str, Any],
    ack: Mapping[str, Any],
    service: str,
    returncode: int,
    stdout: str,
    stderr: str,
    execution_context: str,
) -> Dict[str, Any]:
    return {
        "mission_id": command.get("mission_id"),
        "task_id": command.get("task_id"),
        "platform_id": command.get("platform_id"),
        "capability": command.get("capability"),
        "accepted": ack.get("accepted") is True,
        "reason": ack.get("reason", ""),
        "service": service,
        "rosservice_called": True,
        "returncode": returncode,
        "publish_attempted": False,
        "execution_context": execution_context,
        "stdout_excerpt": stdout[:500],
        "stderr_excerpt": stderr[:500],
    }


def _run_summary(
    *,
    source_artifact: Path,
    profile_path: Path,
    service: str,
    command: Mapping[str, Any],
    dispatch_returncode: int,
    execution_context: str,
    operator_approved: bool,
) -> str:
    return "\n".join([
        "# Unit Hardware Dispatch Artifact",
        "",
        f"- execution_context: `{execution_context}`",
        f"- source_artifact: `{source_artifact}`",
        f"- profile_path: `{profile_path}`",
        f"- service: `{service}`",
        f"- dispatch_returncode: `{dispatch_returncode}`",
        f"- mission_id: `{command.get('mission_id')}`",
        f"- task_id: `{command.get('task_id')}`",
        f"- platform_id: `{command.get('platform_id')}`",
        f"- capability: `{command.get('capability')}`",
        "",
        "This artifact records evidence captured after local operator approval at the unit/workplace execution endpoint.",
        f"- operator_approved: `{str(operator_approved).lower()}`",
        "",
    ])


def _load_json_object(path: Path) -> Dict[str, Any]:
    data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
