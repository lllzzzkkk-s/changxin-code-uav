from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_planning.migration.task_command_extraction import extract_task_command_from_artifact
from task_planning.migration.unit_ugv_artifact_target_map_preflight import (
    check_unit_ugv_artifact_target_map,
)


UNIT_UGV_OBJECT_APPROACH_PREP_BUNDLE_SCHEMA = "UnitUgvObjectApproachPrepBundle.v1"


@dataclass(frozen=True)
class UnitUgvObjectApproachPrepBundleReport:
    ok: bool
    output_dir: str
    artifact_root: str
    target_map_path: str
    platform_id: str
    capability: str
    task_id: str
    object_query: str
    selected_target_id: str
    files: Dict[str, str]
    extracted_task_command: Dict[str, Any]
    artifact_target_map_preflight: Dict[str, Any]
    validation_errors: List[str]
    ros_connected: bool = False
    dispatch_performed: bool = False
    gateway_dry_run_called: bool = False
    schema: str = UNIT_UGV_OBJECT_APPROACH_PREP_BUNDLE_SCHEMA

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "output_dir": self.output_dir,
            "artifact_root": self.artifact_root,
            "target_map_path": self.target_map_path,
            "platform_id": self.platform_id,
            "capability": self.capability,
            "task_id": self.task_id,
            "object_query": self.object_query,
            "selected_target_id": self.selected_target_id,
            "files": dict(self.files),
            "extracted_task_command": dict(self.extracted_task_command),
            "artifact_target_map_preflight": dict(self.artifact_target_map_preflight),
            "validation_errors": list(self.validation_errors),
            "ros_connected": self.ros_connected,
            "dispatch_performed": self.dispatch_performed,
            "gateway_dry_run_called": self.gateway_dry_run_called,
        }


def prepare_unit_ugv_object_approach_bundle(
    *,
    artifact_root: Path,
    target_map_path: Path,
    output_dir: Path,
    platform_id: str = "ugv_0",
    capability: str = "confirm_target",
    task_id: Optional[str] = None,
    index: int = 0,
    max_move_base_distance_m: Optional[float] = None,
) -> UnitUgvObjectApproachPrepBundleReport:
    expanded_artifact_root = artifact_root.expanduser().resolve()
    expanded_target_map_path = target_map_path.expanduser().resolve()
    expanded_output_dir = output_dir.expanduser().resolve()
    expanded_output_dir.mkdir(parents=True, exist_ok=True)

    extracted = extract_task_command_from_artifact(
        artifact_root=expanded_artifact_root,
        platform_id=platform_id,
        capability=capability,
        task_id=task_id,
        index=index,
    )
    extracted_data = extracted.as_dict()
    files: Dict[str, str] = {}
    validation_errors = [f"task_command:{item}" for item in extracted.validation_errors]

    files["extracted_task_command_report"] = str(_write_json(
        expanded_output_dir / "extracted_task_command.report.json",
        extracted_data,
    ))

    command_data: Dict[str, Any] = {}
    selected_task_id = ""
    object_query = ""
    if extracted.command is not None:
        command_data = extracted.command.as_dict()
        selected_task_id = extracted.command.task_id
        object_query = str(extracted.command.parameters.get("object_query") or "").strip()
        files["task_command_json"] = str(_write_json(
            expanded_output_dir / "task_command.json",
            command_data,
        ))
        files["task_command_rosservice_json"] = str(_write_json(
            expanded_output_dir / "task_command.rosservice.json",
            {"task_command_json": extracted_data["task_command_json"]},
        ))

    target_map_copy_path = expanded_output_dir / "unit_ugv_targets.input.json"
    shutil.copyfile(expanded_target_map_path, target_map_copy_path)
    files["target_map_copy"] = str(target_map_copy_path)

    preflight = check_unit_ugv_artifact_target_map(
        artifact_root=expanded_artifact_root,
        target_map_path=expanded_target_map_path,
        platform_id=platform_id,
        capability=capability,
        task_id=task_id,
        index=index,
        max_move_base_distance_m=max_move_base_distance_m,
    )
    preflight_data = preflight.as_dict()
    files["artifact_target_map_preflight"] = str(_write_json(
        expanded_output_dir / "artifact_target_map_preflight.json",
        preflight_data,
    ))
    validation_errors.extend(f"preflight:{item}" for item in preflight.validation_errors)

    files["README"] = str(_write_readme(
        expanded_output_dir / "README.md",
        platform_id=platform_id,
        capability=capability,
        task_id=selected_task_id or preflight.task_id,
    ))

    deduped_errors = _dedupe(validation_errors)
    report_path = expanded_output_dir / "prep_bundle_report.json"
    files["prep_bundle_report"] = str(report_path)
    report = UnitUgvObjectApproachPrepBundleReport(
        ok=not deduped_errors and extracted.ok and preflight.ok,
        output_dir=str(expanded_output_dir),
        artifact_root=str(expanded_artifact_root),
        target_map_path=str(expanded_target_map_path),
        platform_id=platform_id,
        capability=capability,
        task_id=selected_task_id or preflight.task_id,
        object_query=object_query or preflight.object_query,
        selected_target_id=preflight.selected_target_id,
        files=files,
        extracted_task_command=extracted_data,
        artifact_target_map_preflight=preflight_data,
        validation_errors=deduped_errors,
    )
    _write_json(report_path, report.as_dict())
    return report


def _write_json(path: Path, data: Dict[str, Any]) -> Path:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_readme(path: Path, *, platform_id: str, capability: str, task_id: str) -> Path:
    path.write_text(
        "\n".join([
            "# Unit UGV Object Approach Prep Bundle",
            "",
            "This bundle is a source-side preparation artifact for a later ROS1 gateway stage.",
            "It contains a validated TaskCommand, rosservice JSON payload, target-map copy, and local preflight report.",
            "",
            f"- platform_id: `{platform_id}`",
            f"- capability: `{capability}`",
            f"- task_id: `{task_id}`",
            "",
            "Do not treat this bundle as a dispatch record. It does not call gateway services, publish ROS topics, or authorize motion.",
            "",
        ]),
        encoding="utf-8",
    )
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
