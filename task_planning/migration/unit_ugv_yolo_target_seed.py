from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from task_planning.migration.unit_ugv_target_map import write_unit_ugv_target_map_template


UNIT_UGV_YOLO_TARGET_SEED_SCHEMA = "UnitUgvYoloTargetSeed.v1"
OBJECT_DETECTION_SET_SCHEMA = "ObjectDetectionSet.v1"


@dataclass(frozen=True)
class UnitUgvYoloTargetSeedReport:
    ok: bool
    detections_path: str
    target_map_path: str
    platform_id: str
    object_query: str
    detection_schema: str
    selected_label: str
    selected_confidence: Optional[float]
    target_map_template_written: bool
    target_binding_ready: bool
    next_runtime_stage: str
    validation_errors: List[str]
    warnings: List[str]
    yolo_detection_observed: bool = False
    ros_connected: bool = False
    gateway_dry_run_called: bool = False
    dispatch_called: bool = False
    schema: str = UNIT_UGV_YOLO_TARGET_SEED_SCHEMA

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "detections_path": self.detections_path,
            "target_map_path": self.target_map_path,
            "platform_id": self.platform_id,
            "object_query": self.object_query,
            "detection_schema": self.detection_schema,
            "selected_label": self.selected_label,
            "selected_confidence": self.selected_confidence,
            "target_map_template_written": self.target_map_template_written,
            "target_binding_ready": self.target_binding_ready,
            "next_runtime_stage": self.next_runtime_stage,
            "validation_errors": list(self.validation_errors),
            "warnings": list(self.warnings),
            "yolo_detection_observed": self.yolo_detection_observed,
            "ros_connected": self.ros_connected,
            "gateway_dry_run_called": self.gateway_dry_run_called,
            "dispatch_called": self.dispatch_called,
        }


def seed_unit_ugv_target_map_from_yolo_detection(
    *,
    detections_path: Path,
    target_map_path: Path,
    object_query: str,
    platform_id: str = "ugv_0",
    target_id: str = "target_01",
    min_confidence: float = 0.5,
) -> UnitUgvYoloTargetSeedReport:
    expanded_detections_path = detections_path.expanduser()
    expanded_target_map_path = target_map_path.expanduser()
    validation_errors: List[str] = []
    warnings: List[str] = []
    detections = _read_json(expanded_detections_path, validation_errors)
    detection_schema = str(detections.get("schema") or "")
    if detection_schema != OBJECT_DETECTION_SET_SCHEMA:
        validation_errors.append(f"detections schema must be {OBJECT_DETECTION_SET_SCHEMA}")
        return _report(
            detections_path=expanded_detections_path,
            target_map_path=expanded_target_map_path,
            platform_id=platform_id,
            object_query=object_query,
            detection_schema=detection_schema,
            selected=None,
            target_map_template_written=False,
            validation_errors=validation_errors,
            warnings=warnings,
        )
    selected = _select_detection(detections, object_query=object_query, min_confidence=min_confidence)
    if selected is None:
        validation_errors.append(f"no YOLO detection matched object_query above min_confidence: {object_query}")
        return _report(
            detections_path=expanded_detections_path,
            target_map_path=expanded_target_map_path,
            platform_id=platform_id,
            object_query=object_query,
            detection_schema=detection_schema,
            selected=None,
            target_map_template_written=False,
            validation_errors=validation_errors,
            warnings=warnings,
        )

    warnings.append("YOLO detections do not provide a safe navigation target without local target-map confirmation.")
    try:
        write_unit_ugv_target_map_template(
            expanded_target_map_path,
            platform_id=platform_id,
            target_id=target_id,
            object_queries=_object_queries(object_query, selected),
            action="manual_confirm",
            operator_confirmed=False,
            description=(
                "YOLO candidate observed in image space; local operator must confirm "
                "the target-map binding before ROS gateway handoff."
            ),
        )
    except Exception as exc:
        validation_errors.append(
            "YOLO detection observed; failed to write unconfirmed operator target-map template: "
            f"{exc}"
        )
        return _report(
            detections_path=expanded_detections_path,
            target_map_path=expanded_target_map_path,
            platform_id=platform_id,
            object_query=object_query,
            detection_schema=detection_schema,
            selected=selected,
            target_map_template_written=False,
            validation_errors=validation_errors,
            warnings=warnings,
        )
    validation_errors.append("YOLO detection observed but target map remains operator-unconfirmed")
    return _report(
        detections_path=expanded_detections_path,
        target_map_path=expanded_target_map_path,
        platform_id=platform_id,
        object_query=object_query,
        detection_schema=detection_schema,
        selected=selected,
        target_map_template_written=True,
        validation_errors=validation_errors,
        warnings=warnings,
    )


def write_report(path: Path, report: UnitUgvYoloTargetSeedReport) -> Path:
    expanded = path.expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    expanded.write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return expanded


def _read_json(path: Path, errors: List[str]) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"detections parse failed: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append("detections must be a JSON object")
        return {}
    return data


def _select_detection(
    detections: Mapping[str, Any],
    *,
    object_query: str,
    min_confidence: float,
) -> Optional[Mapping[str, Any]]:
    normalized_query = _normalize(object_query)
    candidates: List[Mapping[str, Any]] = []
    raw = detections.get("detections") or []
    if not isinstance(raw, list):
        return None
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("label") or "").strip()
        confidence = _optional_float(item.get("confidence"))
        if _normalize(label) != normalized_query:
            continue
        if confidence is None or confidence < min_confidence:
            continue
        candidates.append(item)
    if not candidates:
        return None
    return max(candidates, key=lambda item: float(item.get("confidence") or 0.0))


def _object_queries(object_query: str, selected: Mapping[str, Any]) -> List[str]:
    result = []
    for value in (object_query, str(selected.get("label") or "")):
        value = value.strip()
        if value and value not in result:
            result.append(value)
    return result


def _report(
    *,
    detections_path: Path,
    target_map_path: Path,
    platform_id: str,
    object_query: str,
    detection_schema: str,
    selected: Optional[Mapping[str, Any]],
    target_map_template_written: bool,
    validation_errors: List[str],
    warnings: List[str],
) -> UnitUgvYoloTargetSeedReport:
    return UnitUgvYoloTargetSeedReport(
        ok=False,
        detections_path=str(detections_path),
        target_map_path=str(target_map_path),
        platform_id=platform_id,
        object_query=object_query,
        detection_schema=detection_schema,
        selected_label=str((selected or {}).get("label") or ""),
        selected_confidence=_optional_float((selected or {}).get("confidence")),
        target_map_template_written=target_map_template_written,
        target_binding_ready=False,
        next_runtime_stage="local_operator_confirm_target_map",
        validation_errors=_dedupe(validation_errors),
        warnings=_dedupe(warnings),
        yolo_detection_observed=selected is not None,
    )


def _normalize(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
