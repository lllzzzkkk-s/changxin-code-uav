from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping

from task_planning.migration.machine_identity import hashed_machine_id_errors
from task_planning.mission_ops.replay import load_artifact_bundle


UNIT_HARDWARE_EXECUTION_CONTEXT = "unit_workplace_hardware"


def inspect_hardware_execution_artifact(path: Path) -> Dict[str, Any]:
    bundle = load_artifact_bundle(path)
    if not bundle.ok:
        return {
            "schema": "HardwareExecutionArtifactEvidence.v1",
            "ok": False,
            "path": str(path),
            "validation_errors": list(bundle.validation_errors),
        }
    errors = hardware_execution_artifact_errors(bundle.data)
    return {
        "schema": "HardwareExecutionArtifactEvidence.v1",
        "ok": not errors,
        "path": str(path),
        "validation_errors": errors,
        "profile": bundle.data.get("environment_profile.json") or {},
        "validation_report": bundle.data.get("validation_report.json") or {},
        "evidence": _hardware_execution_summary(bundle.data),
    }


def hardware_execution_artifact_errors(bundle_data: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    profile = _object(bundle_data, "environment_profile.json", errors)
    mission_input = _object(bundle_data, "mission_input.json", errors)
    validation = _object(bundle_data, "validation_report.json", errors)
    command_acks = _object(bundle_data, "command_acks.json", errors)
    gateway_trace = _object(bundle_data, "gateway_trace.json", errors)
    task_progress = _object(bundle_data, "task_progress.json", errors)

    if profile.get("mission_profile") != "work_hardware":
        errors.append("hardware artifact must use mission_profile=work_hardware")
    if profile.get("platform_backend") != "ros1_gateway":
        errors.append("hardware artifact must use platform_backend=ros1_gateway")
    if profile.get("hardware_approval_required") is not True:
        errors.append("hardware artifact must preserve hardware_approval_required=true")
    if profile.get("operator_approved") is not True:
        errors.append("hardware artifact must record operator_approved=true")
    if profile.get("operator_approval_source") != "local_unit_operator":
        errors.append("hardware artifact must record operator_approval_source=local_unit_operator")
    for error in hashed_machine_id_errors(profile.get("machine_id"), "machine_id"):
        errors.append(f"hardware artifact must record execution endpoint {error}")
    if profile.get("execution_context") != UNIT_HARDWARE_EXECUTION_CONTEXT:
        errors.append(f"hardware artifact must use execution_context={UNIT_HARDWARE_EXECUTION_CONTEXT}")
    if validation.get("schema") != "ValidationReport.v1":
        errors.append("hardware artifact validation_report must use schema ValidationReport.v1")
    if validation.get("status") != "passed":
        errors.append("hardware artifact validation_report must be passed")
    validation_errors = validation.get("errors")
    if not isinstance(validation_errors, list):
        errors.append("hardware artifact validation_report.errors must be a list")
    elif validation_errors:
        errors.append("hardware artifact validation_report.errors must be empty")
    if validation.get("current_state") != "HARDWARE_DISPATCH_RECORDED":
        errors.append("hardware artifact validation_report.current_state must be HARDWARE_DISPATCH_RECORDED")
    errors.extend(_source_validation_report_errors(validation.get("source_validation_report")))
    if not _case_id_from_mission_input(mission_input):
        errors.append("hardware artifact mission_input case_id is required")

    ack_items = _command_ack_items(command_acks, errors)
    accepted_acks = [
        item for item in ack_items
        if item.get("schema") == "CommandAck.v1" and item.get("accepted") is True
    ]
    if not accepted_acks:
        errors.append("hardware artifact must include at least one accepted CommandAck")

    progress_items = _task_progress_items(task_progress, errors)

    trace_records = _gateway_trace_records(gateway_trace, errors)
    dispatch_records = _successful_dispatch_records(trace_records, errors)
    if not dispatch_records:
        errors.append("hardware artifact must include a successful ROS1 /gateway/dispatch service call")
    if any(record.get("publish_attempted") is not False for record in trace_records):
        errors.append("hardware artifact gateway trace must not attempt raw ROS publishes")

    accepted_keys = set()
    for item in accepted_acks:
        if not isinstance(item, Mapping):
            continue
        key = _mission_task_platform_key(item)
        if key is None:
            errors.append("accepted CommandAck must include mission_id/task_id/platform_id")
        else:
            accepted_keys.add(key)

    dispatch_keys = set()
    for record in dispatch_records:
        if not isinstance(record, Mapping):
            continue
        key = _mission_task_platform_key(record)
        if key is None:
            errors.append("ROS1 dispatch trace record must include mission_id/task_id/platform_id")
        else:
            dispatch_keys.add(key)
    if accepted_keys and dispatch_keys:
        unmatched_accepted = accepted_keys - dispatch_keys
        if unmatched_accepted:
            errors.append(
                "all accepted CommandAck entries must correspond to a ROS1 dispatch trace record "
                "by mission_id/task_id/platform_id"
            )
    if accepted_keys and dispatch_keys and accepted_keys.isdisjoint(dispatch_keys):
        errors.append("accepted CommandAck must correspond to a ROS1 dispatch trace record by mission_id/task_id/platform_id")

    progress_keys = set()
    for item in progress_items:
        if item.get("schema") != "TaskProgress.v1":
            continue
        key = _mission_task_platform_key(item)
        if key is None:
            errors.append("TaskProgress must include mission_id/task_id/platform_id")
        else:
            progress_keys.add(key)
    if progress_keys and dispatch_keys:
        unmatched_progress = progress_keys - dispatch_keys
        if unmatched_progress:
            errors.append(
                "all TaskProgress entries must correspond to a ROS1 dispatch trace record "
                "by mission_id/task_id/platform_id"
            )
    if progress_keys and dispatch_keys and progress_keys.isdisjoint(dispatch_keys):
        errors.append("TaskProgress must correspond to a ROS1 dispatch trace record by mission_id/task_id/platform_id")
    if accepted_keys and dispatch_keys and progress_keys and not (accepted_keys & dispatch_keys & progress_keys):
        errors.append(
            "accepted CommandAck, ROS1 dispatch trace record, and TaskProgress must share "
            "the same mission_id/task_id/platform_id"
        )
    return errors


def _object(bundle_data: Mapping[str, Any], name: str, errors: List[str]) -> Dict[str, Any]:
    value = bundle_data.get(name) or {}
    if not isinstance(value, Mapping):
        errors.append(f"{name} must contain an object")
        return {}
    return dict(value)


def _command_ack_items(command_acks: Mapping[str, Any], errors: List[str]) -> List[Dict[str, Any]]:
    if command_acks.get("schema") != "CommandAckSet.v1":
        errors.append("command_acks.json must use schema CommandAckSet.v1")
    raw_items = command_acks.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        errors.append("hardware artifact must include command acknowledgements")
        return []
    items: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, Mapping):
            errors.append(f"command_acks.items[{index}] must be an object")
            continue
        ack = dict(item)
        items.append(ack)
        if ack.get("schema") != "CommandAck.v1":
            errors.append(f"command_acks.items[{index}] must use schema CommandAck.v1")
        for field in ("mission_id", "task_id", "platform_id"):
            if not str(ack.get(field) or "").strip():
                errors.append(f"command_acks.items[{index}] {field} is required")
        if not isinstance(ack.get("accepted"), bool):
            errors.append(f"command_acks.items[{index}] accepted must be a JSON boolean")
        if not isinstance(ack.get("local_check"), Mapping):
            errors.append(f"command_acks.items[{index}] local_check must be an object")
    return items


