import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_planning.migration import build_artifact_package, check_task_planning_site_acceptance


class SiteAcceptanceTest(unittest.TestCase):
    def test_dev_mock_site_acceptance_is_ready_without_ros_runtime(self):
        repo_root = Path(__file__).resolve().parents[2]

        report = check_task_planning_site_acceptance(
            profile_path=repo_root / "profiles/dev_mock.env",
            repo_root=repo_root,
        )

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual("dev_mock_ready", report.acceptance_level)
        self.assertIsNone(report.hardware_gate)

    def test_work_hardware_requires_artifact_package_when_requested(self):
        repo_root = Path(__file__).resolve().parents[2]

        report = check_task_planning_site_acceptance(
            profile_path=repo_root / "profiles/work_hardware.env",
            repo_root=repo_root,
            require_artifact_package=True,
        )

        self.assertFalse(report.ok)
        self.assertIn("at least one verified artifact package is required", report.validation_errors)

    def test_work_hardware_accepts_verified_artifact_package_for_pre_dispatch(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = _write_mission_run(root / "mission-run")
            package = build_artifact_package(
                artifact_paths=[artifact],
                output_dir=root / "package",
                package_name="site-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )

            report = check_task_planning_site_acceptance(
                profile_path=repo_root / "profiles/work_hardware.env",
                repo_root=repo_root,
                artifact_packages=[package.archive],
                artifact_work_dir=root / "verify",
                require_artifact_package=True,
                case_id="uav_ugv_coordination",
            )

            self.assertTrue(report.ok, report.as_dict())
            self.assertEqual("work_hardware_pre_dispatch_ready", report.acceptance_level)
            self.assertEqual("uav_ugv_coordination", report.as_dict()["case_id"])
            self.assertEqual(1, len(report.artifact_packages))
            self.assertTrue(report.artifact_packages[0].ok)
            self.assertEqual("unit_workplace_receiving", report.artifact_packages[0].verification.verification_context)
            self.assertEqual("3333333333333333333333333333333333333333333333333333333333333333", report.artifact_packages[0].verification.source_machine_id)
            self.assertNotEqual(
                report.artifact_packages[0].verification.source_machine_id,
                report.artifact_packages[0].verification.verifier_machine_id,
            )
            self.assertIsNotNone(report.hardware_gate)

    def test_work_hardware_rejects_artifact_package_for_wrong_case(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = _write_mission_run(root / "mission-run", case_id="uav_reconnaissance")
            package = build_artifact_package(
                artifact_paths=[artifact],
                output_dir=root / "package",
                package_name="wrong-case-site-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )

            report = check_task_planning_site_acceptance(
                profile_path=repo_root / "profiles/work_hardware.env",
                repo_root=repo_root,
                artifact_packages=[package.archive],
                artifact_work_dir=root / "verify",
                require_artifact_package=True,
                case_id="uav_ugv_coordination",
            )

            self.assertFalse(report.ok)
            self.assertIn("case_id must match site acceptance case_id", "\n".join(report.validation_errors))

    def test_work_hardware_rosservice_audit_requires_observed_services_when_requested(self):
        repo_root = Path(__file__).resolve().parents[2]

        report = check_task_planning_site_acceptance(
            profile_path=repo_root / "profiles/work_hardware.env",
            repo_root=repo_root,
            platform_ids=["uav_0"],
            require_rosservice_audit=True,
        )

        self.assertFalse(report.ok)
        self.assertIn("ROS1 gateway service acceptance requires PLATFORM_BACKEND=ros1_gateway profile", report.validation_errors)
        self.assertIn("a captured rosservice list is required for ROS1 gateway acceptance", report.validation_errors)

    def test_work_hardware_rosservice_audit_passes_with_matching_capture(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile = _write_ros1_gateway_profile(tmp_path / "work_hardware_ros1.env")
            service_file = tmp_path / "rosservice-list.txt"
            service_file.write_text(
                "\n".join([
                    "/fleet/uav_0/gateway/dry_run",
                    "/fleet/uav_0/gateway/dispatch",
                ]),
                encoding="utf-8",
            )

            report = check_task_planning_site_acceptance(
                profile_path=profile,
                repo_root=repo_root,
                platform_ids=["uav_0"],
                rosservice_list_file=service_file,
                require_rosservice_audit=True,
                command_resolver=_fake_command_resolver,
                import_spec_finder=_fake_import_spec_finder,
            )

            self.assertTrue(report.ok, report.as_dict())
            self.assertEqual("work_hardware_ros1_services_observed", report.acceptance_level)
            self.assertTrue(report.machine_id)
            self.assertEqual("ros1_gateway", report.platform_backend)
            self.assertEqual(2, report.rosservice_audit.observed_service_count)

    def test_work_hardware_rosservice_signature_evidence_upgrades_acceptance(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile = _write_ros1_gateway_profile(tmp_path / "work_hardware_ros1.env")
            service_file = tmp_path / "rosservice-list.txt"
            type_file = tmp_path / "rosservice-types.txt"
            args_file = tmp_path / "rosservice-args.txt"
            service_file.write_text(
                "\n".join([
                    "/fleet/uav_0/gateway/dry_run",
                    "/fleet/uav_0/gateway/dispatch",
                ]),
                encoding="utf-8",
            )
            type_file.write_text(
                "\n".join([
                    "/fleet/uav_0/gateway/dry_run platform_gateway_msgs/TaskCommandJson",
                    "/fleet/uav_0/gateway/dispatch platform_gateway_msgs/TaskCommandJson",
                ]),
                encoding="utf-8",
            )
            args_file.write_text(
                "\n".join([
                    "/fleet/uav_0/gateway/dry_run task_command_json",
                    "/fleet/uav_0/gateway/dispatch task_command_json",
                ]),
                encoding="utf-8",
            )

            report = check_task_planning_site_acceptance(
                profile_path=profile,
                repo_root=repo_root,
                platform_ids=["uav_0"],
                rosservice_list_file=service_file,
                service_type_file=type_file,
                service_args_file=args_file,
                require_rosservice_audit=True,
                require_service_signatures=True,
                command_resolver=_fake_command_resolver,
                import_spec_finder=_fake_import_spec_finder,
            )

            self.assertTrue(report.ok, report.as_dict())
            self.assertEqual("work_hardware_ros1_signatures_observed", report.acceptance_level)
            self.assertTrue(report.as_dict()["machine_id"])
            self.assertEqual("ros1_gateway", report.platform_backend)

    def test_work_hardware_signature_acceptance_requires_service_name_capture(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile = _write_ros1_gateway_profile(tmp_path / "work_hardware_ros1.env")
            type_file = tmp_path / "rosservice-types.txt"
            args_file = tmp_path / "rosservice-args.txt"
            type_file.write_text(
                "\n".join([
                    "/fleet/uav_0/gateway/dry_run platform_gateway_msgs/TaskCommandJson",
                    "/fleet/uav_0/gateway/dispatch platform_gateway_msgs/TaskCommandJson",
                ]),
                encoding="utf-8",
            )
            args_file.write_text(
                "\n".join([
                    "/fleet/uav_0/gateway/dry_run task_command_json",
                    "/fleet/uav_0/gateway/dispatch task_command_json",
                ]),
                encoding="utf-8",
            )

            report = check_task_planning_site_acceptance(
                profile_path=profile,
                repo_root=repo_root,
                platform_ids=["uav_0"],
                service_type_file=type_file,
                service_args_file=args_file,
                require_service_signatures=True,
                command_resolver=_fake_command_resolver,
                import_spec_finder=_fake_import_spec_finder,
            )

            self.assertFalse(report.ok)
            self.assertEqual("work_hardware_pre_dispatch_ready", report.acceptance_level)
            self.assertIn("service-name evidence is required", "\n".join(report.validation_errors))

    def test_site_acceptance_can_collect_read_only_rosservice_signatures(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile = _write_ros1_gateway_profile(tmp_path / "work_hardware_ros1.env")
            calls = []

            def runner(args):
                command = list(args)
                calls.append(command)
                if command == ["rosservice", "list"]:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        stdout="/fleet/uav_0/gateway/dry_run\n/fleet/uav_0/gateway/dispatch\n",
                        stderr="",
                    )
                if command[:2] == ["rosservice", "type"]:
                    return subprocess.CompletedProcess(command, 0, stdout="platform_gateway_msgs/TaskCommandJson\n", stderr="")
                if command[:2] == ["rosservice", "args"]:
                    return subprocess.CompletedProcess(command, 0, stdout="task_command_json\n", stderr="")
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected command")

            report = check_task_planning_site_acceptance(
                profile_path=profile,
                repo_root=repo_root,
                platform_ids=["uav_0"],
                run_rosservice_list=True,
                run_service_signatures=True,
                require_rosservice_audit=True,
                require_service_signatures=True,
                command_resolver=_fake_command_resolver,
                import_spec_finder=_fake_import_spec_finder,
                rosservice_command_runner=runner,
            )

            self.assertTrue(report.ok, report.as_dict())
            self.assertEqual("work_hardware_ros1_signatures_observed", report.acceptance_level)
            self.assertIn(["rosservice", "list"], calls)
            self.assertTrue(all(call[:2] != ["rosservice", "call"] for call in calls))
            self.assertEqual("caller_supplied", report.rosservice_audit.command_environment_source)

    def test_site_acceptance_default_rosservice_runner_uses_profile_environment(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile = _write_ros1_gateway_profile(tmp_path / "work_hardware_ros1.env")
            captured_envs = []

            def fake_run(args, *, env, check, capture_output, text):
                command = list(args)
                captured_envs.append(dict(env))
                if command == ["rosservice", "list"]:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        stdout="/fleet/uav_0/gateway/dry_run\n/fleet/uav_0/gateway/dispatch\n",
                        stderr="",
                    )
                if command[:2] == ["rosservice", "type"]:
                    return subprocess.CompletedProcess(command, 0, stdout="platform_gateway_msgs/TaskCommandJson\n", stderr="")
                if command[:2] == ["rosservice", "args"]:
                    return subprocess.CompletedProcess(command, 0, stdout="task_command_json\n", stderr="")
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected command")

            with mock.patch.dict(
                os.environ,
                {
                    "ROS_MASTER_URI": "http://wrong-master:11311",
                    "ROS_IP": "192.0.2.10",
                },
            ), mock.patch("task_planning.migration.ros1_service_audit.subprocess.run", side_effect=fake_run):
                report = check_task_planning_site_acceptance(
                    profile_path=profile,
                    repo_root=repo_root,
                    platform_ids=["uav_0"],
                    run_rosservice_list=True,
                    run_service_signatures=True,
                    require_rosservice_audit=True,
                    require_service_signatures=True,
                    command_resolver=_fake_command_resolver,
                    import_spec_finder=_fake_import_spec_finder,
                )

            self.assertTrue(report.ok, report.as_dict())
            self.assertEqual("work_hardware_ros1_signatures_observed", report.acceptance_level)
            self.assertEqual("profile", report.rosservice_audit.command_environment_source)
            self.assertTrue(captured_envs)
            self.assertTrue(all(env["ROS_MASTER_URI"] == "http://127.0.0.1:11311" for env in captured_envs))
            self.assertTrue(all(env["ROS_IP"] == "127.0.0.1" for env in captured_envs))

    def test_tampered_artifact_package_blocks_site_acceptance(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = _write_mission_run(root / "mission-run")
            package = build_artifact_package(
                artifact_paths=[artifact],
                output_dir=root / "package",
                package_name="tampered-site-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            (package.root / "artifacts" / "mission-run" / "run_summary.md").write_text("tampered\n", encoding="utf-8")
            tampered = root / "tampered.tar.gz"
            with tarfile.open(tampered, "w:gz") as tar:
                tar.add(package.root, arcname=package.root.name)

            report = check_task_planning_site_acceptance(
                profile_path=repo_root / "profiles/work_hardware.env",
                repo_root=repo_root,
                artifact_packages=[tampered],
                artifact_work_dir=root / "verify",
                require_artifact_package=True,
            )

            self.assertFalse(report.ok)
            self.assertTrue(any("sha256 mismatch" in error for error in report.validation_errors))


def _write_mission_run(root: Path, *, case_id: str = "uav_ugv_coordination") -> Path:
    root.mkdir(parents=True)
    json_files = {
        "environment_profile.json": {
            "schema": "EnvironmentProfile.v1",
            "mission_profile": "dev_mock",
            "model_provider": "mock",
            "platform_backend": "mock",
        },
        "mission_input.json": {"schema": "MissionInput.v1", "run_input": {"case_id": case_id}},
        "model_output.json": {"schema": "ModelOutput.v1", "output": {}},
        "task_schema.json": {"schema": "TaskSchema.v1", "mission_request": {}},
        "validation_report.json": {"schema": "ValidationReport.v1", "status": "passed", "errors": [], "current_state": "COMPLETE"},
        "blackboard_snapshot.json": {"schema": "MissionBlackboard.v1"},
        "planner_output.json": {"schema": "PddlPlan.v1", "steps": []},
        "bt_artifact.json": {"schema": "BehaviorTree.v1", "task_commands": []},
        "gateway_trace.json": {"schema": "GatewayTrace.v1", "records": []},
        "command_acks.json": {"schema": "CommandAckSet.v1", "items": []},
        "task_progress.json": {"schema": "TaskProgressSet.v1", "items": []},
        "failure_report.json": {"schema": "FailureReport.v1", "status": "not_reported"},
        "replan_decision.json": {"schema": "ReplanRequest.v1", "status": "not_requested"},
    }
    for filename, data in json_files.items():
        (root / filename).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    (root / "pddl_problem.pddl").write_text("(define (problem test))\n", encoding="utf-8")
    (root / "run_summary.md").write_text("# Mission Run\n", encoding="utf-8")
    return root


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


def _fake_command_resolver(command: str) -> str:
    return f"/opt/ros/noetic/bin/{command}"


def _fake_import_spec_finder(name: str):
    return object()


if __name__ == "__main__":
    unittest.main()
