import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from task_planning.contracts import TaskSchema
from task_planning.migration.model_lab import evaluate_model_lab_case


class _EquivalentModelHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        task_schema = TaskSchema.from_intent(
            mission_id="golden_uav_ugv_coordination",
            intent="搜索 A 区，发现目标后派无人车接近确认，无人机继续中继或观察",
            area_id="area_A",
            target_id="target_01",
            context_snapshot={"mission_id": "golden_uav_ugv_coordination"},
        )
        _send_model_response(self, task_schema.as_dict())

    def log_message(self, format, *args):
        return


class _DifferentValidModelHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        task_schema = TaskSchema.from_intent(
            mission_id="golden_uav_ugv_coordination",
            intent="搜索 A 区，发现目标后派无人车接近确认，无人机继续中继或观察",
            area_id="area_A",
            target_id="target_alt",
            context_snapshot={"mission_id": "golden_uav_ugv_coordination"},
        )
        _send_model_response(self, task_schema.as_dict())

    def log_message(self, format, *args):
        return


class ModelLabEvaluationTest(unittest.TestCase):
    def test_model_lab_evaluation_writes_portable_artifacts_for_equivalent_schema(self):
        server, thread = _start_server(_EquivalentModelHandler)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile_path = _write_profile(tmp, server.server_address[1])
                evaluation = evaluate_model_lab_case(
                    profile_path=profile_path,
                    case_id="uav_ugv_coordination",
                    output_dir=Path(tmp) / "model-lab",
                    require_baseline_equivalence=True,
                )

                output_dir = Path(evaluation.output_dir)
                self.assertTrue(evaluation.ok, evaluation.as_dict())
                self.assertTrue(evaluation.baseline_equivalent)
                self.assertEqual([], evaluation.diffs)
                self.assertTrue((output_dir / "environment_profile.json").exists())
                self.assertTrue((output_dir / "mission_input.json").exists())
                self.assertTrue((output_dir / "baseline_task_schema.json").exists())
                self.assertTrue((output_dir / "model_task_schema.json").exists())
                report = json.loads((output_dir / "model_lab_evaluation.json").read_text(encoding="utf-8"))
                self.assertEqual("ModelLabEvaluation.v1", report["schema"])
                self.assertTrue(report["baseline_equivalent"])
                self.assertEqual([], report["diffs"])
                self.assertEqual([], report["validation_errors"])
                self.assertEqual("home_model_lab", report["mission_profile"])
                self.assertEqual("local_http", report["model_provider"])
                self.assertEqual("mock", report["platform_backend"])
                self.assertEqual("mock_endpoint", report["model_lab_evidence_kind"])
                self.assertTrue(report["machine_id"])
                self.assertEqual("AcceleratorProbe.v1", report["accelerator_probe"]["schema"])
        finally:
            _stop_server(server, thread)

    def test_valid_model_difference_is_reported_without_touching_hardware(self):
        server, thread = _start_server(_DifferentValidModelHandler)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile_path = _write_profile(tmp, server.server_address[1])
                evaluation = evaluate_model_lab_case(
                    profile_path=profile_path,
                    case_id="uav_ugv_coordination",
                    output_dir=Path(tmp) / "model-lab",
                )

                self.assertTrue(evaluation.ok, evaluation.as_dict())
                self.assertFalse(evaluation.baseline_equivalent)
                self.assertIn("mission_request.targets", {diff.path for diff in evaluation.diffs})
                profile = json.loads((Path(evaluation.output_dir) / "environment_profile.json").read_text(encoding="utf-8"))
                self.assertEqual("mock", profile["platform_backend"])
        finally:
            _stop_server(server, thread)

    def test_require_baseline_equivalence_can_fail_on_difference(self):
        server, thread = _start_server(_DifferentValidModelHandler)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile_path = _write_profile(tmp, server.server_address[1])
                evaluation = evaluate_model_lab_case(
                    profile_path=profile_path,
                    case_id="uav_ugv_coordination",
                    output_dir=Path(tmp) / "model-lab",
                    require_baseline_equivalence=True,
                )

                self.assertFalse(evaluation.ok)
                self.assertIn("model task schema differs from mock baseline", evaluation.validation_errors)
        finally:
            _stop_server(server, thread)

    def test_home_5090_live_requires_accelerator_probe_with_rtx_5090(self):
        server, thread = _start_server(_EquivalentModelHandler)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile_path = _write_profile(
                    tmp,
                    server.server_address[1],
                    model_lab_evidence_kind="home_5090_live",
                )
                evaluation = evaluate_model_lab_case(
                    profile_path=profile_path,
                    case_id="uav_ugv_coordination",
                    output_dir=Path(tmp) / "model-lab",
                    accelerator_probe=_accelerator_probe("NVIDIA GeForce RTX 5090"),
                )

                self.assertTrue(evaluation.ok, evaluation.as_dict())
                self.assertTrue(evaluation.machine_id)
                self.assertEqual("home_5090_live", evaluation.model_lab_evidence_kind)
        finally:
            _stop_server(server, thread)

    def test_home_5090_live_rejects_missing_rtx_5090_probe(self):
        server, thread = _start_server(_EquivalentModelHandler)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile_path = _write_profile(
                    tmp,
                    server.server_address[1],
                    model_lab_evidence_kind="home_5090_live",
                )
                evaluation = evaluate_model_lab_case(
                    profile_path=profile_path,
                    case_id="uav_ugv_coordination",
                    output_dir=Path(tmp) / "model-lab",
                    accelerator_probe=_accelerator_probe("NVIDIA GeForce RTX 4060"),
                )

                self.assertFalse(evaluation.ok)
                self.assertIn("accelerator_probe must include an RTX 5090 GPU", evaluation.validation_errors)
        finally:
            _stop_server(server, thread)

    def test_home_5090_live_rejects_non_nvidia_smi_probe(self):
        server, thread = _start_server(_EquivalentModelHandler)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile_path = _write_profile(
                    tmp,
                    server.server_address[1],
                    model_lab_evidence_kind="home_5090_live",
                )
                evaluation = evaluate_model_lab_case(
                    profile_path=profile_path,
                    case_id="uav_ugv_coordination",
                    output_dir=Path(tmp) / "model-lab",
                    accelerator_probe=_accelerator_probe(
                        "NVIDIA GeForce RTX 5090",
                        source="synthetic",
                        command=["synthetic-probe"],
                    ),
                )

                self.assertFalse(evaluation.ok)
                self.assertIn("accelerator_probe.source must be nvidia-smi", evaluation.validation_errors)
                self.assertIn("accelerator_probe.command must run nvidia-smi", evaluation.validation_errors)
        finally:
            _stop_server(server, thread)


