from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_planning.migration.unit_ugv_gateway_call_plan import plan_unit_ugv_gateway_call
from task_planning.migration.unit_ugv_object_approach_bundle import prepare_unit_ugv_object_approach_bundle
from task_planning.migration.unit_ugv_target_map import check_unit_ugv_target_map
from task_planning.mission_ops.intent_runner import run_task_planning_intent


UNIT_UGV_OBJECT_APPROACH_PIPELINE_SCHEMA = "UnitUgvObjectApproachRosReadyHandoff.v1"


@dataclass(frozen=True)
class UnitUgvObjectApproachPipelineReport:
    ok: bool
    output_dir: str
    intent: str
    case_id: str
    mission_id: str
    platform_id: str
    object_query: str
    selected_target_id: str
    service_name: str
    files: Dict[str, str]
    intent_run: Dict[str, Any]
    target_map_check: Dict[str, Any]
    prep_bundle: Dict[str, Any]
    gateway_dry_run_plan: Dict[str, Any]
    validation_errors: List[str]
    ros_ready: bool = False
    next_runtime_stage: str = "4060_ros1_gateway_dry_run"
    mac_side_ros_connected: bool = False
    mac_side_service_called: bool = False
    mac_side_dispatch_performed: bool = False
    mac_side_rostopic_pub: bool = False
    schema: str = UNIT_UGV_OBJECT_APPROACH_PIPELINE_SCHEMA

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "output_dir": self.output_dir,
            "intent": self.intent,
            "case_id": self.case_id,
            "mission_id": self.mission_id,
            "platform_id": self.platform_id,
            "object_query": self.object_query,
            "selected_target_id": self.selected_target_id,
            "service_name": self.service_name,
            "files": dict(self.files),
            "intent_run": dict(self.intent_run),
            "target_map_check": dict(self.target_map_check),
            "prep_bundle": dict(self.prep_bundle),
            "gateway_dry_run_plan": dict(self.gateway_dry_run_plan),
            "validation_errors": list(self.validation_errors),
            "ros_ready": self.ros_ready,
            "next_runtime_stage": self.next_runtime_stage,
            "mac_side_ros_connected": self.mac_side_ros_connected,
            "mac_side_service_called": self.mac_side_service_called,
            "mac_side_dispatch_performed": self.mac_side_dispatch_performed,
            "mac_side_rostopic_pub": self.mac_side_rostopic_pub,
        }


