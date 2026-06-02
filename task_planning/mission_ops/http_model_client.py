from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Union

from task_planning.config import EnvironmentProfile
from task_planning.contracts import FailureReport, TaskSchema
from task_planning.mission_ops.model_client import NeedsClarification, ReplanAdvice


@dataclass(frozen=True)
class OpenAICompatibleModelClient:
    base_url: str
    model: str
    timeout_s: int = 60

    @classmethod
    def from_profile(cls, profile: EnvironmentProfile) -> "OpenAICompatibleModelClient":
        return cls(base_url=profile.model_base_url, model=profile.model_name)

    def compile_task_schema(
        self,
        intent: str,
        context_snapshot: Mapping[str, Any],
    ) -> Union[TaskSchema, NeedsClarification]:
        mission_id = str(context_snapshot.get("mission_id", "mission_001"))
        content = self._chat_json([
            {
                "role": "system",
                "content": (
                    "Return strict JSON only, with no markdown. Compile the operator intent into exactly one "
                    "TaskSchema.v1 object for a central planner. Do not return empty required fields. "
                    "Use the context_snapshot.mission_id as mission_request.mission_id. "
                    "If the intent names A 区 or area A, use areas=[\"area_A\"]; if it names B 区 or area B, "
                    "use areas=[\"area_B\"]; otherwise choose one non-empty area id. "
                    "Use targets=[\"target_01\"] unless the intent names a more specific target. "
                    "Use mission_type=\"scout_and_confirm\". "
                    "Use required_capabilities=[\"inspect_area\",\"confirm_target\",\"relay_or_overwatch\"]. "
                    "Allowed capabilities are inspect_area, move_to_region, confirm_target, relay_or_overwatch, "
                    "hold_position, return_home, land_or_stop. "
                    "The only valid shape is: {\"schema\":\"TaskSchema.v1\",\"intent\":string,"
                    "\"context_snapshot\":object,\"mission_request\":{\"schema\":\"MissionRequest.v1\","
                    "\"mission_id\":string,\"mission_type\":\"scout_and_confirm\",\"areas\":[string],"
                    "\"targets\":[string],\"required_capabilities\":[string],\"constraints\":object}}. "
                    "Example mission_request for A 区 confirmation: "
                    "{\"schema\":\"MissionRequest.v1\",\"mission_id\":\"mission_001\","
                    "\"mission_type\":\"scout_and_confirm\",\"areas\":[\"area_A\"],"
                    "\"targets\":[\"target_01\"],"
                    "\"required_capabilities\":[\"inspect_area\",\"confirm_target\",\"relay_or_overwatch\"],"
                    "\"constraints\":{\"require_operator_before_motion\":false,\"max_mission_duration_s\":600}}."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "intent": intent,
                    "context_snapshot": dict(context_snapshot),
                    "required_mission_id": mission_id,
                    "phase_1_safety_rules": [
                        "No raw ROS topics or shell commands.",
                        "No platform-local mission replanning.",
                        "The model only emits a high-level task schema for the central planner.",
                    ],
                }, ensure_ascii=False),
            },
        ])
        if "question" in content:
            return NeedsClarification(question=str(content["question"]), reason=str(content.get("reason", "")))
        if "mission_request" not in content:
            content = {
                "schema": "TaskSchema.v1",
                "intent": intent,
                "context_snapshot": dict(context_snapshot),
                "mission_request": content,
            }
        return TaskSchema.from_dict(content)

    def triage_failure(
        self,
        failure_report: FailureReport,
        blackboard_snapshot: Mapping[str, Any],
    ) -> ReplanAdvice:
        content = self._chat_json([
            {
                "role": "system",
                "content": (
                    "Return strict JSON only. Triage the FailureReport for a central planner. "
                    "Use fields: mode, reason, recommended_actions. Never emit ROS topics or shell commands."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "failure_report": failure_report.as_dict(),
                    "blackboard_snapshot": dict(blackboard_snapshot),
                }, ensure_ascii=False),
            },
        ])
        return ReplanAdvice(
            mode=str(content.get("mode", "central_replan")),
            reason=str(content.get("reason", failure_report.failure_type)),
            recommended_actions=list(content.get("recommended_actions") or []),
        )

    def explain_validator_error(
        self,
        error: str,
        schema: Mapping[str, Any],
        context_snapshot: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return self._chat_json([
            {
                "role": "system",
                "content": "Return strict JSON only. Explain the validator error without changing executable commands.",
            },
            {
                "role": "user",
                "content": json.dumps({
                    "error": error,
                    "schema": dict(schema),
                    "context_snapshot": dict(context_snapshot),
                }, ensure_ascii=False),
            },
        ])

    def _chat_json(self, messages: Any) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._chat_completions_url(),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("model response JSON must be an object")
        return parsed

    def _chat_completions_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"
