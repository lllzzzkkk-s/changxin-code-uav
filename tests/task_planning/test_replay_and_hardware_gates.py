import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.config import EnvironmentProfile
from task_planning.hardware import build_hardware_gate_plan
from task_planning.mission_ops.golden_cases import golden_case_by_id
from task_planning.mission_ops.mock_llm_client import MockLLMClient
from task_planning.mission_ops.replay import compare_artifact_bundles, load_artifact_bundle, summarize_artifact_bundle
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore


class ReplayAndHardwareGateTest(unittest.TestCase):
    def test_server_sim_can_replay_and_compare_equivalent_artifact_bundles(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "runs"
            profile = EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "server_sim",
                "MODEL_PROVIDER": "mock",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "sim",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": str(artifact_root),
            })
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp) / "state"),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )
            mission_case = golden_case_by_id("uav_ugv_coordination")

            first = runner.run(mission_case.run_input(), profile.as_env_dict())
            second = runner.run(mission_case.run_input(), profile.as_env_dict())
            first_bundle = load_artifact_bundle(first.artifact_bundle_path)
            comparison = compare_artifact_bundles(first.artifact_bundle_path, second.artifact_bundle_path)

            self.assertTrue(first_bundle.ok)
            self.assertTrue(comparison.equivalent)
            self.assertEqual([], comparison.diffs)
            self.assertEqual("server_sim", first_bundle.data["environment_profile.json"]["mission_profile"])

    def test_artifact_comparison_reports_structured_differences(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "runs"
            profile = EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "dev_mock",
                "MODEL_PROVIDER": "mock",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "mock",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": str(artifact_root),
            })
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp) / "state"),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )
            first = runner.run(golden_case_by_id("uav_ugv_coordination").run_input(), profile.as_env_dict())
            second = runner.run(golden_case_by_id("uav_reconnaissance").run_input(), profile.as_env_dict())

            comparison = compare_artifact_bundles(first.artifact_bundle_path, second.artifact_bundle_path)

            self.assertFalse(comparison.equivalent)
            self.assertIn("mission_input.case_id", {diff.path for diff in comparison.diffs})

    def test_replay_rejects_gateway_trace_that_claims_raw_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "runs"
            profile = EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "dev_mock",
                "MODEL_PROVIDER": "mock",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "mock",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": str(artifact_root),
            })
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp) / "state"),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )
            result = runner.run(golden_case_by_id("uav_ugv_coordination").run_input(), profile.as_env_dict())
            gateway_path = Path(result.artifact_bundle_path) / "gateway_trace.json"
            gateway = json.loads(gateway_path.read_text(encoding="utf-8"))
            gateway["records"][0]["publish_attempted"] = True
            gateway_path.write_text(json.dumps(gateway), encoding="utf-8")

            bundle = load_artifact_bundle(result.artifact_bundle_path)

            self.assertFalse(bundle.ok)
            self.assertIn("gateway_trace record 0 must have publish_attempted=false", bundle.validation_errors)

    def test_replay_rejects_malformed_required_artifact_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "runs"
            profile = EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "dev_mock",
                "MODEL_PROVIDER": "mock",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "mock",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": str(artifact_root),
            })
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp) / "state"),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )
            result = runner.run(golden_case_by_id("uav_ugv_coordination").run_input(), profile.as_env_dict())
            command_acks_path = Path(result.artifact_bundle_path) / "command_acks.json"
            command_acks = json.loads(command_acks_path.read_text(encoding="utf-8"))
            command_acks["schema"] = "LegacyCommandAckSet.v1"
            command_acks_path.write_text(json.dumps(command_acks), encoding="utf-8")

            bundle = load_artifact_bundle(result.artifact_bundle_path)

            self.assertFalse(bundle.ok)
            self.assertIn("command_acks.json must be CommandAckSet.v1", bundle.validation_errors)

    def test_replay_summary_explains_event_and_approval_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "runs"
            profile = EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "dev_mock",
                "MODEL_PROVIDER": "mock",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "mock",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": str(artifact_root),
            })
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp) / "state"),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )
            result = runner.run(golden_case_by_id("uav_ugv_coordination").run_input(), profile.as_env_dict())

            summary = summarize_artifact_bundle(result.artifact_bundle_path)

        self.assertTrue(summary.ok, summary.as_dict())
        self.assertEqual("ArtifactReplayDiagnosticSummary.v1", summary.schema)
        self.assertGreaterEqual(summary.event_counts["bt_runtime_completed"], 1)
        self.assertGreaterEqual(summary.accepted_commands, 1)
        self.assertFalse(summary.approval_required)
        self.assertEqual([], summary.validation_errors)

    def test_replay_summary_cli_outputs_operator_friendly_json(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "runs"
            profile = EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "dev_mock",
                "MODEL_PROVIDER": "mock",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "mock",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": str(artifact_root),
            })
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp) / "state"),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )
            result = runner.run(golden_case_by_id("uav_ugv_coordination").run_input(), profile.as_env_dict())

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "replay_task_planning_artifact.py"),
                    str(result.artifact_bundle_path),
                    "--summary",
                ],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            summary = json.loads(completed.stdout)

        self.assertEqual("ArtifactReplayDiagnosticSummary.v1", summary["schema"])
        self.assertIn("event_counts", summary)
        self.assertIn("accepted_commands", summary)
        self.assertIn("approval_required", summary)

    def test_work_hardware_gate_plan_preserves_no_model_no_raw_ros_boundary(self):
        profile = EnvironmentProfile.from_mapping({
            "MISSION_PROFILE": "work_hardware",
            "MODEL_PROVIDER": "mock",
            "PLANNER_BACKEND": "mock",
            "PLATFORM_BACKEND": "mock",
            "MISSION_STATE_STORE": "json",
            "MISSION_ARTIFACT_ROOT": "/tmp/work-hardware-runs",
            "HARDWARE_APPROVAL_REQUIRED": "true",
        })

        plan = build_hardware_gate_plan(profile, through_stage="mock_gateway_dispatch")

        self.assertTrue(plan.ok)
        self.assertEqual(["read_only_observation", "mock_gateway_dispatch"], [step.stage for step in plan.steps])
        all_forbidden = "\n".join(item for step in plan.steps for item in step.forbidden)
        bench_plan = build_hardware_gate_plan(profile, through_stage="bench_dry_run_no_motion")
        bench_commands = "\n".join(item for step in bench_plan.steps for item in step.command_templates)
        self.assertIn("Do not publish /mavros/* from the center.", all_forbidden)
        self.assertIn("Do not require a local large model on the work 4060 laptop.", all_forbidden)
        self.assertIn("check_task_planning_site_acceptance.py", bench_commands)
        self.assertIn("--run-service-signatures", bench_commands)
        self.assertIn("command_environment_source=profile", bench_commands)
        self.assertIn("extract_task_command_from_artifact.py", bench_commands)
        self.assertIn("PLATFORM_BACKEND=ros1_gateway", "\n".join(bench_plan.validation_errors))
        self.assertTrue(plan.steps[1].requires_operator_approval)

    def test_hardware_gate_rejects_non_work_profile(self):
        profile = EnvironmentProfile.from_mapping({
            "MISSION_PROFILE": "dev_mock",
            "MODEL_PROVIDER": "mock",
            "PLANNER_BACKEND": "mock",
            "PLATFORM_BACKEND": "mock",
            "MISSION_STATE_STORE": "json",
            "MISSION_ARTIFACT_ROOT": "/tmp/dev-runs",
        })

        plan = build_hardware_gate_plan(profile, through_stage="read_only_observation")

        self.assertFalse(plan.ok)
        self.assertIn("hardware gates require MISSION_PROFILE=work_hardware", plan.validation_errors)


if __name__ == "__main__":
    unittest.main()
