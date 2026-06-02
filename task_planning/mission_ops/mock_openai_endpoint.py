from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Mapping

from task_planning.contracts import TaskSchema


MOCK_MODEL_NAME = "mock-openai-model-lab"


def make_mock_openai_handler(
    *,
    model_name: str = MOCK_MODEL_NAME,
    schema_mode: str = "baseline",
):
    if schema_mode not in {"baseline", "alternate_target", "needs_clarification"}:
        raise ValueError(f"unsupported schema_mode: {schema_mode}")

    class MockOpenAIHandler(BaseHTTPRequestHandler):
        server_version = "MockOpenAIModelLab/1.0"

        def do_GET(self):
            if self.path.rstrip("/") == "/v1/models":
                _send_json(self, {
                    "object": "list",
                    "data": [{"id": model_name, "object": "model"}],
                })
                return
            _send_json(self, {"error": "not found"}, status=404)

        def do_POST(self):
            if self.path.rstrip("/") not in {"/v1/chat/completions", "/chat/completions"}:
                _send_json(self, {"error": "not found"}, status=404)
                return
            request = _read_json_request(self)
            messages = request.get("messages") if isinstance(request, Mapping) else []
            content = _response_content(messages, schema_mode=schema_mode)
            _send_json(self, {
                "id": "chatcmpl-mock-model-lab",
                "object": "chat.completion",
                "model": model_name,
                "choices": [{
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(content, ensure_ascii=False),
                    },
                }],
            })

        def log_message(self, format, *args):
            return

    return MockOpenAIHandler


def _response_content(messages: Any, *, schema_mode: str) -> Dict[str, Any]:
    system_text = _joined_content(messages, role="system").lower()
    if "triage" in system_text:
        return {
            "mode": "central_replan",
            "reason": "mock_model_lab_failure_triage",
            "recommended_actions": ["record_failure_report", "request_central_replan"],
        }
    if "explain" in system_text:
        return {
            "summary": "mock model-lab validator explanation",
            "operator_action": "inspect schema fields and rerun validation",
        }
    if schema_mode == "needs_clarification":
        return {
            "question": "Please specify the target area before mission compilation.",
            "reason": "mock endpoint configured for clarification mode",
        }

    payload = _last_user_payload(messages)
    context = dict(payload.get("context_snapshot") or {})
    intent = str(payload.get("intent") or "搜索 A 区并派无人车确认目标")
    mission_id = str(context.get("mission_id") or "mock_model_lab_mission")
    target_id = "target_alt" if schema_mode == "alternate_target" else "target_01"
    return TaskSchema.from_intent(
        mission_id=mission_id,
        intent=intent,
        area_id=str(context.get("area_id") or "area_A"),
        target_id=str(context.get("target_id") or target_id),
        context_snapshot=context,
    ).as_dict()


def _joined_content(messages: Any, *, role: str) -> str:
    if not isinstance(messages, list):
        return ""
    return "\n".join(
        str(message.get("content") or "")
        for message in messages
        if isinstance(message, Mapping) and message.get("role") == role
    )


def _last_user_payload(messages: Any) -> Dict[str, Any]:
    if not isinstance(messages, list):
        return {}
    for message in reversed(messages):
        if not isinstance(message, Mapping) or message.get("role") != "user":
            continue
        try:
            payload = json.loads(str(message.get("content") or "{}"))
        except json.JSONDecodeError:
            return {"intent": str(message.get("content") or "")}
        return payload if isinstance(payload, dict) else {}
    return {}


def _read_json_request(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _send_json(handler: BaseHTTPRequestHandler, data: Mapping[str, Any], *, status: int = 200) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