def _task_progress_items(task_progress: Mapping[str, Any], errors: List[str]) -> List[Dict[str, Any]]:
    if task_progress.get("schema") != "TaskProgressSet.v1":
        errors.append("task_progress.json must use schema TaskProgressSet.v1")
    raw_items = task_progress.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        errors.append("hardware artifact must include TaskProgress evidence")
        return []
    items: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, Mapping):
            errors.append(f"task_progress.items[{index}] must be an object")
            continue
        progress = dict(item)
        items.append(progress)
        if progress.get("schema") != "TaskProgress.v1":
            errors.append(f"task_progress.items[{index}] must use schema TaskProgress.v1")
        for field in ("mission_id", "task_id", "platform_id", "status"):
            if not str(progress.get(field) or "").strip():
                errors.append(f"task_progress.items[{index}] {field} is required")
        ratio = progress.get("progress_ratio")
        if not isinstance(ratio, (int, float)) or isinstance(ratio, bool):
            errors.append(f"task_progress.items[{index}] progress_ratio must be numeric")
        observations = progress.get("observations")
        if observations is not None and not isinstance(observations, Mapping):
            errors.append(f"task_progress.items[{index}] observations must be an object")
    return items


def _source_validation_report_errors(source_validation: Any) -> List[str]:
    if not isinstance(source_validation, Mapping):
        return ["hardware artifact validation_report.source_validation_report must be an object"]
    errors: List[str] = []
    if source_validation.get("schema") != "ValidationReport.v1":
        errors.append("source_validation_report.schema must be ValidationReport.v1")
    if source_validation.get("status") != "passed":
        errors.append("source_validation_report.status must be passed")
    if source_validation.get("current_state") != "OPERATOR_APPROVAL":
        errors.append("source_validation_report.current_state must be OPERATOR_APPROVAL")
    source_errors = source_validation.get("errors")
    if not isinstance(source_errors, list):
        errors.append("source_validation_report.errors must be a list")
    elif source_errors:
        errors.append("source_validation_report.errors must be empty")
    return errors


