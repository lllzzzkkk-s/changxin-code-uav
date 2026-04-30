import math
import unittest

from uav.llm_control.core.pipeline import process_command
from uav.llm_control.schemas.models import (
    BatterySnapshot,
    FcuSnapshot,
    LocalizationSnapshot,
    RcSnapshot,
    StateSnapshot,
)
from uav.llm_control.tools.catalog import tool_catalog


def fresh_snapshot(**overrides):
    values = {
        "captured_at": 100.0,
        "fcu": FcuSnapshot(connected=True, armed=True, mode="OFFBOARD", updated_at=100.0),
        "battery": BatterySnapshot(voltage=24.1, percentage=0.75, updated_at=100.0),
        "rc": RcSnapshot(channels=[1000, 1500, 1500, 1500, 1000, 1000, 1800, 1500], updated_at=100.0),
        "localization": LocalizationSnapshot(
            source="lio",
            position={"x": 1.0, "y": 2.0, "z": 1.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            yaw=0.0,
            updated_at=100.0,
        ),
    }
    values.update(overrides)
    return StateSnapshot(**values)


def envelope(intent, arguments=None):
    return {
        "meta": {"request_id": "test-request"},
        "intent": {"name": intent},
        "arguments": arguments or {},
        "resolution": {},
        "safety": {},
        "execution": {},
    }


class TestToolCatalog(unittest.TestCase):
    def test_a_stage_catalog_is_fixed_to_eight_tools(self):
        self.assertEqual(
            [
                "query_battery",
                "query_fcu_state",
                "query_localization",
                "query_rc_state",
                "takeoff",
                "land",
                "return_home",
                "move_relative",
            ],
            [tool.name for tool in tool_catalog()],
        )


class TestProcessCommand(unittest.TestCase):
    def test_move_relative_world_dry_run_compiles_goal_and_requires_confirmation(self):
        result = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 1.0}),
            fresh_snapshot(),
            now=100.0,
        )

        data = result.as_dict()
        self.assertEqual("needs_confirmation", data["status"])
        self.assertEqual("move_relative", data["intent"]["name"])
        self.assertEqual("/goal", data["execution"]["ros_payload"]["topic"])
        self.assertEqual("geometry_msgs/PoseStamped", data["execution"]["ros_payload"]["message_type"])
        self.assertFalse(data["execution"]["publish_attempted"])
        self.assertTrue(data["execution"]["dry_run"])
        self.assertEqual({"x": 2.0, "y": 2.0, "z": 1.0}, data["resolution"]["target_position"])
        self.assertIn("confirmation_required", data["safety"]["reasons"])

    def test_move_relative_body_frame_uses_yaw_to_compile_world_goal(self):
        snapshot = fresh_snapshot(
            localization=LocalizationSnapshot(
                source="lio",
                position={"x": 1.0, "y": 2.0, "z": 1.0},
                velocity={"x": 0.0, "y": 0.0, "z": 0.0},
                yaw=math.pi / 2,
                updated_at=100.0,
            )
        )

        result = process_command(
            envelope("move_relative", {"frame": "body", "direction": "forward", "distance_m": 1.0}),
            snapshot,
            now=100.0,
        )

        target = result.as_dict()["resolution"]["target_position"]
        self.assertAlmostEqual(1.0, target["x"], places=6)
        self.assertAlmostEqual(3.0, target["y"], places=6)
        self.assertAlmostEqual(1.0, target["z"], places=6)

    def test_move_relative_accepts_sim_localization_for_a_to_bc_transition_testing(self):
        snapshot = fresh_snapshot(
            localization=LocalizationSnapshot(
                source="sim",
                position={"x": -15.0, "y": 0.0, "z": 1.0},
                velocity={"x": 0.0, "y": 0.0, "z": 0.0},
                yaw=0.0,
                updated_at=100.0,
            )
        )

        result = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 1.0}),
            snapshot,
            now=100.0,
        )

        data = result.as_dict()
        self.assertEqual("needs_confirmation", data["status"])
        self.assertEqual("sim", data["resolution"]["localization_source"])
        self.assertEqual({"x": -14.0, "y": 0.0, "z": 1.0}, data["resolution"]["target_position"])
        self.assertEqual("/goal", data["execution"]["ros_payload"]["topic"])

    def test_move_relative_rejects_stale_localization(self):
        snapshot = fresh_snapshot(
            localization=LocalizationSnapshot(
                source="lio",
                position={"x": 1.0, "y": 2.0, "z": 1.0},
                velocity={"x": 0.0, "y": 0.0, "z": 0.0},
                yaw=0.0,
                updated_at=95.0,
            )
        )

        result = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 1.0}),
            snapshot,
            now=100.0,
        )

        data = result.as_dict()
        self.assertEqual("failed", data["status"])
        self.assertEqual("precheck_failure", data["failure_code"])
        self.assertIn("localization_stale", data["message"])

    def test_move_relative_rejects_invalid_distance_and_altitude(self):
        invalid_distance = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 6.0}),
            fresh_snapshot(),
            now=100.0,
        )
        self.assertEqual("validation_failure", invalid_distance.as_dict()["failure_code"])

        invalid_altitude = process_command(
            envelope("move_relative", {"frame": "world", "direction": "down", "distance_m": 1.0}),
            fresh_snapshot(localization=LocalizationSnapshot(
                source="lio",
                position={"x": 1.0, "y": 2.0, "z": 0.8},
                velocity={"x": 0.0, "y": 0.0, "z": 0.0},
                yaw=0.0,
                updated_at=100.0,
            )),
            now=100.0,
        )
        self.assertEqual("safety_rejected", invalid_altitude.as_dict()["status"])
        self.assertIn("target_z_out_of_bounds", invalid_altitude.as_dict()["safety"]["reasons"])

    def test_unknown_intent_is_validation_failure(self):
        result = process_command(envelope("publish_setpoints_cmd"), fresh_snapshot(), now=100.0)

        self.assertEqual("failed", result.as_dict()["status"])
        self.assertEqual("validation_failure", result.as_dict()["failure_code"])

    def test_query_battery_succeeds_without_confirmation_or_ros_payload(self):
        result = process_command(envelope("query_battery"), fresh_snapshot(), now=100.0)

        data = result.as_dict()
        self.assertEqual("succeeded", data["status"])
        self.assertEqual({"voltage": 24.1, "percentage": 0.75}, data["data"])
        self.assertEqual("none", data["safety"]["confirmation_policy"])
        self.assertIsNone(data["execution"]["ros_payload"])

    def test_takeoff_is_dry_run_action_requiring_confirmation(self):
        result = process_command(envelope("takeoff"), fresh_snapshot(), now=100.0)

        data = result.as_dict()
        self.assertEqual("needs_confirmation", data["status"])
        self.assertEqual("/px4ctrl/takeoff_land", data["execution"]["ros_payload"]["topic"])
        self.assertEqual({"takeoff_land_cmd": 1}, data["execution"]["ros_payload"]["message"])
        self.assertFalse(data["execution"]["publish_attempted"])


if __name__ == "__main__":
    unittest.main()
