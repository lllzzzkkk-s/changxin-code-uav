import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

from platform_gateway.ros1_service_node import build_arg_parser, config_from_args, run_gateway_node
from platform_gateway.unit_ugv_executor import UnitUgvExecutor, UnitUgvTarget, UnitUgvTargetMap
from task_planning.contracts import TaskCommand


class UnitUgvExecutorTest(unittest.TestCase):
    def test_dry_run_rejects_unmapped_target(self):
        executor = UnitUgvExecutor(target_map=_target_map({}))

        ack = executor.dry_run(_command())

        self.assertFalse(ack.accepted)
        self.assertEqual("target_id is not mapped on this unit UGV: target_01", ack.reason)
        self.assertFalse(ack.local_check["motion_attempted"])
        self.assertFalse(ack.local_check["raw_ros_publish_attempted"])

    def test_dry_run_accepts_operator_confirmed_mapping_without_motion(self):
        executor = UnitUgvExecutor(target_map=_target_map({"target_01": _manual_target()}))

        ack = executor.dry_run(_command())

        self.assertTrue(ack.accepted)
        self.assertEqual("unit_ugv_dry_run_ok", ack.reason)
        self.assertTrue(ack.local_check["target_mapped"])
        self.assertTrue(ack.local_check["mapping_operator_confirmed"])
        self.assertFalse(ack.local_check["motion_attempted"])

    def test_dispatch_requires_operator_approval(self):
        executor = UnitUgvExecutor(target_map=_target_map({"target_01": _manual_target()}))

        ack = executor.dispatch(_command())

        self.assertFalse(ack.accepted)
        self.assertEqual("operator approval required for unit UGV dispatch", ack.reason)
        self.assertFalse(ack.local_check["motion_attempted"])

    def test_manual_confirm_dispatch_writes_progress_after_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            progress_path = Path(tmp) / "task-progress.json"
            executor = UnitUgvExecutor(
                target_map=_target_map({"target_01": _manual_target()}),
                operator_approved=True,
                progress_output=progress_path,
            )

            ack = executor.dispatch(_command())

            self.assertTrue(ack.accepted)
            self.assertEqual("manual_confirm_completed", ack.reason)
            self.assertFalse(ack.local_check["motion_attempted"])
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            self.assertEqual("TaskProgressSet.v1", progress["schema"])
            self.assertEqual(1, len(progress["items"]))
            item = progress["items"][0]
            self.assertEqual("TaskProgress.v1", item["schema"])
            self.assertEqual("completed", item["status"])
            self.assertEqual("golden_uav_ugv_coordination", item["mission_id"])
            self.assertEqual("task_002", item["task_id"])
            self.assertEqual("ugv_0", item["platform_id"])
            self.assertEqual("target_01", item["observations"]["target_id"])

    def test_move_base_mapping_rejects_when_move_base_bridge_is_not_enabled(self):
        executor = UnitUgvExecutor(
            target_map=_target_map({"target_01": {
                "capability": "confirm_target",
                "action": "move_base_goal",
                "operator_confirmed_mapping": True,
                "frame_id": "map",
                "x": 1.0,
                "y": 2.0,
                "yaw": 0.0,
                "max_distance_m": 1.0,
            }}),
            operator_approved=True,
        )

        ack = executor.dispatch(_command())

        self.assertFalse(ack.accepted)
        self.assertEqual("move_base bridge is not enabled", ack.reason)
        self.assertFalse(ack.local_check["motion_attempted"])


class Ros1ServiceNodeUnitUgvExecutorTest(unittest.TestCase):
    def setUp(self):
        module = types.ModuleType("fake_gateway_msgs.srv")
        module.TaskCommandJson = FakeService
        sys.modules["fake_gateway_msgs"] = types.ModuleType("fake_gateway_msgs")
        sys.modules["fake_gateway_msgs.srv"] = module

    def tearDown(self):
        sys.modules.pop("fake_gateway_msgs.srv", None)
        sys.modules.pop("fake_gateway_msgs", None)

    def test_node_uses_unit_ugv_executor_when_target_map_is_supplied(self):
        with tempfile.TemporaryDirectory() as tmp:
            target_map_path = Path(tmp) / "targets.json"
            target_map_path.write_text(json.dumps({
                "schema": "UnitUgvTargetMap.v1",
                "platform_id": "ugv_0",
                "targets": {"target_01": _manual_target()},
            }), encoding="utf-8")
            progress_path = Path(tmp) / "progress.json"
            args = build_arg_parser().parse_args([
                "--platform-id", "ugv_0",
                "--platform-type", "ugv",
                "--capability", "confirm_target",
                "--service-symbol", "fake_gateway_msgs.srv:TaskCommandJson",
                "--unit-ugv-target-map", str(target_map_path),
                "--unit-ugv-operator-approved",
                "--unit-ugv-progress-output", str(progress_path),
            ])
            config = config_from_args(args)
            rospy = FakeRospy()

            run_gateway_node(rospy, config)

            dispatch_handler = rospy.services[1][2]
            response = dispatch_handler(FakeRequest(_command_json()))
            parsed = json.loads(response.response_json)
            self.assertTrue(parsed["ack"]["accepted"])
            self.assertFalse(parsed["motion_attempted"])
            self.assertTrue(progress_path.exists())


class FakeResponse:
    def __init__(self, response_json=""):
        self.response_json = response_json


class FakeService:
    _response_class = FakeResponse


class FakeRospy:
    def __init__(self):
        self.services = []

    def init_node(self, name):
        self.node_name = name

    def Service(self, name, service_type, handler):
        self.services.append((name, service_type, handler))

    def spin(self):
        pass


class FakeRequest:
    def __init__(self, task_command_json):
        self.task_command_json = task_command_json


def _target_map(targets):
    return UnitUgvTargetMap(
        platform_id="ugv_0",
        targets={
            target_id: UnitUgvTarget.from_mapping(target_id, target)
            for target_id, target in targets.items()
        },
    )


def _manual_target():
    return {
        "capability": "confirm_target",
        "action": "manual_confirm",
        "operator_confirmed_mapping": True,
        "description": "operator-confirmed no-motion target check",
    }


def _command():
    return TaskCommand.from_dict(json.loads(_command_json()))


def _command_json():
    return json.dumps({
        "schema": "TaskCommand.v1",
        "mission_id": "golden_uav_ugv_coordination",
        "task_id": "task_002",
        "platform_id": "ugv_0",
        "capability": "confirm_target",
        "parameters": {"target_id": "target_01"},
        "preconditions": {"localization_ok": True, "min_battery_percentage": 0.3},
        "disconnect_policy": "continue_current_task",
        "timeout_s": 180,
    }, sort_keys=True)


if __name__ == "__main__":
    unittest.main()
