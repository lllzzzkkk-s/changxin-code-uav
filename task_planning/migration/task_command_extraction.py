from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from task_planning.contracts import CapabilityRegistry, TaskCommand, validate_task_command
from task_planning.mission_ops.replay import load_artifact_bundle


@dataclass(frozen=True)
class ExtractedTaskCommand:
    artifact_root: Path
    command: Optional[TaskCommand]
    selected_index: Optional[int]
    candidate_count: int
    validation_errors: List[str]
    schema: str = "ExtractedTaskCommand.v1"

    @property
    def ok(self) -> bool:
        return self.command is not None and not self.validation_errors

    def as_dict(self) -> Dict[str, Any]:
        command_data = self.command.as_dict() if self.command else None
        return {
            "schema": self.schema,
            "ok": self.ok,
            "artifact_root": str(self.artifact_root),
            "candidate_count": self.candidate_count,
            "selected_index": self.selected_index,
            "task_command": command_data,
            "task_command_json": json.dumps(command_data, ensure_ascii=False, sort_keys=True) if command_data else "",
            "validation_errors": list(self.validation_errors),
        }


def extract_task_command_from_artifact(
    *,
    artifact_root: Path,
    platform_id: Optional[str] = None,
    capability: Optional[str] = None,
    task_id: Optional[str] = None,
    index: int = 0,
) -> ExtractedTaskCommand:
    artifact_root = artifact_root.expanduser().resolve()
    bundle = load_artifact_bundle(artifact_root)
    errors = list(bundle.validation_errors)
    commands = _task_commands(bundle.data)
    filtered = _filter_commands(commands, platform_id=platform_id, capability=capability, task_id=task_id)
    if index < 0:
        errors.append("index must be >= 0")
        selected = None
        selected_index = None
    elif index >= len(filtered):
        errors.append(f"no TaskCommand matched filters at index {index}")
        selected = None
        selected_index = None
    else:
        selected_index, selected = filtered[index]

    command = None
    if selected is not None:
        command = TaskCommand.from_dict(selected)
        errors.extend(validate_task_command(command, CapabilityRegistry.scout_and_confirm_default()))

    return ExtractedTaskCommand(
        artifact_root=artifact_root,
        command=command,
        selected_index=selected_index,
        candidate_count=len(filtered),
        validation_errors=errors,
    )


def _task_commands(bundle_data: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    bt = bundle_data.get("bt_artifact.json") or {}
    if not isinstance(bt, Mapping):
        return []
    commands = bt.get("task_commands") or []
    return [item for item in commands if isinstance(item, Mapping)]


def _filter_commands(
    commands: Sequence[Mapping[str, Any]],
    *,
    platform_id: Optional[str],
    capability: Optional[str],
    task_id: Optional[str],
) -> List[tuple[int, Mapping[str, Any]]]:
    result: List[tuple[int, Mapping[str, Any]]] = []
    for original_index, command in enumerate(commands):
        if platform_id is not None and command.get("platform_id") != platform_id:
            continue
        if capability is not None and command.get("capability") != capability:
            continue
        if task_id is not None and command.get("task_id") != task_id:
            continue
        result.append((original_index, command))
    return result
