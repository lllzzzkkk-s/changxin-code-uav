import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from task_planning.mission_ops.golden_cases import golden_case_by_id
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore
from task_planning.migration.task_command_extraction import extract_task_command_from_artifact


class TaskCommandExtractionTest(unittest.TestCase):
    def test_extracts_validated_task_command_from_artifact_for_platform_gateway_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_dev_mock_case(Path(tmp))

            extracted = extract_task_command_from_artifact(
                artifact_root=Path(result.artifact_bundle_path),
                platform_id="uav_0",
                capability="inspect_area",
            )

            self.assertTrue(extracted.ok, extracted.as_dict())
            self.assertEqual("uav_0", extracted.command.platform_id)
            self.assertEqual("inspect_area", extracted.command.capability)
            report = extracted.as_dict()
            self.assertEqual("ExtractedTaskCommand.v1", report["schema"])
            self.assertEqual(extracted.command.as_dict(), json.loads(report["task_command_json"]))

    def test_extraction_reports_no_match_without_fabricating_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_dev_mock_case(Path(tmp))

            extracted = extract_task_command_from_artifact(
                artifact_root=Path(result.artifact_bundle_path),
                platform_id="missing_platform",
            )

            self.assertFalse(extracted.ok)
            self.assertIsNone(extracted.command)
            self.assertIn("no TaskCommand matched filters", "\n".join(extracted.validation_errors))

    def test_cli_can_emit_rosservice_yaml_argument_without_sending_ros(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_dev_mock_case(Path(tmp))

            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/extract_task_command_from_artifact.py",
                    str(result.artifact_bundle_path),
                    "--platform-id",
                    "uav_0",
                    "--capability",
                    "inspect_area",
                    "--format",
                    "rosservice-yaml",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads(completed.stdout)
            command = json.loads(payload["task_command_json"])
            self.assertEqual("TaskCommand.v1", command["schema"])
            self.assertEqual("uav_0", command["platform_id"])


def _run_dev_mock_case(tmp_path: Path):
    runner = MissionManagerRunner(state_store=JsonMissionOpsStateStore(tmp_path / "state"))
    return runner.run(
        golden_case_by_id("uav_ugv_coordination").run_input(),
        {
            "MISSION_PROFILE": "dev_mock",
            "MODEL_PROVIDER": "mock",
            "PLANNER_BACKEND": "mock",
            "PLATFORM_BACKEND": "mock",
            "MISSION_STATE_STORE": "json",
            "MISSION_ARTIFACT_ROOT": str(tmp_path / "runs"),
        },
    )


if __name__ == "__main__":
    unittest.main()
