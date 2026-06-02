from __future__ import annotations

from typing import Any, Dict, List, Mapping

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.contracts import (
    CapabilityRegistry,
    CommandAck,
    FailureReport,
    MissionBlackboard,
    TaskSchema,
    validate_failure_report,
    validate_mission_request,
)
from task_planning.execution import BehaviorTreeArtifact, compile_plan_to_bt
from task_planning.mission_ops.model_client import ModelClient, ReplanAdvice
from task_planning.pddl import PddlPlan, PddlProblem, generate_problem, mock_plan
from task_planning.validation import validate_pddl_problem, validate_plan


def compile_task_schema_tool(
    model_client: ModelClient,
    intent: str,
    context_snapshot: Mapping[str, Any],
) -> TaskSchema:
    result = model_client.compile_task_schema(intent, context_snapshot)
    if not isinstance(result, TaskSchema):
        raise ValueError(result.question)
    return result


def validate_task_schema_tool(task_schema: TaskSchema, registry: CapabilityRegistry) -> List[str]:
    return validate_mission_request(task_schema.mission_request, registry)


def update_blackboard_tool(task_schema: TaskSchema, registry: CapabilityRegistry) -> MissionBlackboard:
    return MissionBlackboard.from_request(task_schema.mission_request, registry)


def generate_pddl_problem_tool(task_schema: TaskSchema) -> PddlProblem:
    return generate_problem(task_schema.mission_request)


def validate_pddl_problem_tool(problem: PddlProblem) -> List[str]:
    return validate_pddl_problem(problem)


def run_pddl_planner_tool(problem: PddlProblem) -> PddlPlan:
    return mock_plan(problem)


def validate_plan_tool(plan: PddlPlan, registry: CapabilityRegistry) -> List[str]:
    return validate_plan(plan, registry)


def compile_plan_to_bt_tool(plan: PddlPlan, mission_id: str) -> BehaviorTreeArtifact:
    return compile_plan_to_bt(plan, mission_id=mission_id)


def dry_run_gateway_tool(gateway: MockPlatformGateway, behavior_tree: BehaviorTreeArtifact) -> List[CommandAck]:
    return [gateway.dispatch(command) for command in behavior_tree.task_commands]


def triage_failure_tool(
    model_client: ModelClient,
    failure_report: FailureReport,
    blackboard_snapshot: Mapping[str, Any],
) -> ReplanAdvice:
    errors = validate_failure_report(failure_report)
    if errors:
        raise ValueError("; ".join(errors))
    return model_client.triage_failure(failure_report, blackboard_snapshot)


def request_replan_tool(advice: ReplanAdvice, failure_report: FailureReport) -> Dict[str, Any]:
    return {
        "schema": "ReplanRequest.v1",
        "mode": advice.mode,
        "reason": advice.reason,
        "mission_id": failure_report.mission_id,
        "task_id": failure_report.task_id,
        "platform_id": failure_report.platform_id,
        "recommended_actions": list(advice.recommended_actions),
    }
