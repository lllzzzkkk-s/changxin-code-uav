import unittest

from uav.llm_control.core.pipeline import process_command
from uav.llm_control.safety.action_gate import (
    ActionApproval,
    ActionGateConfig,
    evaluate_action_gate,
)
from uav.llm_control.safety.profiles import (
    a_stage_sim_dry_run_profile,
    b_stage_bench_profile,
    c_stage_real_profile,
)
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
            position={"x": -15.0, "y": 0.0, "z": 1.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            yaw=0.0,
            updated_at=100.0,
        ),
    }
    values.update(overrides)
    return StateSnapshot(**values)


def envelope(intent, arguments=None):
    return {
        "meta": {"request_id": "gate-test-request"},
        "intent": {"name": intent},
        "arguments": arguments or {},
    }


def approval(**overrides):
    values = {
        "operator_id": "operator-a",
        "confirmation_phrase": "CONFIRM gate-test-request move_relative /goal",
        "approved_at": 100.0,
        "expires_at": 103.0,
        "sim_evidence_id": "g3c-20-22",
        "rollback_plan_id": "sim-kill-launch-pid",
        "action_summary": "move_relative forward 1m in sim graph",
    }
    values.update(overrides)
    return ActionApproval(**values)


def approval_for(intent, topic, **overrides):
    return approval(confirmation_phrase=f"CONFIRM gate-test-request {intent} {topic}", **overrides)


