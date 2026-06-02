import json
import tempfile
import unittest
from pathlib import Path

from task_planning.migration import (
    build_external_evidence_handoff,
    discover_goal_evidence_inputs,
)


class ExternalEvidenceHandoffTest(unittest.TestCase):
    def test_handoff_writes_machine_readable_slots_without_fake_evidence(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            evidence_dir = Path(tmp) / "evidence"
            handoff = build_external_evidence_handoff(
                repo_root=repo_root,
                evidence_dir=evidence_dir,
                case_id="uav_ugv_coordination",
                missing_required=[
                    "home_5090_model_lab_evaluated",
                    "unit_ros1_gateway_signatures_observed",
                ],
            )

            self.assertTrue(handoff.requirements_path.exists())
            self.assertTrue(handoff.next_steps_path.exists())
            self.assertTrue((evidence_dir / "reports").is_dir())
            self.assertTrue((evidence_dir / "artifact_packages").is_dir())
            self.assertTrue((evidence_dir / "hardware_artifacts").is_dir())

            data = json.loads(handoff.requirements_path.read_text(encoding="utf-8"))
            self.assertEqual("DistributedFleetExternalEvidenceHandoff.v1", data["schema"])
            self.assertEqual("uav_ugv_coordination", data["case_id"])
            self.assertEqual(
                ["home_5090_model_lab_evaluated", "unit_ros1_gateway_signatures_observed"],
                data["missing_required"],
            )
            slots = {slot["name"]: slot for slot in data["slots"]}
            self.assertIn("home_5090_model_lab_evaluated", slots)
            self.assertIn("migration_bundle_verified_after_transfer", slots)
            self.assertIn(
                "--verification-context receiving_machine",
                slots["migration_bundle_verified_after_transfer"]["commands"][0],
            )
            self.assertIn(
                "reports/handoff_package_verification.json",
                slots["migration_bundle_verified_after_transfer"]["target_paths"],
            )
            self.assertTrue(any(
                "verify_distributed_fleet_handoff_package.py" in command
                for command in slots["migration_bundle_verified_after_transfer"]["commands"]
            ))
            self.assertIn(
                "Verification reports must include verifier-produced archive/extract_dir paths, checked file counts, manifest or embedded migration manifest audit fields, and empty verifier error lists; a bare ok=true JSON is not transfer proof.",
                slots["migration_bundle_verified_after_transfer"]["constraints"],
            )
            self.assertEqual(
                "reports/model_lab_evaluation.json",
                slots["home_5090_model_lab_evaluated"]["target_paths"][0],
            )
            self.assertIn("PLATFORM_BACKEND=mock", slots["home_5090_model_lab_evaluated"]["constraints"])
            self.assertIn(
                "The evaluation report case_id must be uav_ugv_coordination and must match reports/lane_matrix.json.",
                slots["home_5090_model_lab_evaluated"]["constraints"],
            )
            self.assertIn(
                "Package the full model-lab artifact directory, not only model_lab_evaluation.json.",
                slots["home_5090_model_lab_evaluated"]["constraints"],
            )
            self.assertIn(
                "The matching artifact package must contain a model_lab_evaluation artifact whose case_id and metadata match the evaluation report.",
                slots["home_5090_model_lab_evaluated"]["constraints"],
            )
            self.assertIn(
                "The matching artifact package must be verified through reports/artifact_package_verification.json with verification_context=unit_workplace_receiving; a source-machine package check is not enough to bind home_5090_model_lab_evaluated.",
                slots["home_5090_model_lab_evaluated"]["constraints"],
            )
            self.assertIn(
                "reports/artifact_package_verification.json",
                slots["artifact_package_verified_after_transfer"]["target_paths"],
            )
            self.assertIn(
                "Every verified artifact-level case_id must be uav_ugv_coordination and must match reports/lane_matrix.json.",
                slots["artifact_package_verified_after_transfer"]["constraints"],
            )
            self.assertIn(
                "For home_model_lab proof, the verified model_lab_evaluation artifact metadata must match reports/model_lab_evaluation.json fields: mission_profile, model_provider, platform_backend, model_lab_evidence_kind, and machine_id.",
                slots["artifact_package_verified_after_transfer"]["constraints"],
            )
            self.assertIn(
                "Artifact package verification reports must include archive/extract_dir/package_root, checked_files > 0, manifest_errors=[], artifact_validations, and unit_workplace_receiving source/verifier machine ids.",
                slots["artifact_package_verified_after_transfer"]["constraints"],
            )
            self.assertIn(
                "Import pre-produced unit/workplace package verification reports with --artifact-package-verification-report so the receiving-machine verifier identity is preserved.",
                slots["artifact_package_verified_after_transfer"]["constraints"],
            )
            self.assertTrue(any(
                "--artifact-package-verification-report" in command
                for command in slots["artifact_package_verified_after_transfer"]["commands"]
            ))
            self.assertIn(
                "reports/site_acceptance_work_hardware_ros1.json",
                slots["unit_ros1_gateway_signatures_observed"]["target_paths"],
            )
            self.assertIn(
                "Direct site acceptance collection should report rosservice_audit.command_environment_source=profile; file replay should report captured_files.",
                slots["unit_ros1_gateway_signatures_observed"]["constraints"],
            )
            self.assertTrue(any(
                "work_hardware_ros1_gateway.env.template" in command
                for command in slots["unit_ros1_gateway_signatures_observed"]["commands"]
            ))
            self.assertTrue(any(
                "--profile <local-work-hardware-ros1-gateway.env>" in command
                for command in slots["unit_ros1_gateway_signatures_observed"]["commands"]
            ))
            self.assertIn(
                "Requires a successful /gateway/dispatch ROS1 service trace, not dry_run-only evidence.",
                slots["unit_hardware_execution_artifact_verified"]["constraints"],
            )
            self.assertIn(
                "Requires accepted CommandAck and TaskProgress artifacts from the execution endpoint.",
                slots["unit_hardware_execution_artifact_verified"]["constraints"],
            )
            self.assertIn(
                "Requires execution_context=unit_workplace_hardware and CommandAck/TaskProgress matching the dispatch mission/task/platform.",
                slots["unit_hardware_execution_artifact_verified"]["constraints"],
            )
            self.assertIn(
                "Requires validation_report.schema=ValidationReport.v1, current_state=HARDWARE_DISPATCH_RECORDED, and errors=[] in the final artifact.",
                slots["unit_hardware_execution_artifact_verified"]["constraints"],
            )
            self.assertIn(
                "Requires validation_report.source_validation_report.schema=ValidationReport.v1, current_state=OPERATOR_APPROVAL, and errors=[] from the pre-dispatch artifact.",
                slots["unit_hardware_execution_artifact_verified"]["constraints"],
            )
            self.assertIn(
                "Requires mission_input.run_input.case_id=uav_ugv_coordination matching reports/lane_matrix.json.",
                slots["unit_hardware_execution_artifact_verified"]["constraints"],
            )
            self.assertTrue(any(
                "record_unit_hardware_dispatch_artifact.py" in command
                for command in slots["unit_hardware_execution_artifact_verified"]["commands"]
            ))

            discovered = discover_goal_evidence_inputs([evidence_dir])
            self.assertEqual([], discovered.model_lab_evaluations)
            self.assertEqual([], discovered.migration_verification_reports)
            self.assertEqual([], discovered.artifact_packages)
            self.assertEqual([], discovered.hardware_run_artifacts)

    def test_handoff_markdown_contains_copy_targets_and_goal_check(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            handoff = build_external_evidence_handoff(
                repo_root=repo_root,
                evidence_dir=Path(tmp) / "evidence",
                case_id="uav_ugv_coordination",
                missing_required=["artifact_package_verified_after_transfer"],
            )

            text = handoff.next_steps_path.read_text(encoding="utf-8")
            self.assertIn("reports/model_lab_evaluation.json", text)
            self.assertIn("reports/handoff_package_verification.json", text)
            self.assertIn("artifact_packages/*.tar.gz", text)
            self.assertIn("hardware_artifacts/<run_id>/", text)
            self.assertIn("check_distributed_fleet_goal_evidence.py --evidence-dir", text)
            self.assertIn("--missing-only --print-discovered-inputs", text)
            self.assertIn("--artifact-package-verification-report", text)
            self.assertIn("The home 5090 lane must keep `PLATFORM_BACKEND=mock`", text)
            self.assertIn("All external proof for this handoff must stay on case `uav_ugv_coordination`.", text)
            self.assertIn("requires both `reports/model_lab_evaluation.json` and a `unit_workplace_receiving`-verified model-lab artifact package", text)
            self.assertIn("A bare `ok=true` JSON is not proof", text)
            self.assertIn("does not match `reports/lane_matrix.json`", text)
            self.assertIn("real `work_hardware` + `ros1_gateway` dispatch artifacts", text)
            self.assertIn("execution_context=unit_workplace_hardware", text)
            self.assertIn("validation_report.schema=ValidationReport.v1", text)
            self.assertIn("validation_report.current_state=HARDWARE_DISPATCH_RECORDED", text)
            self.assertIn("validation_report.errors=[]", text)
            self.assertIn("source validation still tied to `ValidationReport.v1` and `OPERATOR_APPROVAL`", text)


if __name__ == "__main__":
    unittest.main()
