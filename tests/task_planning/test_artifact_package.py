import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from task_planning.migration import build_artifact_package, verify_artifact_package


class ArtifactPackageTest(unittest.TestCase):
    def test_package_cli_accepts_source_machine_id_override(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mission = _write_mission_run(root / "dev-run")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "package_task_planning_artifacts.py"),
                    "--artifact",
                    str(mission),
                    "--output-dir",
                    str(root / "out"),
                    "--package-name",
                    "artifacts-cli-under-test",
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

    def test_build_artifact_package_rejects_unhashed_source_machine_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mission = _write_mission_run(root / "dev-run")
            with self.assertRaisesRegex(ValueError, "64-character lowercase sha256"):
                build_artifact_package(
                    artifact_paths=[mission],
                    output_dir=root / "out",
                    source_machine_id="not-a-hash",
                )

    def test_package_and_verify_mission_run_and_model_lab_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mission = _write_mission_run(root / "dev-run")
            model_lab = _write_model_lab(root / "model-lab")

            package = build_artifact_package(
                artifact_paths=[mission, model_lab],
                output_dir=root / "out",
                package_name="artifacts-under-test",
            )
            result = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
            )

            self.assertTrue(result.ok, result.as_dict())
            self.assertEqual("unspecified", result.verification_context)
            self.assertEqual(package.source_machine_id, result.source_machine_id)
            self.assertEqual(2, len(result.artifact_validations))
            kinds = {item.kind for item in result.artifact_validations}
            self.assertEqual({"mission_run", "model_lab_evaluation"}, kinds)
            self.assertEqual({"uav_ugv_coordination"}, {item.case_id for item in result.artifact_validations})

    def test_tampered_package_fails_checksum_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mission = _write_mission_run(root / "dev-run")
            package = build_artifact_package(
                artifact_paths=[mission],
                output_dir=root / "out",
                package_name="tamper-test",
            )
            (package.root / "artifacts" / "dev-run" / "run_summary.md").write_text("tampered\n", encoding="utf-8")
            tampered_archive = root / "tampered.tar.gz"
            with tarfile.open(tampered_archive, "w:gz") as tar:
                tar.add(package.root, arcname=package.root.name)

            result = verify_artifact_package(
                archive_path=tampered_archive,
                work_dir=root / "verify",
            )

            self.assertFalse(result.ok)
            self.assertTrue(any("sha256 mismatch" in error for error in result.manifest_errors))

    def test_receiving_machine_verification_context_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "dev-run")],
                output_dir=root / "out",
                package_name="receiving-context-test",
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            result = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="receiving_machine",
            )

            self.assertTrue(result.ok, result.as_dict())
            self.assertEqual("receiving_machine", result.as_dict()["verification_context"])
            self.assertEqual("2222222222222222222222222222222222222222222222222222222222222222", result.as_dict()["source_machine_id"])
            self.assertNotEqual(result.as_dict()["source_machine_id"], result.as_dict()["verifier_machine_id"])

    def test_model_lab_package_rejects_success_report_without_model_task_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_lab = _write_model_lab(root / "model-lab")
            (model_lab / "model_task_schema.json").unlink()
            package = build_artifact_package(
                artifact_paths=[model_lab],
                output_dir=root / "out",
                package_name="model-lab-missing-schema",
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            result = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="receiving_machine",
            )

            self.assertFalse(result.ok)
            errors = "\n".join(error for item in result.artifact_validations for error in item.errors)
            self.assertIn("model_task_schema.json is required", errors)

    def test_model_lab_package_rejects_profile_evaluation_lane_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_lab = _write_model_lab(root / "model-lab", evaluation_platform_backend="ros1_gateway")
            package = build_artifact_package(
                artifact_paths=[model_lab],
                output_dir=root / "out",
                package_name="model-lab-mismatch",
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            result = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="receiving_machine",
            )

            self.assertFalse(result.ok)
            errors = "\n".join(error for item in result.artifact_validations for error in item.errors)
            self.assertIn("platform_backend", errors)

    def test_model_lab_package_rejects_case_id_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_lab = _write_model_lab(root / "model-lab", evaluation_case_id="uav_reconnaissance")
            package = build_artifact_package(
                artifact_paths=[model_lab],
                output_dir=root / "out",
                package_name="model-lab-case-mismatch",
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            result = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="receiving_machine",
            )

            self.assertFalse(result.ok)
            errors = "\n".join(error for item in result.artifact_validations for error in item.errors)
            self.assertIn("case_id must match", errors)

    def test_model_lab_package_rejects_schema_mismatch_hidden_by_equivalent_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_lab = _write_model_lab(
                root / "model-lab",
                model_mission_request={"mission_id": "different_mission"},
            )
            package = build_artifact_package(
                artifact_paths=[model_lab],
                output_dir=root / "out",
                package_name="model-lab-hidden-schema-mismatch",
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            result = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="receiving_machine",
            )

            self.assertFalse(result.ok)
            errors = "\n".join(error for item in result.artifact_validations for error in item.errors)
            self.assertIn("baseline_equivalent must match baseline/model schema diff", errors)
            self.assertIn("diffs must match baseline/model schema diff", errors)

    def test_model_lab_package_rejects_stale_diff_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_lab = _write_model_lab(
                root / "model-lab",
                baseline_equivalent=False,
                diffs=[{"path": "mission_request.stale", "baseline": "old", "model": "new"}],
            )
            package = build_artifact_package(
                artifact_paths=[model_lab],
                output_dir=root / "out",
                package_name="model-lab-stale-diff",
                source_machine_id="2222222222222222222222222222222222222222222222222222222222222222",
            )

            result = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="receiving_machine",
            )

            self.assertFalse(result.ok)
            errors = "\n".join(error for item in result.artifact_validations for error in item.errors)
            self.assertIn("baseline_equivalent must match baseline/model schema diff", errors)
            self.assertIn("diffs must match baseline/model schema diff", errors)

    def test_receiving_machine_verification_rejects_source_machine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = build_artifact_package(
                artifact_paths=[_write_mission_run(root / "dev-run")],
                output_dir=root / "out",
                package_name="source-context-test",
            )

            result = verify_artifact_package(
                archive_path=package.archive,
                work_dir=root / "verify",
                verification_context="unit_workplace_receiving",
            )

            self.assertFalse(result.ok)
            self.assertTrue(any("different machine" in error for error in result.manifest_errors))

    def test_unsafe_archive_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "unsafe.tar.gz"
            payload = b"unsafe"
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo("../escape.txt")
                info.size = len(payload)
                import io
                tar.addfile(info, io.BytesIO(payload))

            with self.assertRaises(ValueError):
                verify_artifact_package(archive_path=archive, work_dir=Path(tmp) / "verify")


