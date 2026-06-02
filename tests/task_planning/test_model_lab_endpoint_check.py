import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from task_planning.contracts import TaskSchema
from tools.check_model_lab_endpoint import check_model_lab_endpoint


class _ModelHandler(BaseHTTPRequestHandler):
    seen_payload = None

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
        type(self).seen_payload = payload
        task_schema = TaskSchema.from_intent(
            mission_id="model_lab_smoke",
            intent="搜索 A 区并派无人车确认目标",
            area_id="area_A",
            target_id="target_01",
        )
        response = {
            "choices": [{
                "message": {
                    "content": json.dumps(task_schema.as_dict(), ensure_ascii=False),
                },
            }],
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class ModelLabEndpointCheckTest(unittest.TestCase):
    def test_home_model_lab_endpoint_check_validates_task_schema_without_gateway(self):
        server = HTTPServer(("127.0.0.1", 0), _ModelHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile_path = Path(tmp) / "home_model_lab.env"
                profile_path.write_text("\n".join([
                    "MISSION_PROFILE=home_model_lab",
                    "MODEL_PROVIDER=local_http",
                    f"MODEL_BASE_URL=http://127.0.0.1:{server.server_address[1]}/v1",
                    "MODEL_NAME=fake-qwen",
                    "PLANNER_BACKEND=mock",
                    "PLATFORM_BACKEND=mock",
                    "MISSION_STATE_STORE=json",
                    f"MISSION_ARTIFACT_ROOT={Path(tmp) / 'runs'}",
                    "HARDWARE_APPROVAL_REQUIRED=false",
                ]), encoding="utf-8")

                result = check_model_lab_endpoint(profile_path, intent="搜索 A 区并派无人车确认目标")

            self.assertTrue(result["ok"])
            self.assertEqual("home_model_lab", result["mission_profile"])
            self.assertEqual("mock", result["platform_backend"])
            self.assertEqual("TaskSchema.v1", result["task_schema"]["schema"])
            payload = _ModelHandler.seen_payload
            self.assertIsNotNone(payload)
            system_prompt = payload["messages"][0]["content"]
            user_payload = json.loads(payload["messages"][1]["content"])
            self.assertIn("Do not return empty required fields", system_prompt)
            self.assertIn("areas=[\"area_A\"]", system_prompt)
            self.assertIn("target_01", system_prompt)
            self.assertEqual("model_lab_smoke", user_payload["required_mission_id"])
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def test_model_lab_endpoint_check_rejects_non_model_lab_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "dev_mock.env"
            profile_path.write_text("\n".join([
                "MISSION_PROFILE=dev_mock",
                "MODEL_PROVIDER=mock",
                "PLANNER_BACKEND=mock",
                "PLATFORM_BACKEND=mock",
                "MISSION_STATE_STORE=json",
                f"MISSION_ARTIFACT_ROOT={Path(tmp) / 'runs'}",
            ]), encoding="utf-8")

            result = check_model_lab_endpoint(profile_path, intent="搜索 A 区")

        self.assertFalse(result["ok"])
        self.assertIn("model lab check requires MISSION_PROFILE=home_model_lab", result["validation_errors"])


if __name__ == "__main__":
    unittest.main()