class TestActionSafetyGate(unittest.TestCase):
    def test_confirmed_goal_payload_is_allowed_without_publish_side_effect(self):
        command = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 1.0}),
            fresh_snapshot(),
            now=100.0,
        )

        decision = evaluate_action_gate(
            command,
            fresh_snapshot(),
            approval(),
            now=100.0,
            requested_timeout_s=2.0,
        ).as_dict()

        self.assertTrue(decision["allowed"])
        self.assertEqual([], decision["reasons"])
        self.assertEqual("/goal", decision["topic"])
        self.assertFalse(decision["publish_attempted"])
        self.assertEqual("operator-a", decision["audit"]["operator_id"])
        self.assertEqual("gate-test-request", decision["audit"]["request_id"])

    def test_missing_confirmation_rejects_even_when_command_is_ready(self):
        command = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 1.0}),
            fresh_snapshot(),
            now=100.0,
        )

        decision = evaluate_action_gate(command, fresh_snapshot(), None, now=100.0, requested_timeout_s=2.0)

        self.assertFalse(decision.allowed)
        self.assertIn("operator_confirmation_missing", decision.reasons)
        self.assertFalse(decision.publish_attempted)

    def test_rejects_disallowed_low_level_setpoint_topic(self):
        command = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 1.0}),
            fresh_snapshot(),
            now=100.0,
        )
        command.execution["ros_payload"]["topic"] = "/setpoints_cmd"

        decision = evaluate_action_gate(command, fresh_snapshot(), approval(), now=100.0, requested_timeout_s=2.0)

        self.assertFalse(decision.allowed)
        self.assertIn("topic_not_allowlisted", decision.reasons)
        self.assertIn("low_level_setpoint_topic_denied", decision.reasons)

    def test_rejects_direct_mavros_endpoint(self):
        command = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 1.0}),
            fresh_snapshot(),
            now=100.0,
        )
        command.execution["ros_payload"]["topic"] = "/mavros/set_mode"

        decision = evaluate_action_gate(command, fresh_snapshot(), approval(), now=100.0, requested_timeout_s=2.0)

        self.assertFalse(decision.allowed)
        self.assertIn("topic_not_allowlisted", decision.reasons)
        self.assertIn("low_level_mavros_endpoint_denied", decision.reasons)

    def test_rejects_when_state_is_stale_or_not_offboard(self):
        command = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 1.0}),
            fresh_snapshot(),
            now=100.0,
        )

        stale_decision = evaluate_action_gate(
            command,
            fresh_snapshot(fcu=FcuSnapshot(connected=True, armed=True, mode="OFFBOARD", updated_at=90.0)),
            approval(),
            now=100.0,
            requested_timeout_s=2.0,
        )
        manual_decision = evaluate_action_gate(
            command,
            fresh_snapshot(fcu=FcuSnapshot(connected=True, armed=True, mode="MANUAL", updated_at=100.0)),
            approval(),
            now=100.0,
            requested_timeout_s=2.0,
        )

        self.assertFalse(stale_decision.allowed)
        self.assertIn("fcu_stale", stale_decision.reasons)
        self.assertFalse(manual_decision.allowed)
        self.assertIn("fcu_mode_not_offboard", manual_decision.reasons)

    def test_rejects_expired_confirmation_timeout_and_out_of_bounds_goal(self):
        command = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 1.0}),
            fresh_snapshot(),
            now=100.0,
        )
        command.execution["ros_payload"]["message"]["pose"]["position"]["z"] = 3.5

        decision = evaluate_action_gate(
            command,
            fresh_snapshot(),
            approval(expires_at=99.0),
            now=100.0,
            requested_timeout_s=5.0,
            config=ActionGateConfig(max_execution_timeout_s=3.0),
        )

        self.assertFalse(decision.allowed)
        self.assertIn("operator_confirmation_expired", decision.reasons)
        self.assertIn("execution_timeout_too_long", decision.reasons)
        self.assertIn("target_z_out_of_bounds", decision.reasons)

    def test_rejects_missing_sim_evidence_and_rollback_plan(self):
        command = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 1.0}),
            fresh_snapshot(),
            now=100.0,
        )

        decision = evaluate_action_gate(
            command,
            fresh_snapshot(),
            approval(sim_evidence_id="", rollback_plan_id="", action_summary=""),
            now=100.0,
            requested_timeout_s=2.0,
        )

        self.assertFalse(decision.allowed)
        self.assertIn("sim_evidence_missing", decision.reasons)
        self.assertIn("rollback_plan_missing", decision.reasons)
        self.assertIn("action_summary_missing", decision.reasons)

    def test_rejects_goal_farther_than_action_gate_limit(self):
        command = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 5.0}),
            fresh_snapshot(),
            now=100.0,
        )

        decision = evaluate_action_gate(command, fresh_snapshot(), approval(), now=100.0, requested_timeout_s=2.0)

        self.assertFalse(decision.allowed)
        self.assertIn("target_distance_too_large", decision.reasons)

    def test_stage_profiles_get_stricter_from_a_to_c(self):
        a_profile = a_stage_sim_dry_run_profile()
        b_profile = b_stage_bench_profile()
        c_profile = c_stage_real_profile()

        self.assertEqual("a-stage-sim-dry-run", a_profile.profile_name)
        self.assertIn("sim", a_profile.allowed_localization_sources)
        self.assertNotIn("sim", b_profile.allowed_localization_sources)
        self.assertNotIn("sim", c_profile.allowed_localization_sources)
        self.assertIn("/px4ctrl/takeoff_land", a_profile.allowed_topics)
        self.assertNotIn("/px4ctrl/takeoff_land", c_profile.allowed_topics)
        self.assertGreater(a_profile.max_goal_distance_m, b_profile.max_goal_distance_m)
        self.assertGreater(b_profile.max_goal_distance_m, c_profile.max_goal_distance_m)

    def test_real_profile_rejects_sim_source_even_when_a_stage_profile_would_allow_it(self):
        command = process_command(
            envelope("move_relative", {"frame": "world", "direction": "forward", "distance_m": 1.0}),
            fresh_snapshot(localization=LocalizationSnapshot(
                source="sim",
                position={"x": -15.0, "y": 0.0, "z": 1.0},
                velocity={"x": 0.0, "y": 0.0, "z": 0.0},
                yaw=0.0,
                updated_at=100.0,
            )),
            now=100.0,
        )

        a_decision = evaluate_action_gate(
            command,
            fresh_snapshot(localization=LocalizationSnapshot(
                source="sim",
                position={"x": -15.0, "y": 0.0, "z": 1.0},
                velocity={"x": 0.0, "y": 0.0, "z": 0.0},
                yaw=0.0,
                updated_at=100.0,
            )),
            approval(),
            now=100.0,
            requested_timeout_s=2.0,
            config=a_stage_sim_dry_run_profile(),
        )
        c_decision = evaluate_action_gate(
            command,
            fresh_snapshot(localization=LocalizationSnapshot(
                source="sim",
                position={"x": -15.0, "y": 0.0, "z": 1.0},
                velocity={"x": 0.0, "y": 0.0, "z": 0.0},
                yaw=0.0,
                updated_at=100.0,
            )),
            approval(),
            now=100.0,
            requested_timeout_s=1.0,
            config=c_stage_real_profile(),
        )

        self.assertTrue(a_decision.allowed)
        self.assertFalse(c_decision.allowed)
        self.assertIn("unsupported_localization_source", c_decision.reasons)

    def test_bench_profile_allows_return_home_candidate_but_real_profile_rejects_it(self):
        command = process_command(envelope("return_home"), fresh_snapshot(), now=100.0)

        b_decision = evaluate_action_gate(
            command,
            fresh_snapshot(),
            approval_for("return_home", "/back_trigger"),
            now=100.0,
            requested_timeout_s=1.0,
            config=b_stage_bench_profile(),
        )
        c_decision = evaluate_action_gate(
            command,
            fresh_snapshot(),
            approval_for("return_home", "/back_trigger"),
            now=100.0,
            requested_timeout_s=1.0,
            config=c_stage_real_profile(),
        )

        self.assertTrue(b_decision.allowed)
        self.assertFalse(c_decision.allowed)
        self.assertIn("intent_not_allowlisted", c_decision.reasons)
        self.assertIn("topic_not_allowlisted", c_decision.reasons)

    def test_real_profile_rejects_takeoff_land_command_surface(self):
        command = process_command(envelope("takeoff"), fresh_snapshot(), now=100.0)

        decision = evaluate_action_gate(
            command,
            fresh_snapshot(),
            approval_for("takeoff", "/px4ctrl/takeoff_land"),
            now=100.0,
            requested_timeout_s=1.0,
            config=c_stage_real_profile(),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual("/px4ctrl/takeoff_land", decision.topic)
        self.assertIn("intent_not_allowlisted", decision.reasons)
        self.assertIn("topic_not_allowlisted", decision.reasons)


if __name__ == "__main__":
    unittest.main()
