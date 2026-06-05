import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.config import EnvironmentProfile
from task_planning.migration.unit_ugv_object_approach_bundle import (
    prepare_unit_ugv_object_approach_bundle,
)
from task_planning.mission_ops.golden_cases import golden_case_by_id
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore


class UnitUgvObjectApproachBundleTest(unittest.TestCase):
    def test_prepare_bundle_writes_command_payload_and_preflight_without_ros(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            artifact_root = _run_single_ugv_object_approach_artifact(tmp_path)
            target_map_path = _write_target_map(tmp_path, object_queries=["充电桩", "charging_station"])
            output_dir = tmp_path / "prep_bundle"

            report = prepare_unit_ugv_object_approach_bundle(
                artifact_root=artifact_root,
                target_map_path=target_map_path,
                output_dir=output_dir,
                platform_id="ugv_0",
                index=1,
                max_move_base_distance_m=1.0,
            )

            command = json.loads(Path(report.files["task_command_json"]).read_text(encoding="utf-8"))
            rosservice_payload = json.loads(Path(report.files["task_command_rosservice_json"]).read_text(encoding="utf-8"))
            preflight = json.loads(Path(report.files["artifact_target_map_preflight"]).read_text(encoding="utf-8"))
            bundle_report = json.loads((output_dir / "prep_bundle_report.json").read_text(encoding="utf-8"))

        self.assertTrue(report.ok, report.validation_errors)
        self.assertEqual("UnitUgvObjectApproachPrepBundle.v1", report.schema)
        self.assertEqual("task_002", report.task_id)
        self.assertEqual("充电桩", report.object_query)
        self.assertEqual("target_01", report.selected_target_id)
        self.assertEqual("TaskCommand.v1", command["schema"])
        self.assertEqual(command, json.loads(rosservice_payload["task_command_json"]))
        self.assertTrue(preflight["ok"], preflight)
        self.assertFalse(report.ros_connected)
        self.assertFalse(report.dispatch_performed)
        self.assertFalse(report.gateway_dry_run_called)
        self.assertEqual(report.as_dict(), bundle_report)

    def test_cli_prepares_bundle_for_agent_or_operator_handoff(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            artifact_root = _run_single_ugv_object_approach_artifact(tmp_path)
            target_map_path = _write_target_map(tmp_path, object_queries=["充电桩", "charging_station"])
            output_dir = tmp_path / "prep_bundle"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "prepare_unit_ugv_object_approach_bundle.py"),
                    str(artifact_root),
                    "--target-map", str(target_map_path),
                    "--output-dir", str(output_dir),
                    "--platform-id", "ugv_0",
                    "--index", "1",
                    "--max-move-base-distance-m", "1.0",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            report = json.loads(completed.stdout)
            rosservice_payload = json.loads(Path(report["files"]["task_command_rosservice_json"]).read_text(encoding="utf-8"))

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(report["ok"], report)
        self.assertEqual("UnitUgvObjectApproachPrepBundle.v1", report["schema"])
        self.assertIn("task_command_json", rosservice_payload)
        self.assertFalse(report["ros_connected"])
        self.assertFalse(report["dispatch_performed"])
        self.assertFalse(report["gateway_dry_run_called"])


def _run_single_ugv_object_approach_artifact(tmp: Path) -> Path:
    profile = EnvironmentProfile.from_mapping({
        "MISSION_PROFILE": "dev_mock",
        "MODEL_PROVIDER": "mock",
        "PLANNER_BACKEND": "mock",
        "PLATFORM_BACKEND": "mock",
        "MISSION_STATE_STORE": "json",
        "MISSION_ARTIFACT_ROOT": str(tmp / "runs"),
    })
    runner = MissionManagerRunner(
        state_store=JsonMissionOpsStateStore(tmp / "state"),
        gateway=MockPlatformGateway(),
    )
    result = runner.run(golden_case_by_id("single_ugv_object_approach").run_input(), profile.as_env_dict())
    return Path(result.artifact_bundle_path)


def _write_target_map(tmp: Path, *, object_queries):
    target_map_path = tmp / "unit_ugv_targets.json"
    target_map_path.write_text(json.dumps({
        "schema": "UnitUgvTargetMap.v1",
        "platform_id": "ugv_0",
        "targets": {
            "target_01": {
                "capability": "confirm_target",
                "action": "manual_confirm",
                "operator_confirmed_mapping": True,
                "object_queries": list(object_queries),
                "description": "operator-confirmed local object approach target",
            },
        },
    }, ensure_ascii=False), encoding="utf-8")
    return target_map_path


if __name__ == "__main__":
    unittest.main()
