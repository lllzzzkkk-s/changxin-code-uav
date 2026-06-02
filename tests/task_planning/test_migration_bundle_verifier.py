import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path

from task_planning.migration import (
    build_migration_bundle,
    extract_bundle,
    verify_manifest,
    verify_migration_archive,
)


class MigrationBundleVerifierTest(unittest.TestCase):
    def test_verify_migration_archive_extracts_and_checks_manifest(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle = build_migration_bundle(
                repo_root=repo_root,
                output_dir=tmp_path / "bundle",
                bundle_name="bundle-under-test",
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            result = verify_migration_archive(
                archive_path=bundle.archive,
                work_dir=tmp_path / "verify",
                run_checks=False,
            )

            self.assertTrue(result.ok)
            self.assertTrue(result.bundle_root.exists())
            self.assertEqual("bundle-under-test", result.manifest.bundle_name)
            self.assertGreater(result.manifest.checked_files, 0)
            self.assertEqual([], result.checks)
            self.assertEqual("MigrationVerification.v1", result.as_dict()["schema"])
            self.assertEqual("unspecified", result.verification_context)

    @unittest.skipIf(
        os.environ.get("TASK_PLANNING_MIGRATION_VERIFY_SUBPROCESS") == "1",
        "avoid recursively invoking the migration bundle verifier from its own first-check suite",
    )
    def test_verify_migration_archive_can_run_first_checks_from_extracted_bundle(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle = build_migration_bundle(
                repo_root=repo_root,
                output_dir=tmp_path / "bundle",
                bundle_name="bundle-under-test",
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            result = verify_migration_archive(
                archive_path=bundle.archive,
                work_dir=tmp_path / "verify",
                run_checks=True,
                verification_context="receiving_machine",
            )

            self.assertTrue(result.ok, result.as_dict())
            self.assertEqual("receiving_machine", result.as_dict()["verification_context"])
            self.assertEqual("2222222222222222222222222222222222222222222222222222222222222222", result.as_dict()["source_machine_id"])
            self.assertNotEqual(result.as_dict()["source_machine_id"], result.as_dict()["verifier_machine_id"])
            self.assertEqual(
                [
                    "task_planning_tests",
                    "dev_mock_golden",
                    "dev_mock_golden_suite",
                    "lane_matrix",
                    "external_evidence_handoff",
                    "external_evidence_import",
                    "ros1_service_audit_plan",
                    "site_acceptance_work_hardware",
                ],
                [check.name for check in result.checks],
            )

    def test_receiving_context_rejects_verification_on_source_machine(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle = build_migration_bundle(
                repo_root=repo_root,
                output_dir=tmp_path / "bundle",
                bundle_name="bundle-under-test",
            )

            result = verify_migration_archive(
                archive_path=bundle.archive,
                work_dir=tmp_path / "verify",
                run_checks=False,
                verification_context="receiving_machine",
            )

            self.assertFalse(result.ok)
            self.assertTrue(any("different machine" in error for error in result.manifest.errors))

    def test_verify_manifest_rejects_unhashed_source_machine_id(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle = build_migration_bundle(
                repo_root=repo_root,
                output_dir=tmp_path / "bundle",
                bundle_name="bundle-under-test",
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )
            extracted_root = extract_bundle(bundle.archive, tmp_path / "extract-unhashed")
            manifest_path = extracted_root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_machine_id"] = "not-a-hash"
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

            result = verify_manifest(extracted_root)

            self.assertFalse(result.ok)
            self.assertTrue(any("64-character lowercase sha256" in error for error in result.errors))

    def test_verify_manifest_reports_checksum_mismatch(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle = build_migration_bundle(
                repo_root=repo_root,
                output_dir=tmp_path / "bundle",
                bundle_name="bundle-under-test",
            )
            extracted_root = extract_bundle(bundle.archive, tmp_path / "extract")
            manifest = json.loads((extracted_root / "manifest.json").read_text(encoding="utf-8"))
            target = extracted_root / manifest["files"][0]["path"]
            target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")

            result = verify_manifest(extracted_root)

            self.assertFalse(result.ok)
            self.assertTrue(any("sha256 mismatch" in error for error in result.errors))

    def test_extract_bundle_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive = tmp_path / "bad.tar.gz"
            source = tmp_path / "payload.txt"
            source.write_text("bad", encoding="utf-8")
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(source, arcname="../evil.txt")

            with self.assertRaises(ValueError):
                extract_bundle(archive, tmp_path / "extract")


if __name__ == "__main__":
    unittest.main()
