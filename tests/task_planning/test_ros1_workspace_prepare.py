import tempfile
import unittest
from pathlib import Path

from task_planning.migration.ros1_workspace import prepare_ros1_gateway_workspace


class Ros1WorkspacePrepareTest(unittest.TestCase):
    def test_dry_run_reports_next_commands_without_modifying_workspace(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            catkin_src = Path(tmp) / "catkin_ws" / "src"
            catkin_src.mkdir(parents=True)

            plan = prepare_ros1_gateway_workspace(
                repo_root=repo_root,
                catkin_src=catkin_src,
            )

            self.assertTrue(plan.ok, plan.as_dict())
            self.assertTrue(plan.dry_run)
            self.assertFalse(plan.installed)
            self.assertFalse((catkin_src / "platform_gateway_msgs").exists())
            self.assertIn("catkin_make", plan.next_commands)
            self.assertTrue(any("run_ros1_platform_gateway_node.py" in command for command in plan.next_commands))

    def test_apply_copy_installs_catkin_package(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            catkin_src = Path(tmp) / "catkin_ws" / "src"
            catkin_src.mkdir(parents=True)

            plan = prepare_ros1_gateway_workspace(
                repo_root=repo_root,
                catkin_src=catkin_src,
                apply=True,
            )

            target = catkin_src / "platform_gateway_msgs"
            self.assertTrue(plan.ok, plan.as_dict())
            self.assertTrue(plan.installed)
            self.assertTrue((target / "package.xml").exists())
            self.assertEqual(
                "string task_command_json\n---\nstring response_json",
                (target / "srv/TaskCommandJson.srv").read_text(encoding="utf-8").strip(),
            )

    def test_apply_refuses_existing_package_without_force(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            catkin_src = Path(tmp) / "catkin_ws" / "src"
            existing = catkin_src / "platform_gateway_msgs"
            existing.mkdir(parents=True)

            plan = prepare_ros1_gateway_workspace(
                repo_root=repo_root,
                catkin_src=catkin_src,
                apply=True,
            )

            self.assertFalse(plan.ok)
            self.assertIn("target package already exists", "\n".join(plan.validation_errors))

    def test_missing_catkin_src_fails_before_install(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            plan = prepare_ros1_gateway_workspace(
                repo_root=repo_root,
                catkin_src=Path(tmp) / "missing" / "src",
                apply=True,
            )

            self.assertFalse(plan.ok)
            self.assertIn("catkin src path does not exist", "\n".join(plan.validation_errors))


if __name__ == "__main__":
    unittest.main()
