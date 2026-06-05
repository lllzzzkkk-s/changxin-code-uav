from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_planning.config import EnvironmentProfile, load_profile


UNIT_UGV_GATEWAY_CALL_PLAN_SCHEMA = "UnitUgvGatewayCallPlan.v1"


@dataclass(frozen=True)
class UnitUgvGatewayCallPlan:
    ok: bool
    prep_report_path: str
    profile_path: str
    mode: str
    platform_id: str
    service_name: str
    payload_file: str
    task_id: str
    object_query: str
    selected_target_id: str
    service_signature_requirements: Dict[str, Any]
    required_evidence: List[str]
    command_templates: List[str]
    validation_errors: List[str]
    ros_connected: bool = False
    service_called: bool = False
    dispatch_performed: bool = False
    rostopic_pub: bool = False
    schema: str = UNIT_UGV_GATEWAY_CALL_PLAN_SCHEMA

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "prep_report_path": self.prep_report_path,
            "profile_path": self.profile_path,
            "mode": self.mode,
            "platform_id": self.platform_id,
            "service_name": self.service_name,
            "payload_file": self.payload_file,
            "task_id": self.task_id,
            "object_query": self.object_query,
            "selected_target_id": self.selected_target_id,
            "service_signature_requirements": dict(self.service_signature_requirements),
            "required_evidence": list(self.required_evidence),
            "command_templates": list(self.command_templates),
            "validation_errors": list(self.validation_errors),
            "ros_connected": self.ros_connected,
            "service_called": self.service_called,
            "dispatch_performed": self.dispatch_performed,
            "rostopic_pub": self.rostopic_pub,
        }


def plan_unit_ugv_gateway_call(
    *,
    prep_report_path: Path,
    profile_path: Path,
    mode: str = "dry_run",
    operator_approved: bool = False,
) -> UnitUgvGatewayCallPlan:
    expanded_prep_report_path = prep_report_path.expanduser().resolve()
    expanded_profile_path = profile_path.expanduser().resolve()
    validation_errors: List[str] = []
    prep_data = _read_json(expanded_prep_report_path, validation_errors)
    profile = _load_profile(expanded_profile_path, validation_errors)

    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"dry_run", "dispatch"}:
        validation_errors.append("mode must be dry_run or dispatch")
        normalized_mode = "dry_run"

    files = prep_data.get("files") if isinstance(prep_data.get("files"), dict) else {}
    payload_file = str(files.get("task_command_rosservice_json") or "")
    platform_id = str(prep_data.get("platform_id") or "")
    task_id = str(prep_data.get("task_id") or "")
    object_query = str(prep_data.get("object_query") or "")
    selected_target_id = str(prep_data.get("selected_target_id") or "")

    if not prep_data.get("ok"):
        validation_errors.append("prep bundle report must be ok=true before gateway call planning")
    if not payload_file:
        validation_errors.append("prep bundle report must include files.task_command_rosservice_json")

    service_name = ""
    if profile is not None:
        validation_errors.extend(_profile_errors(profile))
        template = (
            profile.ros_gateway_dry_run_service_template
            if normalized_mode == "dry_run"
            else profile.ros_gateway_dispatch_service_template
        )
        service_name = template.format(platform_id=platform_id or "ugv_0")
    if normalized_mode == "dispatch" and not operator_approved:
        validation_errors.append("operator approval is required before planning dispatch")

    return UnitUgvGatewayCallPlan(
        ok=not validation_errors,
        prep_report_path=str(expanded_prep_report_path),
        profile_path=str(expanded_profile_path),
        mode=normalized_mode,
        platform_id=platform_id,
        service_name=service_name,
        payload_file=payload_file,
        task_id=task_id,
        object_query=object_query,
        selected_target_id=selected_target_id,
        service_signature_requirements={
            "type": "platform_gateway_msgs/TaskCommandJson",
            "args": ["task_command_json"],
            "service_name": service_name,
        },
        required_evidence=[
            "TaskPlanningSiteAcceptance.v1 ok=true with work_hardware_ros1_signatures_observed",
            "rosservice type evidence ends with TaskCommandJson",
            "rosservice args evidence includes task_command_json",
            "UnitUgvObjectApproachPrepBundle.v1 ok=true",
            "local operator approval before dispatch mode",
        ],
        command_templates=_command_templates(
            profile_path=expanded_profile_path,
            platform_id=platform_id or "ugv_0",
            service_name=service_name,
            payload_file=payload_file,
            mode=normalized_mode,
        ),
        validation_errors=_dedupe(validation_errors),
    )


def _read_json(path: Path, errors: List[str]) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"prep report parse failed: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append("prep report must be a JSON object")
        return {}
    return data


def _load_profile(path: Path, errors: List[str]) -> Optional[EnvironmentProfile]:
    try:
        return load_profile(path)
    except Exception as exc:
        errors.append(f"profile parse failed: {exc}")
        return None


def _profile_errors(profile: EnvironmentProfile) -> List[str]:
    errors: List[str] = []
    if profile.mission_profile != "work_hardware":
        errors.append("gateway call plan requires MISSION_PROFILE=work_hardware")
    if profile.platform_backend != "ros1_gateway":
        errors.append("gateway call plan requires PLATFORM_BACKEND=ros1_gateway")
    if not profile.hardware_approval_required:
        errors.append("gateway call plan requires HARDWARE_APPROVAL_REQUIRED=true")
    return errors


def _command_templates(
    *,
    profile_path: Path,
    platform_id: str,
    service_name: str,
    payload_file: str,
    mode: str,
) -> List[str]:
    commands = [
        (
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py "
            f"--profile {profile_path} --platform-id {platform_id} "
            "--run-rosservice-list --run-service-signatures "
            "--require-rosservice-audit --require-service-signatures"
        ),
    ]
    if service_name and payload_file:
        commands.append(f"rosservice call {service_name} \"$(cat {payload_file})\"")
    if mode == "dispatch":
        commands.append("Capture CommandAck.v1 and TaskProgress.v1 before recording hardware evidence.")
    return commands


def _dedupe(values: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
