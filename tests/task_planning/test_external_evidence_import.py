import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from task_planning.migration import (
    build_artifact_package,
    build_distributed_fleet_goal_evidence,
    discover_goal_evidence_inputs,
    import_external_evidence,
    verify_artifact_package,
)


class ExternalEvidenceImportTest(unittest.TestCase):
    def test_import_external_evidence_copies_to_standard_paths_and_is_discoverable(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            sources = root / "sources"
            sources.mkdir()

            golden_suite = evidence_dir / "reports" / "dev_mock_golden_suite.json"
            golden_suite.parent.mkdir(parents=True)
            _write_golden_suite_report(golden_suite)
            lane_matrix = evidence_dir / "reports" / "lane_matrix.json"
            _write_lane_matrix_report(lane_matrix)
            model_lab = _write_model_lab_report(sources / "home-model.json")
            migration = _write_json(
                sources / "migration.json",
                _migration_verification_dict(verification_context="receiving_machine"),
            )
            handoff_verification = _write_handoff_package_verification_report(
                sources / "handoff-verification.json",
                verification_context="receiving_machine",
            )
            site_ros1 = _write_site_ros1_report(sources / "site-ros1.json")
            package = build_artifact_package(
                artifact_paths=[
                    _write_artifact(sources / "mission-run", mission_profile="dev_mock", platform_backend="mock", command_acks=[]),
                    _write_model_lab_artifact(sources / "model-lab"),
                ],
                output_dir=sources / "packages",
                package_name="external-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            hardware = _write_artifact(
                sources / "hardware-run",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                model_lab_evaluation=model_lab,
                migration_verification_report=migration,
                handoff_package_verification_report=handoff_verification,
                site_acceptance_ros1_report=site_ros1,
                artifact_packages=[package.archive],
                hardware_run_artifacts=[hardware],
            )

            self.assertTrue(report.ok, report.as_dict())
            self.assertTrue((evidence_dir / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue((evidence_dir / "reports" / "migration_verification.json").exists())
            self.assertTrue((evidence_dir / "reports" / "handoff_package_verification.json").exists())
            migration_import = json.loads((evidence_dir / "reports" / "migration_verification.json").read_text(encoding="utf-8"))
            self.assertEqual("receiving_machine", migration_import["verification_context"])
            self.assertTrue((evidence_dir / "reports" / "site_acceptance_work_hardware_ros1.json").exists())
            self.assertTrue((evidence_dir / "reports" / "artifact_package_verification.json").exists())
            package_verification = json.loads((evidence_dir / "reports" / "artifact_package_verification.json").read_text(encoding="utf-8"))
            self.assertEqual("unit_workplace_receiving", package_verification["verification_context"])
            self.assertEqual("unit_workplace_receiving", package_verification["verifications"][0]["verification_context"])
            self.assertEqual("3333333333333333333333333333333333333333333333333333333333333333", package_verification["verifications"][0]["source_machine_id"])
            self.assertNotEqual(
                package_verification["verifications"][0]["source_machine_id"],
                package_verification["verifications"][0]["verifier_machine_id"],
            )
            self.assertTrue((evidence_dir / "artifact_packages" / package.archive.name).exists())
            self.assertTrue((evidence_dir / "hardware_artifacts" / "hardware-run").is_dir())
            self.assertTrue((evidence_dir / "reports" / "external_evidence_import.json").exists())

            discovered = discover_goal_evidence_inputs([evidence_dir])
            self.assertEqual([evidence_dir.resolve() / "reports" / "model_lab_evaluation.json"], discovered.model_lab_evaluations)
            self.assertEqual([evidence_dir.resolve() / "reports" / "lane_matrix.json"], discovered.lane_matrix_reports)
            self.assertEqual([evidence_dir.resolve() / "reports" / "migration_verification.json"], discovered.migration_verification_reports)
            self.assertEqual(
                [evidence_dir.resolve() / "reports" / "handoff_package_verification.json"],
                discovered.handoff_package_verification_reports,
            )
            self.assertEqual([evidence_dir.resolve() / "reports" / "artifact_package_verification.json"], discovered.artifact_package_verification_reports)
            self.assertEqual([evidence_dir.resolve() / "artifact_packages" / package.archive.name], discovered.artifact_packages)
            self.assertEqual([evidence_dir.resolve() / "hardware_artifacts" / "hardware-run"], discovered.hardware_run_artifacts)

            goal = build_distributed_fleet_goal_evidence(
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
            self.assertTrue(goal.ok, goal.as_dict())

    def test_import_external_evidence_rejects_bad_model_lab_schema_without_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_model_lab = _write_json(root / "bad-model.json", {
                "schema": "NotModelLabEvaluation.v1",
                "ok": True,
            })

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                model_lab_evaluation=bad_model_lab,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("ModelLabEvaluation.v1" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_mock_model_lab_as_home_5090_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mock_model_lab = _write_model_lab_report(root / "mock-model.json", model_lab_evidence_kind="mock_endpoint")

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                model_lab_evaluation=mock_model_lab,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("model_lab_evidence_kind" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_mock_provider_as_home_5090_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mock_provider = _write_model_lab_report(root / "mock-provider.json", model_provider="mock")

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                model_lab_evaluation=mock_provider,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("model_provider" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_model_lab_without_rtx_5090_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            weak_probe = _write_model_lab_report(
                root / "weak-probe.json",
                gpu_name="NVIDIA GeForce RTX 4060 Laptop GPU",
            )

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                model_lab_evaluation=weak_probe,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("RTX 5090" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_model_lab_without_nvidia_smi_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            synthetic_probe = _write_model_lab_report(
                root / "synthetic-probe.json",
                probe_source="synthetic",
                probe_command=["synthetic-probe"],
            )

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                model_lab_evaluation=synthetic_probe,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("nvidia-smi" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_model_lab_without_baseline_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_lab = _write_model_lab_report(root / "home-model.json", include_comparison=False)

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                model_lab_evaluation=model_lab,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("baseline_equivalent" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_model_lab_without_lane_matrix_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_lab = _write_model_lab_report(root / "home-model.json")

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                model_lab_evaluation=model_lab,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("lane_matrix report is required" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_model_lab_case_mismatch_without_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json", case_id="uav_ugv_coordination")
            model_lab = _write_model_lab_report(root / "home-model.json", case_id="uav_reconnaissance")

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                model_lab_evaluation=model_lab,
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("case_id must match an OK lane_matrix" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_model_lab_without_artifact_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            model_lab = _write_model_lab_report(root / "home-model.json")

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                model_lab_evaluation=model_lab,
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("matching model-lab artifact package is required" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_model_lab_with_package_metadata_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            model_lab = _write_model_lab_report(root / "home-model.json")
            package = build_artifact_package(
                artifact_paths=[
                    _write_model_lab_artifact(
                        root / "model-lab",
                        machine_id="5555555555555555555555555555555555555555555555555555555555555555",
                    ),
                ],
                output_dir=root / "packages",
                package_name="metadata-mismatch-model-lab",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                model_lab_evaluation=model_lab,
                artifact_packages=[package.archive],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("metadata.machine_id must match" in error for error in report.validation_errors))

    def test_import_external_evidence_accepts_model_lab_after_prior_package_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            model_lab = _write_model_lab_report(root / "home-model.json")
            package = build_artifact_package(
                artifact_paths=[_write_model_lab_artifact(root / "model-lab")],
                output_dir=root / "packages",
                package_name="staged-model-lab",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )

            package_import = import_external_evidence(
                evidence_dir=evidence_dir,
                artifact_packages=[package.archive],
            )
            self.assertTrue(package_import.ok, package_import.as_dict())

            report_import = import_external_evidence(
                evidence_dir=evidence_dir,
                model_lab_evaluation=model_lab,
            )

            self.assertTrue(report_import.ok, report_import.as_dict())
            self.assertTrue((evidence_dir / "reports" / "model_lab_evaluation.json").exists())

    def test_import_external_evidence_accepts_preproduced_artifact_package_verification_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            model_lab = _write_model_lab_report(root / "home-model.json")
            package = build_artifact_package(
                artifact_paths=[_write_model_lab_artifact(root / "model-lab")],
                output_dir=root / "packages",
                package_name="preverified-model-lab",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            verification = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "unit-verify",
                verification_context="unit_workplace_receiving",
            ).as_dict()
            verification_report = _write_json(root / "artifact-package-verification.json", {
                "schema": "TaskPlanningArtifactPackageVerificationSet.v1",
                "ok": True,
                "verification_context": "unit_workplace_receiving",
                "verifications": [verification],
            })

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                model_lab_evaluation=model_lab,
                artifact_packages=[package.archive],
                artifact_package_verification_report=verification_report,
            )

            self.assertTrue(report.ok, report.as_dict())
            imported_report = json.loads((reports / "artifact_package_verification.json").read_text(encoding="utf-8"))
            imported_verification = imported_report["verifications"][0]
            self.assertEqual("unit_workplace_receiving", imported_verification["verification_context"])
            self.assertEqual(
                str((evidence_dir / "artifact_packages" / package.archive.name).resolve()),
                imported_verification["archive"],
            )
            self.assertEqual(verification["source_machine_id"], imported_verification["source_machine_id"])
            self.assertEqual(verification["verifier_machine_id"], imported_verification["verifier_machine_id"])
            self.assertTrue((reports / "model_lab_evaluation.json").exists())

    def test_import_external_evidence_rejects_preproduced_artifact_report_without_matching_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            package = build_artifact_package(
                artifact_paths=[_write_model_lab_artifact(root / "model-lab")],
                output_dir=root / "packages",
                package_name="unprovided-model-lab",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            verification = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "unit-verify",
                verification_context="unit_workplace_receiving",
            ).as_dict()
            verification_report = _write_json(root / "artifact-package-verification.json", {
                "schema": "TaskPlanningArtifactPackageVerificationSet.v1",
                "ok": True,
                "verification_context": "unit_workplace_receiving",
                "verifications": [verification],
            })

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                artifact_package_verification_report=verification_report,
            )

            self.assertFalse(report.ok)
            self.assertFalse((reports / "artifact_package_verification.json").exists())
            self.assertTrue(any("matching artifact package archive" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_model_lab_with_forged_existing_package_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            model_lab = _write_model_lab_report(root / "home-model.json")
            (reports / "artifact_package_verification.json").write_text(json.dumps({
                "schema": "TaskPlanningArtifactPackageVerificationSet.v1",
                "ok": True,
                "verification_context": "unit_workplace_receiving",
                "verifications": [{
                    "schema": "TaskPlanningArtifactPackageVerification.v1",
                    "ok": True,
                    "archive": str(evidence_dir / "artifact_packages" / "missing-model-lab.tar.gz"),
                    "verification_context": "unit_workplace_receiving",
                    "source_machine_id": "3333333333333333333333333333333333333333333333333333333333333333",
                    "verifier_machine_id": "4444444444444444444444444444444444444444444444444444444444444444",
                    "artifact_validations": [{
                        "ok": True,
                        "name": "model-lab",
                        "kind": "model_lab_evaluation",
                        "case_id": "uav_ugv_coordination",
                        "metadata": {
                            "mission_profile": "home_model_lab",
                            "model_provider": "local_http",
                            "platform_backend": "mock",
                            "model_lab_evidence_kind": "home_5090_live",
                            "machine_id": "6666666666666666666666666666666666666666666666666666666666666666",
                        },
                        "errors": [],
                    }],
                }],
            }, indent=2, sort_keys=True), encoding="utf-8")

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                model_lab_evaluation=model_lab,
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("existing artifact package archive is missing" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_model_lab_when_existing_package_archive_is_tampered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            model_lab = _write_model_lab_report(root / "home-model.json")
            package = build_artifact_package(
                artifact_paths=[_write_model_lab_artifact(root / "model-lab")],
                output_dir=root / "packages",
                package_name="tampered-existing-model-lab",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            package_import = import_external_evidence(
                evidence_dir=evidence_dir,
                artifact_packages=[package.archive],
            )
            self.assertTrue(package_import.ok, package_import.as_dict())

            (package.root / "artifacts" / "model-lab" / "model_task_schema.json").write_text(
                json.dumps({"schema": "TaskSchema.v1", "tampered": True}, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            copied_archive = evidence_dir / "artifact_packages" / package.archive.name
            with tarfile.open(copied_archive, "w:gz") as tar:
                tar.add(package.root, arcname=package.root.name)

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                model_lab_evaluation=model_lab,
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("sha256 mismatch" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_model_lab_with_source_machine_existing_package_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            packages_dir = evidence_dir / "artifact_packages"
            reports.mkdir(parents=True)
            packages_dir.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            model_lab = _write_model_lab_report(root / "home-model.json")
            package = build_artifact_package(
                artifact_paths=[_write_model_lab_artifact(root / "model-lab")],
                output_dir=root / "packages",
                package_name="source-only-model-lab",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )
            copied_archive = packages_dir / package.archive.name
            copied_archive.write_bytes(package.archive.read_bytes())
            verification = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify-source",
                verification_context="source_machine",
            ).as_dict()
            verification["archive"] = str(copied_archive)
            (reports / "artifact_package_verification.json").write_text(json.dumps({
                "schema": "TaskPlanningArtifactPackageVerificationSet.v1",
                "ok": True,
                "verification_context": "source_machine",
                "verifications": [verification],
            }, indent=2, sort_keys=True), encoding="utf-8")

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                model_lab_evaluation=model_lab,
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "reports" / "model_lab_evaluation.json").exists())
            self.assertTrue(any("verification_context must be unit_workplace_receiving" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_source_machine_migration_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            migration = _write_json(root / "migration.json", {
                "ok": True,
                "schema": "MigrationVerification.v1",
                "verification_context": "source_machine",
            })

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                migration_verification_report=migration,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "migration_verification.json").exists())
            self.assertTrue(any("verification_context" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_migration_report_without_manifest_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            migration = _write_json(root / "migration.json", {
                "ok": True,
                "schema": "MigrationVerification.v1",
                "verification_context": "receiving_machine",
                "source_machine_id": "3333333333333333333333333333333333333333333333333333333333333333",
                "verifier_machine_id": "4444444444444444444444444444444444444444444444444444444444444444",
            })

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                migration_verification_report=migration,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "migration_verification.json").exists())
            self.assertTrue(any("manifest" in error for error in report.validation_errors))

    def test_import_external_evidence_imports_receiving_handoff_package_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_verification = _write_handoff_package_verification_report(
                root / "handoff-verification.json",
                verification_context="receiving_machine",
            )

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                handoff_package_verification_report=handoff_verification,
            )

            self.assertTrue(report.ok, report.as_dict())
            self.assertTrue((root / "evidence" / "reports" / "handoff_package_verification.json").exists())
            self.assertEqual("handoff_package_verification", report.imported[0].kind)

    def test_import_external_evidence_rejects_source_machine_handoff_package_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_verification = _write_handoff_package_verification_report(
                root / "handoff-source.json",
                verification_context="source_machine",
            )

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                handoff_package_verification_report=handoff_verification,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "handoff_package_verification.json").exists())
            self.assertTrue(any("handoff_package_verification failed" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_receiving_handoff_verification_on_source_machine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_verification = _write_handoff_package_verification_report(
                root / "handoff-same-machine.json",
                verification_context="receiving_machine",
                source_machine_id="5555555555555555555555555555555555555555555555555555555555555555",
                verifier_machine_id="5555555555555555555555555555555555555555555555555555555555555555",
            )

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                handoff_package_verification_report=handoff_verification,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "handoff_package_verification.json").exists())
            self.assertTrue(any("source_machine_id and verifier_machine_id must differ" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_handoff_migration_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_verification = _write_handoff_package_verification_report(
                root / "handoff-mismatched-migration.json",
                verification_context="receiving_machine",
                migration_source_machine_id="8888888888888888888888888888888888888888888888888888888888888888",
            )

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                handoff_package_verification_report=handoff_verification,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "handoff_package_verification.json").exists())
            self.assertTrue(any("embedded migration_verification source_machine_id" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_handoff_without_verifier_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_verification = _write_json(root / "handoff-missing-audit.json", {
                "schema": "DistributedFleetHandoffPackageVerification.v1",
                "ok": True,
                "verification_context": "receiving_machine",
                "source_machine_id": "3333333333333333333333333333333333333333333333333333333333333333",
                "verifier_machine_id": "4444444444444444444444444444444444444444444444444444444444444444",
                "migration_verification": _migration_verification_dict(verification_context="receiving_machine"),
            })

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                handoff_package_verification_report=handoff_verification,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "handoff_package_verification.json").exists())
            self.assertTrue(any("archive" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_handoff_with_embedded_migration_missing_manifest_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_verification = _write_json(root / "handoff-embedded-migration-missing-audit.json", {
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
            })

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                handoff_package_verification_report=handoff_verification,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "handoff_package_verification.json").exists())
            errors = "\n".join(report.validation_errors)
            self.assertIn("migration_verification", errors)
            self.assertIn("manifest", errors)

    def test_import_external_evidence_rejects_malformed_artifact_package_without_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "bad-artifacts.tar.gz"
            payload = root / "payload.txt"
            payload.write_text("not an artifact package", encoding="utf-8")
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(payload, arcname="bad-package/payload.txt")

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                artifact_packages=[archive],
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "artifact_packages" / archive.name).exists())
            self.assertTrue(any("artifact package verification failed" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_source_machine_artifact_package_without_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_artifact(root / "mission-run", mission_profile="dev_mock", platform_backend="mock", command_acks=[])],
                output_dir=root / "packages",
                package_name="source-machine-artifacts",
            )

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                artifact_packages=[package.archive],
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "artifact_packages" / package.archive.name).exists())
            self.assertTrue(any("different machine" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_artifact_package_without_lane_matrix_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_artifact(root / "mission-run", mission_profile="dev_mock", platform_backend="mock", command_acks=[])],
                output_dir=root / "packages",
                package_name="no-lane-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                artifact_packages=[package.archive],
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "artifact_packages" / package.archive.name).exists())
            self.assertTrue(any("lane_matrix report is required" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_artifact_package_case_mismatch_without_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json", case_id="uav_ugv_coordination")
            package = build_artifact_package(
                artifact_paths=[_write_artifact(
                    root / "mission-run",
                    mission_profile="dev_mock",
                    platform_backend="mock",
                    command_acks=[],
                    case_id="uav_reconnaissance",
                )],
                output_dir=root / "packages",
                package_name="wrong-case-artifacts",
                source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
            )

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                artifact_packages=[package.archive],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "artifact_packages" / package.archive.name).exists())
            self.assertTrue(any("artifact package case_id must match" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_mock_profile_ros1_signature_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json", platform_backend="mock")

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                site_acceptance_ros1_report=site_ros1,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "site_acceptance_work_hardware_ros1.json").exists())
            self.assertTrue(any("platform_backend" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_caller_supplied_ros1_signature_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json", command_environment_source="caller_supplied")

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                site_acceptance_ros1_report=site_ros1,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "site_acceptance_work_hardware_ros1.json").exists())
            self.assertTrue(any("command_environment_source" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_ros1_signature_report_without_machine_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json", machine_id="")

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                site_acceptance_ros1_report=site_ros1,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "site_acceptance_work_hardware_ros1.json").exists())
            self.assertTrue(any("machine_id" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_ros1_signature_without_readiness_and_hardware_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
            data = json.loads(site_ros1.read_text(encoding="utf-8"))
            data.pop("readiness", None)
            data.pop("hardware_gate", None)
            site_ros1.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                site_acceptance_ros1_report=site_ros1,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "site_acceptance_work_hardware_ros1.json").exists())
            errors = "\n".join(report.validation_errors)
            self.assertIn("readiness", errors)
            self.assertIn("hardware_gate", errors)

    def test_import_external_evidence_rejects_ros1_signature_not_matched_to_observed_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
            data = json.loads(site_ros1.read_text(encoding="utf-8"))
            data["rosservice_audit"]["matched_services"] = ["/fleet/uav_0/gateway/dry_run"]
            site_ros1.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                site_acceptance_ros1_report=site_ros1,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "site_acceptance_work_hardware_ros1.json").exists())
            self.assertTrue(any("matched_services" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_ros1_signature_without_paired_dry_run_and_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
            data = json.loads(site_ros1.read_text(encoding="utf-8"))
            data["rosservice_audit"]["matched_services"] = ["/fleet/uav_0/gateway/dry_run"]
            data["rosservice_audit"]["observed_service_count"] = 1
            data["rosservice_audit"]["service_signatures"] = [
                signature
                for signature in data["rosservice_audit"]["service_signatures"]
                if signature["service_name"] == "/fleet/uav_0/gateway/dry_run"
            ]
            site_ros1.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                site_acceptance_ros1_report=site_ros1,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "site_acceptance_work_hardware_ros1.json").exists())
            self.assertTrue(any("paired dry_run and dispatch" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_ros1_signature_with_unpaired_gateway_prefixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
            data = json.loads(site_ros1.read_text(encoding="utf-8"))
            data["rosservice_audit"]["matched_services"] = [
                "/fleet/uav_0/gateway/dry_run",
                "/fleet/ugv_0/gateway/dispatch",
            ]
            data["rosservice_audit"]["service_signatures"][1]["service_name"] = "/fleet/ugv_0/gateway/dispatch"
            site_ros1.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                site_acceptance_ros1_report=site_ros1,
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "reports" / "site_acceptance_work_hardware_ros1.json").exists())
            self.assertTrue(any("paired dry_run and dispatch" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_non_hardware_artifact_without_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dev_mock_artifact = _write_artifact(
                root / "dev-mock-run",
                mission_profile="dev_mock",
                platform_backend="mock",
                command_acks=[],
            )

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                hardware_run_artifacts=[dev_mock_artifact],
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "hardware_artifacts" / "dev-mock-run").exists())
            self.assertTrue(any("mission_profile=work_hardware" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_without_lane_matrix_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("lane_matrix report is required" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_case_mismatch_without_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json", case_id="uav_ugv_coordination")
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
                case_id="uav_reconnaissance",
            )

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("hardware artifact case_id must match" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_without_ros1_signature_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
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

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("site_acceptance_work_hardware_ros1 report is required" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_machine_mismatch_with_ros1_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json", machine_id="8888888888888888888888888888888888888888888888888888888888888888")
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

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("hardware artifact machine_id must match" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_dispatch_service_without_signed_gate_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
            site_data = json.loads(site_ros1.read_text(encoding="utf-8"))
            site_data["rosservice_audit"]["matched_services"] = [
                "/fleet/ugv_0/gateway/dry_run",
                "/fleet/ugv_0/gateway/dispatch",
            ]
            site_data["rosservice_audit"]["service_signatures"][0]["service_name"] = "/fleet/ugv_0/gateway/dry_run"
            site_data["rosservice_audit"]["service_signatures"][1]["service_name"] = "/fleet/ugv_0/gateway/dispatch"
            site_ros1.write_text(json.dumps(site_data, indent=2, sort_keys=True), encoding="utf-8")
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

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("dispatch service must match a signed" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_with_non_gateway_dispatch_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
            non_gateway_dispatch = _dispatch_gateway_record()
            non_gateway_dispatch["service"] = "/fleet/uav_0/custom/dispatch"
            hardware = _write_artifact(
                root / "hardware-run",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[non_gateway_dispatch],
                task_progress=[_task_progress()],
            )

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("/gateway/dispatch" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_with_rejected_dispatch_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
            trace = _dispatch_gateway_record()
            trace["accepted"] = False
            hardware = _write_artifact(
                root / "hardware-run",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[trace],
                task_progress=[_task_progress()],
            )

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("accepted=true" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_with_wrong_gateway_trace_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
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
            gateway_trace = json.loads((hardware / "gateway_trace.json").read_text(encoding="utf-8"))
            gateway_trace["schema"] = "NotGatewayTrace.v1"
            (hardware / "gateway_trace.json").write_text(json.dumps(gateway_trace, indent=2, sort_keys=True), encoding="utf-8")

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("valid mission artifact bundle" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_with_wrong_command_ack_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
            ack = _accepted_ack()
            ack["schema"] = "NotCommandAck.v1"
            hardware = _write_artifact(
                root / "hardware-run",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[ack],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("CommandAck.v1" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_with_wrong_task_progress_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
            progress = _task_progress()
            progress["schema"] = "NotTaskProgress.v1"
            hardware = _write_artifact(
                root / "hardware-run",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[progress],
            )

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("TaskProgress.v1" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_without_dispatch_trace(self):
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

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                hardware_run_artifacts=[dry_run_only],
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "hardware_artifacts" / "dry-run-only").exists())
            self.assertTrue(any("successful ROS1 /gateway/dispatch service call" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_without_unit_context(self):
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

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                hardware_run_artifacts=[missing_context],
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "hardware_artifacts" / "missing-context").exists())
            self.assertTrue(any("execution_context=unit_workplace_hardware" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_without_recorded_dispatch_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
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

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            errors = "\n".join(report.validation_errors)
            self.assertIn("HARDWARE_DISPATCH_RECORDED", errors)
            self.assertIn("source_validation_report", errors)

    def test_import_external_evidence_rejects_hardware_artifact_with_nonempty_validation_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
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

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("validation_report.errors must be empty" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_with_invalid_validation_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
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
            validation["schema"] = "LegacyReport.v1"
            (hardware / "validation_report.json").write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("validation_report.json must be ValidationReport.v1" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_with_invalid_command_ack_set_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
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
            command_acks = json.loads((hardware / "command_acks.json").read_text(encoding="utf-8"))
            command_acks["schema"] = "LegacyCommandAckSet.v1"
            (hardware / "command_acks.json").write_text(json.dumps(command_acks, indent=2, sort_keys=True), encoding="utf-8")

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[hardware],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "hardware-run").exists())
            self.assertTrue(any("command_acks.json must be CommandAckSet.v1" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_with_unmatched_mission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = _task_progress()
            progress["mission_id"] = "other_mission"
            unmatched_mission = _write_artifact(
                root / "unmatched-mission",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[progress],
            )

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                hardware_run_artifacts=[unmatched_mission],
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "hardware_artifacts" / "unmatched-mission").exists())
            self.assertTrue(any("mission_id/task_id/platform_id" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_without_common_ack_trace_progress_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
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

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[split_proof],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "split-proof").exists())
            self.assertTrue(any("must share the same mission_id/task_id/platform_id" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_with_dispatch_service_platform_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            reports = evidence_dir / "reports"
            reports.mkdir(parents=True)
            _write_lane_matrix_report(reports / "lane_matrix.json")
            site_ros1 = _write_site_ros1_report(root / "site-ros1.json")
            site_data = json.loads(site_ros1.read_text(encoding="utf-8"))
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
            site_ros1.write_text(json.dumps(site_data, indent=2, sort_keys=True), encoding="utf-8")
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

            report = import_external_evidence(
                evidence_dir=evidence_dir,
                site_acceptance_ros1_report=site_ros1,
                hardware_run_artifacts=[mismatch],
            )

            self.assertFalse(report.ok)
            self.assertFalse((evidence_dir / "hardware_artifacts" / "service-platform-mismatch").exists())
            self.assertTrue(any("service must match platform_id" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_without_operator_approval_record(self):
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

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                hardware_run_artifacts=[missing_operator_approval],
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "hardware_artifacts" / "missing-operator-approval").exists())
            self.assertTrue(any("operator_approved=true" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_without_machine_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_machine_id = _write_artifact(
                root / "missing-machine-id",
                mission_profile="work_hardware",
                platform_backend="ros1_gateway",
                hardware_approval_required=True,
                operator_approved=True,
                operator_approval_source="local_unit_operator",
                machine_id="",
                execution_context="unit_workplace_hardware",
                command_acks=[_accepted_ack()],
                gateway_records=[_dispatch_gateway_record()],
                task_progress=[_task_progress()],
            )

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                hardware_run_artifacts=[missing_machine_id],
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "hardware_artifacts" / "missing-machine-id").exists())
            self.assertTrue(any("machine_id" in error for error in report.validation_errors))

    def test_import_external_evidence_rejects_hardware_artifact_without_local_operator_source(self):
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

            report = import_external_evidence(
                evidence_dir=root / "evidence",
                hardware_run_artifacts=[wrong_operator_source],
            )

            self.assertFalse(report.ok)
            self.assertFalse((root / "evidence" / "hardware_artifacts" / "wrong-operator-source").exists())
            self.assertTrue(any("operator_approval_source" in error for error in report.validation_errors))


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


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
    include_comparison: bool = True,
    case_id: str = "uav_ugv_coordination",
):
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
        "machine_id": "6666666666666666666666666666666666666666666666666666666666666666",
        "accelerator_probe": _accelerator_probe(gpu_name, source=probe_source, command=probe_command),
    }
    if include_comparison:
        data.update({
            "baseline_equivalent": True,
            "diffs": [],
            "validation_errors": [],
        })
    return _write_json(path, data)


def _write_model_lab_artifact(
    root: Path,
    *,
    case_id: str = "uav_ugv_coordination",
    machine_id: str = "6666666666666666666666666666666666666666666666666666666666666666",
):
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
        _write_json(root / filename, data)
    return root


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
    platform_backend: str = "ros1_gateway",
    command_environment_source: str = "profile",
    machine_id: str = "7777777777777777777777777777777777777777777777777777777777777777",
):
    data = {
        "schema": "TaskPlanningSiteAcceptance.v1",
        "ok": True,
        "mission_profile": "work_hardware",
        "platform_backend": platform_backend,
        "acceptance_level": "work_hardware_ros1_signatures_observed",
        "readiness": {
            "schema": "EnvironmentReadinessReport.v1",
            "ok": True,
            "mission_profile": "work_hardware",
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
    if machine_id:
        data["machine_id"] = machine_id
    return _write_json(path, data)


def _write_golden_suite_report(path: Path) -> None:
    _write_json(path, {
        "schema": "DevMockGoldenSuite.v1",
        "ok": True,
        "required_case_ids": [
            "single_ugv_inspection",
            "uav_reconnaissance",
            "uav_ugv_coordination",
            "failure_and_replan",
            "disconnect_continue_authorized_subtree",
        ],
        "case_results": [
            {"case_id": "single_ugv_inspection", "ok": True, "run_id": "run-1", "artifact_bundle_path": "/tmp/run-1"},
            {"case_id": "uav_reconnaissance", "ok": True, "run_id": "run-2", "artifact_bundle_path": "/tmp/run-2"},
            {"case_id": "uav_ugv_coordination", "ok": True, "run_id": "run-3", "artifact_bundle_path": "/tmp/run-3"},
            {"case_id": "failure_and_replan", "ok": True, "run_id": "run-4", "artifact_bundle_path": "/tmp/run-4"},
            {"case_id": "disconnect_continue_authorized_subtree", "ok": True, "run_id": "run-5", "artifact_bundle_path": "/tmp/run-5"},
        ],
    })


def _write_lane_matrix_report(path: Path, *, case_id: str = "uav_ugv_coordination") -> None:
    _write_json(path, {
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
        "comparisons": [
            {
                "name": "dev_mock_vs_server_sim",
                "mode": "exact",
                "left_lane": "dev_mock",
                "right_lane": "server_sim",
                "equivalent": True,
                "validation_errors": [],
                "diffs": [],
            },
            {
                "name": "dev_mock_vs_work_hardware_pre_dispatch",
                "mode": "pre_dispatch_compatible",
                "left_lane": "dev_mock",
                "right_lane": "work_hardware",
                "equivalent": True,
                "validation_errors": [],
                "diffs": [],
            },
        ],
    })


def _write_handoff_package_verification_report(
    path: Path,
    *,
    verification_context: str,
    source_machine_id: str = "3333333333333333333333333333333333333333333333333333333333333333",
    verifier_machine_id: str = "4444444444444444444444444444444444444444444444444444444444444444",
    migration_verification_context: str = "",
    migration_source_machine_id: str = "",
    migration_verifier_machine_id: str = "",
):
    migration_source = migration_source_machine_id or source_machine_id
    migration_verifier = migration_verifier_machine_id or verifier_machine_id
    return _write_json(path, {
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
    })


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
        _write_json(root / filename, data)
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


if __name__ == "__main__":
    unittest.main()
