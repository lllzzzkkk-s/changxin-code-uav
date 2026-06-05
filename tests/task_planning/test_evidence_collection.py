import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from task_planning.migration import collect_distributed_fleet_evidence


class EvidenceCollectionTest(unittest.TestCase):
    def test_collect_local_evidence_writes_standard_reports_and_artifacts(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            result = collect_distributed_fleet_evidence(
                repo_root=repo_root,
                output_dir=Path(tmp) / "evidence",
                case_id="uav_ugv_coordination",
            )

            self.assertTrue(result.manifest.exists())
            self.assertTrue((result.root / "EVIDENCE.md").exists())
            self.assertTrue((result.root / "PHASE_GATE.md").exists())
            self.assertTrue((result.root / "NEXT_EXTERNAL_EVIDENCE.md").exists())
            self.assertTrue((result.root / "reports" / "phase_gate.json").exists())
            self.assertTrue((result.root / "reports" / "external_evidence_requirements.json").exists())
            self.assertIn("goal_evidence", result.reports)
            self.assertIn("phase_gate", result.reports)
            self.assertIn("phase_gate_report", result.reports)
            self.assertIn("external_evidence_requirements", result.reports)
            self.assertIn("lane_matrix", result.artifact_roots)
            self.assertIn("dev_mock_golden_suite", result.reports)
            self.assertIn("dev_mock_golden_suite", result.artifact_roots)
            manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
            self.assertEqual("waiting_for_external_proofs", manifest["phase_gate"]["status"])
            self.assertTrue(manifest["phase_gate"]["local_v1_freeze"])
            self.assertFalse(manifest["phase_gate"]["next_phase_ready"])
            phase_gate_report = json.loads(result.reports["phase_gate_report"].read_text(encoding="utf-8"))
            self.assertEqual(manifest["phase_gate"], phase_gate_report)
            lane_matrix = json.loads(result.reports["lane_matrix"].read_text(encoding="utf-8"))
            self.assertTrue(lane_matrix["ok"], lane_matrix)
            golden_suite = json.loads(result.reports["dev_mock_golden_suite"].read_text(encoding="utf-8"))
            self.assertTrue(golden_suite["ok"], golden_suite)
            self.assertEqual(6, len(golden_suite["case_results"]))
            goal_evidence = json.loads(result.reports["goal_evidence"].read_text(encoding="utf-8"))
            self.assertFalse(goal_evidence["ok"])
            self.assertEqual("waiting_for_external_proofs", goal_evidence["phase_gate"]["status"])
            passed = {item["name"] for item in goal_evidence["items"] if item["status"] == "pass"}
            self.assertIn("lane_matrix_comparable", passed)
            self.assertIn("dev_mock_golden_suite_recorded", passed)
            missing = {item["name"] for item in goal_evidence["missing_required"]}
            self.assertIn("home_5090_model_lab_evaluated", missing)
            self.assertIn("unit_hardware_execution_artifact_verified", missing)
            external_requirements = json.loads(
                (result.root / "reports" / "external_evidence_requirements.json").read_text(encoding="utf-8")
            )
            self.assertEqual("DistributedFleetExternalEvidenceHandoff.v1", external_requirements["schema"])
            self.assertIn("unit_hardware_execution_artifact_verified", external_requirements["missing_required"])
            evidence_text = (result.root / "EVIDENCE.md").read_text(encoding="utf-8")
            self.assertIn("All external proof must use case `uav_ugv_coordination`", evidence_text)
            self.assertIn("artifact-level `case_id` evidence", evidence_text)
            self.assertIn("verified artifact package containing the full model-lab artifact directory", evidence_text)
            self.assertIn("mission_input.run_input.case_id", evidence_text)
            self.assertIn("validation_report.schema=ValidationReport.v1", evidence_text)
            self.assertIn("validation_report.current_state=HARDWARE_DISPATCH_RECORDED", evidence_text)
            self.assertIn("validation_report.errors=[]", evidence_text)
            self.assertIn("source_validation_report.schema=ValidationReport.v1", evidence_text)
            self.assertIn("source_validation_report.current_state=OPERATOR_APPROVAL", evidence_text)
            self.assertIn("source_validation_report.errors=[]", evidence_text)
            self.assertIn("check_distributed_fleet_phase_gate.py --evidence-dir <evidence-dir>", evidence_text)
            phase_gate_text = (result.root / "PHASE_GATE.md").read_text(encoding="utf-8")
            self.assertIn("Status: `waiting_for_external_proofs`", phase_gate_text)
            self.assertIn("Local v1 freeze: `True`", phase_gate_text)
            self.assertIn("do not keep expanding local implementation", phase_gate_text)

    def test_phase_gate_cli_returns_zero_for_local_freeze_waiting_on_external_proofs(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            result = collect_distributed_fleet_evidence(
                repo_root=repo_root,
                output_dir=Path(tmp) / "evidence",
                case_id="uav_ugv_coordination",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "check_distributed_fleet_phase_gate.py"),
                    "--evidence-dir",
                    str(result.root),
                    "--print-discovered-inputs",
                ],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            phase_gate = json.loads(completed.stdout)
            self.assertEqual("DistributedFleetPhaseGateCheck.v1", phase_gate["schema"])
            self.assertEqual("waiting_for_external_proofs", phase_gate["phase_gate"]["status"])
            self.assertTrue(phase_gate["phase_gate"]["local_v1_freeze"])
            self.assertFalse(phase_gate["phase_gate"]["next_phase_ready"])

            strict = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "check_distributed_fleet_phase_gate.py"),
                    "--evidence-dir",
                    str(result.root),
                    "--require-next-phase-ready",
                ],
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(1, strict.returncode)


if __name__ == "__main__":
    unittest.main()