def _gateway_trace_records(gateway_trace: Mapping[str, Any], errors: List[str]) -> List[Dict[str, Any]]:
    if gateway_trace.get("schema") != "GatewayTrace.v1":
        errors.append("gateway_trace.json must use schema GatewayTrace.v1")
    raw_records = gateway_trace.get("records")
    if not isinstance(raw_records, list) or not raw_records:
        errors.append("hardware artifact must include ROS1 gateway trace records")
        return []
    records: List[Dict[str, Any]] = []
    for index, record in enumerate(raw_records):
        if not isinstance(record, Mapping):
            errors.append(f"gateway_trace.records[{index}] must be an object")
            continue
        records.append(dict(record))
    return records


def _successful_dispatch_records(records: List[Dict[str, Any]], errors: List[str]) -> List[Dict[str, Any]]:
    dispatch_records: List[Dict[str, Any]] = []
    for index, record in enumerate(records):
        if record.get("rosservice_called") is not True or not _is_gateway_dispatch_service(record.get("service")):
            continue
        if record.get("returncode") != 0:
            continue
        if record.get("accepted") is not True:
            errors.append(f"gateway_trace.records[{index}] successful /gateway/dispatch must include accepted=true")
            continue
        if record.get("execution_context") != UNIT_HARDWARE_EXECUTION_CONTEXT:
            errors.append(
                f"gateway_trace.records[{index}] successful /gateway/dispatch must use "
                f"execution_context={UNIT_HARDWARE_EXECUTION_CONTEXT}"
            )
            continue
        if not _dispatch_service_matches_platform(record.get("service"), record.get("platform_id")):
            errors.append(
                f"gateway_trace.records[{index}] successful /gateway/dispatch service must match platform_id"
            )
            continue
        dispatch_records.append(record)
    return dispatch_records


def _mission_task_platform_key(item: Mapping[str, Any]):
    key = (
        str(item.get("mission_id") or "").strip(),
        str(item.get("task_id") or "").strip(),
        str(item.get("platform_id") or "").strip(),
    )
    if any(not part for part in key):
        return None
    return key


