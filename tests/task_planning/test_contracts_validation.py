import unittest

from task_planning.contracts import (
    CapabilityRegistry,
    CommandAck,
    FailureReport,
    MissionRequest,
    PlatformState,
    TaskCommand,
    TaskSchema,
    validate_command_ack,
    validate_failure_report,
    validate_mission_request,
    validate_task_command,
    task_command_example,
    task_schema_example,
)


class TaskPlanningContractsValidationTest(unittest.TestCase):
    def test_validates_local_llm_task_schema_before_core_planning(self):
        schema = TaskSchema.from_intent(
            mission_id="mission_001",
            intent="搜索 A 区并派无人车确认目标",
            area_id="area_A",
            target_id="target_01",
        )

        errors = validate_mission_request(schema.mission_request, CapabilityRegistry.scout_and_confirm_default())

        self.assertEqual([], errors)
        self.assertEqual("TaskSchema.v1", schema.schema)
        self.assertEqual("MissionRequest.v1", schema.mission_request.schema)
        self.assertEqual("scout_and_confirm", schema.mission_request.mission_type)
        self.assertEqual(["area_A"], schema.mission_request.areas)
        self.assertEqual(["target_01"], schema.mission_request.targets)

    def test_rejects_mission_schema_that_has_no_aerial_or_ground_capability(self):
        request = MissionRequest(
            mission_id="mission_bad",
            mission_type="scout_and_confirm",
            areas=["area_A"],
            targets=["target_01"],
            required_capabilities=["inspect_area", "confirm_target"],
        )
        registry = CapabilityRegistry(platforms=[
            PlatformState.example(platform_id="uav_0", platform_type="uav", capabilities=["hold_position"])
        ])

        errors = validate_mission_request(request, registry)

        self.assertIn("no platform can satisfy capability: inspect_area", errors)
        self.assertIn("no platform can satisfy capability: confirm_target", errors)

    def test_task_command_validation_enforces_capability_level_boundary(self):
        command = TaskCommand(
            mission_id="mission_001",
            task_id="task_001",
            platform_id="uav_0",
            capability="/mavros/setpoint_raw/local",
            parameters={"topic": "/mavros/setpoint_raw/local"},
        )

        errors = validate_task_command(command, CapabilityRegistry.scout_and_confirm_default())

        self.assertIn("capability is not allowed: /mavros/setpoint_raw/local", errors)
        self.assertIn("raw ROS topic reference is forbidden in TaskCommand", errors)

    def test_ack_and_failure_report_are_structured_for_gateway_and_replan(self):
        ack = CommandAck.accepted(mission_id="mission_001", task_id="task_001", platform_id="uav_0")
        failure = FailureReport(
            mission_id="mission_001",
            task_id="task_002",
            platform_id="ugv_0",
            failure_type="path_blocked",
            recoverable=True,
            reason="local_planner_no_path",
            recommended_actions=["request_uav_rescan", "try_alternate_region_entry"],
        )

        self.assertEqual([], validate_command_ack(ack))
        self.assertEqual([], validate_failure_report(failure))
        self.assertTrue(ack.accepted)
        self.assertTrue(failure.recoverable)

    def test_contract_examples_validate_as_first_slice_fixtures(self):
        registry = CapabilityRegistry.scout_and_confirm_default()

        self.assertEqual([], validate_mission_request(task_schema_example().mission_request, registry))
        self.assertEqual([], validate_task_command(task_command_example(), registry))


if __name__ == "__main__":
    unittest.main()
