import json
import subprocess
import sys
import unittest

from platform_gateway.service_core import PlatformGatewayServiceCore
from task_planning.contracts import CommandAck, PlatformState, TaskCommand


class AcceptingExecutor:
    def dry_run(self, command):
        return CommandAck.accepted(command.mission_id, command.task_id, command.platform_id)

    def dispatch(self, command):
        return CommandAck(
            mission_id=command.mission_id,
            task_id=command.task_id,
            platform_id=command.platform_id,
            accepted=True,
            reason="local_executor_accepted",
            local_check={
                "capability_known": True,
                "localization_ok": True,
                "battery_ok": True,
                "safety_ok": True,
                "motion_attempted": True,
            },
        )


class PlatformGatewayServiceCoreTest(unittest.TestCase):
    def test_dry_run_accepts_capability_level_task_without_motion_or_raw_publish(self):
        core = PlatformGatewayServiceCore(platform_state=_uav_state())

        response = core.handle_json(_command().as_json(), mode="dry_run")

        self.assertTrue(response.ack.accepted)
        self.assertEqual("dry_run", response.mode)
        self.assertFalse(response.motion_attempted)
        self.assertFalse(response.raw_ros_publish_attempted)
        self.assertFalse(response.ack.local_check["motion_attempted"])

    def test_dispatch_defaults_to_safe_reject_without_local_executor(self):
        core = PlatformGatewayServiceCore(platform_state=_uav_state())

        response = core.handle_json(_command().as_json(), mode="dispatch")

        self.assertFalse(response.ack.accepted)
        self.assertEqual("no local dispatch executor configured", response.ack.reason)
        self.assertFalse(response.motion_attempted)
        self.assertFalse(response.raw_ros_publish_attempted)

    def test_dispatch_can_call_injected_executor_after_validation(self):
        core = PlatformGatewayServiceCore(platform_state=_uav_state(), executor=AcceptingExecutor())

        response = core.handle_json(_command().as_json(), mode="dispatch")

        self.assertTrue(response.ack.accepted)
        self.assertEqual("local_executor_accepted", response.ack.reason)
        self.assertTrue(response.motion_attempted)
        self.assertFalse(response.raw_ros_publish_attempted)

    def test_raw_ros_command_is_rejected_before_executor(self):
        core = PlatformGatewayServiceCore(platform_state=_uav_state(), executor=AcceptingExecutor())
        command = TaskCommand(
            mission_id="mission_001",
            task_id="task_001",
            platform_id="uav_0",
            capability="/mavros/setpoint_raw/local",
            parameters={"topic": "/mavros/setpoint_raw/local"},
        )

        response = core.handle_json(_command_json(command), mode="dispatch")

        self.assertFalse(response.ack.accepted)
        self.assertIn("capability is not allowed", response.ack.reason)
        self.assertFalse(response.motion_attempted)

    def test_wrong_platform_and_low_battery_are_rejected(self):
        core = PlatformGatewayServiceCore(platform_state=_uav_state(battery=0.1))
        command = TaskCommand(
            mission_id="mission_001",
            task_id="task_001",
            platform_id="ugv_0",
            capability="inspect_area",
            parameters={"area_id": "area_A"},
        )

        response = core.handle_json(_command_json(command), mode="dry_run")

        self.assertFalse(response.ack.accepted)
        self.assertIn("unknown platform_id", response.ack.reason)
        self.assertFalse(response.ack.local_check["battery_ok"])

    def test_cli_dry_run_outputs_gateway_service_response(self):
        completed = subprocess.run(
            [
                sys.executable,
                "tools/platform_gateway_service_core.py",
                "--mode",
                "dry_run",
                "--platform-id",
                "uav_0",
                "--platform-type",
                "uav",
                "--capability",
                "inspect_area",
                "--task-command-json",
                _command().as_json(),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, completed.returncode)
        response = json.loads(completed.stdout)
        self.assertEqual("GatewayServiceResponse.v1", response["schema"])
        self.assertTrue(response["ack"]["accepted"])
        self.assertFalse(response["raw_ros_publish_attempted"])


def _uav_state(battery=0.8):
    return PlatformState(
        platform_id="uav_0",
        platform_type="uav",
        capabilities=["inspect_area", "relay_or_overwatch", "hold_position"],
        battery_percentage=battery,
    )


def _command():
    return _JsonTaskCommand(
        mission_id="mission_001",
        task_id="task_001",
        platform_id="uav_0",
        capability="inspect_area",
        parameters={"area_id": "area_A"},
    )


class _JsonTaskCommand(TaskCommand):
    def as_json(self):
        return _command_json(self)


def _command_json(command):
    return json.dumps(command.as_dict(), ensure_ascii=False, sort_keys=True)


if __name__ == "__main__":
    unittest.main()
