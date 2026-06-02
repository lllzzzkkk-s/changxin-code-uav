import json
import sys
import types
import unittest

from platform_gateway.ros1_service_node import config_from_args, build_arg_parser, run_gateway_node


class FakeResponse:
    def __init__(self, response_json=""):
        self.response_json = response_json


class FakeService:
    _response_class = FakeResponse


class FakeRospy:
    def __init__(self):
        self.node_name = None
        self.services = []
        self.spins = 0

    def init_node(self, name):
        self.node_name = name

    def Service(self, name, service_type, handler):
        self.services.append((name, service_type, handler))

    def spin(self):
        self.spins += 1


class FakeRequest:
    def __init__(self, task_command_json):
        self.task_command_json = task_command_json


class Ros1ServiceNodeTest(unittest.TestCase):
    def setUp(self):
        module = types.ModuleType("fake_gateway_msgs.srv")
        module.TaskCommandJson = FakeService
        sys.modules["fake_gateway_msgs"] = types.ModuleType("fake_gateway_msgs")
        sys.modules["fake_gateway_msgs.srv"] = module

    def tearDown(self):
        sys.modules.pop("fake_gateway_msgs.srv", None)
        sys.modules.pop("fake_gateway_msgs", None)

    def test_config_formats_service_names_and_node_name(self):
        args = build_arg_parser().parse_args([
            "--platform-id", "uav_0",
            "--platform-type", "uav",
            "--capability", "inspect_area",
            "--service-symbol", "fake_gateway_msgs.srv:TaskCommandJson",
        ])

        config = config_from_args(args)

        self.assertEqual("platform_gateway_uav_0", config.node_name)
        self.assertEqual("/fleet/uav_0/gateway/dry_run", config.dry_run_service_name)
        self.assertEqual("/fleet/uav_0/gateway/dispatch", config.dispatch_service_name)

    def test_run_gateway_node_registers_services_that_delegate_to_core(self):
        rospy = FakeRospy()
        config = config_from_args(build_arg_parser().parse_args([
            "--platform-id", "uav_0",
            "--platform-type", "uav",
            "--capability", "inspect_area",
            "--service-symbol", "fake_gateway_msgs.srv:TaskCommandJson",
        ]))

        run_gateway_node(rospy, config)

        self.assertEqual("platform_gateway_uav_0", rospy.node_name)
        self.assertEqual(2, len(rospy.services))
        self.assertEqual(1, rospy.spins)
        dry_run_name, service_type, dry_run_handler = rospy.services[0]
        self.assertEqual("/fleet/uav_0/gateway/dry_run", dry_run_name)
        self.assertIs(FakeService, service_type)
        command_json = json.dumps({
            "schema": "TaskCommand.v1",
            "mission_id": "mission_001",
            "task_id": "task_001",
            "platform_id": "uav_0",
            "capability": "inspect_area",
            "parameters": {"area_id": "area_A"},
            "disconnect_policy": "continue_current_task",
        })

        response = dry_run_handler(FakeRequest(command_json))
        parsed = json.loads(response.response_json)

        self.assertEqual("GatewayServiceResponse.v1", parsed["schema"])
        self.assertTrue(parsed["ack"]["accepted"])
        self.assertFalse(parsed["motion_attempted"])
        self.assertFalse(parsed["raw_ros_publish_attempted"])


if __name__ == "__main__":
    unittest.main()
