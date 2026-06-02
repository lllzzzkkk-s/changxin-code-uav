import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from task_planning.migration import (
    HANDOFF_PACKAGE_MANIFEST_SCHEMA,
    HANDOFF_PACKAGE_VERIFICATION_SCHEMA,
    build_distributed_fleet_handoff_package,
    verify_distributed_fleet_handoff_package,
)
from task_planning.migration.verify import ManifestVerification, MigrationVerification


class DistributedFleetHandoffPackageTest(unittest.TestCase):
    def test_package_cli_accepts_source_machine_id_override(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = _write_minimal_evidence_dir(root / "evidence-source")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "package_distributed_fleet_handoff.py"),
                    "--output-dir",
                    str(root / "out"),
                    "--package-name",
                    "handoff-cli-under-test",
                    "--evidence-dir",
                    str(evidence_dir),
                    "--source-machine-id",
                    "1111111111111111111111111111111111111111111111111111111111111111",
                ],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

            package = json.loads(completed.stdout)
            manifest = json.loads(Path(package["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual("1111111111111111111111111111111111111111111111111111111111111111", manifest["source_machine_id"])

    def test_build_handoff_package_rejects_unhashed_source_machine_id(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = _write_minimal_evidence_dir(root / "evidence-source")
            with self.assertRaisesRegex(ValueError, "64-character lowercase sha256"):
                build_distributed_fleet_handoff_package(
                    repo_root=repo_root,
                    output_dir=root / "out",
                    evidence_dir=evidence_dir,
                    source_machine_id="not-a-hash",
                )

    def test_handoff_package_contains_migration_bundle_and_evidence_scaffold(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = _write_minimal_evidence_dir(root / "evidence-source")

            package = build_distributed_fleet_handoff_package(
                repo_root=repo_root,
                output_dir=root / "out",
                package_name="handoff-under-test",
                evidence_dir=evidence_dir,
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            manifest = json.loads(package.manifest.read_text(encoding="utf-8"))
            paths = {item["path"] for item in manifest["files"]}
            components = manifest["components"]

            self.assertEqual(HANDOFF_PACKAGE_MANIFEST_SCHEMA, manifest["schema"])
            self.assertEqual("uav_ugv_coordination", manifest["case_id"])
            self.assertEqual("2222222222222222222222222222222222222222222222222222222222222222", manifest["source_machine_id"])
            self.assertEqual(["home_5090_model_lab_evaluated", "unit_hardware_execution_artifact_verified"], manifest["missing_required"])
            self.assertEqual("migration/task-planning-migration-bundle.tar.gz", components["migration_bundle_archive"])
            self.assertEqual("evidence/manifest.json", components["evidence_manifest"])
            self.assertEqual("evidence/PHASE_GATE.md", components["phase_gate"])
            self.assertEqual("evidence/reports/phase_gate.json", components["phase_gate_report"])
            self.assertEqual("evidence/reports/external_evidence_requirements.json", components["external_evidence_requirements"])
            self.assertEqual("evidence/NEXT_EXTERNAL_EVIDENCE.md", components["next_external_evidence"])
            self.assertIn("HANDOFF.md", paths)
            self.assertIn("migration/task-planning-migration-bundle.tar.gz", paths)
            self.assertIn("migration/task-planning-migration-bundle/tools/package_distributed_fleet_handoff.py", paths)
            self.assertIn("migration/task-planning-migration-bundle/tools/verify_distributed_fleet_handoff_package.py", paths)
            self.assertIn("migration/task-planning-migration-bundle/task_planning/migration/handoff_package.py", paths)
            self.assertIn("evidence/manifest.json", paths)
            self.assertIn("evidence/PHASE_GATE.md", paths)
            self.assertIn("evidence/reports/phase_gate.json", paths)
            self.assertIn("evidence/reports/external_evidence_requirements.json", paths)
            self.assertIn("evidence/NEXT_EXTERNAL_EVIDENCE.md", paths)
            self.assertIn("verify_received_migration_bundle", manifest["commands"])
            self.assertIn("verify_handoff_package", manifest["commands"])
            self.assertIn("inspect_phase_gate", manifest["commands"])
            self.assertIn("check_distributed_fleet_phase_gate.py", manifest["commands"]["inspect_phase_gate"])
            self.assertIn("inspect_missing_evidence", manifest["commands"])
            self.assertIn("verify_distributed_fleet_handoff_package.py", manifest["commands"]["verify_handoff_package_after_transfer"])
            self.assertIn("--verification-context receiving_machine", manifest["commands"]["verify_handoff_package_after_transfer"])

            handoff_doc = (package.root / "HANDOFF.md").read_text(encoding="utf-8")
            self.assertIn("transfer scaffold", handoff_doc)
            self.assertIn("home 5090", handoff_doc)
            self.assertIn("verify_distributed_fleet_handoff_package.py", handoff_doc)
            self.assertIn("--verification-context receiving_machine", handoff_doc)
            self.assertIn("check_distributed_fleet_phase_gate.py", handoff_doc)
            self.assertIn("successful `/gateway/dispatch` trace", handoff_doc)
            self.assertIn("accepted `CommandAck`", handoff_doc)
            self.assertIn("`TaskProgress`", handoff_doc)
            self.assertIn("operator_approval_source=local_unit_operator", handoff_doc)
            self.assertIn("execution_context=unit_workplace_hardware", handoff_doc)
            self.assertIn("evidence/PHASE_GATE.md", handoff_doc)
            self.assertIn("evidence/reports/phase_gate.json", handoff_doc)
            self.assertIn("do not keep expanding local implementation", handoff_doc)

            self.assertTrue(package.archive.exists())
            with tarfile.open(package.archive, "r:gz") as tar:
                names = set(tar.getnames())
            self.assertIn("handoff-under-test/HANDOFF.md", names)
            self.assertIn("handoff-under-test/migration/task-planning-migration-bundle.tar.gz", names)
            self.assertIn("handoff-under-test/evidence/PHASE_GATE.md", names)
            self.assertIn("handoff-under-test/evidence/reports/phase_gate.json", names)
            self.assertIn("handoff-under-test/evidence/reports/external_evidence_requirements.json", names)
            self.assertIn("handoff-under-test/evidence/NEXT_EXTERNAL_EVIDENCE.md", names)

            verification = verify_distributed_fleet_handoff_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="receiving_machine",
            )
            self.assertTrue(verification.ok, verification.as_dict())
            self.assertEqual(HANDOFF_PACKAGE_VERIFICATION_SCHEMA, verification.schema)
            self.assertEqual("receiving_machine", verification.verification_context)
            self.assertEqual("2222222222222222222222222222222222222222222222222222222222222222", verification.source_machine_id)
            self.assertNotEqual(verification.source_machine_id, verification.verifier_machine_id)
            self.assertIsNotNone(verification.migration_verification)
            self.assertEqual("receiving_machine", verification.migration_verification.verification_context)

    def test_receiving_context_rejects_handoff_verification_on_source_machine(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_distributed_fleet_handoff_package(
                repo_root=repo_root,
                output_dir=root / "out",
                package_name="same-source-handoff",
                evidence_dir=_write_minimal_evidence_dir(root / "evidence-source"),
            )

            verification = verify_distributed_fleet_handoff_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="receiving_machine",
            )

            self.assertFalse(verification.ok)
            self.assertTrue(any("different machine" in error for error in verification.manifest_errors))

    def test_handoff_verification_rejects_embedded_migration_source_mismatch(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_distributed_fleet_handoff_package(
                repo_root=repo_root,
                output_dir=root / "out",
                package_name="mismatched-migration-source",
                evidence_dir=_write_minimal_evidence_dir(root / "evidence-source"),
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            def fake_verify_migration_archive(*, archive_path, work_dir, run_checks, verification_context):
                return MigrationVerification(
                    archive=archive_path,
                    extract_dir=work_dir,
                    bundle_root=work_dir,
                    manifest=ManifestVerification(
                        bundle_root=work_dir,
                        bundle_name="task-planning-migration-bundle",
                        checked_files=1,
                        source_machine_id="3333333333333333333333333333333333333333333333333333333333333333",
                    ),
                    verification_context=verification_context,
                    verifier_machine_id=verification_context and "4444444444444444444444444444444444444444444444444444444444444444",
                )

            with mock.patch(
                "task_planning.migration.handoff_package.verify_migration_archive",
                side_effect=fake_verify_migration_archive,
            ):
                verification = verify_distributed_fleet_handoff_package(
                    archive_path=package.archive,
                    work_dir=root / "verify-mismatched-source",
                    verification_context="receiving_machine",
                )

            self.assertFalse(verification.ok)
            self.assertTrue(any(
                "handoff source_machine_id must match embedded migration source_machine_id" in error
                for error in verification.component_errors
            ))

    def test_handoff_package_verification_rejects_tampered_payload(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_distributed_fleet_handoff_package(
                repo_root=repo_root,
                output_dir=root / "out",
                package_name="tampered-handoff",
                evidence_dir=_write_minimal_evidence_dir(root / "evidence-source"),
            )
            (package.root / "HANDOFF.md").write_text("tampered\n", encoding="utf-8")
            tampered_archive = root / "tampered-handoff.tar.gz"
            with tarfile.open(tampered_archive, "w:gz") as tar:
                tar.add(package.root, arcname=package.root.name)

            verification = verify_distributed_fleet_handoff_package(
                archive_path=tampered_archive,
                work_dir=root / "verify-tampered",
                verification_context="receiving_machine",
            )

            self.assertFalse(verification.ok)
            self.assertTrue(any("sha256 mismatch for HANDOFF.md" in error for error in verification.manifest_errors))

    def test_handoff_package_verification_rejects_inconsistent_external_requirements(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_distributed_fleet_handoff_package(
                repo_root=repo_root,
                output_dir=root / "out",
                package_name="inconsistent-requirements-handoff",
                evidence_dir=_write_minimal_evidence_dir(
                    root / "evidence-source",
                    requirements_missing_required=["home_5090_model_lab_evaluated"],
                ),
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            verification = verify_distributed_fleet_handoff_package(
                archive_path=package.archive,
                work_dir=root / "verify-inconsistent",
                verification_context="receiving_machine",
            )

            self.assertFalse(verification.ok)
            self.assertTrue(any(
                "external evidence requirements missing_required" in error
                for error in verification.component_errors
            ))

    def test_handoff_package_verification_rejects_inconsistent_phase_gate(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = _write_minimal_evidence_dir(root / "evidence-source")
            manifest_path = evidence_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["phase_gate"]["missing_external_proofs"] = ["home_5090_model_lab_evaluated"]
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
            package = build_distributed_fleet_handoff_package(
                repo_root=repo_root,
                output_dir=root / "out",
                package_name="inconsistent-phase-gate-handoff",
                evidence_dir=evidence_dir,
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            verification = verify_distributed_fleet_handoff_package(
                archive_path=package.archive,
                work_dir=root / "verify-inconsistent-phase-gate",
                verification_context="receiving_machine",
            )

            self.assertFalse(verification.ok)
            self.assertTrue(any(
                "phase_gate.missing_external_proofs" in error
                for error in verification.component_errors
            ))

    def test_handoff_package_verification_rejects_incomplete_phase_gate_doc(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_distributed_fleet_handoff_package(
                repo_root=repo_root,
                output_dir=root / "out",
                package_name="incomplete-phase-gate-doc",
                evidence_dir=_write_minimal_evidence_dir(root / "evidence-source"),
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )
            _rewrite_packaged_file_and_manifest(
                package,
                "evidence/PHASE_GATE.md",
                "# Distributed Fleet Phase Gate\n\nIncomplete.\n",
            )

            verification = verify_distributed_fleet_handoff_package(
                archive_path=package.archive,
                work_dir=root / "verify-incomplete-phase-gate-doc",
                verification_context="receiving_machine",
            )

            self.assertFalse(verification.ok)
            self.assertEqual([], verification.manifest_errors)
            self.assertTrue(any(
                "PHASE_GATE.md must include Local v1 freeze:" in error
                for error in verification.component_errors
            ))

    def test_handoff_package_verification_rejects_case_id_mismatch(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_distributed_fleet_handoff_package(
                repo_root=repo_root,
                output_dir=root / "out",
                package_name="case-mismatch-handoff",
                evidence_dir=_write_minimal_evidence_dir(
                    root / "evidence-source",
                    requirements_case_id="uav_reconnaissance",
                ),
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            verification = verify_distributed_fleet_handoff_package(
                archive_path=package.archive,
                work_dir=root / "verify-case-mismatch",
                verification_context="receiving_machine",
            )

            self.assertFalse(verification.ok)
            self.assertTrue(any(
                "manifest case_id must match external evidence requirements case_id" in error
                for error in verification.component_errors
            ))

    def test_handoff_package_verification_rejects_missing_external_evidence_slots(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_distributed_fleet_handoff_package(
                repo_root=repo_root,
                output_dir=root / "out",
                package_name="missing-slots-handoff",
                evidence_dir=_write_minimal_evidence_dir(
                    root / "evidence-source",
                    requirements_slots=[],
                ),
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            verification = verify_distributed_fleet_handoff_package(
                archive_path=package.archive,
                work_dir=root / "verify-missing-slots",
                verification_context="receiving_machine",
            )

            self.assertFalse(verification.ok)
            self.assertTrue(any(
                "external evidence requirements slots must be a non-empty list" in error
                for error in verification.component_errors
            ))

    def test_handoff_package_verification_rejects_placeholder_external_evidence_slots(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_distributed_fleet_handoff_package(
                repo_root=repo_root,
                output_dir=root / "out",
                package_name="placeholder-slots-handoff",
                evidence_dir=_write_minimal_evidence_dir(
                    root / "evidence-source",
                    requirements_slots=[_placeholder_external_evidence_slot(name) for name in [
                        "migration_bundle_verified_after_transfer",
                        "home_5090_model_lab_evaluated",
                        "artifact_package_verified_after_transfer",
                        "unit_ros1_gateway_signatures_observed",
                        "unit_hardware_execution_artifact_verified",
                    ]],
                ),
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            verification = verify_distributed_fleet_handoff_package(
                archive_path=package.archive,
                work_dir=root / "verify-placeholder-slots",
                verification_context="receiving_machine",
            )

            self.assertFalse(verification.ok)
            self.assertTrue(any(
                "migration_bundle_verified_after_transfer must mention reports/migration_verification.json" in error
                for error in verification.component_errors
            ))
            self.assertTrue(any(
                "home_5090_model_lab_evaluated must mention evaluate_model_lab_case.py" in error
                for error in verification.component_errors
            ))

    def test_handoff_package_verification_rejects_incomplete_next_external_evidence_doc(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_distributed_fleet_handoff_package(
                repo_root=repo_root,
                output_dir=root / "out",
                package_name="incomplete-next-doc-handoff",
                evidence_dir=_write_minimal_evidence_dir(
                    root / "evidence-source",
                    next_external_text="# Next External Evidence\n",
                ),
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            verification = verify_distributed_fleet_handoff_package(
                archive_path=package.archive,
                work_dir=root / "verify-incomplete-next-doc",
                verification_context="receiving_machine",
            )

            self.assertFalse(verification.ok)
            self.assertTrue(any(
                "NEXT_EXTERNAL_EVIDENCE.md must mention home_5090_model_lab_evaluated" in error
                for error in verification.component_errors
            ))
            self.assertTrue(any(
                "NEXT_EXTERNAL_EVIDENCE.md must include --missing-only --print-discovered-inputs" in error
                for error in verification.component_errors
            ))

    def test_handoff_package_verification_rejects_incomplete_handoff_doc(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_distributed_fleet_handoff_package(
                repo_root=repo_root,
                output_dir=root / "out",
                package_name="incomplete-handoff-doc",
                evidence_dir=_write_minimal_evidence_dir(root / "evidence-source"),
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )
            _rewrite_packaged_file_and_manifest(
                package,
                "HANDOFF.md",
                "# Distributed Fleet Handoff Package\n\nIncomplete operator notes.\n",
            )

            verification = verify_distributed_fleet_handoff_package(
                archive_path=package.archive,
                work_dir=root / "verify-incomplete-handoff",
                verification_context="receiving_machine",
            )

            self.assertFalse(verification.ok)
            self.assertEqual([], verification.manifest_errors)
            self.assertTrue(any(
                "HANDOFF.md must include docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md" in error
                for error in verification.component_errors
            ))
            self.assertTrue(any(
                "HANDOFF.md must include operator_approval_source=local_unit_operator" in error
                for error in verification.component_errors
            ))


def _write_minimal_evidence_dir(
    root: Path,
    *,
    requirements_missing_required=None,
    requirements_case_id: str = "uav_ugv_coordination",
    requirements_slots=None,
    next_external_text: str = "",
) -> Path:
    missing_required = [
        "home_5090_model_lab_evaluated",
        "unit_hardware_execution_artifact_verified",
    ]
    phase_gate = {
        "schema": "DistributedFleetPhaseGate.v1",
        "status": "waiting_for_external_proofs",
        "message": "local v1 is frozen; collect the required external proofs before starting the next phase",
        "local_v1_freeze": True,
        "next_phase_ready": False,
        "required_external_proofs": [
            "migration_bundle_verified_after_transfer",
            "artifact_package_verified_after_transfer",
            "home_5090_model_lab_evaluated",
            "unit_ros1_gateway_signatures_observed",
            "unit_hardware_execution_artifact_verified",
        ],
        "missing_external_proofs": missing_required,
        "failed_external_proofs": [],
        "passed_external_proofs": [],
        "local_unresolved_required": [],
        "policy": "Do not keep iterating local implementation solely because these external proofs are missing.",
    }
    reports = root / "reports"
    reports.mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({
        "schema": "DistributedFleetEvidenceCollectionManifest.v1",
        "case_id": "uav_ugv_coordination",
        "phase_gate": phase_gate,
        "missing_required": missing_required,
        "reports": {
            "external_evidence_requirements": "reports/external_evidence_requirements.json",
            "next_external_evidence": "NEXT_EXTERNAL_EVIDENCE.md",
            "phase_gate": "PHASE_GATE.md",
            "phase_gate_report": "reports/phase_gate.json",
        },
        "artifact_roots": {},
    }, indent=2, sort_keys=True), encoding="utf-8")
    (root / "PHASE_GATE.md").write_text(_phase_gate_text(missing_required), encoding="utf-8")
    (reports / "phase_gate.json").write_text(json.dumps(phase_gate, indent=2, sort_keys=True), encoding="utf-8")
    (root / "NEXT_EXTERNAL_EVIDENCE.md").write_text(
        next_external_text or _next_external_evidence_text(),
        encoding="utf-8",
    )
    (reports / "external_evidence_requirements.json").write_text(json.dumps({
        "schema": "DistributedFleetExternalEvidenceHandoff.v1",
        "case_id": requirements_case_id,
        "missing_required": requirements_missing_required or missing_required,
        "slots": _required_external_evidence_slots() if requirements_slots is None else requirements_slots,
    }, indent=2, sort_keys=True), encoding="utf-8")
    return root


def _phase_gate_text(missing_required) -> str:
    return "\n".join([
        "# Distributed Fleet Phase Gate",
        "",
        "Status: `waiting_for_external_proofs`",
        "Local v1 freeze: `True`",
        "Next phase ready: `False`",
        "",
        "Missing external proofs:",
        "",
        *[f"- `{name}`" for name in missing_required],
        "",
        "Local unresolved requirements:",
        "",
        "- none",
        "",
        "If local v1 freeze is `True`, do not keep expanding local implementation just because external proofs are still missing.",
        "Import the real reports and packages, rerun `tools/check_distributed_fleet_goal_evidence.py`, and start the next phase only when `next_phase_ready` is `True`.",
        "",
    ])


def _required_external_evidence_slots():
    return [
        _external_evidence_slot("migration_bundle_verified_after_transfer"),
        _external_evidence_slot("home_5090_model_lab_evaluated"),
        _external_evidence_slot("artifact_package_verified_after_transfer"),
        _external_evidence_slot("unit_ros1_gateway_signatures_observed"),
        _external_evidence_slot("unit_hardware_execution_artifact_verified"),
    ]


def _external_evidence_slot(name: str):
    snippets = {
        "migration_bundle_verified_after_transfer": {
            "target_paths": ["reports/migration_verification.json", "reports/handoff_package_verification.json"],
            "constraints": ["--verification-context receiving_machine", "bare ok=true JSON is not transfer proof"],
            "commands": ["verify_task_planning_migration_bundle.py", "verify_distributed_fleet_handoff_package.py"],
        },
        "home_5090_model_lab_evaluated": {
            "target_paths": ["reports/model_lab_evaluation.json", "artifact_packages/*.tar.gz"],
            "constraints": ["MODEL_LAB_EVIDENCE_KIND=home_5090_live", "RTX 5090", "PLATFORM_BACKEND=mock"],
            "commands": ["evaluate_model_lab_case.py", "package_task_planning_artifacts.py"],
        },
        "artifact_package_verified_after_transfer": {
            "target_paths": ["artifact_packages/*.tar.gz", "reports/artifact_package_verification.json"],
            "constraints": ["verification_context=unit_workplace_receiving", "source_machine_id", "verifier_machine_id"],
            "commands": ["verify_task_planning_artifacts.py", "--verification-context unit_workplace_receiving", "--artifact-package-verification-report"],
        },
        "unit_ros1_gateway_signatures_observed": {
            "target_paths": ["reports/site_acceptance_work_hardware_ros1.json"],
            "constraints": ["TaskCommandJson", "task_command_json", "Do not send control commands"],
            "commands": ["check_task_planning_site_acceptance.py", "--run-rosservice-list", "--run-service-signatures"],
        },
        "unit_hardware_execution_artifact_verified": {
            "target_paths": ["hardware_artifacts/<run_id>/"],
            "constraints": ["/gateway/dispatch", "operator_approved=true", "execution_context=unit_workplace_hardware"],
            "commands": ["record_unit_hardware_dispatch_artifact.py", "check_distributed_fleet_goal_evidence.py"],
        },
    }[name]
    return {
        "name": name,
        "lane": "test",
        "purpose": f"test slot for {name}",
        "target_paths": snippets["target_paths"],
        "constraints": snippets["constraints"],
        "commands": snippets["commands"],
        "needed_now": False,
    }


def _placeholder_external_evidence_slot(name: str):
    return {
        "name": name,
        "lane": "test",
        "purpose": f"test slot for {name}",
        "target_paths": [f"reports/{name}.json"],
        "constraints": ["test constraint"],
        "commands": ["test command"],
        "needed_now": False,
    }


def _next_external_evidence_text() -> str:
    return "\n".join([
        "# Next External Evidence",
        "",
        "Missing proof slots:",
        *[f"- `{slot['name']}`" for slot in _required_external_evidence_slots()],
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/import_distributed_fleet_external_evidence.py --evidence-dir <evidence-dir> --model-lab-evaluation <model_lab_evaluation.json> --migration-verification-report <migration_verification.json> --handoff-package-verification-report <handoff_package_verification.json> --artifact-package-verification-report <artifact_package_verification.json> --site-acceptance-ros1-report <site_acceptance_work_hardware_ros1.json> --artifact-package <artifact-package.tar.gz> --hardware-run-artifact <hardware-run-artifact-root>",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir <evidence-dir>",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir <evidence-dir> --missing-only --print-discovered-inputs",
        "```",
        "",
    ])


def _rewrite_packaged_file_and_manifest(package, rel_path: str, text: str) -> None:
    path = package.root / rel_path
    path.write_text(text, encoding="utf-8")
    manifest_path = package.root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        if item["path"] == rel_path:
            item["bytes"] = path.stat().st_size
            item["sha256"] = _sha256(path)
            break
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    with tarfile.open(package.archive, "w:gz") as tar:
        tar.add(package.root, arcname=package.root.name)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
