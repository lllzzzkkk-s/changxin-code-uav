from __future__ import annotations

import re
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
        object_query = _object_query_from_intent(intent)
        if _is_single_ugv_object_approach(intent, context_snapshot):
            return TaskSchema.from_intent(
                mission_id=mission_id,
                intent=intent,
                area_id=area_id,
                target_id=target_id,
                context_snapshot=dict(context_snapshot),
                required_capabilities=["confirm_target"],
                constraints={
                    "mission_variant": "single_ugv_object_approach",
                    "primary_platform": str(context_snapshot.get("primary_platform", "ugv_0")),
                    "object_query": object_query,
                    "target_source": "local_perception_or_operator_confirmed_map",
                    "approach_policy": "bounded_move_base_or_manual_confirm",
                    "require_operator_before_motion": True,
                },
            )
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


def _is_single_ugv_object_approach(intent: str, context_snapshot: Mapping[str, Any]) -> bool:
    primary_platform = str(context_snapshot.get("primary_platform", ""))
    asks_approach = any(token in intent for token in ("走过去", "靠近", "接近", "approach", "go to"))
    asks_identify = any(token in intent for token in ("识别", "找到", "检测", "find", "identify", "detect"))
    return primary_platform == "ugv_0" and asks_approach and asks_identify


def _object_query_from_intent(intent: str) -> str:
    for pattern in (
        r"(?:识别|找到|检测)\s*(?:附近的?|一个|一台|这个|那个)?\s*([^，,。；;、]+?)\s*[，,。；;、]?\s*(?:然后|并|并且|后)?\s*(?:走过去|靠近|接近)",
        r"(?:approach|go to)\s+(?:a|an|the|nearby)?\s*([a-zA-Z0-9_\- ]+)",
        r"(?:find|identify|detect)\s+(?:a|an|the|nearby)?\s*([a-zA-Z0-9_\- ]+?)\s+(?:and then\s+)?(?:approach|go to)",
    ):
        match = re.search(pattern, intent, flags=re.IGNORECASE)
        if match:
            query = _clean_object_query(match.group(1))
            if query:
                return query
    return "nearby_object"


def _clean_object_query(value: str) -> str:
    query = value.strip(" ，,。；;、")
    for prefix in ("附近的", "附近", "一个", "一台", "这个", "那个", "the ", "a ", "an ", "nearby "):
        if query.lower().startswith(prefix):
            query = query[len(prefix):].strip()
    return query or "nearby_object"
