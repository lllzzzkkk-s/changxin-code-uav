import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "uav" / "01-scripts" / "diagnose_c2_multipoint.sh"


class DiagnoseC2MultipointScriptTest(unittest.TestCase):
    def run_dry_run(self, *args):
        return subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--dry-run",
                "--diff-planner-dir",
                "/tmp/Diff-planner",
                "--evidence-dir",
                "/tmp/c2-diag-test",
                *args,
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout

    def test_dry_run_is_read_only_and_lists_core_c2_checks(self):
        output = self.run_dry_run("--trigger-window-s", "20")

        self.assertIn("DRY_RUN=1", output)
        self.assertIn("rosnode list", output)
        self.assertIn("rostopic info /goal", output)
        self.assertIn("rostopic info /move_base_simple/goal", output)
        self.assertIn("rostopic info /setpoints_cmd", output)
        self.assertIn("rosparam get /multipointplan/yaml_path", output)
        self.assertIn("rostopic echo -n 1 /mavros/state", output)
        self.assertIn("rostopic echo -n 1 /goal", output)
        self.assertIn("grep -nE", output)
        self.assertNotIn("rostopic pub", output)
        self.assertNotIn("rosservice call /mavros/cmd/arming", output)

    def test_help_documents_listener_before_trigger_workflow(self):
        output = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout

        self.assertIn("Read-only C2 multipoint diagnostic", output)
        self.assertIn("ACTION MONITORS ARMED", output)
        self.assertIn("pub_trigger.sh", output)

    def test_script_is_executable(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))


if __name__ == "__main__":
    unittest.main()
