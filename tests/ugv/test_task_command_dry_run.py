import unittest

from ugv.llm_control.command_adapter import build_task_command_dry_run
from ugv.llm_control.state_adapter import build_platform_state


def platform_state(*, unlocked=True, battery_soc=60, map_tf=True):
    runtime = {
        "captured_at": 100.0,
        "ros_master_reachable": True,
        "nodes": ["/move_base", "/velocity_smoother", "/yhs_can_control_node"],
        "map_to_base_link": {
            "updated_at": 99.9,
            "translation": {"x": -0.394, "y": 3.099, "z": 0.0},
            "rotation": {"yaw": -0.162},
        }
        if map_tf
        else None,
        "odom": {
            "updated_at": 99.9,
            "twist": {
                "linear": {"x": 0.0, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
        },
        "chassis_info_fb": {
            "updated_at": 99.9,
            "ctrl_fb": {"ctrl_fb_gear": 6, "ctrl_fb_linear": 0.0, "ctrl_fb_angular": 0.0},
            "io_fb": {
                "io_fb_unlock": unlocked,
                "io_fb_estop": False,
                "io_fb_charge_state": False,
            },
            "bms_flag_fb": {"bms_flag_fb_soc": battery_soc, "bms_flag_fb_charge_flag": False},
            "bms_fb": {"bms_fb_voltage": 48.0, "bms_fb_current": 0.0},
        },
        "move_base_status": {"updated_at": 99.9, "status_list": []},
    }
    return build_platform_state(runtime, platform_id="ugv_1")


def command(intent, arguments=None):
    return {
        "meta": {"request_id": "cmd-test"},
        "intent": {"name": intent},
        "arguments": arguments or {},
    }


class UgvTaskCommandDryRunTest(unittest.TestCase):
    def test_navigate_to_pose_maps_to_move_base_action_without_publish(self):
        report = build_task_command_dry_run(
            command("navigate_to_pose", {"frame_id": "map", "x": 1.2, "y": 2.3, "yaw": 0.4}),
            platform_state(),
        )

        self.assertEqual("TaskCommandDryRun.v1", report["schema"])
        self.assertEqual("needs_confirmation", report["status"])
        self.assertFalse(report["publish_attempted"])
        self.assertEqual([], report["safety"]["reasons"])
        self.assertEqual("ros_action", report["ros_instruction"]["kind"])
        self.assertEqual("/move_base", report["ros_instruction"]["action_server"])
        self.assertEqual("move_base_msgs/MoveBaseAction", report["ros_instruction"]["action_type"])
        self.assertEqual("map", report["ros_instruction"]["goal"]["target_pose"]["header"]["frame_id"])
        self.assertEqual(1.2, report["ros_instruction"]["goal"]["target_pose"]["pose"]["position"]["x"])
        self.assertEqual(2.3, report["ros_instruction"]["goal"]["target_pose"]["pose"]["position"]["y"])

    def test_navigate_to_pose_is_rejected_when_platform_state_motion_gate_blocks(self):
        report = build_task_command_dry_run(
            command("navigate_to_pose", {"frame_id": "map", "x": 1.2, "y": 2.3, "yaw": 0.0}),
            platform_state(unlocked=False),
        )

        self.assertEqual("safety_rejected", report["status"])
        self.assertFalse(report["publish_attempted"])
        self.assertIsNone(report["ros_instruction"])
        self.assertIn("chassis_locked", report["safety"]["reasons"])

    def test_cancel_navigation_maps_to_move_base_cancel_without_motion_gate(self):
        report = build_task_command_dry_run(command("cancel_navigation"), platform_state(unlocked=False, battery_soc=10))

        self.assertEqual("succeeded", report["status"])
        self.assertFalse(report["publish_attempted"])
        self.assertEqual("ros_topic", report["ros_instruction"]["kind"])
        self.assertEqual("/move_base/cancel", report["ros_instruction"]["topic"])
        self.assertEqual("actionlib_msgs/GoalID", report["ros_instruction"]["message_type"])
        self.assertEqual({}, report["ros_instruction"]["message"])

    def test_report_state_returns_platform_state_without_ros_instruction(self):
        state = platform_state()
        report = build_task_command_dry_run(command("report_state"), state)

        self.assertEqual("succeeded", report["status"])
        self.assertIsNone(report["ros_instruction"])
        self.assertEqual(state, report["data"]["platform_state"])

    def test_direct_velocity_command_is_not_supported(self):
        report = build_task_command_dry_run(command("publish_cmd_vel", {"linear_x": 0.1}), platform_state())

        self.assertEqual("failed", report["status"])
        self.assertEqual("validation_failure", report["failure_code"])
        self.assertIsNone(report["ros_instruction"])
        self.assertFalse(report["publish_attempted"])


if __name__ == "__main__":
    unittest.main()
