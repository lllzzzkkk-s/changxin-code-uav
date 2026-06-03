import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from task_planning.config import load_profile
from task_planning.mission_ops.acceptance_report import (
    build_phase2_no_motion_acceptance_report,
    render_phase2_no_motion_acceptance_markdown,
)
from task_planning.mission_ops.golden_cases import golden_case_by_id
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore


PHASE1_ARCHIVE = r"D:\changxin\final-archives\changxin-distributed-fleet-final-proof-20260602.tar.gz"
PHASE1_SHA256 = "66465e2a1377e9f2dd11dc4136db9b92fa5d6e369f9f1c06c4a8a4c0ca850366"


class Phase2AcceptanceReportTest(unittest.TestCase):
    def test_acceptance_report_separates_phase1_archive_from_phase2_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = _write_dev_mock_artifact(Path(tmp))
            report = build_phase2_no_motion_acceptance_report(
                artifact_roots=[artifact],
                phase1_archive_path=PHASE1_ARCHIVE,
                phase1_archive_sha256=PHASE1_SHA256,
            )

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual("Phase2NoMotionAcceptanceReport.v1", report.schema)
        self.assertEqual(PHASE1_SHA256, report.phase1_baseline["sha256"])
        self.assertEqual(str(artifact), report.phase2_run["artifact_roots"][0])
        self.assertEqual("mock", report.no_motion_boundary["platform_backend"])
        self.assertFalse(report.no_motion_boundary["ros_connected"])
        self.assertFalse(report.no_motion_boundary["dispatch_performed"])
        self.assertFalse(report.no_motion_boundary["hardware_proof"])

    def test_acceptance_report_rejects_raw_motion_command_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = _write_dev_mock_artifact(Path(tmp))
            bt_path = artifact / "bt_artifact.json"
            bt = json.loads(bt_path.read_text(encoding="utf-8"))
            bt["task_commands"][0]["parameters"]["raw_topic"] = "/cmd_vel"
            bt_path.write_text(json.dumps(bt, indent=2, sort_keys=True), encoding="utf-8")

            report = build_phase2_no_motion_acceptance_report(
                artifact_roots=[artifact],
                phase1_archive_path=PHASE1_ARCHIVE,
                phase1_archive_sha256=PHASE1_SHA256,
            )

        self.assertFalse(report.ok)
        self.assertIn("raw motion command token", "\n".join(report.validation_errors))
        self.assertIn("/cmd_vel", "\n".join(report.validation_errors))

    def test_acceptance_report_markdown_contains_operator_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = _write_dev_mock_artifact(Path(tmp))
            report = build_phase2_no_motion_acceptance_report(
                artifact_roots=[artifact],
                phase1_archive_path=PHASE1_ARCHIVE,
                phase1_archive_sha256=PHASE1_SHA256,
            )

        markdown = render_phase2_no_motion_acceptance_markdown(report)

        self.assertIn("No-Motion Boundary", markdown)
        self.assertIn("Approval", markdown)
        self.assertIn("Execution Events", markdown)
        self.assertIn("Not Hardware Proof", markdown)

    def test_acceptance_report_cli_writes_json_and_markdown(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = _write_dev_mock_artifact(root)
            output_dir = root / "report"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "check_phase2_no_motion_acceptance.py"),
                    "--artifact-root",
                    str(artifact),
                    "--phase1-archive-path",
                    PHASE1_ARCHIVE,
                    "--phase1-archive-sha256",
                    PHASE1_SHA256,
                    "--output-dir",
                    str(output_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

            report = json.loads((output_dir / "phase2_no_motion_acceptance.json").read_text(encoding="utf-8"))
            markdown = (output_dir / "phase2_no_motion_acceptance.md").read_text(encoding="utf-8")

        self.assertEqual("Phase2NoMotionAcceptanceReport.v1", report["schema"])
        self.assertTrue(report["ok"])
        self.assertIn("Phase2NoMotionAcceptanceReport.v1", completed.stdout)
        self.assertIn("Not Hardware Proof", markdown)


def _write_dev_mock_artifact(root: Path) -> Path:
    profile = load_profile(Path("profiles/dev_mock.env"))
    env = dict(profile.as_env_dict())
    env["MISSION_ARTIFACT_ROOT"] = str(root / "runs")
    runner = MissionManagerRunner(state_store=JsonMissionOpsStateStore(root / "states"))
    result = runner.run(golden_case_by_id("single_ugv_inspection").run_input(), env)
    assert result.artifact_bundle_path
    return Path(result.artifact_bundle_path)


if __name__ == "__main__":
    unittest.main()
