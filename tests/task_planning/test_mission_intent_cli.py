import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class MissionIntentCliTest(unittest.TestCase):
    def test_cli_runs_single_ugv_object_approach_from_operator_intent(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "runs"
            output_path = Path(tmp) / "intent-run.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "run_task_planning_intent.py"),
                    "--profile", str(repo_root / "profiles" / "dev_mock.env"),
                    "--intent", "让小车识别附近的显示器，然后走过去",
                    "--mission-id", "mission_monitor_approach",
                    "--primary-platform", "ugv_0",
                    "--case-id", "manual_single_ugv_monitor_approach",
                    "--artifact-root", str(artifact_root),
                ],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            output_path.write_text(completed.stdout, encoding="utf-8")
            report = json.loads(output_path.read_text(encoding="utf-8"))
            bundle_root = Path(report["artifact_bundle_path"])

            task_schema = json.loads((bundle_root / "task_schema.json").read_text(encoding="utf-8"))
            planner_output = json.loads((bundle_root / "planner_output.json").read_text(encoding="utf-8"))
            bt_artifact = json.loads((bundle_root / "bt_artifact.json").read_text(encoding="utf-8"))

        self.assertEqual("MissionIntentRun.v1", report["schema"])
        self.assertTrue(report["ok"], report)
        self.assertEqual("dry_run_complete", report["status"])
        self.assertEqual("DISPATCH_OR_HOLD", report["current_state"])
        self.assertEqual("manual_single_ugv_monitor_approach", report["case_id"])
        self.assertEqual("mission_monitor_approach", report["mission_id"])
        self.assertEqual("ugv_0", report["context_snapshot"]["primary_platform"])
        self.assertFalse(report["ros_connected"])
        self.assertFalse(report["hardware_dispatch_performed"])
        self.assertEqual("显示器", task_schema["mission_request"]["constraints"]["object_query"])
        self.assertEqual(["identify-target", "approach-target"], [step["action"] for step in planner_output["steps"]])
        self.assertEqual(["identify_target", "approach_target"], [
            command["parameters"]["stage"] for command in bt_artifact["task_commands"]
        ])

    def test_cli_rejects_ros1_gateway_profile_before_runtime(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "work_hardware_ros1.env"
            profile_path.write_text(
                "\n".join([
                    "MISSION_PROFILE=work_hardware",
                    "MODEL_PROVIDER=mock",
                    "MODEL_BASE_URL=",
                    "MODEL_NAME=",
                    "PLANNER_BACKEND=mock",
                    "PLATFORM_BACKEND=ros1_gateway",
                    "MISSION_STATE_STORE=json",
                    f"MISSION_ARTIFACT_ROOT={Path(tmp) / 'runs'}",
                    "ROS_MASTER_URI=http://127.0.0.1:11311",
                    "ROS_IP=127.0.0.1",
                    "HARDWARE_APPROVAL_REQUIRED=true",
                ]) + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "run_task_planning_intent.py"),
                    "--profile", str(profile_path),
                    "--intent", "让小车识别附近的显示器，然后走过去",
                    "--mission-id", "mission_monitor_approach",
                    "--primary-platform", "ugv_0",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

        self.assertEqual(1, completed.returncode)
        report = json.loads(completed.stdout)
        self.assertFalse(report["ok"])
        self.assertIn("PLATFORM_BACKEND=ros1_gateway is not allowed", report["validation_errors"])
        self.assertFalse(report["ros_connected"])
        self.assertFalse(report["hardware_dispatch_performed"])

    def test_cli_runs_agent_drafted_task_schema_through_same_pipeline(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            draft_path = Path(tmp) / "openclaw-draft.json"
            draft_path.write_text(json.dumps({
                "schema": "TaskSchema.v1",
                "intent": "让小车识别附近的灭火器，然后靠近",
                "context_snapshot": {
                    "mission_id": "mission_agent_extinguisher_approach",
                    "primary_platform": "ugv_0",
                },
                "mission_request": {
                    "schema": "MissionRequest.v1",
                    "mission_id": "mission_agent_extinguisher_approach",
                    "mission_type": "scout_and_confirm",
                    "areas": ["area_A"],
                    "targets": ["target_01"],
                    "required_capabilities": ["confirm_target"],
                    "constraints": {
                        "mission_variant": "single_ugv_object_approach",
                        "object_query": "灭火器",
                        "require_operator_before_motion": True,
                    },
                },
            }, ensure_ascii=False), encoding="utf-8")
            artifact_root = Path(tmp) / "runs"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "run_task_planning_intent.py"),
                    "--profile", str(repo_root / "profiles" / "dev_mock.env"),
                    "--intent", "让小车识别附近的灭火器，然后靠近",
                    "--mission-id", "mission_agent_extinguisher_approach",
                    "--primary-platform", "ugv_0",
                    "--case-id", "agent_single_ugv_extinguisher_approach",
                    "--agent-name", "openclaw",
                    "--agent-draft-file", str(draft_path),
                    "--artifact-root", str(artifact_root),
                ],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            report = json.loads(completed.stdout)
            bundle_root = Path(report["artifact_bundle_path"])
            task_schema = json.loads((bundle_root / "task_schema.json").read_text(encoding="utf-8"))
            plan = json.loads((bundle_root / "planner_output.json").read_text(encoding="utf-8"))

        self.assertEqual("agent_adapter", report["semantic_compiler"]["kind"])
        self.assertEqual("openclaw", report["semantic_compiler"]["agent_name"])
        self.assertEqual("灭火器", task_schema["mission_request"]["constraints"]["object_query"])
        self.assertEqual(["identify-target", "approach-target"], [step["action"] for step in plan["steps"]])
        self.assertFalse(report["ros_connected"])
        self.assertFalse(report["hardware_dispatch_performed"])

    def test_cli_rejects_agent_draft_with_raw_ros_reference(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            draft_path = Path(tmp) / "hermes-unsafe-draft.json"
            draft_path.write_text(json.dumps({
                "schema": "TaskSchema.v1",
                "intent": "让小车直接发速度",
                "context_snapshot": {},
                "mission_request": {
                    "schema": "MissionRequest.v1",
                    "mission_id": "mission_bad_agent",
                    "mission_type": "scout_and_confirm",
                    "areas": ["area_A"],
                    "targets": ["target_01"],
                    "required_capabilities": ["confirm_target"],
                    "constraints": {"unsafe": "/cmd_vel"},
                },
            }, ensure_ascii=False), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "run_task_planning_intent.py"),
                    "--profile", str(repo_root / "profiles" / "dev_mock.env"),
                    "--intent", "让小车直接发速度",
                    "--mission-id", "mission_bad_agent",
                    "--primary-platform", "ugv_0",
                    "--agent-name", "hermes",
                    "--agent-draft-file", str(draft_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

        self.assertEqual(1, completed.returncode)
        report = json.loads(completed.stdout)
        self.assertFalse(report["ok"])
        self.assertEqual("agent_adapter", report["semantic_compiler"]["kind"])
        self.assertEqual("hermes", report["semantic_compiler"]["agent_name"])
        self.assertIn("raw ROS reference is forbidden", "; ".join(report["validation_errors"]))
        self.assertFalse(report["ros_connected"])
        self.assertFalse(report["hardware_dispatch_performed"])


if __name__ == "__main__":
    unittest.main()
