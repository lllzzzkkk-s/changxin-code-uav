import unittest

from uav.llm_control.ros_adapters.action_gate_dry_run import build_action_gate_dry_run_report
from uav.llm_control.safety.action_gate import ActionApproval
from uav.llm_control.safety.profiles import a_stage_sim_dry_run_profile, c_stage_real_profile
from uav.llm_control.schemas.models import (
    BatterySnapshot,
    FcuSnapshot,
    LocalizationSnapshot,
    RcSnapshot,
    StateSnapshot,
)


def fresh_snapshot(source="sim"):
    return StateSnapshot(
        captured_at=100.0,
        fcu=FcuSnapshot(connected=True, armed=True, mode="OFFBOARD", updated_at=100.0),
        battery=BatterySnapshot(voltage=24.1, percentage=0.75, updated_at=100.0),
        rc=RcSnapshot(channels=[1000, 1500, 1500, 1500, 1000, 1000, 1800, 1500], updated_at=100.0),
        localization=LocalizationSnapshot(
            source=source,
            position={"x": -15.0, "y": 0.0, "z": 1.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            yaw=0.0,
            updated_at=100.0,
        ),
    )


def envelope():
    return {
        "meta": {"request_id": "g3d-adapter-test"},
        "intent": {"name": "move_relative"},
        "arguments": {"frame": "world", "direction": "forward", "distance_m": 1.0},
    }


def approval():
    return ActionApproval(
        operator_id="operator-a",
        confirmation_phrase="CONFIRM g3d-adapter-test move_relative /goal",
        approved_at=100.0,
        expires_at=103.0,
        sim_evidence_id="g3c-20-22",
        rollback_plan_id="kill-live-sim-launch-pid",
        action_summary="G3-D live sim action gate dry-run",
    )


class TestActionGateDryRunAdapter(unittest.TestCase):
    def test_a_profile_report_allows_gate_without_publish_side_effect(self):
        report = build_action_gate_dry_run_report(
            envelope(),
            fresh_snapshot(),
            approval(),
            now=100.0,
            requested_timeout_s=2.0,
            config=a_stage_sim_dry_run_profile(),
        ).as_dict()

        self.assertEqual("gate_allowed", report["status"])
        self.assertTrue(report["gate_allowed"])
        self.assertFalse(report["publish_attempted"])
        self.assertEqual("a-stage-sim-dry-run", report["profile_name"])
        self.assertEqual("/goal", report["gate_decision"]["topic"])
        self.assertEqual({"x": -14.0, "y": 0.0, "z": 1.0}, report["command"]["resolution"]["target_position"])
        self.assertEqual("action_gate", report["trace"][-1]["stage"])

    def test_c_profile_rejects_same_sim_candidate_for_real_aircraft_transition(self):
        report = build_action_gate_dry_run_report(
            envelope(),
            fresh_snapshot(),
            approval(),
            now=100.0,
            requested_timeout_s=1.0,
            config=c_stage_real_profile(),
        ).as_dict()

        self.assertEqual("gate_rejected", report["status"])
        self.assertFalse(report["gate_allowed"])
        self.assertEqual("c-stage-real", report["profile_name"])
        self.assertIn("unsupported_localization_source", report["gate_decision"]["reasons"])
        self.assertIn("target_distance_too_large", report["gate_decision"]["reasons"])
        self.assertFalse(report["publish_attempted"])


if __name__ == "__main__":
    unittest.main()
