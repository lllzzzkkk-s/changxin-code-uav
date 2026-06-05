from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping

from task_planning.contracts import CapabilityRegistry, FailureReport, TaskSchema, validate_mission_request
from task_planning.mission_ops.model_client import ReplanAdvice


AgentDraftFn = Callable[[Mapping[str, Any]], Mapping[str, Any]]
RAW_ROS_TOKENS = ("/mavros/", "/cmd_vel", "/setpoints_cmd", "/move_base_simple/goal")


@dataclass(frozen=True)
class AgentTaskSchemaAdapter:
    """Adapter for external agent frameworks that draft TaskSchema only.

    OpenClaw, Hermes, or another agent framework can sit behind `draft_fn`, but
    this adapter keeps the architecture boundary unchanged: the agent returns a
    TaskSchema draft, and the deterministic validator/planner/executor/gateway
    remain responsible for the mission.
    """

    agent_name: str
    draft_fn: AgentDraftFn
    registry: CapabilityRegistry

    def compile_task_schema(self, intent: str, context_snapshot: Mapping[str, Any]) -> TaskSchema:
        draft = self.draft_fn({
            "schema": "AgentTaskSchemaDraftRequest.v1",
            "agent_name": self.agent_name,
            "intent": intent,
            "context_snapshot": dict(context_snapshot),
            "allowed_output_schema": "TaskSchema.v1",
            "forbidden_outputs": list(RAW_ROS_TOKENS),
        })
        if not isinstance(draft, Mapping):
            raise ValueError(f"{self.agent_name} draft must be a JSON object")
        if _contains_raw_ros_reference(draft):
            raise ValueError(f"{self.agent_name} draft raw ROS reference is forbidden")
        task_schema = TaskSchema.from_dict(draft)
        errors = validate_mission_request(task_schema.mission_request, self.registry)
        if errors:
            raise ValueError(f"{self.agent_name} draft failed TaskSchema validation: {'; '.join(errors)}")
        return task_schema

    def triage_failure(
        self,
        failure_report: FailureReport,
        blackboard_snapshot: Mapping[str, Any],
    ) -> ReplanAdvice:
        return ReplanAdvice(
            mode="central_replan" if failure_report.recoverable else "operator_intervention",
            reason=failure_report.failure_type,
            recommended_actions=list(failure_report.recommended_actions or ["request_replan"]),
        )

    def explain_validator_error(
        self,
        error: str,
        schema: Mapping[str, Any],
        context_snapshot: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return {
            "schema": "Explanation.v1",
            "agent_name": self.agent_name,
            "summary": error,
            "artifact_schema": schema.get("schema"),
            "context_keys": sorted(context_snapshot.keys()),
        }


def _contains_raw_ros_reference(value: Any) -> bool:
    if isinstance(value, str):
        return any(token in value for token in RAW_ROS_TOKENS)
    if isinstance(value, Mapping):
        return any(_contains_raw_ros_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_raw_ros_reference(item) for item in value)
    return False
