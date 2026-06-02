import json
import tempfile
import unittest
from pathlib import Path

from platform_gateway.mock_gateway import MockPlatformGateway
from platform_gateway.ros1_service_gateway import CommandResult, Ros1GatewayConfig, Ros1ServiceGateway
from task_planning.config import EnvironmentProfile, ProfileValidationError
from task_planning.contracts import TaskCommand
from task_planning.mission_ops.golden_cases import golden_case_by_id
from task_planning.mission_ops.mock_llm_client import MockLLMClient
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore
from tools.run_task_planning_golden import run_cases


class Ros1ServiceGatewayTest(unittest.TestCase):
    def test_ros1_gateway_builds_allowlisted_rosservice_call(self):
        calls = []

        def fake_runner(args, env):
            calls.append((list(args), dict(env)))
            return CommandResult(returncode=0, stdout=json.dumps({"accepted": True}), stderr="")

        gateway = Ros1ServiceGateway(
            Ros1GatewayConfig(
                ros_master_uri="http://127.0.0.1:11311",
                ros_ip="127.0.0.1",
                use_dry_run_service=True,
                require_operator_approval=True,
            ),
            command_runner=fake_runner,
            operator_approved=True,
        )
        command = TaskCommand(
            mission_id="mission_001",
            task_id="task_001",
            platform_id="uav_0",
            capability="inspect_area",
            parameters={"area_id": "area_A"},
        )

        ack = gateway.dispatch(command)

        self.assertTrue(ack.accepted)
        self.assertEqual("rosservice", calls[0][0][0])
        self.assertEqual("call", calls[0][0][1])
        self.assertEqual("/fleet/uav_0/gateway/dry_run", calls[0][0][2])
        payload = json.loads(calls[0][0][3])
        self.assertEqual("TaskCommand.v1", payload["schema"])
        self.assertEqual("inspect_area", payload["capability"])
        self.assertEqual("http://127.0.0.1:11311", calls[0][1]["ROS_MASTER_URI"])
        self.assertEqual("127.0.0.1", calls[0][1]["ROS_IP"])
        self.assertFalse(gateway.dispatch_log[0]["publish_attempted"])
        self.assertTrue(gateway.dispatch_log[0]["rosservice_called"])

    def test_ros1_gateway_requires_operator_approval_before_rosservice_call(self):
        calls = []
        gateway = Ros1ServiceGateway(
            Ros1GatewayConfig(
                ros_master_uri="http://127.0.0.1:11311",
                ros_ip="127.0.0.1",
                require_operator_approval=True,
            ),
            command_runner=lambda args, env: calls.append(args) or CommandResult(returncode=0),
            operator_approved=False,
        )

        ack = gateway.dispatch(TaskCommand(
            mission_id="mission_001",
            task_id="task_001",
            platform_id="uav_0",
            capability="inspect_area",
            parameters={"area_id": "area_A"},
        ))

        self.assertFalse(ack.accepted)
        self.assertIn("operator approval is required", ack.reason)
        self.assertEqual([], calls)
        self.assertFalse(gateway.dispatch_log[0]["rosservice_called"])

    def test_ros1_gateway_rejects_raw_ros_task_command_before_runner(self):
        calls = []
        gateway = Ros1ServiceGateway(
            Ros1GatewayConfig(
                ros_master_uri="http://127.0.0.1:11311",
                ros_ip="127.0.0.1",
                require_operator_approval=False,
            ),
            command_runner=lambda args, env: calls.append(args) or CommandResult(returncode=0),
            operator_approved=True,
        )

        ack = gateway.dispatch(TaskCommand(
            mission_id="mission_001",
            task_id="task_001",
            platform_id="uav_0",
            capability="/cmd_vel",
            parameters={"topic": "/cmd_vel"},
        ))

        self.assertFalse(ack.accepted)
        self.assertEqual([], calls)
        self.assertFalse(gateway.dispatch_log[0]["rosservice_called"])

    def test_runner_auto_installs_ros1_gateway_and_stops_at_operator_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "work_hardware",
                "MODEL_PROVIDER": "mock",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "ros1_gateway",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": str(Path(tmp) / "runs"),
                "ROS_MASTER_URI": "http://127.0.0.1:11311",
                "ROS_IP": "127.0.0.1",
                "HARDWARE_APPROVAL_REQUIRED": "true",
            })
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp) / "state"),
                model_client=MockLLMClient(),
            )

            result = runner.run(golden_case_by_id("uav_ugv_coordination").run_input(), profile.as_env_dict())

            self.assertEqual("approval_required", result.status)
            self.assertEqual("OPERATOR_APPROVAL", result.state.current_state)
            self.assertIsInstance(runner.manager.gateway, Ros1ServiceGateway)
            self.assertEqual([], runner.manager.gateway.dispatch_log)

    def test_explicit_mock_gateway_is_rejected_for_ros1_gateway_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "work_hardware",
                "MODEL_PROVIDER": "mock",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "ros1_gateway",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": str(Path(tmp) / "runs"),
                "ROS_MASTER_URI": "http://127.0.0.1:11311",
                "ROS_IP": "127.0.0.1",
                "HARDWARE_APPROVAL_REQUIRED": "true",
            })
            runner = MissionManagerRunner(
                state_store=JsonMissionOpsStateStore(Path(tmp) / "state"),
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )

            with self.assertRaisesRegex(ValueError, "requires a non-mock gateway implementation"):
                runner.run(golden_case_by_id("uav_ugv_coordination").run_input(), profile.as_env_dict())

    def test_ros1_gateway_service_templates_must_include_platform_id(self):
        with self.assertRaisesRegex(ProfileValidationError, "must include \\{platform_id\\}"):
            EnvironmentProfile.from_mapping({
                "MISSION_PROFILE": "work_hardware",
                "MODEL_PROVIDER": "mock",
                "PLANNER_BACKEND": "mock",
                "PLATFORM_BACKEND": "ros1_gateway",
                "MISSION_STATE_STORE": "json",
                "MISSION_ARTIFACT_ROOT": "/tmp/runs",
                "ROS_MASTER_URI": "http://127.0.0.1:11311",
                "ROS_IP": "127.0.0.1",
                "HARDWARE_APPROVAL_REQUIRED": "true",
                "ROS_GATEWAY_DISPATCH_SERVICE_TEMPLATE": "/fleet/gateway/dispatch",
            })

    def test_golden_cli_respects_ros1_gateway_profile_without_mock_gateway_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "work_ros1.env"
            profile_path.write_text("\n".join([
                "MISSION_PROFILE=work_hardware",
                "MODEL_PROVIDER=mock",
                "PLANNER_BACKEND=mock",
                "PLATFORM_BACKEND=ros1_gateway",
                "MISSION_STATE_STORE=json",
                f"MISSION_ARTIFACT_ROOT={Path(tmp) / 'runs'}",
                "ROS_MASTER_URI=http://127.0.0.1:11311",
                "ROS_IP=127.0.0.1",
                "HARDWARE_APPROVAL_REQUIRED=true",
                "ROS_GATEWAY_DISPATCH_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dispatch",
                "ROS_GATEWAY_DRY_RUN_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dry_run",
            ]), encoding="utf-8")

            results = run_cases(
                profile_path=profile_path,
                case_ids=["uav_ugv_coordination"],
                artifact_root=Path(tmp) / "override-runs",
            )

            self.assertEqual("approval_required", results[0]["status"])
            self.assertEqual("OPERATOR_APPROVAL", results[0]["current_state"])


if __name__ == "__main__":
    unittest.main()