def _write_mission_run(root: Path) -> Path:
    root.mkdir(parents=True)
    json_files = {
        "environment_profile.json": {
            "schema": "EnvironmentProfile.v1",
            "mission_profile": "dev_mock",
            "model_provider": "mock",
            "platform_backend": "mock",
        },
        "mission_input.json": {"schema": "MissionInput.v1", "run_input": {"case_id": "uav_ugv_coordination"}},
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


def _write_model_lab(
    root: Path,
    *,
    evaluation_platform_backend: str = "mock",
    evaluation_case_id: str = "uav_ugv_coordination",
    baseline_mission_request=None,
    model_mission_request=None,
    baseline_equivalent: bool = True,
    diffs=None,
) -> Path:
    root.mkdir(parents=True)
    baseline_mission_request = baseline_mission_request if baseline_mission_request is not None else {}
    model_mission_request = model_mission_request if model_mission_request is not None else {}
    files = {
        "environment_profile.json": {
            "schema": "EnvironmentProfile.v1",
            "mission_profile": "home_model_lab",
            "model_provider": "local_http",
            "platform_backend": "mock",
        },
        "mission_input.json": {"schema": "ModelLabMissionInput.v1", "case_id": "uav_ugv_coordination"},
        "baseline_task_schema.json": {"schema": "TaskSchema.v1", "mission_request": baseline_mission_request},
        "model_task_schema.json": {"schema": "TaskSchema.v1", "mission_request": model_mission_request},
        "model_lab_evaluation.json": {
            "schema": "ModelLabEvaluation.v1",
            "ok": True,
            "case_id": evaluation_case_id,
            "mission_profile": "home_model_lab",
            "baseline_equivalent": baseline_equivalent,
            "validation_errors": [],
            "diffs": [] if diffs is None else diffs,
            "model_lab_evidence_kind": "mock_endpoint",
            "model_provider": "local_http",
            "platform_backend": evaluation_platform_backend,
            "model_name": "mock-openai-model-lab",
            "model_base_url": "http://127.0.0.1:8000/v1",
        },
    }
    for filename, data in files.items():
        (root / filename).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return root


if __name__ == "__main__":
    unittest.main()
