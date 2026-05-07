import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "uav" / "01-scripts" / "safe_bringup_lio.sh"


class SafeBringupLioScriptTest(unittest.TestCase):
    def run_dry_run(self, *args):
        return subprocess.run(
            [
                "zsh",
                str(SCRIPT),
                "--dry-run",
                "--diff-planner-dir",
                "/tmp/Diff-planner",
                "--log-dir",
                "/tmp/uav-safe-bringup-test",
                *args,
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout

    def test_planner_stage_stops_before_control_nodes(self):
        output = self.run_dry_run("--stage", "planner")

        self.assertIn("STAGE=planner", output)
        self.assertIn("roslaunch mavros px4.launch", output)
        self.assertIn("roslaunch faster_lio mapping_mid360.launch", output)
        self.assertIn("roslaunch ekf ekf_lidar.launch", output)
        self.assertIn("roslaunch diff_planner run_exp_single_lio.launch", output)
        self.assertNotIn("roslaunch px4ctrl run_ctrl_lio.launch", output)
        self.assertNotIn("roslaunch multipoint multipointplan_exp_lio.launch", output)

    def test_control_stage_requires_explicit_confirmation_flag(self):
        output = self.run_dry_run("--stage", "control-standby", "--yes-control")

        self.assertIn("STAGE=control-standby", output)
        self.assertIn("CONTROL_STANDBY_CONFIRMATION=provided", output)
        self.assertIn("roslaunch px4ctrl run_ctrl_lio.launch", output)
        self.assertIn("roslaunch multipoint multipointplan_exp_lio.launch", output)

    def test_script_is_executable(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))


if __name__ == "__main__":
    unittest.main()