def _send_model_response(handler, content):
    response = {
        "choices": [{
            "message": {"content": json.dumps(content, ensure_ascii=False)},
        }],
    }
    body = json.dumps(response).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _start_server(handler_class):
    server = HTTPServer(("127.0.0.1", 0), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server, thread):
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()


def _write_profile(tmp, port, *, model_lab_evidence_kind="mock_endpoint"):
    profile_path = Path(tmp) / "home_model_lab.env"
    profile_path.write_text("\n".join([
        "MISSION_PROFILE=home_model_lab",
        "MODEL_PROVIDER=local_http",
        f"MODEL_BASE_URL=http://127.0.0.1:{port}/v1",
        "MODEL_NAME=fake-qwen",
        f"MODEL_LAB_EVIDENCE_KIND={model_lab_evidence_kind}",
        "PLANNER_BACKEND=mock",
        "PLATFORM_BACKEND=mock",
        "MISSION_STATE_STORE=json",
        f"MISSION_ARTIFACT_ROOT={Path(tmp) / 'runs'}",
        "HARDWARE_APPROVAL_REQUIRED=false",
    ]), encoding="utf-8")
    return profile_path


def _accelerator_probe(name, *, source="nvidia-smi", command=None, errors=None):
    return {
        "schema": "AcceleratorProbe.v1",
        "ok": True,
        "source": source,
        "command": command or ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
        "gpus": [{"name": name, "memory_total": "32768 MiB", "driver_version": "test"}],
        "errors": errors or [],
    }


if __name__ == "__main__":
    unittest.main()
