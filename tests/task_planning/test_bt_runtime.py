import unittest

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.contracts import Heartbeat, PlatformState, TaskCommand
from task_planning.execution import BehaviorTreeRuntime
from task_planning.execution.plan_to_bt import BehaviorTreeArtifact, compile_plan_to_bt
from task_planning.mission_ops.mock_llm_client import MockLLMClient
from task_planning.pddl import generate_problem, mock_plan


def _bt_artifact() -> BehaviorTreeArtifact:
    task_schema = MockLLMClient().compile_task_schema("搜索 A 区并派无人车确认目标", {})
    problem = generate_problem(task_schema.mission_request)
    plan = mock_plan(problem)
    return compile_plan_to_bt(plan, mission_id=task_schema.mission_request.mission_id)


class BehaviorTreeRuntimeTest(unittest.TestCase):
    def test_runtime_dispatches_bt_commands_and_records_progress_without_ros(self):
        gateway = MockPlatformGateway()
        bt = _bt_artifact()

        result = BehaviorTreeRuntime(gateway=gateway).run(bt, run_id="run_phase2a_001")

        self.assertEqual("BehaviorTreeRunResult.v1", result.schema)
        self.assertEqual("completed", result.status)
        self.assertEqual(3, len(result.command_acks))
        self.assertTrue(all(ack.accepted for ack in result.command_acks))
        self.assertEqual(3, len(result.task_progress))
        self.assertTrue(all(progress.status == "completed" for progress in result.task_progress))
        self.assertEqual([False, False, False], [record["publish_attempted"] for record in gateway.dispatch_log])
        event_types = [event.event_type for event in result.events]
        self.assertIn("bt_runtime_started", event_types)
        self.assertIn("task_dispatch_requested", event_types)
        self.assertIn("command_ack_accepted", event_types)
        self.assertIn("task_progress_observed", event_types)
        self.assertIn("bt_runtime_completed", event_types)

    def test_runtime_stops_on_rejected_ack_and_records_failure(self):
        gateway = MockPlatformGateway()
        bt = _bt_artifact()
        bad_commands = list(bt.task_commands)
        bad_commands[1] = TaskCommand(
            mission_id=bad_commands[1].mission_id,
            task_id=bad_commands[1].task_id,
            platform_id="missing_platform",
            capability=bad_commands[1].capability,
            parameters=bad_commands[1].parameters,
        )
        bad_bt = BehaviorTreeArtifact(mission_id=bt.mission_id, root=bt.root, task_commands=bad_commands)

        result = BehaviorTreeRuntime(gateway=gateway).run(bad_bt, run_id="run_phase2a_reject")

        self.assertEqual("failed", result.status)
        self.assertIn("unknown platform_id", result.command_acks[-1].reason)
        self.assertIsNotNone(result.failure_report)
        self.assertEqual("FailureReport.v1", result.failure_report.schema)
        event_types = [event.event_type for event in result.events]
        self.assertIn("command_ack_rejected", event_types)
        self.assertIn("failure_report_recorded", event_types)
        self.assertIn("central_replan_requested", event_types)
        self.assertEqual(["task_001", "task_002"], [record["task_id"] for record in gateway.dispatch_log])

    def test_runtime_disconnect_policy_does_not_create_new_platform_plan(self):
        bt = _bt_artifact()
        original_commands = [command.as_dict() for command in bt.task_commands]
        heartbeat = Heartbeat(
            platform_id="uav_0",
            gateway_status="alive",
            ros_master_ok=False,
            last_state_seq=1,
            last_task_id="task_001",
        )
        degraded_state = PlatformState(
            platform_id="uav_0",
            platform_type="uav",
            capabilities=["inspect_area", "relay_or_overwatch", "hold_position", "return_home"],
            comm_status="degraded",
            task_status="running",
        )

        result = BehaviorTreeRuntime(
            gateway=MockPlatformGateway(),
            heartbeat_events=[heartbeat],
            platform_state_events=[degraded_state],
        ).run(bt, run_id="run_phase2a_disconnect")

        event_types = [event.event_type for event in result.events]
        self.assertIn("heartbeat_observed", event_types)
        self.assertIn("platform_state_observed", event_types)
        self.assertNotIn("platform_replan_created", event_types)
        self.assertEqual(original_commands, [command.as_dict() for command in result.task_commands])


if __name__ == "__main__":
    unittest.main()
