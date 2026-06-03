import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from task_planning.migration import build_migration_bundle


class MigrationBundleTest(unittest.TestCase):
    def test_package_cli_accepts_source_machine_id_override(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "package_task_planning_migration.py"),
                    "--output-dir",
                    str(root / "out"),
                    "--bundle-name",
                    "bundle-cli-under-test",
                    "--source-machine-id",
                    "1111111111111111111111111111111111111111111111111111111111111111",
                ],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

            bundle = json.loads(completed.stdout)
            manifest = json.loads(Path(bundle["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual("1111111111111111111111111111111111111111111111111111111111111111", manifest["source_machine_id"])

    def test_build_migration_bundle_rejects_unhashed_source_machine_id(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "64-character lowercase sha256"):
                build_migration_bundle(
                    repo_root=repo_root,
                    output_dir=Path(tmp),
                    source_machine_id="not-a-hash",
                )

    def test_migration_bundle_contains_required_lanes_gateway_and_commands(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_migration_bundle(
                repo_root=repo_root,
                output_dir=Path(tmp),
                bundle_name="bundle-under-test",
            )

            manifest = json.loads(bundle.manifest.read_text(encoding="utf-8"))
            paths = {item["path"] for item in manifest["files"]}

            self.assertEqual("TaskPlanningMigrationManifest.v1", manifest["schema"])
            self.assertIn("MIGRATION.md", paths)
            self.assertIn("profiles/dev_mock.env", paths)
            self.assertIn("profiles/home_model_lab.env", paths)
            self.assertIn("profiles/home_model_lab_mock_endpoint.env", paths)
            self.assertIn("profiles/server_sim.env", paths)
            self.assertIn("profiles/work_hardware.env", paths)
            self.assertIn("profiles/work_hardware_ros1_gateway.env.template", paths)
            self.assertIn("docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md", paths)
            self.assertIn("docs/superpowers/specs/2026-05-29-windows-safe-unit-receiving-kit.md", paths)
            self.assertIn("docs/superpowers/specs/2026-06-02-distributed-fleet-phase-2-to-langgraph-roadmap.md", paths)
            self.assertIn("docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md", paths)
            self.assertIn("docs/superpowers/specs/2026-06-03-ugv-phase-2a-mac-to-4060-handoff.md", paths)
            self.assertIn("docs/superpowers/plans/2026-06-03-phase-2b-no-hardware-operations-reporting.md", paths)
            self.assertIn("docs/superpowers/specs/2026-06-03-phase-2b-operator-view-signals.md", paths)
            self.assertIn("task_planning/mission_ops/golden_cases.py", paths)
            self.assertIn("task_planning/mission_ops/replay.py", paths)
            self.assertIn("task_planning/hardware/gates.py", paths)
            self.assertIn("task_planning/migration/lane_matrix.py", paths)
            self.assertIn("task_planning/migration/readiness.py", paths)
            self.assertIn("platform_gateway/ros/catkin_pkg/platform_gateway_msgs/srv/TaskCommandJson.srv", paths)
            self.assertIn("tools/check_model_lab_endpoint.py", paths)
            self.assertIn("tools/check_distributed_fleet_phase_gate.py", paths)
            self.assertIn("tools/check_distributed_fleet_goal_evidence.py", paths)
            self.assertIn("tools/check_phase2_no_motion_acceptance.py", paths)
            self.assertIn("tools/check_task_planning_readiness.py", paths)
            self.assertIn("tools/check_task_planning_site_acceptance.py", paths)
            self.assertIn("tools/collect_distributed_fleet_evidence.py", paths)
            self.assertIn("tools/init_external_evidence_handoff.py", paths)
            self.assertIn("tools/import_distributed_fleet_external_evidence.py", paths)
            self.assertIn("tools/package_distributed_fleet_handoff.py", paths)
            self.assertIn("tools/verify_distributed_fleet_handoff_package.py", paths)
            self.assertIn("task_planning/migration/handoff_package.py", paths)
            self.assertIn("tools/run_mock_model_lab_endpoint.py", paths)
            self.assertIn("tools/run_dev_mock_golden_suite.py", paths)
            self.assertIn("tools/evaluate_model_lab_case.py", paths)
            self.assertIn("tools/extract_task_command_from_artifact.py", paths)
            self.assertIn("tools/package_task_planning_artifacts.py", paths)
            self.assertIn("tools/audit_ros1_gateway_services.py", paths)
            self.assertIn("tools/prepare_ros1_gateway_workspace.py", paths)
            self.assertIn("tools/record_unit_hardware_dispatch_artifact.py", paths)
            self.assertIn("tools/replay_task_planning_artifact.py", paths)
            self.assertIn("tools/run_ros1_platform_gateway_node.py", paths)
            self.assertIn("tools/run_prevalidated_task_schema.py", paths)
            self.assertIn("tools/run_task_planning_lane_matrix.py", paths)
            self.assertIn("tools/verify_task_planning_artifacts.py", paths)
            self.assertIn("tools/unit_receiving_wsl2.sh", paths)
            self.assertIn("tools/windows_unit_receiving_entry.ps1", paths)
            self.assertIn("tools/verify_task_planning_migration_bundle.py", paths)
            self.assertIn("lane_matrix", manifest["commands"])
            self.assertIn("audit_ros1_gateway_services", manifest["commands"])
            self.assertIn("check_task_planning_site_acceptance.py", manifest["commands"]["audit_ros1_gateway_services"])
            self.assertIn("--run-service-signatures", manifest["commands"]["audit_ros1_gateway_services"])
            self.assertIn("prepare_ros1_gateway_workspace", manifest["commands"])
            self.assertIn("work_hardware_gate", manifest["commands"])
            self.assertIn("readiness", manifest["commands"])
            self.assertIn("site_acceptance", manifest["commands"])
            self.assertIn("phase_gate", manifest["commands"])
            self.assertIn("goal_evidence", manifest["commands"])
            self.assertIn("goal_evidence_missing_only", manifest["commands"])
            self.assertIn("collect_evidence", manifest["commands"])
            self.assertIn("external_evidence_handoff", manifest["commands"])
            self.assertIn("import_external_evidence", manifest["commands"])
            self.assertIn("handoff_package", manifest["commands"])
            self.assertIn("verify_handoff_package", manifest["commands"])
            self.assertIn("dev_mock_golden_suite", manifest["commands"])
            self.assertIn("model_lab_evaluation", manifest["commands"])
            self.assertIn("mock_model_lab_endpoint", manifest["commands"])
            self.assertIn("mock_model_lab_check", manifest["commands"])
            self.assertIn("package_artifacts", manifest["commands"])
            self.assertIn("extract_task_command", manifest["commands"])
            self.assertIn("record_unit_hardware_dispatch_artifact", manifest["commands"])
            self.assertIn("verify_artifacts", manifest["commands"])
            self.assertIn("prevalidated_schema_replay", manifest["commands"])
            self.assertIn("phase2_no_motion_acceptance", manifest["commands"])
            self.assertIn("check_phase2_no_motion_acceptance.py", manifest["commands"]["phase2_no_motion_acceptance"])
            self.assertIn("verify_bundle", manifest["commands"])
            self.assertIn("windows_unit_receiving", manifest["commands"])
            migration_doc = (bundle.root / "MIGRATION.md").read_text(encoding="utf-8")
            self.assertIn("The unit/workplace platform is the hardware execution endpoint.", migration_doc)
            self.assertIn("2026-05-26-unit-execution-agent-runbook.md", migration_doc)
            self.assertIn("The home RTX 5090 server is only a model-capability lab", migration_doc)
            self.assertIn("tools/windows_unit_receiving_entry.ps1", migration_doc)
            self.assertIn("C:\\changxin-evidence\\logs", migration_doc)
            self.assertIn("/tmp/changxin-distributed-fleet-evidence", migration_doc)
            self.assertIn("check_task_planning_readiness.py --profile profiles/work_hardware.env", migration_doc)
            self.assertIn("check_task_planning_site_acceptance.py --profile profiles/work_hardware.env", migration_doc)
            self.assertIn("check_distributed_fleet_phase_gate.py --evidence-dir /tmp/changxin-distributed-fleet-evidence", migration_doc)
            self.assertIn("check_distributed_fleet_goal_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence", migration_doc)
            self.assertIn("check_phase2_no_motion_acceptance.py --artifact-root <artifact_root>", migration_doc)
            self.assertIn("--missing-only --print-discovered-inputs", migration_doc)
            self.assertIn("collect_distributed_fleet_evidence.py --output-dir /tmp/changxin-distributed-fleet-evidence", migration_doc)
            self.assertIn("init_external_evidence_handoff.py --evidence-dir /tmp/changxin-distributed-fleet-evidence", migration_doc)
            self.assertIn("package_distributed_fleet_handoff.py --output-dir /tmp/changxin-handoff-package", migration_doc)
            self.assertIn("verify_distributed_fleet_handoff_package.py /path/to/distributed-fleet-handoff-package.tar.gz", migration_doc)
            self.assertIn("verify_task_planning_migration_bundle.py /path/to/task-planning-migration-bundle.tar.gz --work-dir /tmp/changxin-migration-verify --verification-context receiving_machine", migration_doc)
            self.assertIn("run_dev_mock_golden_suite.py --artifact-root /tmp/changxin-dev-mock-golden-suite", migration_doc)
            self.assertIn("run_task_planning_lane_matrix.py --artifact-root /tmp/changxin-lane-matrix", migration_doc)
            self.assertIn("prepare_ros1_gateway_workspace.py --catkin-src ~/catkin_ws/src", migration_doc)
            self.assertIn("check_task_planning_site_acceptance.py --profile <local-work-hardware-ros1-gateway.env>", migration_doc)
            self.assertIn("--run-rosservice-list --run-service-signatures", migration_doc)
            self.assertIn("evaluate_model_lab_case.py --profile profiles/home_model_lab.env", migration_doc)
            self.assertIn("run_mock_model_lab_endpoint.py --port 8000", migration_doc)
            self.assertIn("MODEL_LAB_EVIDENCE_KIND=mock_endpoint", migration_doc)
            self.assertIn("package_task_planning_artifacts.py --artifact /tmp/changxin-model-lab/uav_ugv_coordination", migration_doc)
            self.assertIn("extract_task_command_from_artifact.py <artifact_bundle_path>", migration_doc)
            self.assertIn("record_unit_hardware_dispatch_artifact.py --source-artifact", migration_doc)
            self.assertIn("verify_task_planning_artifacts.py /path/to/task-planning-artifacts.tar.gz", migration_doc)
            self.assertIn("--verification-context unit_workplace_receiving", migration_doc)
            self.assertIn("run_prevalidated_task_schema.py --profile profiles/work_hardware.env", migration_doc)
            self.assertTrue(bundle.archive.exists())
            with tarfile.open(bundle.archive, "r:gz") as tar:
                names = set(tar.getnames())
            self.assertIn("bundle-under-test/MIGRATION.md", names)

    def test_migration_bundle_excludes_generated_and_binary_outputs(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_migration_bundle(repo_root=repo_root, output_dir=Path(tmp))
            manifest = json.loads(bundle.manifest.read_text(encoding="utf-8"))

        paths = {item["path"] for item in manifest["files"]}
        self.assertFalse(any("__pycache__" in path for path in paths))
        self.assertFalse(any(path.endswith(".docx") for path in paths))
        self.assertFalse(any(path.endswith(".xlsx") for path in paths))
        self.assertFalse(any(path.startswith("runs/") for path in paths))


if __name__ == "__main__":
    unittest.main()
