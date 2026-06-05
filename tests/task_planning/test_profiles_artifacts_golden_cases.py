import json
import tempfile
import unittest
from pathlib import Path

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.config import EnvironmentProfile, ProfileValidationError, load_profile
from task_planning.mission_ops.artifacts import ARTIFACT_FILENAMES
from task_planning.mission_ops.golden_cases import golden_case_by_id, golden_mission_cases
from task_planning.mission_ops.mock_llm_client import MockLLMClient
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore


class DistributedProfileArtifactTest(unittest.TestCase):
    def test_repo_profiles_encode_the_four_distributed_test_lanes(self):
        repo_root = Path(__file__).resolve().parents[2]

        dev_mock = load_profile(repo_root / "profiles/dev_mock.env")
        home_model_lab = load_profile(repo_root / "profiles/home_model_lab.env")
        server_sim = load_profile(repo_root / "profiles/server_sim.env")
        work_hardware = load_profile(repo_root / "profiles/work_hardware.env")

        self.assertEqual("dev_mock", dev_mock.mission_profile)
        self.assertEqual("mock", dev_mock.model_provider)
        self.assertEqual("mock", dev_mock.platform_backend)
        self.assertEqual("home_model_lab", home_model_lab.mission_profile)
        self.assertEqual("local_http", home_model_lab.model_provider)
        self.assertEqual("mock", home_model_lab.platform_backend)
        self.assertEqual("home_5090_live", home_model_lab.model_lab_evidence_kind)
        self.assertEqual("server_sim", server_sim.mission_profile)
        self.assertEqual("sim", server_sim.platform_backend)
        self.assertEqual("work_hardware", work_hardware.mission_profile)
        self.assertEqual("mock", work_hardware.model_provider)
        self.assertTrue(work_hardware.hardware_approval_required)

    def test_unsafe_profiles_fail_before_runtime(self):
        with self.assertRaisesRegex(ProfileValidationError, "dev_mock must use MODEL_PROVIDER=mock"):
            EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "dev_mock",
                "MODEL_PROVIDER": "local_http",
                "MODEL_BASE_URL": "http://127.0.0.1:8000/v1",
                "MODEL_NAME": "qwen",
                "PLATFORM_BACKEND": "mock",
                "PLANNER_BACKEND": "mock",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": "/tmp/runs",
            })

        with self.assertRaisesRegex(ProfileValidationError, "ROS_MASTER_URI is required"):
            EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "work_hardware",
                "MODEL_PROVIDER": "mock",
                "PLATFORM_BACKEND": "ros1_gateway",
                "PLANNER_BACKEND": "mock",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": "/tmp/runs",
                "HARDWARE_APPROVAL_REQUIRED": "true",
            })

        with self.assertRaisesRegex(ProfileValidationError, "home_model_lab must use PLATFORM_BACKEND=mock"):
            EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "home_model_lab",
                "MODEL_PROVIDER": "local_http",
                "MODEL_BASE_URL": "http://127.0.0.1:8000/v1",
                "MODEL_NAME": "qwen",
                "PLATFORM_BACKEND": "ros1_gateway",
                "PLANNER_BACKEND": "mock",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": "/tmp/runs",
            })

    def test_ros1_gateway_template_placeholders_fail_before_runtime(self):
        repo_root = Path(__file__).resolve().parents[2]

        with self.assertRaisesRegex(ProfileValidationError, "ROS_MASTER_URI still contains a template placeholder"):
            load_profile(repo_root / "profiles/work_hardware_ros1_gateway.env.template")

    def test_dev_mock_run_writes_complete_portable_artifact_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "dev_mock",
                "MODEL_PROVIDER": "mock",
                "MODEL_BASE_URL": "",
                "MODEL_NAME": "",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "mock",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": str(Path(tmp) / "runs"),
                "ROS_MASTER_URI": "",
                "ROS_IP": "",
            })
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp) / "state"),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )
            mission_case = golden_case_by_id("uav_ugv_coordination")

            result = runner.run(mission_case.run_input(), profile.as_env_dict())

            bundle_root = Path(result.artifact_bundle_path)
            self.assertEqual("dry_run_complete", result.status)
            self.assertEqual(set(ARTIFACT_FILENAMES), {path.name for path in bundle_root.iterdir()})
            self.assertIn("(define (problem golden_uav_ugv_coordination)", (bundle_root / "pddl_problem.pddl").read_text(encoding="utf-8"))
            self.assertEqual("dev_mock", json.loads((bundle_root / "environment_profile.json").read_text(encoding="utf-8"))["mission_profile"])
            gateway_trace = json.loads((bundle_root / "gateway_trace.json").read_text(encoding="utf-8"))
            self.assertEqual([False, False, False], [record["publish_attempted"] for record in gateway_trace["records"]])
            command_acks = json.loads((bundle_root / "command_acks.json").read_text(encoding="utf-8"))
            task_progress = json.loads((bundle_root / "task_progress.json").read_text(encoding="utf-8"))
            execution_events = json.loads((bundle_root / "execution_events.json").read_text(encoding="utf-8"))
            ledger_record = json.loads((Path(tmp) / "runs" / "_ledger" / f"{result.run_id}.ledger.json").read_text(encoding="utf-8"))
            run_summary = (bundle_root / "run_summary.md").read_text(encoding="utf-8")
            self.assertEqual("ExecutionEventLog.v1", execution_events["schema"])
            self.assertEqual(3, len(command_acks["items"]))
            self.assertEqual(3, len(task_progress["items"]))
            self.assertIn("bt_runtime_completed", [event["event_type"] for event in execution_events["items"]])
            self.assertEqual("MissionRunRecord.v1", ledger_record["schema"])
            self.assertEqual("next_phase_ready", ledger_record["phase_baseline"])
            self.assertEqual(str(bundle_root), ledger_record["artifact_bundle_path"])
            self.assertEqual("bt_runtime_started", ledger_record["events"][0]["event_type"])
            self.assertIn("approval_required", run_summary)

    def test_golden_failure_case_updates_artifacts_with_replan_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "dev_mock",
                "MODEL_PROVIDER": "mock",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "mock",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": str(Path(tmp) / "runs"),
            })
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp) / "state"),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )
            mission_case = golden_case_by_id("failure_and_replan")

            result = runner.run(mission_case.run_input(), profile.as_env_dict())
            replanned = runner.resume(result.run_id, {"failure_report": mission_case.resume_failure_report.as_dict()})

            bundle_root = Path(replanned.artifact_bundle_path)
            failure_report = json.loads((bundle_root / "failure_report.json").read_text(encoding="utf-8"))
            replan = json.loads((bundle_root / "replan_decision.json").read_text(encoding="utf-8"))
            self.assertEqual("path_blocked", failure_report["failure_type"])
            self.assertEqual("central_replan", replan["mode"])
            self.assertEqual("REQUEST_REPLAN", replanned.state.current_state)

    def test_work_hardware_profile_requires_approval_before_gateway_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "work_hardware",
                "MODEL_PROVIDER": "mock",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "mock",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": str(Path(tmp) / "runs"),
                "HARDWARE_APPROVAL_REQUIRED": "true",
            })
            gateway = MockPlatformGateway()
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp) / "state"),
                model_client=MockLLMClient(),
                gateway=gateway,
            )

            result = runner.run(golden_case_by_id("uav_ugv_coordination").run_input(), profile.as_env_dict())

            self.assertEqual("approval_required", result.status)
            self.assertEqual("OPERATOR_APPROVAL", result.state.current_state)
            self.assertEqual([], gateway.dispatch_log)
            bundle_root = Path(result.artifact_bundle_path)
            gateway_trace = json.loads((bundle_root / "gateway_trace.json").read_text(encoding="utf-8"))
            execution_events = json.loads((bundle_root / "execution_events.json").read_text(encoding="utf-8"))
            self.assertEqual([], gateway_trace["records"])
            self.assertIn("operator_approval_required", [event["event_type"] for event in execution_events["items"]])
            self.assertTrue(result.state.approval_state["required"])

    def test_ros1_gateway_profile_cannot_run_through_mock_gateway(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "work_hardware",
                "MODEL_PROVIDER": "mock",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "ros1_gateway",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": str(Path(tmp) / "runs"),
                "ROS_MASTER_URI": "http://127.0.0.1:11311",
                "ROS_IP": "127.0.0.1",
                "HARDWARE_APPROVAL_REQUIRED": "true",
            })
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp) / "state"),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )

            with self.assertRaisesRegex(ValueError, "requires a non-mock gateway implementation"):
                runner.run(golden_case_by_id("uav_ugv_coordination").run_input(), profile.as_env_dict())

    def test_golden_cases_cover_required_migration_scenarios(self):
        case_ids = {mission_case.case_id for mission_case in golden_mission_cases()}

        self.assertEqual({
            "single_ugv_inspection",
            "single_ugv_object_approach",
            "uav_reconnaissance",
            "uav_ugv_coordination",
            "failure_and_replan",
            "disconnect_continue_authorized_subtree",
        }, case_ids)


if __name__ == "__main__":
    unittest.main()
