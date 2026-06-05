import unittest

from task_planning.contracts import CapabilityRegistry
from task_planning.mission_ops.agent_adapter import AgentTaskSchemaAdapter
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore
from platform_gateway.mock_gateway import MockPlatformGateway

import tempfile
from pathlib import Path


class AgentTaskSchemaAdapterTest(unittest.TestCase):
    def test_agent_adapter_allows_external_framework_to_draft_task_schema_only(self):
        adapter = AgentTaskSchemaAdapter(
            agent_name="openclaw",
            draft_fn=lambda payload: {
                "schema": "TaskSchema.v1",
                "intent": payload["intent"],
                "context_snapshot": dict(payload["context_snapshot"]),
                "mission_request": {
                    "schema": "MissionRequest.v1",
                    "mission_id": payload["context_snapshot"]["mission_id"],
                    "mission_type": "scout_and_confirm",
                    "areas": ["area_A"],
                    "targets": ["target_01"],
                    "required_capabilities": ["confirm_target"],
                    "constraints": {
                        "mission_variant": "single_ugv_object_approach",
                        "object_query": "阀门",
                        "require_operator_before_motion": True,
                    },
                },
            },
            registry=CapabilityRegistry.scout_and_confirm_default(),
        )

        schema = adapter.compile_task_schema(
            "让小车识别附近的阀门，然后靠近",
            {"mission_id": "mission_agent_object_approach", "primary_platform": "ugv_0"},
        )

        self.assertEqual("mission_agent_object_approach", schema.mission_request.mission_id)
        self.assertEqual("阀门", schema.mission_request.constraints["object_query"])

    def test_agent_adapter_rejects_raw_ros_topics_from_external_agent(self):
        adapter = AgentTaskSchemaAdapter(
            agent_name="hermes",
            draft_fn=lambda payload: {
                "schema": "TaskSchema.v1",
                "intent": payload["intent"],
                "context_snapshot": {},
                "mission_request": {
                    "schema": "MissionRequest.v1",
                    "mission_id": "mission_bad_agent",
                    "mission_type": "scout_and_confirm",
                    "areas": ["area_A"],
                    "targets": ["target_01"],
                    "required_capabilities": ["confirm_target"],
                    "constraints": {"unsafe": "/cmd_vel"},
                },
            },
            registry=CapabilityRegistry.scout_and_confirm_default(),
        )

        with self.assertRaisesRegex(ValueError, "raw ROS reference is forbidden"):
            adapter.compile_task_schema("让小车直接发速度", {})

    def test_runner_can_use_agent_adapter_without_changing_planner_executor_gateway(self):
        adapter = AgentTaskSchemaAdapter(
            agent_name="openclaw",
            draft_fn=lambda payload: {
                "schema": "TaskSchema.v1",
                "intent": payload["intent"],
                "context_snapshot": dict(payload["context_snapshot"]),
                "mission_request": {
                    "schema": "MissionRequest.v1",
                    "mission_id": payload["context_snapshot"]["mission_id"],
                    "mission_type": "scout_and_confirm",
                    "areas": ["area_A"],
                    "targets": ["target_01"],
                    "required_capabilities": ["confirm_target"],
                    "constraints": {
                        "mission_variant": "single_ugv_object_approach",
                        "object_query": "消防栓",
                        "require_operator_before_motion": True,
                    },
                },
            },
            registry=CapabilityRegistry.scout_and_confirm_default(),
        )

        with tempfile.TemporaryDirectory() as tmp:
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp)),
                model_client=adapter,
                gateway=MockPlatformGateway(),
            )
            result = runner.run({
                "intent": "让小车识别附近的消防栓，然后走过去",
                "context_snapshot": {
                    "mission_id": "mission_agent_pipeline",
                    "primary_platform": "ugv_0",
                },
            }, {"dry_run": True})

        self.assertEqual("dry_run_complete", result.status)
        plan = result.state.output_artifact_refs["plan"]
        self.assertEqual(["identify-target", "approach-target"], [step["action"] for step in plan["steps"]])


if __name__ == "__main__":
    unittest.main()
