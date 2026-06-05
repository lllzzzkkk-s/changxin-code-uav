from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from task_planning.contracts import TaskCommand
from task_planning.pddl import PddlPlan, PlanStep


ACTION_TO_CAPABILITY = {
    "scan-area": "inspect_area",
    "confirm-target": "confirm_target",
    "identify-target": "confirm_target",
    "approach-target": "confirm_target",
    "relay-or-overwatch": "relay_or_overwatch",
}


@dataclass(frozen=True)
class BehaviorTreeArtifact:
    mission_id: str
    root: Dict[str, Any]
    task_commands: List[TaskCommand]
    schema: str = "BehaviorTree.v1"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "mission_id": self.mission_id,
            "root": self.root,
            "task_commands": [command.as_dict() for command in self.task_commands],
        }


def compile_plan_to_bt(plan: PddlPlan, *, mission_id: str) -> BehaviorTreeArtifact:
    commands = []
    children = []
    for step in plan.steps:
        command = _command_for_step(step, mission_id=mission_id, metadata=dict(plan.metadata or {}))
        commands.append(command)
        children.append({
            "type": "Sequence",
            "name": f"{step.action}_{step.index}",
            "children": [
                {"type": "CheckPlatformOnline", "platform_id": command.platform_id},
                {"type": "CheckCapability", "platform_id": command.platform_id, "capability": command.capability},
                {"type": "DispatchTaskCommand", "task_id": command.task_id},
                {"type": "WaitAck", "platform_id": command.platform_id, "task_id": command.task_id},
                {"type": "MonitorProgress", "platform_id": command.platform_id, "task_id": command.task_id},
                {"type": "OnFailure", "children": [
                    {"type": "ReportFailureToBlackboard"},
                    {"type": "RequestReplan"},
                ]},
            ],
        })
    return BehaviorTreeArtifact(
        mission_id=mission_id,
        root={"type": "Sequence", "name": "mission_root", "children": children},
        task_commands=commands,
    )


def _command_for_step(step: PlanStep, *, mission_id: str, metadata: Optional[Dict[str, Any]] = None) -> TaskCommand:
    task_id = f"task_{step.index:03d}"
    object_query = str((metadata or {}).get("object_query") or "nearby_object")
    if step.action == "scan-area":
        return TaskCommand(
            mission_id=mission_id,
            task_id=task_id,
            platform_id=step.arguments[0],
            capability=ACTION_TO_CAPABILITY[step.action],
            parameters={"area_id": step.arguments[1], "max_duration_s": 120},
        )
    if step.action == "confirm-target":
        return TaskCommand(
            mission_id=mission_id,
            task_id=task_id,
            platform_id=step.arguments[0],
            capability=ACTION_TO_CAPABILITY[step.action],
            parameters={"target_id": step.arguments[1]},
        )
    if step.action == "identify-target":
        return TaskCommand(
            mission_id=mission_id,
            task_id=task_id,
            platform_id=step.arguments[0],
            capability=ACTION_TO_CAPABILITY[step.action],
            parameters={
                "target_id": step.arguments[1],
                "stage": "identify_target",
                "object_query": object_query,
            },
            requires_operator_confirm=False,
        )
    if step.action == "approach-target":
        return TaskCommand(
            mission_id=mission_id,
            task_id=task_id,
            platform_id=step.arguments[0],
            capability=ACTION_TO_CAPABILITY[step.action],
            parameters={
                "target_id": step.arguments[1],
                "stage": "approach_target",
                "object_query": object_query,
                "approach_policy": "bounded_move_base_or_manual_confirm",
            },
            requires_operator_confirm=True,
        )
    if step.action == "relay-or-overwatch":
        return TaskCommand(
            mission_id=mission_id,
            task_id=task_id,
            platform_id=step.arguments[0],
            capability=ACTION_TO_CAPABILITY[step.action],
            parameters={"target_id": step.arguments[1]},
        )
    raise ValueError(f"unsupported plan action: {step.action}")
