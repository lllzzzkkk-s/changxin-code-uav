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


if __name__ == "__main__":
    unittest.main()
