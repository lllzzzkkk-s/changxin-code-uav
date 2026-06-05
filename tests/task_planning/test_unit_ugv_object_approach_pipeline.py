import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from task_planning.migration.unit_ugv_object_approach_pipeline import (
    prepare_unit_ugv_object_approach_pipeline,
)


class UnitUgvObjectApproachPipelineTest(unittest.TestCase):
    def test_pipeline_prepares_ros_ready_gateway_handoff_from_operator_intent(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_map_path = _write_target_map(tmp_path, object_query="显示器")
            ros_profile_path = _write_ros1_profile(tmp_path)

            report = prepare_unit_ugv_object_approach_pipeline(
                profile_path=repo_root / "profiles" / "dev_mock.env",
                intent="让小车识别附近的显示器，然后走过去",
                mission_id="mission_monitor_approach",
                case_id="manual_single_ugv_monitor_approach",
                target_map_path=target_map_path,
                ros1_gateway_profile_path=ros_profile_path,
                output_dir=tmp_path / "handoff",
                platform_id="ugv_0",
                index=1,
                max_move_base_distance_m=1.0,
                repo_root=repo_root,
            )

        self.assertTrue(report.ok, report.validation_errors)
        self.assertEqual("UnitUgvObjectApproachRosReadyHandoff.v1", report.schema)
        self.assertTrue(report.ros_ready)
        self.assertEqual("4060_ros1_gateway_dry_run", report.next_runtime_stage)
        self.assertEqual("manual_single_ugv_monitor_approach", report.case_id)
        self.assertEqual("mission_monitor_approach", report.mission_id)
        self.assertEqual("ugv_0", report.platform_id)
        self.assertEqual("显示器", report.object_query)
        self.assertEqual("target_01", report.selected_target_id)
        self.assertEqual("/fleet/ugv_0/gateway/dry_run", report.service_name)
        self.assertFalse(report.mac_side_ros_connected)
        self.assertFalse(report.mac_side_service_called)
        self.assertFalse(report.mac_side_dispatch_performed)
        self.assertFalse(report.mac_side_rostopic_pub)
        self.assertIn("intent_run", report.files)
        self.assertIn("target_map_check", report.files)
        self.assertIn("prep_bundle_report", report.files)
        self.assertIn("gateway_dry_run_plan", report.files)
        self.assertEqual("MissionIntentRun.v1", report.intent_run["schema"])
        self.assertEqual("UnitUgvTargetMapCheckReport.v1", report.target_map_check["schema"])
        self.assertEqual("UnitUgvObjectApproachPrepBundle.v1", report.prep_bundle["schema"])
        self.assertEqual("UnitUgvGatewayCallPlan.v1", report.gateway_dry_run_plan["schema"])

    def test_cli_writes_ros_ready_handoff_report(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_map_path = _write_target_map(tmp_path, object_query="灭火器")
            ros_profile_path = _write_ros1_profile(tmp_path)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "prepare_unit_ugv_object_approach_pipeline.py"),
                    "--profile", str(repo_root / "profiles" / "dev_mock.env"),
                    "--intent", "让小车识别附近的灭火器，然后靠近",
                    "--mission-id", "mission_extinguisher_approach",
                    "--case-id", "manual_single_ugv_extinguisher_approach",
                    "--target-map", str(target_map_path),
                    "--ros1-gateway-profile", str(ros_profile_path),
                    "--output-dir", str(tmp_path / "handoff"),
                    "--platform-id", "ugv_0",
                    "--index", "1",
                    "--max-move-base-distance-m", "1.0",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertTrue(Path(report["files"]["handoff_report"]).exists())

        self.assertTrue(report["ok"], report)
        self.assertEqual("UnitUgvObjectApproachRosReadyHandoff.v1", report["schema"])
        self.assertTrue(report["ros_ready"])
        self.assertEqual("4060_ros1_gateway_dry_run", report["next_runtime_stage"])
        self.assertEqual("灭火器", report["object_query"])
        self.assertEqual("/fleet/ugv_0/gateway/dry_run", report["service_name"])
        self.assertFalse(report["mac_side_ros_connected"])
        self.assertFalse(report["mac_side_service_called"])
        self.assertFalse(report["mac_side_dispatch_performed"])


def _write_target_map(tmp: Path, *, object_query: str) -> Path:
    target_map_path = tmp / "unit_ugv_targets.json"
    target_map_path.write_text(json.dumps({
        "schema": "UnitUgvTargetMap.v1",
        "platform_id": "ugv_0",
        "targets": {
            "target_01": {
                "capability": "confirm_target",
                "action": "manual_confirm",
                "operator_confirmed_mapping": True,
                "object_queries": [object_query, "nearby_object"],
                "description": "operator-confirmed local object approach target",
            },
        },
    }, ensure_ascii=False), encoding="utf-8")
    return target_map_path


def _write_ros1_profile(tmp: Path) -> Path:
    profile_path = tmp / "work_hardware_ros1_gateway.env"
    profile_path.write_text(
        "\n".join([
            "MISSION_PROFILE=work_hardware",
            "MODEL_PROVIDER=mock",
            "MODEL_BASE_URL=",
            "MODEL_NAME=",
            "PLANNER_BACKEND=mock",
            "PLATFORM_BACKEND=ros1_gateway",
            "MISSION_STATE_STORE=json",
            f"MISSION_ARTIFACT_ROOT={tmp / 'ros1_runs'}",
            "ROS_MASTER_URI=http://192.168.0.201:11311",
            "ROS_IP=172.20.26.179",
            "HARDWARE_APPROVAL_REQUIRED=true",
            "ROS_GATEWAY_DISPATCH_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dispatch",
            "ROS_GATEWAY_DRY_RUN_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dry_run",
        ]) + "\n",
        encoding="utf-8",
    )
    return profile_path


if __name__ == "__main__":
    unittest.main()
