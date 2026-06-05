import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.config import EnvironmentProfile
from task_planning.migration.unit_ugv_gateway_call_plan import plan_unit_ugv_gateway_call
from task_planning.migration.unit_ugv_object_approach_bundle import prepare_unit_ugv_object_approach_bundle
from task_planning.mission_ops.golden_cases import golden_case_by_id
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore


class UnitUgvGatewayCallPlanTest(unittest.TestCase):
    def test_plan_dry_run_gateway_call_from_prep_bundle_without_ros(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            prep_report_path = _write_prep_bundle(tmp_path)
            profile_path = _write_ros1_profile(tmp_path)

            report = plan_unit_ugv_gateway_call(
                prep_report_path=prep_report_path,
                profile_path=profile_path,
                mode="dry_run",
            )

        self.assertTrue(report.ok, report.validation_errors)
        self.assertEqual("UnitUgvGatewayCallPlan.v1", report.schema)
        self.assertEqual("dry_run", report.mode)
        self.assertEqual("/fleet/ugv_0/gateway/dry_run", report.service_name)
        self.assertIn("task_command.rosservice.json", report.payload_file)
        self.assertEqual("task_002", report.task_id)
        self.assertEqual("充电桩", report.object_query)
        self.assertIn("TaskCommandJson", report.service_signature_requirements["type"])
        self.assertEqual("task_command_json", report.service_signature_requirements["args"][0])
        self.assertFalse(report.ros_connected)
        self.assertFalse(report.service_called)
        self.assertFalse(report.dispatch_performed)
        self.assertFalse(report.rostopic_pub)

    def test_plan_rejects_dispatch_without_operator_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            prep_report_path = _write_prep_bundle(tmp_path)
            profile_path = _write_ros1_profile(tmp_path)

            report = plan_unit_ugv_gateway_call(
                prep_report_path=prep_report_path,
                profile_path=profile_path,
                mode="dispatch",
            )

        self.assertFalse(report.ok)
        self.assertIn("operator approval is required before planning dispatch", report.validation_errors)
        self.assertEqual("/fleet/ugv_0/gateway/dispatch", report.service_name)
        self.assertFalse(report.ros_connected)
        self.assertFalse(report.service_called)
        self.assertFalse(report.dispatch_performed)

    def test_cli_writes_gateway_call_plan(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            prep_report_path = _write_prep_bundle(tmp_path)
            profile_path = _write_ros1_profile(tmp_path)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "plan_unit_ugv_gateway_call.py"),
                    "--prep-report", str(prep_report_path),
                    "--profile", str(profile_path),
                    "--mode", "dry_run",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["ok"], report)
        self.assertEqual("UnitUgvGatewayCallPlan.v1", report["schema"])
        self.assertEqual("/fleet/ugv_0/gateway/dry_run", report["service_name"])
        self.assertFalse(report["ros_connected"])
        self.assertFalse(report["service_called"])


def _write_prep_bundle(tmp: Path) -> Path:
    artifact_root = _run_single_ugv_object_approach_artifact(tmp)
    target_map_path = tmp / "unit_ugv_targets.json"
    target_map_path.write_text(json.dumps({
        "schema": "UnitUgvTargetMap.v1",
        "platform_id": "ugv_0",
        "targets": {
            "target_01": {
                "capability": "confirm_target",
                "action": "manual_confirm",
                "operator_confirmed_mapping": True,
                "object_queries": ["充电桩", "charging_station"],
                "description": "operator-confirmed local object approach target",
            },
        },
    }, ensure_ascii=False), encoding="utf-8")
    prep = prepare_unit_ugv_object_approach_bundle(
        artifact_root=artifact_root,
        target_map_path=target_map_path,
        output_dir=tmp / "prep",
        platform_id="ugv_0",
        index=1,
        max_move_base_distance_m=1.0,
    )
    return Path(prep.files["prep_bundle_report"])


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