def prepare_unit_ugv_object_approach_pipeline(
    *,
    profile_path: Path,
    intent: str,
    mission_id: str,
    case_id: str,
    target_map_path: Path,
    ros1_gateway_profile_path: Path,
    output_dir: Path,
    platform_id: str = "ugv_0",
    capability: str = "confirm_target",
    index: int = 1,
    max_move_base_distance_m: Optional[float] = None,
    repo_root: Optional[Path] = None,
) -> UnitUgvObjectApproachPipelineReport:
    expanded_output_dir = output_dir.expanduser().resolve()
    expanded_output_dir.mkdir(parents=True, exist_ok=True)
    files: Dict[str, str] = {}
    validation_errors: List[str] = []

    intent_run = run_task_planning_intent(
        profile_path=profile_path,
        intent=intent,
        context_snapshot={
            "mission_id": mission_id,
            "primary_platform": platform_id,
        },
        case_id=case_id,
        artifact_root=expanded_output_dir / "intent_runs",
        repo_root=repo_root,
    )
    intent_run_data = intent_run.as_dict()
    files["intent_run"] = str(_write_json(expanded_output_dir / "intent_run.json", intent_run_data))
    if not intent_run.ok:
        validation_errors.extend(f"intent_run:{item}" for item in intent_run.validation_errors)

    artifact_root = Path(intent_run.artifact_bundle_path) if intent_run.artifact_bundle_path else Path()
    object_query = _object_query_from_artifact(artifact_root, validation_errors)

    target_map_check = check_unit_ugv_target_map(
        target_map_path,
        expected_platform_id=platform_id,
        object_query=object_query,
        require_operator_confirmed=True,
        require_object_queries=True,
        max_move_base_distance_m=max_move_base_distance_m,
    )
    target_map_check_data = target_map_check.as_dict()
    files["target_map_check"] = str(_write_json(
        expanded_output_dir / "target_map_check.json",
        target_map_check_data,
    ))
    if not target_map_check.ok:
        validation_errors.extend(f"target_map:{item}" for item in target_map_check.validation_errors)

    prep_bundle_data: Dict[str, Any] = {}
    gateway_plan_data: Dict[str, Any] = {}
    if artifact_root and artifact_root.exists():
        prep_bundle = prepare_unit_ugv_object_approach_bundle(
            artifact_root=artifact_root,
            target_map_path=target_map_path,
            output_dir=expanded_output_dir / "prep_bundle",
            platform_id=platform_id,
            capability=capability,
            index=index,
            max_move_base_distance_m=max_move_base_distance_m,
        )
        prep_bundle_data = prep_bundle.as_dict()
        files["prep_bundle_report"] = prep_bundle.files.get("prep_bundle_report", "")
        if not prep_bundle.ok:
            validation_errors.extend(f"prep_bundle:{item}" for item in prep_bundle.validation_errors)

        gateway_plan = plan_unit_ugv_gateway_call(
            prep_report_path=Path(files["prep_bundle_report"]),
            profile_path=ros1_gateway_profile_path,
            mode="dry_run",
        )
        gateway_plan_data = gateway_plan.as_dict()
        files["gateway_dry_run_plan"] = str(_write_json(
            expanded_output_dir / "gateway_dry_run_plan.json",
            gateway_plan_data,
        ))
        if not gateway_plan.ok:
            validation_errors.extend(f"gateway_plan:{item}" for item in gateway_plan.validation_errors)
    else:
        validation_errors.append("intent_run artifact_bundle_path is required before ROS-ready handoff")

    service_name = str(gateway_plan_data.get("service_name") or "")
    selected_target_id = str(target_map_check_data.get("selected_target_id") or "")
    deduped_errors = _dedupe(validation_errors)
    report = UnitUgvObjectApproachPipelineReport(
        ok=not deduped_errors,
        output_dir=str(expanded_output_dir),
        intent=intent,
        case_id=case_id,
        mission_id=mission_id,
        platform_id=platform_id,
        object_query=object_query,
        selected_target_id=selected_target_id,
        service_name=service_name,
        files=files,
        intent_run=intent_run_data,
        target_map_check=target_map_check_data,
        prep_bundle=prep_bundle_data,
        gateway_dry_run_plan=gateway_plan_data,
        validation_errors=deduped_errors,
        ros_ready=not deduped_errors and bool(service_name),
    )
    report_path = expanded_output_dir / "ros_ready_handoff_report.json"
    files["handoff_report"] = str(report_path)
    report = UnitUgvObjectApproachPipelineReport(
        ok=report.ok,
        output_dir=report.output_dir,
        intent=report.intent,
        case_id=report.case_id,
        mission_id=report.mission_id,
        platform_id=report.platform_id,
        object_query=report.object_query,
        selected_target_id=report.selected_target_id,
        service_name=report.service_name,
        files=files,
        intent_run=report.intent_run,
        target_map_check=report.target_map_check,
        prep_bundle=report.prep_bundle,
        gateway_dry_run_plan=report.gateway_dry_run_plan,
        validation_errors=report.validation_errors,
        ros_ready=report.ros_ready,
    )
    _write_json(report_path, report.as_dict())
    return report


def _object_query_from_artifact(artifact_root: Path, errors: List[str]) -> str:
    if not artifact_root or not artifact_root.exists():
        errors.append("intent_run artifact bundle is missing")
        return ""
    task_schema_path = artifact_root / "task_schema.json"
    try:
        task_schema = json.loads(task_schema_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"task_schema parse failed: {exc}")
        return ""
    constraints = (
        task_schema.get("mission_request", {}).get("constraints", {})
        if isinstance(task_schema.get("mission_request"), dict)
        else {}
    )
    object_query = str(constraints.get("object_query") or "").strip()
    if not object_query:
        errors.append("task_schema mission_request.constraints.object_query is required")
    return object_query


def _write_json(path: Path, data: Dict[str, Any]) -> Path:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _dedupe(values: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