def _hardware_execution_summary(bundle_data: Mapping[str, Any]) -> Dict[str, Any]:
    mission_input = bundle_data.get("mission_input.json") or {}
    command_acks = bundle_data.get("command_acks.json") or {}
    gateway_trace = bundle_data.get("gateway_trace.json") or {}
    task_progress = bundle_data.get("task_progress.json") or {}
    ack_items = command_acks.get("items") if isinstance(command_acks, Mapping) else []
    trace_records = gateway_trace.get("records") if isinstance(gateway_trace, Mapping) else []
    progress_items = task_progress.get("items") if isinstance(task_progress, Mapping) else []
    strict_dispatch_records = [
        record for record in (trace_records or [])
        if isinstance(record, Mapping) and _strict_successful_dispatch_record(record)
    ] if isinstance(trace_records, list) else []
    strict_dispatch_keys = _key_set(strict_dispatch_records)
    strict_ack_keys = _key_set([
        item for item in (ack_items or [])
        if (
            isinstance(item, Mapping)
            and item.get("schema") == "CommandAck.v1"
            and item.get("accepted") is True
            and _mission_task_platform_key(item) in strict_dispatch_keys
        )
    ]) if isinstance(ack_items, list) else set()
    strict_progress_keys = _key_set([
        item for item in (progress_items or [])
        if (
            isinstance(item, Mapping)
            and item.get("schema") == "TaskProgress.v1"
            and _mission_task_platform_key(item) in strict_dispatch_keys
        )
    ]) if isinstance(progress_items, list) else set()
    common_proof_keys = strict_dispatch_keys & strict_ack_keys & strict_progress_keys
    return {
        "command_ack_count": len(ack_items) if isinstance(ack_items, list) else 0,
        "accepted_command_ack_count": len([
            item for item in (ack_items or [])
            if isinstance(item, Mapping) and item.get("accepted") is True
        ]) if isinstance(ack_items, list) else 0,
        "gateway_trace_count": len(trace_records) if isinstance(trace_records, list) else 0,
        "ros1_dispatch_call_count": len(strict_dispatch_records),
        "ros1_dispatch_services": sorted({
            str(record.get("service") or "")
            for record in strict_dispatch_records
            if str(record.get("service") or "")
        }),
        "strict_dispatch_key_count": len(strict_dispatch_keys),
        "strict_accepted_ack_matches_dispatch_count": len(strict_ack_keys),
        "strict_task_progress_matches_dispatch_count": len(strict_progress_keys),
        "strict_common_ack_dispatch_progress_key_count": len(common_proof_keys),
        "strict_common_ack_dispatch_progress_keys": [
            {"mission_id": mission_id, "task_id": task_id, "platform_id": platform_id}
            for mission_id, task_id, platform_id in sorted(common_proof_keys)
        ],
        "execution_context": (
            (bundle_data.get("environment_profile.json") or {}).get("execution_context")
            if isinstance(bundle_data.get("environment_profile.json") or {}, Mapping)
            else ""
        ),
        "operator_approved": (
            (bundle_data.get("environment_profile.json") or {}).get("operator_approved")
            if isinstance(bundle_data.get("environment_profile.json") or {}, Mapping)
            else None
        ),
        "operator_approval_source": (
            (bundle_data.get("environment_profile.json") or {}).get("operator_approval_source")
            if isinstance(bundle_data.get("environment_profile.json") or {}, Mapping)
            else ""
        ),
        "machine_id": (
            (bundle_data.get("environment_profile.json") or {}).get("machine_id")
            if isinstance(bundle_data.get("environment_profile.json") or {}, Mapping)
            else ""
        ),
        "case_id": _case_id_from_mission_input(mission_input),
        "task_progress_count": len(progress_items) if isinstance(progress_items, list) else 0,
    }


def _case_id_from_mission_input(mission_input: Any) -> str:
    if not isinstance(mission_input, Mapping):
        return ""
    run_input = mission_input.get("run_input")
    if not isinstance(run_input, Mapping):
        return ""
    return str(run_input.get("case_id") or "").strip()


def _is_gateway_dispatch_service(service: Any) -> bool:
    return isinstance(service, str) and service.strip().endswith("/gateway/dispatch")


def _key_set(items: List[Mapping[str, Any]]) -> set:
    keys = set()
    for item in items:
        key = _mission_task_platform_key(item)
        if key is not None:
            keys.add(key)
    return keys


def _strict_successful_dispatch_record(record: Mapping[str, Any]) -> bool:
    return (
        record.get("rosservice_called") is True
        and _is_gateway_dispatch_service(record.get("service"))
        and record.get("returncode") == 0
        and record.get("accepted") is True
        and record.get("publish_attempted") is False
        and record.get("execution_context") == UNIT_HARDWARE_EXECUTION_CONTEXT
        and _mission_task_platform_key(record) is not None
        and _dispatch_service_matches_platform(record.get("service"), record.get("platform_id"))
    )


def _dispatch_service_matches_platform(service: Any, platform_id: Any) -> bool:
    if not isinstance(service, str):
        return False
    platform = str(platform_id or "").strip()
    if not platform:
        return False
    return service.strip().endswith(f"/{platform}/gateway/dispatch")
