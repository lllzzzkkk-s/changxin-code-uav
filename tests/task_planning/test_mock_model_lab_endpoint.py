import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path

from task_planning.migration import build_distributed_fleet_goal_evidence, evaluate_model_lab_case
from task_planning.mission_ops.mock_openai_endpoint import make_mock_openai_handler
from tools.check_model_lab_endpoint import check_model_lab_endpoint


class MockModelLabEndpointTest(unittest.TestCase):
    def test_mock_endpoint_exercises_openai_compatible_model_lab_without_home_5090_proof(self):
        server = HTTPServer(("127.0.0.1", 0), make_mock_openai_handler())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile_path = _write_mock_endpoint_profile(Path(tmp), server.server_address[1])

                endpoint_check = check_model_lab_endpoint(profile_path, intent="搜索 A 区并派无人车确认目标")
                evaluation = evaluate_model_lab_case(
                    profile_path=profile_path,
                    case_id="uav_ugv_coordination",
                    output_dir=Path(tmp) / "model-lab",
                )
                goal = build_distributed_fleet_goal_evidence(
                    repo_root=Path(__file__).resolve().parents[2],
                    model_lab_evaluations=[Path(evaluation.output_dir) / "model_lab_evaluation.json"],
                )

            self.assertTrue(endpoint_check["ok"], endpoint_check)
            self.assertEqual("mock_endpoint", endpoint_check["model_lab_evidence_kind"])
            self.assertTrue(evaluation.ok, evaluation.as_dict())
            self.assertEqual("mock_endpoint", evaluation.model_lab_evidence_kind)
            item = {item.name: item for item in goal.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def test_mock_endpoint_can_force_needs_clarification_for_negative_probe(self):
        server = HTTPServer(("127.0.0.1", 0), make_mock_openai_handler(schema_mode="needs_clarification"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile_path = _write_mock_endpoint_profile(Path(tmp), server.server_address[1])
                result = check_model_lab_endpoint(profile_path, intent="搜索 A 区")

            self.assertFalse(result["ok"])
            self.assertIn("model returned NeedsClarification", result["validation_errors"])
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()


def _write_mock_endpoint_profile(root: Path, port: int) -> Path:
    profile_path = root / "home_model_lab_mock_endpoint.env"
    profile_path.write_text("\n".join([
        "MISSION_PROFILE=home_model_lab",
        "MODEL_PROVIDER=local_http",
        f"MODEL_BASE_URL=http://127.0.0.1:{port}/v1",
        "MODEL_NAME=mock-openai-model-lab",
        "MODEL_LAB_EVIDENCE_KIND=mock_endpoint",
        "PLANNER_BACKEND=mock",
        "PLATFORM_BACKEND=mock",
        "MISSION_STATE_STORE=json",
        f"MISSION_ARTIFACT_ROOT={root / 'runs'}",
        "HARDWARE_APPROVAL_REQUIRED=false",
    ]), encoding="utf-8")
    return profile_path


if __name__ == "__main__":
    unittest.main()
