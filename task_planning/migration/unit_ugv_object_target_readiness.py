from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from task_planning.migration.unit_ugv_target_map import (
    UnitUgvTargetMapCheckReport,
    check_unit_ugv_target_map,
    write_unit_ugv_target_map_template,
)


UNIT_UGV_OBJECT_TARGET_READINESS_SCHEMA = "UnitUgvObjectTargetReadiness.v1"


@dataclass(frozen=True)
class UnitUgvObjectTargetReadinessReport:
    ok: bool
    target_map_path: str
    platform_id: str
    object_query: str
    perception_backend: str
    target_map_exists: bool
    target_map_template_written: bool
    target_binding_ready: bool
    selected_target_id: str
    target_map_check: Dict[str, Any]
    next_runtime_stage: str
    validation_errors: List[str]
    warnings: List[str]
    yolo_connected: bool = False
    ros_connected: bool = False
    gateway_dry_run_called: bool = False
    dispatch_called: bool = False
    schema: str = UNIT_UGV_OBJECT_TARGET_READINESS_SCHEMA

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "target_map_path": self.target_map_path,
            "platform_id": self.platform_id,
            "object_query": self.object_query,
            "perception_backend": self.perception_backend,
            "target_map_exists": self.target_map_exists,
            "target_map_template_written": self.target_map_template_written,
            "target_binding_ready": self.target_binding_ready,
            "selected_target_id": self.selected_target_id,
            "target_map_check": dict(self.target_map_check),
            "next_runtime_stage": self.next_runtime_stage,
            "validation_errors": list(self.validation_errors),
            "warnings": list(self.warnings),
            "yolo_connected": self.yolo_connected,
            "ros_connected": self.ros_connected,
            "gateway_dry_run_called": self.gateway_dry_run_called,
            "dispatch_called": self.dispatch_called,
        }


def check_unit_ugv_object_target_readiness(
    *,
    target_map_path: Path,
    object_query: str,
    platform_id: str = "ugv_0",
    target_id: str = "target_01",
    perception_backend: str = "operator_confirmed_target_map",
    write_missing_template: bool = False,
    max_move_base_distance_m: float | None = None,
) -> UnitUgvObjectTargetReadinessReport:
    expanded_target_map_path = target_map_path.expanduser()
    normalized_backend = perception_backend.strip().lower()
    validation_errors: List[str] = []
    warnings: List[str] = []
    target_map_check_data: Dict[str, Any] = {}
    selected_target_id = ""
    template_written = False
    target_map_exists = expanded_target_map_path.exists()

    if normalized_backend not in {"operator_confirmed_target_map", "yolo"}:
        validation_errors.append("perception_backend must be operator_confirmed_target_map or yolo")
        normalized_backend = "operator_confirmed_target_map"
    if normalized_backend == "yolo":
        validation_errors.append("YOLO perception backend is not integrated yet")
        warnings.append("Use operator_confirmed_target_map for the current UGV gateway dry-run gate.")

    if not target_map_exists:
        if write_missing_template:
            try:
                write_unit_ugv_target_map_template(
                    expanded_target_map_path,
                    platform_id=platform_id,
                    target_id=target_id,
                    object_queries=[object_query],
                    action="manual_confirm",
                    operator_confirmed=False,
                    description=(
                        "TODO: local operator must confirm this object-target mapping; "
                        "future YOLO integration should replace this manual binding evidence."
                    ),
                )
            except Exception as exc:
                validation_errors.append(
                    "target map is missing; failed to write unconfirmed operator target-map template: "
                    f"{exc}"
                )
            else:
                template_written = True
                validation_errors.append("target map is missing; wrote an unconfirmed operator target-map template")
        else:
            validation_errors.append("target map is missing")
    else:
        check = check_unit_ugv_target_map(
            expanded_target_map_path,
            expected_platform_id=platform_id,
            object_query=object_query,
            require_operator_confirmed=True,
            require_object_queries=True,
            max_move_base_distance_m=max_move_base_distance_m,
        )
        target_map_check_data = check.as_dict()
        selected_target_id = check.selected_target_id
        validation_errors.extend(check.validation_errors)
        warnings.extend(check.warnings)

    target_binding_ready = (
        normalized_backend == "operator_confirmed_target_map"
        and target_map_exists
        and bool(selected_target_id)
        and not validation_errors
    )
    next_runtime_stage = _next_runtime_stage(
        perception_backend=normalized_backend,
        target_binding_ready=target_binding_ready,
    )
    return UnitUgvObjectTargetReadinessReport(
        ok=target_binding_ready,
        target_map_path=str(expanded_target_map_path),
        platform_id=platform_id,
        object_query=object_query,
        perception_backend=normalized_backend,
        target_map_exists=target_map_exists,
        target_map_template_written=template_written,
        target_binding_ready=target_binding_ready,
        selected_target_id=selected_target_id,
        target_map_check=target_map_check_data,
        next_runtime_stage=next_runtime_stage,
        validation_errors=_dedupe(validation_errors),
        warnings=_dedupe(warnings),
    )


def write_report(path: Path, report: UnitUgvObjectTargetReadinessReport) -> Path:
    path.expanduser().parent.mkdir(parents=True, exist_ok=True)
    path.expanduser().write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path.expanduser()


def _next_runtime_stage(*, perception_backend: str, target_binding_ready: bool) -> str:
    if perception_backend == "yolo":
        return "wait_for_yolo_integration_or_operator_target_map"
    if target_binding_ready:
        return "4060_ros1_gateway_handoff"
    return "local_operator_confirm_target_map"


def _dedupe(values: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
