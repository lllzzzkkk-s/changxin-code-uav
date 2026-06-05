import tempfile
import unittest
from pathlib import Path

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.contracts import FailureReport
from task_planning.execution.plan_to_bt import compile_plan_to_bt
from task_planning.mission_ops.mock_llm_client import MockLLMClient
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore
from task_planning.pddl import generate_problem, mock_plan, scout_and_confirm_domain


class MissionOpsDryRunTest(unittest.TestCase):
    def test_minimal_pddl_problem_mock_plan_and_plan_to_bt_compile_to_task_commands(self):
        task_schema = MockLLMClient().compile_task_schema("搜索 A 区并派无人车确认目标", {})
        problem = generate_problem(task_schema.mission_request)
        plan = mock_plan(problem)
        bt = compile_plan_to_bt(plan, mission_id=task_schema.mission_request.mission_id)

        self.assertIn("(:action scan-area", scout_and_confirm_domain())
        self.assertIn("(:action confirm-target", scout_and_confirm_domain())
        self.assertIn("(:action relay-or-overwatch", scout_and_confirm_domain())
        self.assertIn("area_A", problem.pddl)
        self.assertEqual(["scan-area", "confirm-target", "relay-or-overwatch"], [step.action for step in plan.steps])
        self.assertEqual("BehaviorTree.v1", bt.schema)
        self.assertEqual(["inspect_area", "confirm_target", "relay_or_overwatch"], [
            command.capability for command in bt.task_commands
        ])

    def test_single_ugv_object_approach_intent_compiles_to_identify_then_approach_commands(self):
        task_schema = MockLLMClient().compile_task_schema(
            "让小车识别附近的充电桩，然后走过去",
            {"mission_id": "golden_single_ugv_object_approach", "primary_platform": "ugv_0"},
        )
        problem = generate_problem(task_schema.mission_request)
        plan = mock_plan(problem)
        bt = compile_plan_to_bt(plan, mission_id=task_schema.mission_request.mission_id)

        self.assertEqual("single_ugv_object_approach", task_schema.mission_request.constraints["mission_variant"])
        self.assertEqual("充电桩", task_schema.mission_request.constraints["object_query"])
        self.assertEqual("operator_confirmed_target_map", task_schema.mission_request.constraints["target_source"])
        self.assertEqual("yolo", task_schema.mission_request.constraints["future_perception_backend"])
        self.assertIn("(approached ?target - target)", scout_and_confirm_domain())
        self.assertIn("(:goal (and (approached target_01))", problem.pddl)
        self.assertEqual(["identify-target", "approach-target"], [step.action for step in plan.steps])
        self.assertEqual(["ugv_0", "ugv_0"], [command.platform_id for command in bt.task_commands])
        self.assertEqual(["confirm_target", "confirm_target"], [command.capability for command in bt.task_commands])
        self.assertEqual("identify_target", bt.task_commands[0].parameters["stage"])
        self.assertEqual("approach_target", bt.task_commands[1].parameters["stage"])
        self.assertEqual("充电桩", bt.task_commands[1].parameters["object_query"])
        self.assertTrue(bt.task_commands[1].requires_operator_confirm)

    def test_mock_gateway_accepts_allowed_capability_commands_without_ros_publish(self):
        task_schema = MockLLMClient().compile_task_schema("搜索 A 区并派无人车确认目标", {})
        bt = compile_plan_to_bt(mock_plan(generate_problem(task_schema.mission_request)), mission_id="mission_001")
        gateway = MockPlatformGateway()

        acks = [gateway.dispatch(command) for command in bt.task_commands]

        self.assertTrue(all(ack.accepted for ack in acks))
        self.assertEqual([False, False, False], [record["publish_attempted"] for record in gateway.dispatch_log])
        self.assertEqual(["uav_0", "ugv_0", "uav_0"], [record["platform_id"] for record in gateway.dispatch_log])

    def test_runner_persists_mission_ops_state_and_dry_runs_full_slice(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp)),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )

            result = runner.run({"intent": "搜索 A 区并派无人车确认目标"}, {"dry_run": True})
            restored = runner.get_state(result.run_id)

        self.assertEqual("dry_run_complete", result.status)
        self.assertEqual("DISPATCH_OR_HOLD", result.state.current_state)
        self.assertFalse(result.state.approval_required)
        self.assertEqual("DISPATCH_OR_HOLD", restored.current_state)
        self.assertIn("task_schema", restored.output_artifact_refs)
        self.assertIn("pddl_problem", restored.output_artifact_refs)
        self.assertIn("plan", restored.output_artifact_refs)
        self.assertIn("behavior_tree", restored.output_artifact_refs)
        self.assertIn("gateway_acks", restored.output_artifact_refs)
        self.assertIn("task_progress", restored.output_artifact_refs)
        self.assertIn("execution_events", restored.output_artifact_refs)
        self.assertEqual("OperatorApprovalState.v1", restored.approval_state["schema"])
        self.assertFalse(restored.approval_state["required"])
        event_types = [event["event_type"] for event in restored.output_artifact_refs["execution_events"]]
        self.assertIn("bt_runtime_completed", event_types)

    def test_runner_dry_runs_single_ugv_object_approach_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp)),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )

            result = runner.run({
                "intent": "让小车识别附近的桌子，然后走过去",
                "context_snapshot": {
                    "mission_id": "mission_object_approach_001",
                    "primary_platform": "ugv_0",
                },
            }, {"dry_run": True})

        self.assertEqual("dry_run_complete", result.status)
        task_schema = result.state.output_artifact_refs["task_schema"]
        plan = result.state.output_artifact_refs["plan"]
        behavior_tree = result.state.output_artifact_refs["behavior_tree"]
        self.assertEqual("single_ugv_object_approach", task_schema["mission_request"]["constraints"]["mission_variant"])
        self.assertEqual(["identify-target", "approach-target"], [step["action"] for step in plan["steps"]])
        self.assertEqual(["ugv_0", "ugv_0"], [
            command["platform_id"] for command in behavior_tree["task_commands"]
        ])
        self.assertEqual(["identify_target", "approach_target"], [
            command["parameters"]["stage"] for command in behavior_tree["task_commands"]
        ])

    def test_failure_report_resume_triages_and_requests_central_replan(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp)),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )
            result = runner.run({"intent": "搜索 A 区并派无人车确认目标"}, {"dry_run": True})
            failure = FailureReport(
                mission_id="mission_001",
                task_id="task_002",
                platform_id="ugv_0",
                failure_type="path_blocked",
                recoverable=True,
                reason="local_planner_no_path",
                recommended_actions=["request_uav_rescan"],
            )

            replanned = runner.resume(result.run_id, {"failure_report": failure.as_dict()})

        self.assertEqual("replan_requested", replanned.status)
        self.assertEqual("REQUEST_REPLAN", replanned.state.current_state)
        self.assertTrue(replanned.state.approval_required)
        self.assertEqual("central_replan", replanned.state.output_artifact_refs["replan_request"]["mode"])
        self.assertEqual("path_blocked", replanned.state.output_artifact_refs["failure_report"]["failure_type"])


if __name__ == "__main__":
    unittest.main()
