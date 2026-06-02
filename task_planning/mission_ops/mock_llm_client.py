from __future__ import annotations

from typing import Any, Dict, Mapping

from task_planning.contracts import FailureReport, TaskSchema
from task_planning.mission_ops.model_client import NeedsClarification, ReplanAdvice


class MockLLMClient:
    """Deterministic model client for command-driven phase-1 mission ops."""

    def compile_task_schema(self, intent: str, context_snapshot: Mapping[str, Any]) -> TaskSchema:
        if not intent.strip():
            raise ValueError("intent is required")
        area_id = "area_B" if "B" in intent or "b" in intent else "area_A"
        target_id = "target_01"
        mission_id = str(context_snapshot.get("mission_id", "mission_001"))
        return TaskSchema.from_intent(
            mission_id=mission_id,
            intent=intent,
            area_id=area_id,
            target_id=target_id,
            context_snapshot=dict(context_snapshot),
        )

    def triage_failure(self, failure_report: FailureReport, blackboard_snapshot: Mapping[str, Any]) -> ReplanAdvice:
        if failure_report.recoverable:
            actions = list(failure_report.recommended_actions or ["request_replan"])
            return ReplanAdvice(
                mode="central_replan",
                reason=failure_report.failure_type,
                recommended_actions=actions,
            )
        return ReplanAdvice(
            mode="operator_intervention",
            reason=failure_report.failure_type,
            recommended_actions=["hold_platform", "wait_for_operator"],
        )

    def explain_validator_error(
        self,
        error: str,
        schema: Mapping[str, Any],
        context_snapshot: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return {
            "schema": "Explanation.v1",
            "summary": error,
            "context_keys": sorted(context_snapshot.keys()),
            "artifact_schema": schema.get("schema"),
        }


__all__ = ["MockLLMClient", "NeedsClarification", "ReplanAdvice"]
