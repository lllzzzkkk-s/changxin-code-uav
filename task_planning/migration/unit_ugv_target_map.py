from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from platform_gateway.unit_ugv_executor import UnitUgvTarget, UnitUgvTargetMap


UNIT_UGV_TARGET_MAP_CHECK_REPORT_SCHEMA = "UnitUgvTargetMapCheckReport.v1"
UNIT_UGV_TARGET_MAP_TEMPLATE_WRITE_REPORT_SCHEMA = "UnitUgvTargetMapTemplateWriteReport.v1"


@dataclass(frozen=True)
class UnitUgvTargetMapCheckReport:
    ok: bool
    target_map_path: str
    platform_id: str
    expected_platform_id: str
    target_count: int
    selected_object_query: str
    selected_target_id: str
    object_query_index: List[Dict[str, str]]
    validation_errors: List[str]
    warnings: List[str]
    schema: str = UNIT_UGV_TARGET_MAP_CHECK_REPORT_SCHEMA

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "target_map_path": self.target_map_path,
            "platform_id": self.platform_id,
            "expected_platform_id": self.expected_platform_id,
            "target_count": self.target_count,
            "selected_object_query": self.selected_object_query,
            "selected_target_id": self.selected_target_id,
            "object_query_index": [dict(item) for item in self.object_query_index],
            "validation_errors": list(self.validation_errors),
            "warnings": list(self.warnings),
        }


def check_unit_ugv_target_map(
    target_map_path: Path,
    *,
    expected_platform_id: Optional[str] = None,
    object_query: Optional[str] = None,
    require_operator_confirmed: bool = True,
    require_object_queries: bool = False,
    max_move_base_distance_m: Optional[float] = None,
) -> UnitUgvTargetMapCheckReport:
    path = target_map_path.expanduser()
    validation_errors: List[str] = []
    warnings: List[str] = []
    object_query_index: List[Dict[str, str]] = []
    selected_target_id = ""

    try:
        target_map = UnitUgvTargetMap.from_path(path)
    except Exception as exc:
        return UnitUgvTargetMapCheckReport(
            ok=False,
            target_map_path=str(path),
            platform_id="",
            expected_platform_id=str(expected_platform_id or ""),
            target_count=0,
            selected_object_query=str(object_query or ""),
            selected_target_id="",
            object_query_index=[],
            validation_errors=[f"target map parse failed: {exc}"],
            warnings=[],
        )

    expected = str(expected_platform_id or "").strip()
    if expected and target_map.platform_id != expected:
        validation_errors.append(f"target map platform_id {target_map.platform_id} does not match expected {expected}")

    aliases_by_normalized: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for target_id in sorted(target_map.targets):
        target = target_map.targets[target_id]
        validation_errors.extend(_target_validation_errors(
            target,
            require_operator_confirmed=require_operator_confirmed,
            require_object_queries=require_object_queries,
            max_move_base_distance_m=max_move_base_distance_m,
        ))
        for raw_query in target.object_queries or []:
            normalized = _normalize_object_query(raw_query)
            if not normalized:
                continue
            aliases_by_normalized[normalized].append((target_id, raw_query))
            object_query_index.append({
                "target_id": target_id,
                "object_query": raw_query,
                "normalized_object_query": normalized,
            })

    duplicate_normalized_queries = {
        normalized_query: sorted({target_id for target_id, _ in matches})
        for normalized_query, matches in aliases_by_normalized.items()
        if len({target_id for target_id, _ in matches}) > 1
    }
    for normalized_query, target_ids in sorted(duplicate_normalized_queries.items()):
        validation_errors.append(
            f"object_query maps to multiple targets: {normalized_query}: {', '.join(target_ids)}"
        )

    selected_query = str(object_query or "").strip()
    if selected_query:
        normalized_selected_query = _normalize_object_query(selected_query)
        matching_target_ids = sorted({
            target_id for target_id, _ in aliases_by_normalized.get(normalized_selected_query, [])
        })
        if not matching_target_ids:
            validation_errors.append(f"object_query is not mapped on this unit UGV: {selected_query}")
        elif len(matching_target_ids) == 1 and normalized_selected_query not in duplicate_normalized_queries:
            selected_target_id = matching_target_ids[0]

    if require_object_queries and not object_query_index:
        validation_errors.append("target map requires at least one object_queries alias")

    return UnitUgvTargetMapCheckReport(
        ok=not validation_errors,
        target_map_path=str(path),
        platform_id=target_map.platform_id,
        expected_platform_id=expected,
        target_count=len(target_map.targets),
        selected_object_query=selected_query,
        selected_target_id=selected_target_id,
        object_query_index=object_query_index,
        validation_errors=validation_errors,
        warnings=warnings,
    )


