import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "ugv" / "01-scripts" / "probe_ugv_runtime_readonly.sh"


class ProbeUgvRuntimeReadonlyScriptTest(unittest.TestCase):
    def run_dry_run(self, *args):
        return subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--dry-run",
                "--workspace-dir",
                "/tmp/catkin_ws",
                "--evidence-dir",
                "/tmp/ugv-runtime-test",
                *args,
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout

    def test_dry_run_lists_runtime_checks_without_writes_to_ros(self):
        output = self.run_dry_run("--echo-timeout-s", "2", "--tf-timeout-s", "2")

        self.assertIn("dry_run: 1", output)
        self.assertIn("rosnode list", output)
        self.assertIn("rostopic info /cmd_vel", output)
        self.assertIn("rostopic info /smoother_cmd_vel", output)
        self.assertIn("rostopic info /move_base_simple/goal", output)
        self.assertIn("rostopic info /move_base/status", output)
        self.assertIn("rostopic echo -n 1 /chassis_info_fb", output)
        self.assertIn("rosrun tf tf_echo map base_link", output)
        self.assertIn("rosrun tf tf_echo odom base_link", output)
        self.assertNotIn("rostopic pub", output)
        self.assertNotIn("rosservice call", output)
        self.assertNotIn("rosparam set", output)

    def test_help_documents_read_only_runtime_probe(self):
        output = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout

        self.assertIn("Read-only UGV runtime probe", output)
        self.assertIn("does not publish", output)
        self.assertIn("--dry-run", output)

    def test_script_is_executable(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))


if __name__ == "__main__":
    unittest.main()
