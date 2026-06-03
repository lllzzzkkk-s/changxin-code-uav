from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Union

from task_planning.mission_ops.replay import load_artifact_bundle
from task_planning.mission_ops.run_ledger import utc_timestamp


RAW_MOTION_TOKENS = ("/cmd_vel", "/move_base", "/mavros/", "/setpoints_cmd")


@dataclass(frozen=True)
class Phase2NoMotionAcceptanceReport:
    phase1_baseline: Dict[str, Any]
    phase2_run: Dict[str, Any]
    artifact_health: Dict[str, Any]
    runtime_summary: Dict[str, Any]
    approval_summary: Dict[str, Any]
    no_motion_boundary: Dict[str, Any]
    operator_view: Dict[str, Any]
    validation_errors: List[str]
    generated_at: str = field(default_factory=utc_timestamp)
    schema: str = "Phase2NoMotionAcceptanceReport.v1"

    @property
    def ok(self) -> bool:
        return not self.validation_errors

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["ok"] = self.ok
        return data


def build_phase2_no_motion_acceptance_report(
    *,
    artifact_roots: Sequence[Union[str, Path]],
    phase1_archive_path: str,
    phase1_archive_sha256: str,
) -> Phase2NoMotionAcceptanceReport:
    roots = [Path(root) for root in artifact_roots]
    loaded = [load_artifact_bundle(root) for root in roots]
    validation_errors: List[str] = []
    validation_errors.extend(_artifact_validation_errors(loaded))
    validation_errors.extend(_raw_motion_token_errors(loaded))

    platform_backends = _unique_values(
        _path_value(bundle.data, ["environment_profile.json", "platform_backend"], "")
        for bundle in loaded
    )
    mission_profiles = _unique_values(
        _path_value(bundle.data, ["environment_profile.json", "mission_profile"], "")
        for bundle in loaded
    )
    event_counts = Counter()
    accepted_commands = 0
    rejected_commands = 0
    progress_count = 0
    approval_required = False
    approval_sources: List[str] = []
    current_states: List[str] = []

    for bundle in loaded:
        data = bundle.data
        events = _items(data, "execution_events.json")
        event_counts.update(
            str(event.get("event_type"))
            for event in events
            if isinstance(event, Mapping) and event.get("event_type")
        )
        acks = _items(data, "command_acks.json")
        accepted_commands += len([ack for ack in acks if isinstance(ack, Mapping) and ack.get("accepted") is True])
        rejected_commands += len([ack for ack in acks if isinstance(ack, Mapping) and ack.get("accepted") is False])
        progress_count += len(_items(data, "task_progress.json"))
        current_state = str(_path_value(data, ["validation_report.json", "current_state"], ""))
        if current_state:
            current_states.append(current_state)
        if "operator_approval_required" in {
            str(event.get("event_type"))
            for event in events
            if isinstance(event, Mapping)
        }:
            approval_required = True
        for event in events:
            if not isinstance(event, Mapping) or event.get("event_type") != "operator_approval_recorded":
                continue
            source = _path_value(event, ["payload", "source"], "")
            if source:
                approval_sources.append(str(source))

    platform_backend = _single_or_mixed(platform_backends)
    report = Phase2NoMotionAcceptanceReport(
        phase1_baseline={
            "archive_path": phase1_archive_path,
            "sha256": phase1_archive_sha256,
            "verified_by_this_report": False,
        },
        phase2_run={
            "artifact_roots": [str(root) for root in roots],
            "artifact_count": len(roots),
            "mission_profiles": mission_profiles,
            "current_states": current_states,
        },
        artifact_health={
            "ok": not validation_errors,
            "artifact_roots": [bundle.as_dict() for bundle in loaded],
        },
        runtime_summary={
            "event_counts": dict(sorted(event_counts.items())),
            "accepted_commands": accepted_commands,
            "rejected_commands": rejected_commands,
            "progress_count": progress_count,
        },
        approval_summary={
            "required": approval_required,
            "source": _single_or_mixed(approval_sources),
            "event_count": event_counts.get("operator_approval_required", 0),
        },
        no_motion_boundary={
            "platform_backend": platform_backend,
            "ros_connected": False,
            "dispatch_performed": False,
            "hardware_proof": False,
            "controlled_motion_authorized": False,
            "raw_motion_tokens": list(RAW_MOTION_TOKENS),
        },
        operator_view={
            "status": "ready" if not validation_errors else "needs_review",
            "display_fields": [
                "phase1_baseline",
                "phase2_run",
                "runtime_summary",
                "approval_summary",
                "no_motion_boundary",
                "validation_errors",
            ],
            "forbidden_controls": list(RAW_MOTION_TOKENS),
        },
        validation_errors=validation_errors,
    )
    return report


