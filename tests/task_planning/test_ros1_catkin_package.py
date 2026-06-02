import unittest
from pathlib import Path


class Ros1CatkinPackageTest(unittest.TestCase):
    def test_platform_gateway_msgs_catkin_package_declares_task_command_json_service(self):
        repo_root = Path(__file__).resolve().parents[2]
        package_root = repo_root / "platform_gateway/ros/catkin_pkg/platform_gateway_msgs"

        package_xml = (package_root / "package.xml").read_text(encoding="utf-8")
        cmake = (package_root / "CMakeLists.txt").read_text(encoding="utf-8")
        service = (package_root / "srv/TaskCommandJson.srv").read_text(encoding="utf-8")

        self.assertIn("<name>platform_gateway_msgs</name>", package_xml)
        self.assertIn("<build_depend>message_generation</build_depend>", package_xml)
        self.assertIn("<exec_depend>message_runtime</exec_depend>", package_xml)
        self.assertIn("add_service_files(", cmake)
        self.assertIn("TaskCommandJson.srv", cmake)
        self.assertIn("generate_messages(", cmake)
        self.assertIn("CATKIN_DEPENDS message_runtime std_msgs", cmake)
        self.assertEqual("string task_command_json\n---\nstring response_json", service.strip())


if __name__ == "__main__":
    unittest.main()
