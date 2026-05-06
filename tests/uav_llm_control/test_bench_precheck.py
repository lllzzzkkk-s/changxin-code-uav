import unittest

from uav.llm_control.ros_adapters.bench_precheck import (
    BenchGraphSnapshot,
    build_b_stage_bench_precheck_report,
    graph_snapshot_from_ros_cli,
)
from uav.llm_control.safety.action_gate import ActionApproval
from uav.llm_control.schemas.models import (
    BatterySnapshot,
    FcuSnapshot,
    LocalizationSnapshot,
    RcSnapshot,
    StateSnapshot,
)


def fresh_snapshot(source="lio"):
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


def envelope(distance_m=0.3):
    return {
        "meta": {"request_id": "b-stage-bench-precheck"},
        "intent": {"name": "move_relative"},
        "arguments": {"frame": "world", "direction": "forward", "distance_m": distance_m},
    }


def approval():
    return ActionApproval(
        operator_id="operator-a",
        confirmation_phrase="CONFIRM b-stage-bench-precheck move_relative /goal",
        approved_at=100.0,
        expires_at=102.0,
        sim_evidence_id="g3d-live-sim-gate",
        rollback_plan_id="bench-disable-publisher-and-kill-launch",
        action_summary="B-stage bench profile precheck without publish",
    )


def healthy_graph():
    return BenchGraphSnapshot(
        nodes=[
            "/drone_0_diff_planner_node",
            "/drone_0_traj_server",
            "/rosout",
        ],
        published_topics=[
            "/drone_0_planning/trajectory",
            "/drone_0_traj_server/heartbeat",
            "/rosout",
        ],
        subscribed_topics=[
            "/goal",
            "/back_trigger",
            "/drone_0_visual_slam/odom",
        ],
    )


class TestBenchPrecheck(unittest.TestCase):
    def test_graph_snapshot_parses_ros_cli_outputs(self):
        nodes_text = """/drone_0_diff_planner_node
/drone_0_traj_server
/rosout
"""
        topics_text = """
Published topics:
 * /drone_0_planning/trajectory [traj_utils/PolyTraj] 1 publisher
 * /drone_0_traj_server/heartbeat [std_msgs/Empty] 1 publisher

Subscribed topics:
 * /goal [geometry_msgs/PoseStamped] 1 subscriber
 * /back_trigger [geometry_msgs/PoseStamped] 1 subscriber
"""

        graph = graph_snapshot_from_ros_cli(nodes_text, topics_text).as_dict()

        self.assertEqual(
            ["/drone_0_diff_planner_node", "/drone_0_traj_server", "/rosout"],
            graph["nodes"],
        )
        self.assertEqual(
            ["/drone_0_planning/trajectory", "/drone_0_traj_server/heartbeat"],
            graph["published_topics"],
        )
        self.assertEqual(["/goal", "/back_trigger"], graph["subscribed_topics"])

    def test_b_stage_precheck_passes_with_lio_source_and_required_graph(self):
        report = build_b_stage_bench_precheck_report(
            envelope(),
            fresh_snapshot("lio"),
            approval(),
            healthy_graph(),
            action_topic_message_received=False,
            now=100.0,
            requested_timeout_s=1.5,
        ).as_dict()

        self.assertEqual("bench_precheck_passed", report["status"])
        self.assertTrue(report["graph_ok"])
        self.assertTrue(report["gate_allowed"])
        self.assertFalse(report["publish_attempted"])
        self.assertFalse(report["action_topic_message_received"])
        self.assertEqual("b-stage-bench", report["gate_report"]["profile_name"])
        self.assertEqual("/goal", report["gate_report"]["gate_decision"]["topic"])
        self.assertEqual({"x": -14.7, "y": 0.0, "z": 1.0}, report["gate_report"]["command"]["resolution"]["target_position"])

    def test_b_stage_precheck_fails_for_sim_source_and_missing_goal_subscriber(self):
        graph = BenchGraphSnapshot(
            nodes=["/drone_0_diff_planner_node", "/drone_0_traj_server", "/rosout"],
            published_topics=["/drone_0_planning/trajectory", "/drone_0_traj_server/heartbeat"],
            subscribed_topics=["/back_trigger"],
        )

        report = build_b_stage_bench_precheck_report(
            envelope(),
            fresh_snapshot("sim"),
            approval(),
            graph,
            action_topic_message_received=False,
            now=100.0,
            requested_timeout_s=1.5,
        ).as_dict()

        self.assertEqual("bench_precheck_failed", report["status"])
        self.assertFalse(report["graph_ok"])
        self.assertFalse(report["gate_allowed"])
        self.assertIn("/goal", report["missing_subscribed_topics"])
        self.assertIn("unsupported_localization_source", report["gate_report"]["gate_decision"]["reasons"])
        self.assertFalse(report["publish_attempted"])


if __name__ == "__main__":
    unittest.main()
