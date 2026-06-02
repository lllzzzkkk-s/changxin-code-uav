import subprocess
import tempfile
import unittest
from pathlib import Path

from task_planning.config import load_profile
from task_planning.migration.ros1_service_audit import audit_ros1_gateway_services, ros1_profile_environment


class Ros1ServiceAuditTest(unittest.TestCase):
    def test_plan_only_audit_outputs_expected_gateway_services_without_ros(self):
        repo_root = Path(__file__).resolve().parents[2]

        report = audit_ros1_gateway_services(
            profile_path=repo_root / "profiles/work_hardware.env",
            platform_ids=["uav_0", "ugv_0"],
        )

        self.assertTrue(report.ok, report.as_dict())
        service_names = {service.service_name for service in report.expected_services}
        self.assertIn("/fleet/uav_0/gateway/dry_run", service_names)
        self.assertIn("/fleet/uav_0/gateway/dispatch", service_names)
        self.assertIn("/fleet/ugv_0/gateway/dry_run", service_names)
        self.assertIn("/fleet/ugv_0/gateway/dispatch", service_names)
        self.assertIn("no rosservice list was provided", "\n".join(report.warnings))
        self.assertTrue(any("--run-service-signatures" in command for command in report.next_commands))
        self.assertEqual("not_run", report.command_environment_source)

    def test_audit_matches_observed_services_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = _write_ros1_gateway_profile(Path(tmp) / "work_hardware_ros1.env")

            report = audit_ros1_gateway_services(
                profile_path=profile,
                platform_ids=["uav_0"],
                observed_services=[
                    "/rosout/get_loggers",
                    "/fleet/uav_0/gateway/dry_run",
                    "/fleet/uav_0/gateway/dispatch",
                ],
            )

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual([], report.missing_services)
        self.assertEqual([
            "/fleet/uav_0/gateway/dispatch",
            "/fleet/uav_0/gateway/dry_run",
        ], report.matched_services)

    def test_audit_reports_missing_expected_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = _write_ros1_gateway_profile(Path(tmp) / "work_hardware_ros1.env")

            report = audit_ros1_gateway_services(
                profile_path=profile,
                platform_ids=["uav_0"],
                observed_services=["/fleet/uav_0/gateway/dry_run"],
            )

        self.assertFalse(report.ok)
        self.assertEqual(["/fleet/uav_0/gateway/dispatch"], report.missing_services)

    def test_audit_can_use_read_only_rosservice_list_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = _write_ros1_gateway_profile(Path(tmp) / "work_hardware_ros1.env")

            def runner(args):
                self.assertEqual(["rosservice", "list"], list(args))
                return subprocess.CompletedProcess(
                    list(args),
                    0,
                    stdout="/fleet/uav_0/gateway/dry_run\n/fleet/uav_0/gateway/dispatch\n",
                    stderr="",
                )

            report = audit_ros1_gateway_services(
                profile_path=profile,
                platform_ids=["uav_0"],
                command_runner=runner,
            )

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual(2, report.observed_service_count)
        self.assertEqual("caller_supplied", report.command_environment_source)

    def test_cli_style_service_list_file_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile = _write_ros1_gateway_profile(tmp_path / "work_hardware_ros1.env")
            service_list = tmp_path / "services.txt"
            service_list.write_text("/fleet/uav_0/gateway/dry_run\n/fleet/uav_0/gateway/dispatch\n", encoding="utf-8")

            report = audit_ros1_gateway_services(
                profile_path=profile,
                platform_ids=["uav_0"],
                observed_services=service_list.read_text(encoding="utf-8").splitlines(),
            )

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual("captured_files", report.command_environment_source)

    def test_audit_validates_service_type_and_args_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = _write_ros1_gateway_profile(Path(tmp) / "work_hardware_ros1.env")

            report = audit_ros1_gateway_services(
                profile_path=profile,
                platform_ids=["uav_0"],
                observed_services=[
                    "/fleet/uav_0/gateway/dry_run",
                    "/fleet/uav_0/gateway/dispatch",
                ],
                observed_service_types={
                    "/fleet/uav_0/gateway/dry_run": "platform_gateway_msgs/TaskCommandJson",
                    "/fleet/uav_0/gateway/dispatch": "platform_gateway_msgs/TaskCommandJson",
                },
                observed_service_args={
                    "/fleet/uav_0/gateway/dry_run": ["task_command_json"],
                    "/fleet/uav_0/gateway/dispatch": ["task_command_json"],
                },
                require_service_signatures=True,
            )

        self.assertTrue(report.ok, report.as_dict())
        self.assertTrue(all(signature.type_ok and signature.args_ok for signature in report.service_signatures))

    def test_audit_rejects_service_signatures_without_service_name_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = _write_ros1_gateway_profile(Path(tmp) / "work_hardware_ros1.env")

            report = audit_ros1_gateway_services(
                profile_path=profile,
                platform_ids=["uav_0"],
                observed_service_types={
                    "/fleet/uav_0/gateway/dry_run": "platform_gateway_msgs/TaskCommandJson",
                    "/fleet/uav_0/gateway/dispatch": "platform_gateway_msgs/TaskCommandJson",
                },
                observed_service_args={
                    "/fleet/uav_0/gateway/dry_run": ["task_command_json"],
                    "/fleet/uav_0/gateway/dispatch": ["task_command_json"],
                },
                require_service_signatures=True,
            )

        self.assertFalse(report.ok)
        self.assertEqual(0, report.observed_service_count)
        self.assertIn("service-name evidence is required", "\n".join(report.validation_errors))

    def test_audit_rejects_wrong_service_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = _write_ros1_gateway_profile(Path(tmp) / "work_hardware_ros1.env")

            report = audit_ros1_gateway_services(
                profile_path=profile,
                platform_ids=["uav_0"],
                observed_services=[
                    "/fleet/uav_0/gateway/dry_run",
                    "/fleet/uav_0/gateway/dispatch",
                ],
                observed_service_types={
                    "/fleet/uav_0/gateway/dry_run": "std_srvs/Trigger",
                    "/fleet/uav_0/gateway/dispatch": "platform_gateway_msgs/TaskCommandJson",
                },
                observed_service_args={
                    "/fleet/uav_0/gateway/dry_run": ["data"],
                    "/fleet/uav_0/gateway/dispatch": ["task_command_json"],
                },
                require_service_signatures=True,
            )

        self.assertFalse(report.ok)
        errors = "\n".join(error for signature in report.service_signatures for error in signature.errors)
        self.assertIn("TaskCommandJson", errors)
        self.assertIn("task_command_json", errors)

    def test_audit_rejects_observed_proof_with_mock_profile(self):
        repo_root = Path(__file__).resolve().parents[2]

        report = audit_ros1_gateway_services(
            profile_path=repo_root / "profiles/work_hardware.env",
            platform_ids=["uav_0"],
            observed_services=[
                "/fleet/uav_0/gateway/dry_run",
                "/fleet/uav_0/gateway/dispatch",
            ],
        )

        self.assertFalse(report.ok)
        self.assertIn("PLATFORM_BACKEND=ros1_gateway", "\n".join(report.validation_errors))

    def test_rosservice_runner_environment_uses_profile_ros_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = _write_ros1_gateway_profile(Path(tmp) / "work_hardware_ros1.env")
            profile = load_profile(profile_path)

            env = ros1_profile_environment(
                profile,
                base_env={
                    "PATH": "/opt/ros/noetic/bin",
                    "ROS_MASTER_URI": "http://wrong-master:11311",
                    "ROS_IP": "192.0.2.10",
                },
            )

        self.assertEqual("/opt/ros/noetic/bin", env["PATH"])
        self.assertEqual("http://127.0.0.1:11311", env["ROS_MASTER_URI"])
        self.assertEqual("127.0.0.1", env["ROS_IP"])


def _write_ros1_gateway_profile(path: Path) -> Path:
    path.write_text("\n".join([
        "MISSION_PROFILE=work_hardware",
        "MODEL_PROVIDER=mock",
        "MODEL_BASE_URL=",
        "MODEL_NAME=",
        "PLANNER_BACKEND=mock",
        "PLATFORM_BACKEND=ros1_gateway",
        "MISSION_STATE_STORE=json",
        "MISSION_ARTIFACT_ROOT=/tmp/changxin-work-hardware-runs",
        "ROS_MASTER_URI=http://127.0.0.1:11311",
        "ROS_IP=127.0.0.1",
        "HARDWARE_APPROVAL_REQUIRED=true",
        "ROS_GATEWAY_DISPATCH_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dispatch",
        "ROS_GATEWAY_DRY_RUN_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dry_run",
    ]), encoding="utf-8")
    return path


if __name__ == "__main__":
    unittest.main()