def render_phase2_no_motion_acceptance_markdown(report: Phase2NoMotionAcceptanceReport) -> str:
    data = report.as_dict()
    validation_errors = data["validation_errors"] or ["none"]
    return "\n".join([
        "# Phase 2 No-Motion Acceptance",
        "",
        f"- ok: `{str(data['ok']).lower()}`",
        f"- generated_at: `{data['generated_at']}`",
        "",
        "## Phase 1 Baseline",
        f"- archive: `{data['phase1_baseline'].get('archive_path', '')}`",
        f"- sha256: `{data['phase1_baseline'].get('sha256', '')}`",
        "- verified_by_this_report: `false`",
        "",
        "## Phase 2 Run",
        f"- artifact_roots: `{data['phase2_run'].get('artifact_roots', [])}`",
        f"- current_states: `{data['phase2_run'].get('current_states', [])}`",
        "",
        "## No-Motion Boundary",
        f"- platform_backend: `{data['no_motion_boundary'].get('platform_backend')}`",
        f"- ros_connected: `{data['no_motion_boundary'].get('ros_connected')}`",
        f"- dispatch_performed: `{data['no_motion_boundary'].get('dispatch_performed')}`",
        f"- hardware_proof: `{data['no_motion_boundary'].get('hardware_proof')}`",
        f"- controlled_motion_authorized: `{data['no_motion_boundary'].get('controlled_motion_authorized')}`",
        "",
        "## Execution Events",
        f"- event_counts: `{data['runtime_summary'].get('event_counts', {})}`",
        f"- accepted_commands: `{data['runtime_summary'].get('accepted_commands')}`",
        f"- rejected_commands: `{data['runtime_summary'].get('rejected_commands')}`",
        f"- progress_count: `{data['runtime_summary'].get('progress_count')}`",
        "",
        "## Approval",
        f"- approval_required: `{data['approval_summary'].get('required')}`",
        f"- approval_source: `{data['approval_summary'].get('source', '')}`",
        "",
        "## Not Hardware Proof",
        "This report is no-hardware acceptance evidence only. It does not verify the unit archive, connect ROS, run gateway dry_run, dispatch, or authorize controlled motion.",
        "",
        "## Validation Errors",
        *[f"- `{error}`" for error in validation_errors],
    ])


def _artifact_validation_errors(loaded: Sequence[Any]) -> List[str]:
    errors: List[str] = []
    for bundle in loaded:
        for error in bundle.validation_errors:
            errors.append(f"{bundle.root}: {error}")
    return errors


def _raw_motion_token_errors(loaded: Sequence[Any]) -> List[str]:
    errors: List[str] = []
    for bundle in loaded:
        for filename, document in bundle.data.items():
            if not filename.endswith(".json"):
                continue
            for token, location in _find_raw_motion_tokens(document):
                errors.append(f"{bundle.root}/{filename}: raw motion command token {token} at {location}")
    return errors


def _find_raw_motion_tokens(value: Any, *, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        for token in RAW_MOTION_TOKENS:
            if token in value:
                yield token, path
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _find_raw_motion_tokens(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _find_raw_motion_tokens(item, path=f"{path}[{index}]")


def _items(data: Mapping[str, Any], filename: str) -> List[Mapping[str, Any]]:
    value = _path_value(data, [filename, "items"], [])
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _path_value(data: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _unique_values(values: Iterable[Any]) -> List[str]:
    return sorted({str(value) for value in values if str(value).strip()})


def _single_or_mixed(values: Sequence[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return "mixed"


def write_phase2_no_motion_acceptance_outputs(
    report: Phase2NoMotionAcceptanceReport,
    *,
    output_dir: Union[str, Path],
) -> Dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "phase2_no_motion_acceptance.json"
    markdown_path = root / "phase2_no_motion_acceptance.md"
    json_path.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_phase2_no_motion_acceptance_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}
