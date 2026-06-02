import subprocess
import unittest
from pathlib import Path


class WindowsUnitReceivingKitTest(unittest.TestCase):
    def test_powershell_entry_is_windows_intake_only(self):
        repo_root = Path(__file__).resolve().parents[2]
        script = repo_root / "tools" / "windows_unit_receiving_entry.ps1"
        text = script.read_text(encoding="utf-8")

        self.assertIn("Get-FileHash", text)
        self.assertIn("wsl.exe", text)
        self.assertIn("C:\\changxin-evidence", text)
        self.assertIn("logs\\incoming", text)
        self.assertIn("unit_receiving_wsl2.sh", text)
        self.assertNotIn("python3 tools/", text)
        self.assertNotIn("rosservice", text)
        self.assertNotIn("rostopic", text)

    def test_wsl2_script_runs_verifiers_and_keeps_missing_proofs_honest(self):
        repo_root = Path(__file__).resolve().parents[2]
        script = repo_root / "tools" / "unit_receiving_wsl2.sh"
        text = script.read_text(encoding="utf-8")

        subprocess.run(["bash", "-n", str(script)], check=True)
        self.assertIn("verify_distributed_fleet_handoff_package.py", text)
        self.assertIn("--verification-context receiving_machine", text)
        self.assertIn("import_distributed_fleet_external_evidence.py", text)
        self.assertIn("unit_workplace_receiving", text)
        self.assertIn("check_distributed_fleet_phase_gate.py", text)
        self.assertIn("check_distributed_fleet_goal_evidence.py", text)
        self.assertIn("/tmp/changxin-distributed-fleet-evidence", text)
        self.assertIn("waiting_for_external_proofs", text)
        self.assertIn("no artifact package supplied", text)
        self.assertNotIn("rosservice call", text)
        self.assertNotIn("/cmd_vel", text)
        self.assertNotIn("/mavros/", text)

    def test_runbook_lists_expected_outputs_and_boundaries(self):
        repo_root = Path(__file__).resolve().parents[2]
        doc = repo_root / "docs" / "superpowers" / "specs" / "2026-05-29-windows-safe-unit-receiving-kit.md"
        text = doc.read_text(encoding="utf-8")

        self.assertIn("One PowerShell Entry", text)
        self.assertIn("C:\\changxin-evidence\\logs", text)
        self.assertIn("/tmp/changxin-distributed-fleet-evidence", text)
        self.assertIn("Expected output", text)
        self.assertIn("Pass condition", text)
        self.assertIn("Fail condition", text)
        self.assertIn("does not prove unit ROS1 gateway signatures", text)
        self.assertIn("does not turn Mac/source-machine baseline evidence into unit receiving proof", text)
        self.assertIn("No model is deployed to UAV/UGV platforms", text)
        self.assertIn("no LLM may directly publish ROS topics", text)


if __name__ == "__main__":
    unittest.main()
