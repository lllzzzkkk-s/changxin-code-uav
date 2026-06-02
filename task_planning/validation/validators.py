from __future__ import annotations

from typing import List

from task_planning.contracts import CapabilityRegistry
from task_planning.pddl import PddlPlan, PddlProblem


ALLOWED_PLAN_ACTIONS = {
    "scan-area": {"platform_type": "uav", "capability": "inspect_area"},
    "confirm-target": {"platform_type": "ugv", "capability": "confirm_target"},
    "relay-or-overwatch": {"platform_type": "uav", "capability": "relay_or_overwatch"},
}


def validate_pddl_problem(problem: PddlProblem) -> List[str]:
    errors = []
    if problem.schema != "PddlProblem.v1":
        errors.append("schema must be PddlProblem.v1")
    for object_type in ("uav", "ugv", "area", "target"):
        if not problem.objects.get(object_type):
            errors.append(f"missing PDDL object type: {object_type}")
    if not problem.goals:
        errors.append("PDDL problem must include at least one goal")
    if "/mavros/" in problem.pddl or "/cmd_vel" in problem.pddl or "/setpoints_cmd" in problem.pddl:
        errors.append("PDDL problem must not contain raw ROS topic references")
    return errors


def validate_plan(plan: PddlPlan, registry: CapabilityRegistry) -> List[str]:
    errors = []
    if plan.schema != "PddlPlan.v1":
        errors.append("schema must be PddlPlan.v1")
    for step in plan.steps:
        action_contract = ALLOWED_PLAN_ACTIONS.get(step.action)
        if action_contract is None:
            errors.append(f"unsupported plan action: {step.action}")
            continue
        platform_id = step.arguments[0] if step.arguments else ""
        platform = registry.platform_by_id(platform_id)
        if platform is None:
            errors.append(f"unknown plan platform: {platform_id}")
            continue
        if platform.platform_type != action_contract["platform_type"]:
            errors.append(f"wrong platform type for {step.action}: {platform_id}")
        if action_contract["capability"] not in platform.capabilities:
            errors.append(f"platform {platform_id} lacks capability {action_contract['capability']}")
    return errors
