import unittest

from uav.llm_control.ros_adapters.dry_run import build_dry_run_report
from uav.llm_control.schemas.models import (
    BatterySnapshot,
    FcuSnapshot,
    LocalizationSnapshot,
    RcSnapshot,
    StateSnapshot,
)


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
        "meta": {"request_id": "adapter-test"},
        "intent": {"name": intent},
        "arguments": arguments or {},
    }


class TestDryRunRosAdapter(unittest.TestCase):
    def test_move_relative_report_contains_full_ros_payload_trace_without_publish(self):
        report = build_dry_run_report(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 1.0}),
            fresh_snapshot(),
            now=100.0,
        ).as_dict()

        self.assertEqual("needs_confirmation", report["status"])
        self.assertFalse(report["publish_attempted"])
        self.assertEqual(
            [
                "input",
                "schema_validation",
                "state_snapshot",
                "safety_policy",
                "target_point",
                "ros_payload",
                "confirmation_gate",
            ],
            [entry["stage"] for entry in report["trace"]],
        )
        self.assertEqual("/goal", report["trace"][5]["topic"])
        self.assertEqual("geometry_msgs/PoseStamped", report["trace"][5]["message_type"])
        self.assertEqual({"x": 2.0, "y": 2.0, "z": 1.0}, report["trace"][4]["target_position"])
        self.assertEqual("blocked_for_confirmation", report["trace"][6]["status"])

    def test_validation_failure_report_keeps_ros_payload_empty_and_publish_blocked(self):
        report = build_dry_run_report(
            envelope("publish_setpoints_cmd"),
            fresh_snapshot(),
            now=100.0,
        ).as_dict()

        self.assertEqual("failed", report["status"])
        self.assertFalse(report["publish_attempted"])
        self.assertEqual("rejected", report["trace"][1]["status"])
        self.assertEqual("validation_failure", report["trace"][1]["failure_code"])
        self.assertIsNone(report["trace"][5]["payload"])

    def test_takeoff_report_maps_to_takeoff_land_topic_without_publish(self):
        report = build_dry_run_report(envelope("takeoff"), fresh_snapshot(), now=100.0).as_dict()

        self.assertEqual("needs_confirmation", report["status"])
        self.assertEqual("/px4ctrl/takeoff_land", report["trace"][5]["topic"])
        self.assertEqual("quadrotor_msgs/TakeoffLand", report["trace"][5]["message_type"])
        self.assertEqual({"takeoff_land_cmd": 1}, report["trace"][5]["message"])
        self.assertFalse(report["trace"][6]["publish_attempted"])


if __name__ == "__main__":
    unittest.main()
