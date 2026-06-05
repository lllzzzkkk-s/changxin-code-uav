from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from platform_gateway.unit_ugv_executor import UnitUgvExecutor, UnitUgvTargetMap
from task_planning.migration.task_command_extraction import extract_task_command_from_artifact
from task_planning.migration.unit_ugv_target_map import check_unit_ugv_target_map


UNIT_UGV_ARTIFACT_TARGET_MAP_PREFLIGHT_SCHEMA = "UnitUgvArtifactTargetMapPreflight.v1"


@dataclass(frozen=True)
class UnitUgvArtifactTargetMapPreflightReport:
    ok: bool
    artifact_root: str
    target_map_path: str
    platform_id: str
    capability: str
    task_id: str
    object_query: str
    selected_target_id: str
    command_candidate_count: int
    command_selected_index: Optional[int]
    target_map_check: Dict[str, Any]
    command_ack: Dict[str, Any]
    validation_errors: List[str]
    ros_connected: bool = False
    dispatch_performed: bool = False
    schema: str = UNIT_UGV_ARTIFACT_TARGET_MAP_PREFLIGHT_SCHEMA

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "artifact_root": self.artifact_root,
            "target_map_path": self.target_map_path,
            "platform_id": self.platform_id,
            "capability": self.capability,
            "task_id": self.task_id,
            "object_query": self.object_query,
            "selected_target_id": self.selected_target_id,
            "command_candidate_count": self.command_candidate_count,
            "command_selected_index": self.command_selected_index,
            "target_map_check": dict(self.target_map_check),
            "command_ack": dict(self.command_ack),
            "validation_errors": list(self.validation_errors),
            "ros_connected": self.ros_connected,
            "dispatch_performed": self.dispatch_performed,
        }


def check_unit_ugv_artifact_target_map(
    *,
    artifact_root: Path,
    target_map_path: Path,
    platform_id: str = "ugv_0",
    capability: str = "confirm_target",
    task_id: Optional[str] = None,
    index: int = 0,
    require_object_queries: bool = True,
    max_move_base_distance_m: Optional[float] = None,
) -> UnitUgvArtifactTargetMapPreflightReport:
    expanded_artifact_root = artifact_root.expanduser()
    expanded_target_map_path = target_map_path.expanduser()
    validation_errors: List[str] = []
    command_ack: Dict[str, Any] = {}
    target_map_check_data: Dict[str, Any] = {}
    selected_target_id = ""
    selected_task_id = ""
    object_query = ""

    extracted = extract_task_command_from_artifact(
        artifact_root=expanded_artifact_root,
        platform_id=platform_id,
        capability=capability,
        task_id=task_id,
        index=index,
    )
    validation_errors.extend(f"task_command:{item}" for item in extracted.validation_errors)

    command = extracted.command
    if command is not None:
        selected_task_id = command.task_id
        object_query = str(command.parameters.get("object_query") or "").strip()
        if not object_query and not str(command.parameters.get("target_id") or "").strip():
            validation_errors.append("task_command:parameters.object_query or parameters.target_id is required")

    target_map_check = check_unit_ugv_target_map(
        expanded_target_map_path,
        expected_platform_id=platform_id,
        object_query=object_query or None,
        require_object_queries=require_object_queries,
        max_move_base_distance_m=max_move_base_distance_m,
    )
    target_map_check_data = target_map_check.as_dict()
    validation_errors.extend(f"target_map:{item}" for item in target_map_check.validation_errors)
    command_target_id = str(command.parameters.get("target_id") or "").strip() if command is not None else ""
    if command_target_id and target_map_check.selected_target_id and command_target_id != target_map_check.selected_target_id:
        validation_errors.append(
            f"task_command target_id {command_target_id} "
            f"does not match object_query-selected target {target_map_check.selected_target_id}"
        )

    if command is not None and target_map_check.ok:
        try:
            target_map = UnitUgvTargetMap.from_path(expanded_target_map_path)
            ack = UnitUgvExecutor(
                target_map=target_map,
                max_move_base_distance_m=max_move_base_distance_m,
            ).dry_run(command)
            command_ack = ack.as_dict()
            selected_target_id = str(ack.local_check.get("resolved_target_id") or target_map_check.selected_target_id)
            if not ack.accepted:
                validation_errors.append(f"unit_ugv_dry_run_preflight:{ack.reason}")
            if bool(ack.local_check.get("motion_attempted")):
                validation_errors.append("unit_ugv_dry_run_preflight unexpectedly attempted motion")
            if bool(ack.local_check.get("raw_ros_publish_attempted")):
                validation_errors.append("unit_ugv_dry_run_preflight unexpectedly attempted raw ROS publish")
        except Exception as exc:
            validation_errors.append(f"unit_ugv_dry_run_preflight:{exc}")
    elif target_map_check.selected_target_id:
        selected_target_id = target_map_check.selected_target_id

    return UnitUgvArtifactTargetMapPreflightReport(
        ok=not validation_errors,
        artifact_root=str(expanded_artifact_root),
        target_map_path=str(expanded_target_map_path),
        platform_id=platform_id,
        capability=capability,
        task_id=selected_task_id,
        object_query=object_query,
        selected_target_id=selected_target_id,
        command_candidate_count=extracted.candidate_count,
        command_selected_index=extracted.selected_index,
        target_map_check=target_map_check_data,
        command_ack=command_ack,
        validation_errors=validation_errors,
    )
