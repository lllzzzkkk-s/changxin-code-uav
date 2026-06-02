import tempfile
import unittest
from pathlib import Path

from task_planning.migration import check_task_planning_readiness


class MigrationReadinessTest(unittest.TestCase):
    def test_dev_mock_readiness_passes_without_ros_runtime(self):
        repo_root = Path(__file__).resolve().parents[2]

        report = check_task_planning_readiness(
            repo_root / "profiles/dev_mock.env",
            repo_root=repo_root,
            command_resolver=lambda _command: None,
            import_spec_finder=lambda _name: None,
        )

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual("dev_mock", report.mission_profile)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests/task_planning", report.next_commands)
        self.assertTrue(any("run_dev_mock_golden_suite.py" in command for command in report.next_commands))
        self.assertEqual("skip", _check(report, "ros_cli_rostopic").status)

    def test_work_hardware_mock_readiness_warns_but_does_not_fail_without_ros_runtime(self):
        repo_root = Path(__file__).resolve().parents[2]

        report = check_task_planning_readiness(
            repo_root / "profiles/work_hardware.env",
            repo_root=repo_root,
            command_resolver=lambda _command: None,
            import_spec_finder=lambda _name: None,
        )

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual("work_hardware", report.mission_profile)
        self.assertEqual("pass", _check(report, "unit_execution_boundary").status)
        self.assertEqual("warn", _check(report, "ros_cli_rostopic").status)
        self.assertTrue(any("plan_work_hardware_gate.py" in command for command in report.next_commands))

    def test_work_hardware_real_gateway_fails_without_ros_runtime(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "work_hardware_ros1.env"
            profile.write_text("\n".join([
                "MISSION_PROFILE=work_hardware",
                "MODEL_PROVIDER=mock",
                "MODEL_BASE_URL=",
                "MODEL_NAME=",
                "PLANNER_BACKEND=mock",
                "PLATFORM_BACKEND=ros1_gateway",
                "MISSION_STATE_STORE=json",
                f"MISSION_ARTIFACT_ROOT={tmp}/runs",
                "ROS_MASTER_URI=http://127.0.0.1:11311",
                "ROS_IP=127.0.0.1",
                "HARDWARE_APPROVAL_REQUIRED=true",
                "ROS_GATEWAY_DISPATCH_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dispatch",
                "ROS_GATEWAY_DRY_RUN_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dry_run",
            ]), encoding="utf-8")

            report = check_task_planning_readiness(
                profile,
                repo_root=repo_root,
                command_resolver=lambda _command: None,
                import_spec_finder=lambda _name: None,
            )

            self.assertFalse(report.ok)
            self.assertEqual("fail", _check(report, "ros_cli_rosservice").status)
            self.assertEqual("fail", _check(report, "python_rospy").status)

    def test_home_model_lab_readiness_keeps_hardware_boundary(self):
        repo_root = Path(__file__).resolve().parents[2]

        report = check_task_planning_readiness(
            repo_root / "profiles/home_model_lab.env",
            repo_root=repo_root,
            command_resolver=lambda _command: None,
            import_spec_finder=lambda _name: None,
        )

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual("home_model_lab", report.mission_profile)
        self.assertEqual("pass", _check(report, "hardware_boundary").status)
        self.assertEqual("warn", _check(report, "model_endpoint_probe").status)
        self.assertTrue(any("check_model_lab_endpoint.py" in command for command in report.next_commands))
        self.assertTrue(any("package_task_planning_artifacts.py" in command for command in report.next_commands))

    def test_work_hardware_readiness_starts_with_artifact_verification(self):
        repo_root = Path(__file__).resolve().parents[2]

        report = check_task_planning_readiness(
            repo_root / "profiles/work_hardware.env",
            repo_root=repo_root,
            command_resolver=lambda _command: None,
            import_spec_finder=lambda _name: None,
        )

        self.assertIn("check_task_planning_site_acceptance.py", report.next_commands[0])
        self.assertTrue(any("verify_task_planning_artifacts.py" in command for command in report.next_commands))


def _check(report, name):
    matches = [check for check in report.checks if check.name == name]
    if not matches:
        raise AssertionError(f"missing readiness check {name!r}: {report.as_dict()}")
    return matches[0]


if __name__ == "__main__":
    unittest.main()
