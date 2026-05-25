import unittest

from ugv.llm_control.state_adapter import build_platform_state


def runtime_fixture(**overrides):
    runtime = {
        "captured_at": 100.0,
        "ros_master_reachable": True,
        "nodes": ["/move_base", "/velocity_smoother", "/yhs_can_control_node"],
        "map_to_base_link": {
            "updated_at": 99.7,
            "translation": {"x": -0.394, "y": 3.099, "z": 0.0},
            "rotation": {"yaw": -0.162},
        },
        "odom_to_base_link_error": '"odom" passed to lookupTransform argument target_frame does not exist.',
        "odom": {
            "updated_at": 99.8,
            "twist": {
                "linear": {"x": 0.0, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
        },
        "chassis_info_fb": {
            "updated_at": 99.9,
            "ctrl_fb": {
                "ctrl_fb_gear": 6,
                "ctrl_fb_linear": 0.0,
                "ctrl_fb_angular": 0.0,
                "ctrl_fb_slipangle": 0.0,
            },
            "io_fb": {
                "io_fb_unlock": False,
                "io_fb_estop": False,
                "io_fb_charge_state": False,
            },
            "bms_flag_fb": {
                "bms_flag_fb_soc": 29,
                "bms_flag_fb_charge_flag": True,
            },
            "bms_fb": {
                "bms_fb_voltage": 47.23,
                "bms_fb_current": 7.8,
                "bms_fb_remaining_capacity": 11.8,
            },
        },
        "move_base_status": {
            "updated_at": 99.8,
            "status_list": [],
        },
        "cmd_vel": None,
        "smoother_cmd_vel": {
            "updated_at": 99.9,
            "linear": {"x": 0.0, "y": 0.0, "z": 0.0},
            "angular": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
    }
    runtime.update(overrides)
    return runtime


class UgvPlatformStateAdapterTest(unittest.TestCase):
    def test_builds_platform_state_from_confirmed_runtime_topics(self):
        state = build_platform_state(runtime_fixture(), platform_id="ugv_1")

        self.assertEqual("PlatformState.v1", state["schema"])
        self.assertEqual("ugv_1", state["platform_id"])
        self.assertEqual("ugv", state["platform_type"])
        self.assertEqual("map", state["pose"]["frame_id"])
        self.assertEqual("map->base_link", state["pose"]["transform"])
        self.assertAlmostEqual(-0.394, state["pose"]["x"])
        self.assertAlmostEqual(3.099, state["pose"]["y"])
        self.assertAlmostEqual(-0.162, state["pose"]["yaw"])
        self.assertEqual("idle", state["local_navigation"]["task_state"])
        self.assertEqual(6, state["chassis"]["gear"])
        self.assertAlmostEqual(0.29, state["battery"]["percentage"])
        self.assertAlmostEqual(47.23, state["battery"]["voltage"])
        self.assertTrue(state["battery"]["charging"])

    def test_motion_gate_rejects_locked_platform_without_unlocking_it(self):
        state = build_platform_state(runtime_fixture(), platform_id="ugv_1")

        self.assertFalse(state["safety"]["is_unlocked"])
        self.assertFalse(state["safety"]["motion_ready"])
        self.assertIn("chassis_locked", state["safety"]["reasons"])
        self.assertFalse(state["safety"]["gateway_may_unlock"])

    def test_uses_map_tf_for_pose_when_odom_tf_is_absent(self):
        state = build_platform_state(runtime_fixture(), platform_id="ugv_1")

        self.assertTrue(state["localization"]["ok"])
        self.assertEqual("tf", state["pose"]["source"])
        self.assertEqual("map->base_link", state["pose"]["transform"])
        self.assertIn("odom", state["diagnostics"]["ignored_tf_failures"][0])

    def test_missing_map_tf_blocks_localization_even_if_odom_tf_exists(self):
        state = build_platform_state(
            runtime_fixture(
                map_to_base_link=None,
                odom_to_base_link={
                    "updated_at": 99.9,
                    "translation": {"x": 1.0, "y": 2.0, "z": 0.0},
                    "rotation": {"yaw": 0.5},
                },
            ),
            platform_id="ugv_1",
        )

        self.assertFalse(state["localization"]["ok"])
        self.assertEqual("missing_map_to_base_link_tf", state["localization"]["reason"])
        self.assertIsNone(state["pose"]["frame_id"])
        self.assertFalse(state["safety"]["motion_ready"])
        self.assertIn("localization_unavailable", state["safety"]["reasons"])

    def test_motion_ready_requires_ros_master_move_base_fresh_tf_unlocked_and_battery(self):
        runtime = runtime_fixture()
        runtime["chassis_info_fb"]["io_fb"]["io_fb_unlock"] = True
        state = build_platform_state(runtime, platform_id="ugv_1", min_battery_percentage=0.25)

        self.assertTrue(state["safety"]["motion_ready"])
        self.assertEqual([], state["safety"]["reasons"])


if __name__ == "__main__":
    unittest.main()
