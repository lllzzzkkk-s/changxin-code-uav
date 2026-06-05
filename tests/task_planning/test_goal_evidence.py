import json
import tempfile
import unittest
from pathlib import Path

from task_planning.migration import (
    build_artifact_package,
    build_distributed_fleet_goal_evidence,
    discover_goal_evidence_inputs,
    summarize_goal_evidence_report,
    verify_artifact_package,
)


class GoalEvidenceTest(unittest.TestCase):
    def test_goal_evidence_reports_missing_external_proof_by_default(self):
        repo_root = Path(__file__).resolve().parents[2]

        report = build_distributed_fleet_goal_evidence(repo_root=repo_root)

        self.assertFalse(report.ok)
        missing = {item.name for item in report.missing_required}
        self.assertIn("home_5090_model_lab_evaluated", missing)
        self.assertIn("lane_matrix_comparable", missing)
        self.assertIn("dev_mock_golden_suite_recorded", missing)
        self.assertIn("unit_ros1_gateway_signatures_observed", missing)
        self.assertIn("unit_hardware_execution_artifact_verified", missing)
        passed = {item.name for item in report.items if item.status == "pass"}
        self.assertIn("mock_first_model_boundary", passed)

    def test_goal_evidence_summary_keeps_missing_items_actionable(self):
        repo_root = Path(__file__).resolve().parents[2]

        report = build_distributed_fleet_goal_evidence(repo_root=repo_root)
        summary = summarize_goal_evidence_report(report, missing_only=True)

        self.assertEqual("DistributedFleetGoalEvidenceSummary.v1", summary["schema"])
        self.assertFalse(summary["ok"])
        self.assertGreaterEqual(summary["counts"]["missing_required"], 1)
        names = {item["name"] for item in summary["items"]}
        self.assertIn("home_5090_model_lab_evaluated", names)
        self.assertIn("lane_matrix_comparable", names)
        self.assertIn("unit_ros1_gateway_signatures_observed", names)
        self.assertNotIn("mock_first_model_boundary", names)
        self.assertTrue(any(
            item["next_commands"]
            for item in summary["items"]
            if item["name"] == "home_5090_model_lab_evaluated"
        ))
        self.assertEqual("DistributedFleetPhaseGate.v1", summary["phase_gate"]["schema"])
        self.assertEqual("local_implementation_required", summary["phase_gate"]["status"])
        self.assertFalse(summary["phase_gate"]["local_v1_freeze"])

    def test_goal_evidence_phase_gate_freezes_local_v1_when_only_external_proofs_are_missing(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            golden_suite_report = root / "dev_mock_golden_suite.json"
            site_report = root / "site_acceptance_work_hardware.json"
            _write_lane_matrix_report(lane_matrix_report)
            _write_golden_suite_report(golden_suite_report)
            _write_site_ros1_report(
                site_report,
                platform_backend="mock",
                acceptance_level="work_hardware_pre_dispatch_ready",
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
                lane_matrix_reports=[lane_matrix_report],
                dev_mock_golden_suite_reports=[golden_suite_report],
            )

            phase_gate = report.phase_gate
            self.assertEqual("waiting_for_external_proofs", phase_gate["status"])
            self.assertTrue(phase_gate["local_v1_freeze"])
            self.assertFalse(phase_gate["next_phase_ready"])
            self.assertEqual([], phase_gate["local_unresolved_required"])
            self.assertEqual([
                "artifact_package_verified_after_transfer",
                "home_5090_model_lab_evaluated",
                "migration_bundle_verified_after_transfer",
                "unit_hardware_execution_artifact_verified",
                "unit_ros1_gateway_signatures_observed",
            ], phase_gate["missing_external_proofs"])
            self.assertIn("Do not keep iterating local implementation", phase_gate["policy"])

    def test_goal_evidence_accepts_supplied_external_reports(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = _write_mission_run(root / "mission-run")
            model_lab_artifact = _write_model_lab_artifact(root / "model-lab")
            package = build_artifact_package(
                artifact_paths=[artifact, model_lab_artifact],
                output_dir=root / "package",
                package_name="goal-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            package_report = root / "artifact_package_verification.json"
            package_report.write_text(json.dumps(
                verify_artifact_package(
                    archive_path=package.archive,
                    work_dir=root / "verify-package",
                    verification_context="unit_workplace_receiving",
                ).as_dict(),
                indent=2,
                sort_keys=True,
            ), encoding="utf-8")
            site_report = root / "site.json"
            _write_site_ros1_report(site_report)
            model_report = root / "model_lab_evaluation.json"
            _write_model_lab_report(model_report)
            golden_suite_report = root / "dev_mock_golden_suite.json"
            golden_suite_report.write_text(json.dumps({
                "schema": "DevMockGoldenSuite.v1",
                "ok": True,
                "required_case_ids": [
                    "single_ugv_inspection",
                    "single_ugv_object_approach",
                    "uav_reconnaissance",
                    "uav_ugv_coordination",
                    "failure_and_replan",
                    "disconnect_continue_authorized_subtree",
                ],
                "case_results": [
                    {"case_id": "single_ugv_inspection", "ok": True, "run_id": "run-1", "artifact_bundle_path": "/tmp/run-1"},
                    {"case_id": "single_ugv_object_approach", "ok": True, "run_id": "run-2", "artifact_bundle_path": "/tmp/run-2"},
                    {"case_id": "uav_reconnaissance", "ok": True, "run_id": "run-3", "artifact_bundle_path": "/tmp/run-3"},
                    {"case_id": "uav_ugv_coordination", "ok": True, "run_id": "run-4", "artifact_bundle_path": "/tmp/run-4"},
                    {"case_id": "failure_and_replan", "ok": True, "run_id": "run-5", "artifact_bundle_path": "/tmp/run-5"},
                    {"case_id": "disconnect_continue_authorized_subtree", "ok": True, "run_id": "run-6", "artifact_bundle_path": "/tmp/run-6"},
                ],
            }), encoding="utf-8")
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            migration_report = root / "migration.json"
            migration_report.write_text(json.dumps(
                _migration_verification_dict(verification_context="receiving_machine"),
                indent=2,
                sort_keys=True,
            ), encoding="utf-8")
            hardware_artifact = _write_hardware_run(root / "hardware-run")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_packages=[package.archive],
                artifact_package_verification_reports=[package_report],
                artifact_work_dir=root / "verify",
                site_acceptance_reports=[site_report],
                lane_matrix_reports=[lane_matrix_report],
                dev_mock_golden_suite_reports=[golden_suite_report],
                model_lab_evaluations=[model_report],
                migration_verification_reports=[migration_report],
                hardware_run_artifacts=[hardware_artifact],
            )

            self.assertTrue(report.ok, report.as_dict())
            statuses = {item.name: item.status for item in report.items}
            self.assertEqual("pass", statuses["artifact_package_verified_after_transfer"])
            artifact_item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("3333333333333333333333333333333333333333333333333333333333333333", artifact_item.evidence["report_validations"][0]["source_machine_ids"][0])
            self.assertEqual("pass", statuses["lane_matrix_comparable"])
            self.assertEqual("pass", statuses["dev_mock_golden_suite_recorded"])
            self.assertEqual("pass", statuses["home_5090_model_lab_evaluated"])
            self.assertEqual("pass", statuses["unit_hardware_execution_artifact_verified"])
            self.assertEqual("next_phase_ready", report.phase_gate["status"])
            self.assertTrue(report.phase_gate["next_phase_ready"])

    def test_goal_evidence_rejects_work_site_acceptance_without_machine_id(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            site_report = Path(tmp) / "site.json"
            _write_site_ros1_report(site_report, machine_id="")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["work_hardware_site_acceptance_recorded"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["accepted_count"])
            self.assertIn("machine_id", "\n".join(item.evidence["report_validations"][0]["errors"]))

    def test_goal_evidence_rejects_work_site_acceptance_without_readiness_and_hardware_gate(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            site_report = Path(tmp) / "site.json"
            _write_site_ros1_report(site_report)
            data = json.loads(site_report.read_text(encoding="utf-8"))
            data.pop("readiness", None)
            data.pop("hardware_gate", None)
            site_report.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["work_hardware_site_acceptance_recorded"]
            self.assertEqual("missing", item.status)
            errors = "\n".join(item.evidence["report_validations"][0]["errors"])
            self.assertIn("readiness", errors)
            self.assertIn("hardware_gate", errors)

    def test_goal_evidence_discovers_standard_evidence_directory_inputs(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "evidence" / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            _write_golden_suite_report(reports / "dev_mock_golden_suite.json")
            _write_site_ros1_report(reports / "site_acceptance_work_hardware_ros1.json")
            _write_model_lab_report(reports / "model_lab_evaluation.json")
            (reports / "migration_verification.json").write_text(json.dumps(
                _migration_verification_dict(verification_context="receiving_machine"),
                indent=2,
                sort_keys=True,
            ), encoding="utf-8")
            handoff_report = reports / "handoff_package_verification.json"
            _write_handoff_package_verification_report(handoff_report, verification_context="receiving_machine")
            artifact = _write_mission_run(root / "mission-run")
            model_lab_artifact = _write_model_lab_artifact(root / "model-lab")
            package = build_artifact_package(
                artifact_paths=[artifact, model_lab_artifact],
                output_dir=root / "evidence" / "artifact_packages",
                package_name="discovered-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            package_report = reports / "artifact_package_verification.json"
            package_report.write_text(json.dumps(
                verify_artifact_package(
                    archive_path=package.archive,
                    work_dir=root / "evidence" / "_artifact_package_verify",
                    verification_context="unit_workplace_receiving",
                ).as_dict(),
                indent=2,
                sort_keys=True,
            ), encoding="utf-8")
            self.assertTrue(package.archive.exists())
            hardware_artifact = _write_hardware_run(root / "evidence" / "hardware_artifacts" / "hardware-run")

            discovered = discover_goal_evidence_inputs([root / "evidence"])
            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_packages=discovered.artifact_packages,
                artifact_package_verification_reports=discovered.artifact_package_verification_reports,
                artifact_work_dir=discovered.artifact_work_dir,
                site_acceptance_reports=discovered.site_acceptance_reports,
                lane_matrix_reports=discovered.lane_matrix_reports,
                dev_mock_golden_suite_reports=discovered.dev_mock_golden_suite_reports,
                model_lab_evaluations=discovered.model_lab_evaluations,
                migration_verification_reports=discovered.migration_verification_reports,
                handoff_package_verification_reports=discovered.handoff_package_verification_reports,
                hardware_run_artifacts=discovered.hardware_run_artifacts,
            )

            self.assertEqual([package.archive.resolve()], discovered.artifact_packages)
            self.assertEqual([(reports / "lane_matrix.json").resolve()], discovered.lane_matrix_reports)
            self.assertEqual([package_report.resolve()], discovered.artifact_package_verification_reports)
            self.assertEqual([handoff_report.resolve()], discovered.handoff_package_verification_reports)
            self.assertEqual([hardware_artifact.resolve()], discovered.hardware_run_artifacts)
            self.assertTrue(report.ok, report.as_dict())

    def test_goal_evidence_rejects_lane_matrix_without_work_hardware_pre_dispatch_comparison(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            lane_matrix_report = Path(tmp) / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report, include_work_hardware_comparison=False)

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["lane_matrix_comparable"]
            self.assertEqual("fail", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn(
                "dev_mock_vs_work_hardware_pre_dispatch",
                "\n".join(item.evidence["validations"][0]["errors"]),
            )

    def test_goal_evidence_does_not_accept_source_only_artifact_package_as_transfer_proof(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="source-only-artifacts",
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_packages=[package.archive],
                artifact_work_dir=root / "verify",
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(1, item.evidence["direct_ok_count"])

    def test_goal_evidence_rejects_source_machine_migration_verification_report(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            migration_report = Path(tmp) / "migration.json"
            migration_report.write_text(json.dumps({
                "ok": True,
                "schema": "MigrationVerification.v1",
                "verification_context": "source_machine",
            }), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                migration_verification_reports=[migration_report],
            )

            item = {item.name: item for item in report.items}["migration_bundle_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])

    def test_goal_evidence_rejects_receiving_migration_verification_without_manifest_audit(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            migration_report = Path(tmp) / "migration.json"
            migration_report.write_text(json.dumps({
                "ok": True,
                "schema": "MigrationVerification.v1",
                "verification_context": "receiving_machine",
                "source_machine_id": "3333333333333333333333333333333333333333333333333333333333333333",
                "verifier_machine_id": "4444444444444444444444444444444444444444444444444444444444444444",
            }), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                migration_verification_reports=[migration_report],
            )

            item = {item.name: item for item in report.items}["migration_bundle_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            self.assertIn("manifest", "\n".join(item.evidence["validations"][0]["errors"]))

    def test_goal_evidence_accepts_receiving_handoff_package_verification_as_migration_proof(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            handoff_report = Path(tmp) / "handoff_package_verification.json"
            _write_handoff_package_verification_report(handoff_report, verification_context="receiving_machine")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                handoff_package_verification_reports=[handoff_report],
            )

            item = {item.name: item for item in report.items}["migration_bundle_verified_after_transfer"]
            self.assertEqual("pass", item.status)
            self.assertEqual(1, item.evidence["receiving_ok_count"])
            self.assertEqual(1, item.evidence["handoff_report_count"])

    def test_goal_evidence_rejects_source_machine_handoff_package_verification(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            handoff_report = Path(tmp) / "handoff_package_verification.json"
            _write_handoff_package_verification_report(handoff_report, verification_context="source_machine")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                handoff_package_verification_reports=[handoff_report],
            )

            item = {item.name: item for item in report.items}["migration_bundle_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])

    def test_goal_evidence_rejects_receiving_handoff_verification_on_source_machine(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            handoff_report = Path(tmp) / "handoff_package_verification.json"
            _write_handoff_package_verification_report(
                handoff_report,
                verification_context="receiving_machine",
                source_machine_id="5555555555555555555555555555555555555555555555555555555555555555",
                verifier_machine_id="5555555555555555555555555555555555555555555555555555555555555555",
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                handoff_package_verification_reports=[handoff_report],
            )

            item = {item.name: item for item in report.items}["migration_bundle_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            self.assertTrue(any(
                "source_machine_id and verifier_machine_id must differ" in error
                for error in item.evidence["handoff_validations"][0]["errors"]
            ))

    def test_goal_evidence_rejects_handoff_migration_identity_mismatch(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            handoff_report = Path(tmp) / "handoff_package_verification.json"
            _write_handoff_package_verification_report(
                handoff_report,
                verification_context="receiving_machine",
                migration_verifier_machine_id="8888888888888888888888888888888888888888888888888888888888888888",
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                handoff_package_verification_reports=[handoff_report],
            )

            item = {item.name: item for item in report.items}["migration_bundle_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            self.assertTrue(any(
                "embedded migration_verification verifier_machine_id" in error
                for error in item.evidence["handoff_validations"][0]["errors"]
            ))

    def test_goal_evidence_rejects_handoff_without_verifier_audit(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            handoff_report = Path(tmp) / "handoff_package_verification.json"
            handoff_report.write_text(json.dumps({
                "schema": "DistributedFleetHandoffPackageVerification.v1",
                "ok": True,
                "verification_context": "receiving_machine",
                "source_machine_id": "3333333333333333333333333333333333333333333333333333333333333333",
                "verifier_machine_id": "4444444444444444444444444444444444444444444444444444444444444444",
                "migration_verification": _migration_verification_dict(verification_context="receiving_machine"),
            }), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                handoff_package_verification_reports=[handoff_report],
            )

            item = {item.name: item for item in report.items}["migration_bundle_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            self.assertIn("archive", "\n".join(item.evidence["handoff_validations"][0]["errors"]))

    def test_goal_evidence_rejects_handoff_with_embedded_migration_missing_manifest_audit(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            handoff_report = Path(tmp) / "handoff_package_verification.json"
            handoff_report.write_text(json.dumps({
                "schema": "DistributedFleetHandoffPackageVerification.v1",
                "ok": True,
                "archive": "/tmp/distributed-fleet-handoff-package.tar.gz",
                "extract_dir": "/tmp/changxin-handoff-verify",
                "package_root": "/tmp/changxin-handoff-verify/distributed-fleet-handoff-package",
                "checked_files": 18,
                "verification_context": "receiving_machine",
                "source_machine_id": "3333333333333333333333333333333333333333333333333333333333333333",
                "verifier_machine_id": "4444444444444444444444444444444444444444444444444444444444444444",
                "manifest_errors": [],
                "component_errors": [],
                "migration_verification": {
                    "schema": "MigrationVerification.v1",
                    "ok": True,
                    "verification_context": "receiving_machine",
                    "source_machine_id": "3333333333333333333333333333333333333333333333333333333333333333",
                    "verifier_machine_id": "4444444444444444444444444444444444444444444444444444444444444444",
                },
            }), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                handoff_package_verification_reports=[handoff_report],
            )

            item = {item.name: item for item in report.items}["migration_bundle_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            errors = "\n".join(item.evidence["handoff_validations"][0]["errors"])
            self.assertIn("migration_verification", errors)
            self.assertIn("manifest", errors)

    def test_goal_evidence_rejects_source_machine_artifact_verification_report(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="source-report-artifacts",
            )
            package_report = root / "artifact_package_verification.json"
            package_report.write_text(json.dumps(
                verify_artifact_package(
                    archive_path=package.archive,
                    work_dir=root / "verify-source",
                    verification_context="source_machine",
                ).as_dict(),
                indent=2,
                sort_keys=True,
            ), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_package_verification_reports=[package_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])

    def test_goal_evidence_rejects_unit_receiving_artifact_verification_on_source_machine(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="same-machine-artifacts",
            )
            package_report = root / "artifact_package_verification.json"
            package_report.write_text(json.dumps(
                verify_artifact_package(
                    archive_path=package.archive,
                    work_dir=root / "verify-source",
                    verification_context="unit_workplace_receiving",
                ).as_dict(),
                indent=2,
                sort_keys=True,
            ), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_package_verification_reports=[package_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            self.assertTrue(any(
                "source_machine_id and verifier_machine_id must differ" in error
                for error in item.evidence["report_validations"][0]["errors"]
            ))

    def test_goal_evidence_rejects_generic_receiving_artifact_verification_report(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="generic-receiving-artifacts",
            )
            package_report = root / "artifact_package_verification.json"
            package_report.write_text(json.dumps(
                verify_artifact_package(
                    archive_path=package.archive,
                    work_dir=root / "verify-receiving",
                    verification_context="receiving_machine",
                ).as_dict(),
                indent=2,
                sort_keys=True,
            ), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_package_verification_reports=[package_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            self.assertEqual("receiving_machine", item.evidence["report_validations"][0]["contexts"][0])

    def test_goal_evidence_rejects_artifact_verification_without_verifier_audit(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="forged-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            package_report = root / "artifact_package_verification.json"
            package_report.write_text(json.dumps({
                "schema": "TaskPlanningArtifactPackageVerification.v1",
                "ok": True,
                "archive": str(package.archive.resolve()),
                "verification_context": "unit_workplace_receiving",
                "source_machine_id": "3333333333333333333333333333333333333333333333333333333333333333",
                "verifier_machine_id": "4444444444444444444444444444444444444444444444444444444444444444",
                "artifact_validations": [{
                    "ok": True,
                    "name": "mission-run",
                    "kind": "mission_run",
                    "case_id": "uav_ugv_coordination",
                    "errors": [],
                }],
            }, indent=2, sort_keys=True), encoding="utf-8")
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_packages=[package.archive],
                artifact_work_dir=root / "verify",
                artifact_package_verification_reports=[package_report],
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            errors = "\n".join(item.evidence["report_validations"][0]["errors"])
            self.assertIn("checked_files", errors)
            self.assertIn("manifest_errors", errors)

    def test_goal_evidence_accepts_artifact_verification_embedded_in_site_acceptance(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="embedded-site-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            verification = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="unit_workplace_receiving",
            ).as_dict()
            site_report = root / "site.json"
            _write_site_ros1_report(
                site_report,
                machine_id=verification["verifier_machine_id"],
                artifact_package_verification=verification,
            )
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("pass", item.status)
            self.assertEqual(1, item.evidence["site_embedded_verification_count"])
            self.assertEqual(1, item.evidence["receiving_ok_count"])

    def test_goal_evidence_rejects_embedded_artifact_verification_from_incomplete_site_acceptance(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="incomplete-site-embedded-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            verification = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="unit_workplace_receiving",
            ).as_dict()
            site_report = root / "site.json"
            _write_site_ros1_report(
                site_report,
                machine_id=verification["verifier_machine_id"],
                artifact_package_verification=verification,
            )
            site_data = json.loads(site_report.read_text(encoding="utf-8"))
            site_data.pop("readiness", None)
            site_data.pop("hardware_gate", None)
            site_report.write_text(json.dumps(site_data, indent=2, sort_keys=True), encoding="utf-8")
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["site_embedded_verification_count"])
            self.assertEqual(0, item.evidence["receiving_ok_count"])

    def test_goal_evidence_rejects_embedded_artifact_verification_machine_mismatch(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="embedded-site-machine-mismatch-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            verification = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="unit_workplace_receiving",
            ).as_dict()
            verification["verifier_machine_id"] = "9999999999999999999999999999999999999999999999999999999999999999"
            site_report = root / "site.json"
            _write_site_ros1_report(
                site_report,
                machine_id="7777777777777777777777777777777777777777777777777777777777777777",
                artifact_package_verification=verification,
            )
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(1, item.evidence["site_embedded_verification_count"])
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            self.assertIn(
                "site machine_id must match artifact verification verifier_machine_id",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_embedded_artifact_verification_archive_mismatch(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="embedded-site-archive-mismatch-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            verification = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="unit_workplace_receiving",
            ).as_dict()
            site_report = root / "site.json"
            _write_site_ros1_report(
                site_report,
                machine_id=verification["verifier_machine_id"],
                artifact_package_verification=verification,
                artifact_package_archive="/tmp/different-task-planning-artifacts.tar.gz",
            )
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(1, item.evidence["site_embedded_verification_count"])
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            self.assertIn(
                "site artifact archive must match artifact verification archive",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_artifact_verification_without_lane_matrix_case(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="no-lane-case-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            package_report = root / "artifact_package_verification.json"
            package_report.write_text(json.dumps(
                verify_artifact_package(
                    archive_path=package.archive,
                    work_dir=root / "verify",
                    verification_context="unit_workplace_receiving",
                ).as_dict(),
                indent=2,
                sort_keys=True,
            ), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_package_verification_reports=[package_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            self.assertIn(
                "no OK lane matrix case_id available",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_artifact_verification_case_mismatch(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run", case_id="uav_reconnaissance")],
                output_dir=root / "package",
                package_name="wrong-case-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            package_report = root / "artifact_package_verification.json"
            package_report.write_text(json.dumps(
                verify_artifact_package(
                    archive_path=package.archive,
                    work_dir=root / "verify",
                    verification_context="unit_workplace_receiving",
                ).as_dict(),
                indent=2,
                sort_keys=True,
            ), encoding="utf-8")
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report, case_id="uav_ugv_coordination")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_package_verification_reports=[package_report],
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            self.assertIn(
                "artifact package case_id must match",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_standalone_artifact_verification_archive_mismatch(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="verified-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            other_package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "other-mission-run")],
                output_dir=root / "other-package",
                package_name="other-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            package_report = root / "artifact_package_verification.json"
            package_report.write_text(json.dumps(
                verify_artifact_package(
                    archive_path=package.archive,
                    work_dir=root / "verify",
                    verification_context="unit_workplace_receiving",
                ).as_dict(),
                indent=2,
                sort_keys=True,
            ), encoding="utf-8")
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_packages=[other_package.archive],
                artifact_package_verification_reports=[package_report],
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["receiving_ok_count"])
            self.assertIn(
                "artifact verification archive must match a provided artifact package archive",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_embedded_artifact_verification_from_failed_site_acceptance(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="failed-site-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            verification = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="unit_workplace_receiving",
            ).as_dict()
            site_report = root / "site.json"
            _write_site_ros1_report(site_report, ok=False, artifact_package_verification=verification)

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["site_embedded_verification_count"])
            self.assertEqual(0, item.evidence["receiving_ok_count"])

    def test_goal_evidence_rejects_embedded_artifact_verification_from_non_work_hardware_site(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="dev-site-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            verification = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="unit_workplace_receiving",
            ).as_dict()
            site_report = root / "site.json"
            _write_site_ros1_report(
                site_report,
                mission_profile="dev_mock",
                artifact_package_verification=verification,
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["site_embedded_verification_count"])
            self.assertEqual(0, item.evidence["receiving_ok_count"])

    def test_goal_evidence_rejects_embedded_artifact_verification_from_unsupported_site_level(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="wrong-level-site-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            verification = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="unit_workplace_receiving",
            ).as_dict()
            site_report = root / "site.json"
            _write_site_ros1_report(
                site_report,
                acceptance_level="dev_mock_ready",
                artifact_package_verification=verification,
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["site_embedded_verification_count"])
            self.assertEqual(0, item.evidence["receiving_ok_count"])

    def test_goal_evidence_rejects_embedded_artifact_verification_without_site_machine_id(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "mission-run")],
                output_dir=root / "package",
                package_name="site-no-machine-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            verification = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="unit_workplace_receiving",
            ).as_dict()
            site_report = root / "site.json"
            _write_site_ros1_report(site_report, machine_id="", artifact_package_verification=verification)

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["artifact_package_verified_after_transfer"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["site_embedded_verification_count"])
            self.assertEqual(0, item.evidence["receiving_ok_count"])

    def test_goal_evidence_rejects_hardware_artifact_without_unit_dispatch_trace(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dry_run_only = _write_artifact(
                root / "dry-run-only",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                command_acks=[_accepted_ack()],
                gateway_records=[{
                    "mission_id": "mission_001",
                    "task_id": "task_001",
                    "platform_id": "uav_0",
                    "capability": "inspect_area",
                    "accepted": True,
                    "reason": "",
                    "service": "/fleet/uav_0/gateway/dry_run",
                    "rosservice_called": True,
                    "returncode": 0,
                    "publish_attempted": False,
                }],
                task_progress=[_task_progress()],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                hardware_run_artifacts=[dry_run_only],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])

    def test_goal_evidence_rejects_hardware_artifact_without_unit_execution_context(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_context = _write_artifact(
                root / "missing-context",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                hardware_run_artifacts=[missing_context],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])

    def test_goal_evidence_rejects_hardware_artifact_without_recorded_dispatch_state(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            site_report = root / "site.json"
            _write_site_ros1_report(site_report)
            hardware = _write_artifact(
                root / "hardware-run",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )
            validation = json.loads((hardware / "validation_report.json").read_text(encoding="utf-8"))
            validation["current_state"] = "COMPLETE"
            validation.pop("source_validation_report", None)
            (hardware / "validation_report.json").write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                lane_matrix_reports=[lane_matrix_report],
                site_acceptance_reports=[site_report],
                hardware_run_artifacts=[hardware],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            errors = "\n".join(item.evidence["report_validations"][0]["errors"])
            self.assertIn("HARDWARE_DISPATCH_RECORDED", errors)
            self.assertIn("source_validation_report", errors)

    def test_goal_evidence_rejects_hardware_artifact_with_nonempty_validation_errors(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            site_report = root / "site.json"
            _write_site_ros1_report(site_report)
            hardware = _write_artifact(
                root / "hardware-run",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )
            validation = json.loads((hardware / "validation_report.json").read_text(encoding="utf-8"))
            validation["errors"] = ["late safety warning"]
            (hardware / "validation_report.json").write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                lane_matrix_reports=[lane_matrix_report],
                site_acceptance_reports=[site_report],
                hardware_run_artifacts=[hardware],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn(
                "validation_report.errors must be empty",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_hardware_artifact_with_invalid_source_validation_schema(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            site_report = root / "site.json"
            _write_site_ros1_report(site_report)
            hardware = _write_artifact(
                root / "hardware-run",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )
            validation = json.loads((hardware / "validation_report.json").read_text(encoding="utf-8"))
            validation["source_validation_report"]["schema"] = "LegacyReport.v1"
            (hardware / "validation_report.json").write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                lane_matrix_reports=[lane_matrix_report],
                site_acceptance_reports=[site_report],
                hardware_run_artifacts=[hardware],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn(
                "source_validation_report.schema must be ValidationReport.v1",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_hardware_artifact_with_invalid_task_progress_set_schema(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            site_report = root / "site.json"
            _write_site_ros1_report(site_report)
            hardware = _write_artifact(
                root / "hardware-run",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )
            task_progress = json.loads((hardware / "task_progress.json").read_text(encoding="utf-8"))
            task_progress["schema"] = "LegacyTaskProgressSet.v1"
            (hardware / "task_progress.json").write_text(json.dumps(task_progress, indent=2, sort_keys=True), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                lane_matrix_reports=[lane_matrix_report],
                site_acceptance_reports=[site_report],
                hardware_run_artifacts=[hardware],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn(
                "task_progress.json must be TaskProgressSet.v1",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_hardware_artifact_with_unmatched_progress(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = _task_progress()
            progress["task_id"] = "other_task"
            unmatched_progress = _write_artifact(
                root / "unmatched-progress",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[progress],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                hardware_run_artifacts=[unmatched_progress],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])

    def test_goal_evidence_rejects_hardware_artifact_with_unmatched_ack_mission(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ack = _accepted_ack()
            ack["mission_id"] = "other_mission"
            unmatched_ack = _write_artifact(
                root / "unmatched-ack-mission",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[ack],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                hardware_run_artifacts=[unmatched_ack],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])

    def test_goal_evidence_rejects_hardware_artifact_without_common_ack_trace_progress_key(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            site_report = root / "site.json"
            _write_site_ros1_report(site_report)
            second_dispatch = _dispatch_gateway_record()
            second_dispatch["task_id"] = "task_002"
            progress = _task_progress()
            progress["task_id"] = "task_002"
            split_proof = _write_artifact(
                root / "split-proof",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record(), second_dispatch],
                task_progress=[progress],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                lane_matrix_reports=[lane_matrix_report],
                site_acceptance_reports=[site_report],
                hardware_run_artifacts=[split_proof],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn(
                "must share the same mission_id/task_id/platform_id",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_hardware_artifact_with_dispatch_service_platform_mismatch(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            site_report = root / "site.json"
            _write_site_ros1_report(site_report)
            site_data = json.loads(site_report.read_text(encoding="utf-8"))
            site_data["rosservice_audit"]["matched_services"].append("/fleet/ugv_0/gateway/dispatch")
            site_data["rosservice_audit"]["service_signatures"].append({
                "service_name": "/fleet/ugv_0/gateway/dispatch",
                "observed_type": "platform_gateway_msgs/TaskCommandJson",
                "observed_args": ["task_command_json"],
                "type_ok": True,
                "args_ok": True,
                "errors": [],
                "warnings": [],
            })
            site_report.write_text(json.dumps(site_data, indent=2, sort_keys=True), encoding="utf-8")
            trace = _dispatch_gateway_record()
            trace["service"] = "/fleet/ugv_0/gateway/dispatch"
            mismatch = _write_artifact(
                root / "service-platform-mismatch",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[trace],
                task_progress=[_task_progress()],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                lane_matrix_reports=[lane_matrix_report],
                site_acceptance_reports=[site_report],
                hardware_run_artifacts=[mismatch],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn(
                "service must match platform_id",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_hardware_artifact_with_rejected_dispatch_trace(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            site_report = root / "site.json"
            _write_site_ros1_report(site_report)
            trace = _dispatch_gateway_record()
            trace["accepted"] = False
            rejected_trace = _write_artifact(
                root / "rejected-dispatch-trace",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[trace],
                task_progress=[_task_progress()],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                lane_matrix_reports=[lane_matrix_report],
                site_acceptance_reports=[site_report],
                hardware_run_artifacts=[rejected_trace],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn("accepted=true", "\n".join(item.evidence["report_validations"][0]["errors"]))

    def test_goal_evidence_rejects_hardware_artifact_with_wrong_command_ack_schema(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            site_report = root / "site.json"
            _write_site_ros1_report(site_report)
            ack = _accepted_ack()
            ack["schema"] = "NotCommandAck.v1"
            bad_ack_schema = _write_artifact(
                root / "bad-ack-schema",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[ack],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                lane_matrix_reports=[lane_matrix_report],
                site_acceptance_reports=[site_report],
                hardware_run_artifacts=[bad_ack_schema],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn("CommandAck.v1", "\n".join(item.evidence["report_validations"][0]["errors"]))

    def test_goal_evidence_rejects_hardware_artifact_with_wrong_task_progress_schema(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            site_report = root / "site.json"
            _write_site_ros1_report(site_report)
            progress = _task_progress()
            progress["schema"] = "NotTaskProgress.v1"
            bad_progress_schema = _write_artifact(
                root / "bad-progress-schema",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[progress],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                lane_matrix_reports=[lane_matrix_report],
                site_acceptance_reports=[site_report],
                hardware_run_artifacts=[bad_progress_schema],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn("TaskProgress.v1", "\n".join(item.evidence["report_validations"][0]["errors"]))

    def test_goal_evidence_rejects_hardware_artifact_without_operator_approval_record(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_operator_approval = _write_artifact(
                root / "missing-operator-approval",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                hardware_run_artifacts=[missing_operator_approval],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])

    def test_goal_evidence_rejects_hardware_artifact_without_machine_id(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_machine_id = _write_artifact(
                root / "missing-machine-id",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                operator_approval_source="local_unit_operator",
                execution_context="unit_workplace_hardware",
                machine_id="",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                hardware_run_artifacts=[missing_machine_id],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])

    def test_goal_evidence_rejects_hardware_artifact_with_unhashed_machine_id(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unhashed_machine_id = _write_artifact(
                root / "unhashed-machine-id",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                operator_approval_source="local_unit_operator",
                execution_context="unit_workplace_hardware",
                machine_id="not-a-hash",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                hardware_run_artifacts=[unhashed_machine_id],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn(
                "64-character lowercase sha256",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_hardware_artifact_without_local_operator_source(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrong_operator_source = _write_artifact(
                root / "wrong-operator-source",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                operator_approval_source="remote_agent",
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                hardware_run_artifacts=[wrong_operator_source],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])

    def test_goal_evidence_rejects_hardware_artifact_case_mismatch_with_lane_matrix(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report, case_id="uav_ugv_coordination")
            wrong_case_hardware = _write_artifact(
                root / "wrong-case-hardware",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                operator_approval_source="local_unit_operator",
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
                case_id="uav_reconnaissance",
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                lane_matrix_reports=[lane_matrix_report],
                hardware_run_artifacts=[wrong_case_hardware],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertEqual(["uav_ugv_coordination"], item.evidence["lane_matrix_case_ids"])
            self.assertIn(
                "hardware execution artifact case_id must match an OK lane matrix case_id",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_requires_lane_matrix_before_hardware_artifact_counts(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            hardware = _write_hardware_run(Path(tmp) / "hardware-run")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                hardware_run_artifacts=[hardware],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertEqual([], item.evidence["lane_matrix_case_ids"])
            self.assertIn(
                "no OK lane matrix case_id available",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_requires_ros1_signature_gate_before_hardware_artifact_counts(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            hardware = _write_hardware_run(root / "hardware-run")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                lane_matrix_reports=[lane_matrix_report],
                hardware_run_artifacts=[hardware],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertEqual([], item.evidence["valid_ros1_signature_machine_ids"])
            self.assertIn(
                "no OK unit ROS1 signature machine_id available",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_hardware_artifact_machine_mismatch_with_ros1_signature_gate(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            site_report = root / "site.json"
            _write_site_ros1_report(
                site_report,
                machine_id="8888888888888888888888888888888888888888888888888888888888888888",
            )
            hardware = _write_hardware_run(root / "hardware-run")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
                lane_matrix_reports=[lane_matrix_report],
                hardware_run_artifacts=[hardware],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertEqual(
                ["8888888888888888888888888888888888888888888888888888888888888888"],
                item.evidence["valid_ros1_signature_machine_ids"],
            )
            self.assertIn(
                "hardware execution machine_id must match an OK unit ROS1 signature report machine_id",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_hardware_dispatch_service_without_matching_ros1_signature(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            site_report = root / "site.json"
            _write_site_ros1_report(site_report)
            site_data = json.loads(site_report.read_text(encoding="utf-8"))
            site_data["rosservice_audit"]["matched_services"] = [
                "/fleet/ugv_0/gateway/dry_run",
                "/fleet/ugv_0/gateway/dispatch",
            ]
            site_data["rosservice_audit"]["service_signatures"][0]["service_name"] = "/fleet/ugv_0/gateway/dry_run"
            site_data["rosservice_audit"]["service_signatures"][1]["service_name"] = "/fleet/ugv_0/gateway/dispatch"
            site_report.write_text(json.dumps(site_data, indent=2, sort_keys=True), encoding="utf-8")
            hardware = _write_hardware_run(root / "hardware-run")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
                lane_matrix_reports=[lane_matrix_report],
                hardware_run_artifacts=[hardware],
            )

            item = {item.name: item for item in report.items}["unit_hardware_execution_artifact_verified"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertEqual(
                [
                    "/fleet/ugv_0/gateway/dispatch",
                    "/fleet/ugv_0/gateway/dry_run",
                ],
                item.evidence["valid_ros1_signature_services_by_machine"][
                    "7777777777777777777777777777777777777777777777777777777777777777"
                ],
            )
            self.assertIn(
                "hardware dispatch service must match an OK unit ROS1 signed service",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_mock_profile_ros1_signature_report(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            site_report = Path(tmp) / "site.json"
            _write_site_ros1_report(site_report, platform_backend="mock")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["unit_ros1_gateway_signatures_observed"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["signature_report_count"])

    def test_goal_evidence_rejects_caller_supplied_ros1_signature_report(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            site_report = Path(tmp) / "site.json"
            _write_site_ros1_report(site_report, command_environment_source="caller_supplied")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["unit_ros1_gateway_signatures_observed"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["signature_report_count"])
            self.assertIn("command_environment_source", "\n".join(item.evidence["report_validations"][0]["errors"]))

    def test_goal_evidence_rejects_ros1_signature_without_paired_dry_run_and_dispatch(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            site_report = Path(tmp) / "site.json"
            _write_site_ros1_report(site_report)
            data = json.loads(site_report.read_text(encoding="utf-8"))
            data["rosservice_audit"]["matched_services"] = ["/fleet/uav_0/gateway/dry_run"]
            data["rosservice_audit"]["observed_service_count"] = 1
            data["rosservice_audit"]["service_signatures"] = [
                signature
                for signature in data["rosservice_audit"]["service_signatures"]
                if signature["service_name"] == "/fleet/uav_0/gateway/dry_run"
            ]
            site_report.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["unit_ros1_gateway_signatures_observed"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["signature_report_count"])
            self.assertIn(
                "paired dry_run and dispatch",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_ros1_signature_with_unpaired_gateway_prefixes(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            site_report = Path(tmp) / "site.json"
            _write_site_ros1_report(site_report)
            data = json.loads(site_report.read_text(encoding="utf-8"))
            data["rosservice_audit"]["matched_services"] = [
                "/fleet/uav_0/gateway/dry_run",
                "/fleet/ugv_0/gateway/dispatch",
            ]
            data["rosservice_audit"]["service_signatures"][1]["service_name"] = "/fleet/ugv_0/gateway/dispatch"
            site_report.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["unit_ros1_gateway_signatures_observed"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["signature_report_count"])
            self.assertIn(
                "paired dry_run and dispatch",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_ros1_signature_report_without_machine_id(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            site_report = Path(tmp) / "site.json"
            _write_site_ros1_report(site_report, machine_id="")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["unit_ros1_gateway_signatures_observed"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["signature_report_count"])
            self.assertIn("machine_id", "\n".join(item.evidence["report_validations"][0]["errors"]))

    def test_goal_evidence_rejects_ros1_signature_without_readiness_and_hardware_gate(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            site_report = Path(tmp) / "site.json"
            _write_site_ros1_report(site_report)
            data = json.loads(site_report.read_text(encoding="utf-8"))
            data.pop("readiness", None)
            data.pop("hardware_gate", None)
            site_report.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["unit_ros1_gateway_signatures_observed"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["signature_report_count"])
            errors = "\n".join(item.evidence["report_validations"][0]["errors"])
            self.assertIn("readiness", errors)
            self.assertIn("hardware_gate", errors)

    def test_goal_evidence_rejects_ros1_signature_report_with_unhashed_machine_id(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            site_report = Path(tmp) / "site.json"
            _write_site_ros1_report(site_report, machine_id="not-a-hash")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["unit_ros1_gateway_signatures_observed"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["signature_report_count"])
            self.assertIn(
                "64-character lowercase sha256",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_ros1_signature_not_matched_to_observed_service(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            site_report = Path(tmp) / "site.json"
            _write_site_ros1_report(site_report)
            data = json.loads(site_report.read_text(encoding="utf-8"))
            data["rosservice_audit"]["matched_services"] = ["/fleet/uav_0/gateway/dry_run"]
            site_report.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                site_acceptance_reports=[site_report],
            )

            item = {item.name: item for item in report.items}["unit_ros1_gateway_signatures_observed"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["signature_report_count"])
            self.assertIn("matched_services", "\n".join(item.evidence["report_validations"][0]["errors"]))

    def test_goal_evidence_does_not_accept_mock_endpoint_as_home_5090_proof(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_report = root / "model_lab_evaluation.json"
            _write_model_lab_report(model_report, model_lab_evidence_kind="mock_endpoint")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                model_lab_evaluations=[model_report],
            )

            item = {item.name: item for item in report.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
            self.assertEqual(1, item.evidence["rejected_mock_endpoint_count"])

    def test_goal_evidence_rejects_mock_provider_as_home_5090_proof(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            model_report = Path(tmp) / "model_lab_evaluation.json"
            _write_model_lab_report(model_report, model_provider="mock")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                model_lab_evaluations=[model_report],
            )

            item = {item.name: item for item in report.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn("model_provider", "\n".join(item.evidence["report_validations"][0]["errors"]))

    def test_goal_evidence_rejects_home_5090_report_without_rtx_5090_probe(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            model_report = Path(tmp) / "model_lab_evaluation.json"
            _write_model_lab_report(model_report, gpu_name="NVIDIA GeForce RTX 4060 Laptop GPU")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                model_lab_evaluations=[model_report],
            )

            item = {item.name: item for item in report.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn("RTX 5090", "\n".join(item.evidence["report_validations"][0]["errors"]))

    def test_goal_evidence_rejects_home_5090_report_without_nvidia_smi_probe(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            model_report = Path(tmp) / "model_lab_evaluation.json"
            _write_model_lab_report(
                model_report,
                probe_source="synthetic",
                probe_command=["synthetic-probe"],
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                model_lab_evaluations=[model_report],
            )

            item = {item.name: item for item in report.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            errors = "\n".join(item.evidence["report_validations"][0]["errors"])
            self.assertIn("accelerator_probe.source must be nvidia-smi", errors)
            self.assertIn("accelerator_probe.command must run nvidia-smi", errors)

    def test_goal_evidence_rejects_home_5090_report_without_baseline_comparison(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            model_report = Path(tmp) / "model_lab_evaluation.json"
            _write_model_lab_report(model_report, include_comparison=False)

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                model_lab_evaluations=[model_report],
            )

            item = {item.name: item for item in report.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            errors = "\n".join(item.evidence["report_validations"][0]["errors"])
            self.assertIn("baseline_equivalent", errors)
            self.assertIn("diffs", errors)

    def test_goal_evidence_rejects_home_5090_report_with_unhashed_machine_id(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            model_report = Path(tmp) / "model_lab_evaluation.json"
            _write_model_lab_report(model_report, machine_id="not-a-hash")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                model_lab_evaluations=[model_report],
            )

            item = {item.name: item for item in report.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertIn(
                "64-character lowercase sha256",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_requires_home_5090_case_to_match_lane_matrix(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_report = root / "model_lab_evaluation.json"
            _write_model_lab_report(model_report, case_id="uav_reconnaissance")
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report, case_id="uav_ugv_coordination")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                model_lab_evaluations=[model_report],
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertEqual(["uav_ugv_coordination"], item.evidence["lane_matrix_case_ids"])
            self.assertIn(
                "case_id must match an OK lane matrix case_id",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_requires_home_5090_model_lab_artifact_package(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_report = root / "model_lab_evaluation.json"
            _write_model_lab_report(model_report)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                model_lab_evaluations=[model_report],
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertEqual([], item.evidence["model_lab_artifact_package_case_ids"])
            self.assertIn(
                "model-lab artifact package evidence is required",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_rejects_home_5090_package_without_unit_receiving_verification(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_report = root / "model_lab_evaluation.json"
            _write_model_lab_report(model_report)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            model_lab_artifact = _write_model_lab_artifact(root / "model-lab")
            package = build_artifact_package(
                artifact_paths=[model_lab_artifact],
                output_dir=root / "package",
                package_name="source-only-model-lab",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_packages=[package.archive],
                artifact_work_dir=root / "verify",
                model_lab_evaluations=[model_report],
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertEqual([], item.evidence["model_lab_artifact_package_case_ids"])
            self.assertIn(
                "model-lab artifact package evidence is required",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_requires_home_5090_package_to_pass_unit_receiving_case_validation(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_report = root / "model_lab_evaluation.json"
            _write_model_lab_report(model_report, case_id="uav_ugv_coordination")
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report, case_id="uav_ugv_coordination")
            model_lab_artifact = _write_model_lab_artifact(root / "model-lab", case_id="uav_reconnaissance")
            package = build_artifact_package(
                artifact_paths=[model_lab_artifact],
                output_dir=root / "package",
                package_name="mismatched-model-lab",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            package_report = root / "artifact_package_verification.json"
            package_report.write_text(json.dumps(
                verify_artifact_package(
                    archive_path=package.archive,
                    work_dir=root / "verify-package",
                    verification_context="unit_workplace_receiving",
                ).as_dict(),
                indent=2,
                sort_keys=True,
            ), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_packages=[package.archive],
                artifact_work_dir=root / "verify",
                artifact_package_verification_reports=[package_report],
                model_lab_evaluations=[model_report],
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
            self.assertEqual([], item.evidence["model_lab_artifact_package_case_ids"])
            self.assertIn(
                "model-lab artifact package evidence is required",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_requires_home_5090_package_metadata_to_match_report(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_report = root / "model_lab_evaluation.json"
            _write_model_lab_report(model_report)
            lane_matrix_report = root / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix_report)
            model_lab_artifact = _write_model_lab_artifact(
                root / "model-lab",
                machine_id="5555555555555555555555555555555555555555555555555555555555555555",
            )
            package = build_artifact_package(
                artifact_paths=[model_lab_artifact],
                output_dir=root / "package",
                package_name="metadata-mismatch-model-lab",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            package_report = root / "artifact_package_verification.json"
            package_report.write_text(json.dumps(
                verify_artifact_package(
                    archive_path=package.archive,
                    work_dir=root / "verify-package",
                    verification_context="unit_workplace_receiving",
                ).as_dict(),
                indent=2,
                sort_keys=True,
            ), encoding="utf-8")

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                artifact_packages=[package.archive],
                artifact_work_dir=root / "verify",
                artifact_package_verification_reports=[package_report],
                model_lab_evaluations=[model_report],
                lane_matrix_reports=[lane_matrix_report],
            )

            item = {item.name: item for item in report.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
            self.assertIn(
                "model-lab artifact package metadata.machine_id must match evaluation report",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )

    def test_goal_evidence_requires_lane_matrix_before_home_5090_case_counts(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            model_report = Path(tmp) / "model_lab_evaluation.json"
            _write_model_lab_report(model_report)

            report = build_distributed_fleet_goal_evidence(
                repo_root=repo_root,
                model_lab_evaluations=[model_report],
            )

            item = {item.name: item for item in report.items}["home_5090_model_lab_evaluated"]
            self.assertEqual("missing", item.status)
            self.assertEqual(0, item.evidence["ok_count"])
            self.assertEqual([], item.evidence["lane_matrix_case_ids"])
            self.assertIn(
                "no OK lane matrix case_id available",
                "\n".join(item.evidence["report_validations"][0]["errors"]),
            )


def _write_mission_run(root: Path, *, case_id: str = "uav_ugv_coordination") -> Path:
    return _write_artifact(root, mission_profile="dev_mock", platform_backend="mock", command_acks=[], case_id=case_id)


def _write_model_lab_artifact(
    root: Path,
    *,
    case_id: str = "uav_ugv_coordination",
    machine_id: str = "6666666666666666666666666666666666666666666666666666666666666666",
) -> Path:
    root.mkdir(parents=True)
    files = {
        "environment_profile.json": {
            "schema": "EnvironmentProfile.v1",
            "mission_profile": "home_model_lab",
            "model_provider": "local_http",
            "platform_backend": "mock",
        },
        "mission_input.json": {
            "schema": "ModelLabMissionInput.v1",
            "case_id": case_id,
        },
        "baseline_task_schema.json": {
            "schema": "TaskSchema.v1",
            "mission_request": {},
        },
        "model_task_schema.json": {
            "schema": "TaskSchema.v1",
            "mission_request": {},
        },
        "model_lab_evaluation.json": {
            "schema": "ModelLabEvaluation.v1",
            "ok": True,
            "case_id": case_id,
            "mission_profile": "home_model_lab",
            "model_provider": "local_http",
            "model_name": "qwen3.5-35b-a3b",
            "model_base_url": "http://home-model-lab.local:8000/v1",
            "model_lab_evidence_kind": "home_5090_live",
            "platform_backend": "mock",
            "machine_id": machine_id,
            "accelerator_probe": _accelerator_probe("NVIDIA GeForce RTX 5090"),
            "baseline_equivalent": True,
            "diffs": [],
            "validation_errors": [],
        },
    }
    for filename, data in files.items():
        (root / filename).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return root


def _write_model_lab_report(
    path: Path,
    *,
    mission_profile: str = "home_model_lab",
    model_provider: str = "local_http",
    platform_backend: str = "mock",
    model_lab_evidence_kind: str = "home_5090_live",
    gpu_name: str = "NVIDIA GeForce RTX 5090",
    probe_source: str = "nvidia-smi",
    probe_command=None,
    machine_id: str = "6666666666666666666666666666666666666666666666666666666666666666",
    include_comparison: bool = True,
    case_id: str = "uav_ugv_coordination",
) -> None:
    data = {
        "schema": "ModelLabEvaluation.v1",
        "ok": True,
        "case_id": case_id,
        "mission_profile": mission_profile,
        "model_provider": model_provider,
        "model_name": "qwen3.5-35b-a3b",
        "model_base_url": "http://home-model-lab.local:8000/v1",
        "model_lab_evidence_kind": model_lab_evidence_kind,
        "platform_backend": platform_backend,
        "machine_id": machine_id,
        "accelerator_probe": _accelerator_probe(gpu_name, source=probe_source, command=probe_command),
    }
    if include_comparison:
        data.update({
            "baseline_equivalent": True,
            "diffs": [],
            "validation_errors": [],
        })
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _accelerator_probe(gpu_name: str, *, source="nvidia-smi", command=None):
    return {
        "schema": "AcceleratorProbe.v1",
        "ok": True,
        "source": source,
        "command": command or ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
        "gpus": [{"name": gpu_name, "memory_total": "32768 MiB", "driver_version": "test"}],
        "errors": [],
    }


def _write_site_ros1_report(
    path: Path,
    *,
    ok: bool = True,
    mission_profile: str = "work_hardware",
    platform_backend: str = "ros1_gateway",
    acceptance_level: str = "work_hardware_ros1_signatures_observed",
    command_environment_source: str = "profile",
    machine_id: str = "7777777777777777777777777777777777777777777777777777777777777777",
    artifact_package_verification=None,
    artifact_package_archive=None,
) -> None:
    data = {
        "schema": "TaskPlanningSiteAcceptance.v1",
        "ok": ok,
        "mission_profile": mission_profile,
        "platform_backend": platform_backend,
        "acceptance_level": acceptance_level,
        "readiness": {
            "schema": "EnvironmentReadinessReport.v1",
            "ok": True,
            "mission_profile": mission_profile,
            "checks": [],
            "failures": [],
            "warnings": [],
            "next_commands": [],
        },
        "hardware_gate": {
            "schema": "HardwareGatePlan.v1",
            "ok": True,
            "requested_stage": "mock_gateway_dispatch",
            "steps": [],
            "validation_errors": [],
        },
        "rosservice_audit": {
            "schema": "Ros1GatewayServiceAudit.v1",
            "ok": True,
            "observed_service_count": 2,
            "matched_services": [
                "/fleet/uav_0/gateway/dry_run",
                "/fleet/uav_0/gateway/dispatch",
            ],
            "missing_services": [],
            "command_environment_source": command_environment_source,
            "service_signatures": [
                {
                    "service_name": "/fleet/uav_0/gateway/dry_run",
                    "observed_type": "platform_gateway_msgs/TaskCommandJson",
                    "observed_args": ["task_command_json"],
                    "type_ok": True,
                    "args_ok": True,
                    "errors": [],
                    "warnings": [],
                },
                {
                    "service_name": "/fleet/uav_0/gateway/dispatch",
                    "observed_type": "platform_gateway_msgs/TaskCommandJson",
                    "observed_args": ["task_command_json"],
                    "type_ok": True,
                    "args_ok": True,
                    "errors": [],
                    "warnings": [],
                },
            ],
        },
        "validation_errors": [],
    }
    if artifact_package_verification is not None:
        archive = str(artifact_package_archive or "/tmp/task-planning-artifacts.tar.gz")
        if isinstance(artifact_package_verification, dict):
            archive = str(artifact_package_archive or artifact_package_verification.get("archive") or archive)
        data["artifact_packages"] = [{
            "ok": True,
            "archive": archive,
            "verification": artifact_package_verification,
            "errors": [],
        }]
    if machine_id:
        data["machine_id"] = machine_id
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_hardware_run(root: Path) -> Path:
    return _write_artifact(
        root,
        mission_profile="work_hardware",
        platform_backend="ros1_gateway",
        hardware_approval_required=True,
        operator_approved=True,
        execution_context="unit_workplace_hardware",
        command_acks=[_accepted_ack()],
        gateway_records=[_dispatch_gateway_record()],
        task_progress=[_task_progress()],
    )


def _write_artifact(
    root: Path,
    *,
    mission_profile: str,
    platform_backend: str,
    command_acks,
    hardware_approval_required: bool = False,
    operator_approved: bool = False,
    operator_approval_source: str = "local_unit_operator",
    machine_id: str = "7777777777777777777777777777777777777777777777777777777777777777",
    execution_context: str = "",
    gateway_records=None,
    task_progress=None,
    case_id: str = "uav_ugv_coordination",
):
    root.mkdir(parents=True)
    profile = {
        "schema": "EnvironmentProfile.v1",
        "mission_profile": mission_profile,
        "model_provider": "mock",
        "platform_backend": platform_backend,
        "hardware_approval_required": hardware_approval_required,
    }
    if operator_approved:
        profile["operator_approved"] = True
        if operator_approval_source:
            profile["operator_approval_source"] = operator_approval_source
        if machine_id:
            profile["machine_id"] = machine_id
    if execution_context:
        profile["execution_context"] = execution_context
    validation_report = {
        "schema": "ValidationReport.v1",
        "status": "passed",
        "errors": [],
        "current_state": "COMPLETE",
    }
    if mission_profile == "work_hardware" and platform_backend == "ros1_gateway":
        validation_report = {
            "schema": "ValidationReport.v1",
            "status": "passed",
            "errors": [],
            "current_state": "HARDWARE_DISPATCH_RECORDED",
            "source_validation_report": {
                "schema": "ValidationReport.v1",
                "status": "passed",
                "errors": [],
                "current_state": "OPERATOR_APPROVAL",
            },
        }
    json_files = {
        "environment_profile.json": profile,
        "mission_input.json": {"schema": "MissionInput.v1", "run_input": {"case_id": case_id}},
        "model_output.json": {"schema": "ModelOutput.v1", "output": {}},
        "task_schema.json": {"schema": "TaskSchema.v1", "mission_request": {}},
        "validation_report.json": validation_report,
        "blackboard_snapshot.json": {"schema": "MissionBlackboard.v1"},
        "planner_output.json": {"schema": "PddlPlan.v1", "steps": []},
        "bt_artifact.json": {"schema": "BehaviorTree.v1", "task_commands": []},
        "gateway_trace.json": {"schema": "GatewayTrace.v1", "records": gateway_records or []},
        "command_acks.json": {"schema": "CommandAckSet.v1", "items": command_acks},
        "task_progress.json": {"schema": "TaskProgressSet.v1", "items": task_progress or []},
        "failure_report.json": {"schema": "FailureReport.v1", "status": "not_reported"},
        "replan_decision.json": {"schema": "ReplanRequest.v1", "status": "not_requested"},
    }
    for filename, data in json_files.items():
        (root / filename).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    (root / "pddl_problem.pddl").write_text("(define (problem test))\n", encoding="utf-8")
    (root / "run_summary.md").write_text("# Mission Run\n", encoding="utf-8")
    return root


def _accepted_ack():
    return {
        "schema": "CommandAck.v1",
        "mission_id": "mission_001",
        "task_id": "task_001",
        "platform_id": "uav_0",
        "accepted": True,
        "reason": "",
        "local_check": {
            "capability_known": True,
            "localization_ok": True,
            "battery_ok": True,
            "safety_ok": True,
        },
    }


def _dispatch_gateway_record():
    return {
        "mission_id": "mission_001",
        "task_id": "task_001",
        "platform_id": "uav_0",
        "capability": "inspect_area",
        "accepted": True,
        "reason": "",
        "service": "/fleet/uav_0/gateway/dispatch",
        "rosservice_called": True,
        "returncode": 0,
        "publish_attempted": False,
        "execution_context": "unit_workplace_hardware",
    }


def _task_progress():
    return {
        "schema": "TaskProgress.v1",
        "mission_id": "mission_001",
        "task_id": "task_001",
        "platform_id": "uav_0",
        "status": "completed",
        "progress_ratio": 1.0,
        "message": "dispatch completed",
        "observations": {},
    }


def _write_golden_suite_report(path: Path) -> None:
    path.write_text(json.dumps({
        "schema": "DevMockGoldenSuite.v1",
        "ok": True,
        "required_case_ids": [
            "single_ugv_inspection",
            "single_ugv_object_approach",
            "uav_reconnaissance",
            "uav_ugv_coordination",
            "failure_and_replan",
            "disconnect_continue_authorized_subtree",
        ],
        "case_results": [
            {"case_id": "single_ugv_inspection", "ok": True, "run_id": "run-1", "artifact_bundle_path": "/tmp/run-1"},
            {"case_id": "single_ugv_object_approach", "ok": True, "run_id": "run-2", "artifact_bundle_path": "/tmp/run-2"},
            {"case_id": "uav_reconnaissance", "ok": True, "run_id": "run-3", "artifact_bundle_path": "/tmp/run-3"},
            {"case_id": "uav_ugv_coordination", "ok": True, "run_id": "run-4", "artifact_bundle_path": "/tmp/run-4"},
            {"case_id": "failure_and_replan", "ok": True, "run_id": "run-5", "artifact_bundle_path": "/tmp/run-5"},
            {"case_id": "disconnect_continue_authorized_subtree", "ok": True, "run_id": "run-6", "artifact_bundle_path": "/tmp/run-6"},
        ],
    }), encoding="utf-8")


def _write_lane_matrix_report(
    path: Path,
    *,
    include_work_hardware_comparison: bool = True,
    case_id: str = "uav_ugv_coordination",
) -> None:
    comparisons = [
        {
            "name": "dev_mock_vs_server_sim",
            "mode": "exact",
            "left_lane": "dev_mock",
            "right_lane": "server_sim",
            "equivalent": True,
            "validation_errors": [],
            "diffs": [],
        },
    ]
    if include_work_hardware_comparison:
        comparisons.append({
            "name": "dev_mock_vs_work_hardware_pre_dispatch",
            "mode": "pre_dispatch_compatible",
            "left_lane": "dev_mock",
            "right_lane": "work_hardware",
            "equivalent": True,
            "validation_errors": [],
            "diffs": [],
        })
    path.write_text(json.dumps({
        "schema": "TaskPlanningLaneMatrix.v1",
        "ok": True,
        "case_id": case_id,
        "artifact_root": "/tmp/lane-matrix",
        "runs": [
            {
                "lane": "dev_mock",
                "ok": True,
                "status": "dry_run_complete",
                "current_state": "DISPATCH_OR_HOLD",
                "profile_path": "profiles/dev_mock.env",
                "artifact_bundle_path": "/tmp/lane-matrix/dev_mock/run-1",
                "validation_errors": [],
            },
            {
                "lane": "server_sim",
                "ok": True,
                "status": "dry_run_complete",
                "current_state": "DISPATCH_OR_HOLD",
                "profile_path": "profiles/server_sim.env",
                "artifact_bundle_path": "/tmp/lane-matrix/server_sim/run-1",
                "validation_errors": [],
            },
            {
                "lane": "work_hardware",
                "ok": True,
                "status": "approval_required",
                "current_state": "OPERATOR_APPROVAL",
                "profile_path": "profiles/work_hardware.env",
                "artifact_bundle_path": "/tmp/lane-matrix/work_hardware/run-1",
                "validation_errors": [],
            },
        ],
        "comparisons": comparisons,
    }, indent=2, sort_keys=True), encoding="utf-8")


def _write_handoff_package_verification_report(
    path: Path,
    *,
    verification_context: str,
    source_machine_id: str = "3333333333333333333333333333333333333333333333333333333333333333",
    verifier_machine_id: str = "4444444444444444444444444444444444444444444444444444444444444444",
    migration_verification_context: str = "",
    migration_source_machine_id: str = "",
    migration_verifier_machine_id: str = "",
) -> None:
    migration_source = migration_source_machine_id or source_machine_id
    migration_verifier = migration_verifier_machine_id or verifier_machine_id
    path.write_text(json.dumps({
        "schema": "DistributedFleetHandoffPackageVerification.v1",
        "ok": True,
        "archive": "/tmp/distributed-fleet-handoff-package.tar.gz",
        "extract_dir": "/tmp/changxin-handoff-verify",
        "package_root": "/tmp/changxin-handoff-verify/distributed-fleet-handoff-package",
        "checked_files": 18,
        "verification_context": verification_context,
        "source_machine_id": source_machine_id,
        "verifier_machine_id": verifier_machine_id,
        "manifest_errors": [],
        "component_errors": [],
        "migration_verification": _migration_verification_dict(
            verification_context=migration_verification_context or verification_context,
            source_machine_id=migration_source,
            verifier_machine_id=migration_verifier,
        ),
    }, indent=2, sort_keys=True), encoding="utf-8")


def _migration_verification_dict(
    *,
    verification_context: str = "receiving_machine",
    source_machine_id: str = "3333333333333333333333333333333333333333333333333333333333333333",
    verifier_machine_id: str = "4444444444444444444444444444444444444444444444444444444444444444",
) -> dict:
    return {
        "schema": "MigrationVerification.v1",
        "ok": True,
        "archive": "/tmp/task-planning-migration-bundle.tar.gz",
        "extract_dir": "/tmp/changxin-migration-verify",
        "bundle_root": "/tmp/changxin-migration-verify/task-planning-migration-bundle",
        "manifest": {
            "ok": True,
            "bundle_root": "/tmp/changxin-migration-verify/task-planning-migration-bundle",
            "bundle_name": "task-planning-migration-bundle",
            "checked_files": 12,
            "source_machine_id": source_machine_id,
            "errors": [],
        },
        "checks": [],
        "verification_context": verification_context,
        "source_machine_id": source_machine_id,
        "verifier_machine_id": verifier_machine_id,
    }


if __name__ == "__main__":
    unittest.main()