def build_unit_ugv_target_map_template(
    *,
    platform_id: str,
    target_id: str,
    object_queries: List[str],
    action: str = "manual_confirm",
    operator_confirmed: bool = False,
    description: str = "TODO: replace with a local operator-confirmed UGV target",
    frame_id: str = "map",
    x: Optional[float] = None,
    y: Optional[float] = None,
    yaw: float = 0.0,
    max_distance_m: Optional[float] = None,
) -> Dict[str, Any]:
    target: Dict[str, Any] = {
        "capability": "confirm_target",
        "action": action,
        "operator_confirmed_mapping": operator_confirmed,
        "object_queries": [str(item).strip() for item in object_queries if str(item).strip()],
        "description": description,
    }
    if action == "move_base_goal":
        target.update({
            "frame_id": frame_id,
            "yaw": float(yaw),
        })
        if x is not None:
            target["x"] = float(x)
        if y is not None:
            target["y"] = float(y)
        if max_distance_m is not None:
            target["max_distance_m"] = float(max_distance_m)
    return {
        "schema": "UnitUgvTargetMap.v1",
        "platform_id": platform_id,
        "targets": {
            target_id: target,
        },
    }


def write_unit_ugv_target_map_template(
    path: Path,
    *,
    platform_id: str,
    target_id: str,
    object_queries: List[str],
    action: str = "manual_confirm",
    operator_confirmed: bool = False,
    description: str = "TODO: replace with a local operator-confirmed UGV target",
    frame_id: str = "map",
    x: Optional[float] = None,
    y: Optional[float] = None,
    yaw: float = 0.0,
    max_distance_m: Optional[float] = None,
) -> Dict[str, Any]:
    template = build_unit_ugv_target_map_template(
        platform_id=platform_id,
        target_id=target_id,
        object_queries=object_queries,
        action=action,
        operator_confirmed=operator_confirmed,
        description=description,
        frame_id=frame_id,
        x=x,
        y=y,
        yaw=yaw,
        max_distance_m=max_distance_m,
    )
    expanded_path = path.expanduser()
    expanded_path.parent.mkdir(parents=True, exist_ok=True)
    expanded_path.write_text(json.dumps(template, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "schema": UNIT_UGV_TARGET_MAP_TEMPLATE_WRITE_REPORT_SCHEMA,
        "ok": True,
        "target_map_path": str(expanded_path),
        "platform_id": platform_id,
        "target_id": target_id,
        "operator_confirmed_mapping": operator_confirmed,
        "object_queries": [str(item).strip() for item in object_queries if str(item).strip()],
    }


def _target_validation_errors(
    target: UnitUgvTarget,
    *,
    require_operator_confirmed: bool,
    require_object_queries: bool,
    max_move_base_distance_m: Optional[float],
) -> List[str]:
    errors: List[str] = []
    if target.capability != "confirm_target":
        errors.append(f"target {target.target_id} capability must be confirm_target")
    if require_operator_confirmed and not target.operator_confirmed_mapping:
        errors.append(f"target {target.target_id} operator_confirmed_mapping must be true")
    if require_object_queries and not (target.object_queries or []):
        errors.append(f"target {target.target_id} requires at least one object_queries alias")
    if target.action == "manual_confirm":
        return errors
    if target.action != "move_base_goal":
        errors.append(f"target {target.target_id} action must be manual_confirm or move_base_goal")
        return errors
    if not target.frame_id:
        errors.append(f"target {target.target_id} move_base_goal requires frame_id")
    if target.x is None or target.y is None:
        errors.append(f"target {target.target_id} move_base_goal requires x and y")
    if target.max_distance_m is None or target.max_distance_m <= 0:
        errors.append(f"target {target.target_id} move_base_goal requires positive max_distance_m")
    elif max_move_base_distance_m is not None and target.max_distance_m > max_move_base_distance_m:
        errors.append(
            f"target {target.target_id} max_distance_m {target.max_distance_m} "
            f"exceeds site limit {max_move_base_distance_m}"
        )
    return errors


def _normalize_object_query(value: str) -> str:
    return " ".join(value.strip().casefold().split())
