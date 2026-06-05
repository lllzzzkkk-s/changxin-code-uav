import json
import tempfile
import unittest
from pathlib import Path

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.config import EnvironmentProfile
from task_planning.migration.unit_ugv_artifact_target_map_preflight import (
    check_unit_ugv_artifact_target_map,
)
from task_planning.mission_ops.golden_cases import golden_case_by_id
from task_planning.mission_ops.mock_llm_client import MockLLMClient
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore


class UnitUgvArtifactTargetMapPreflightTest(unittest.TestCase):
    def test_preflight_accepts_object_approach_artifact_against_confirmed_target_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = _run_single_ugv_object_approach_artifact(Path(tmp))
            target_map_path = _write_target_map(Path(tmp), object_queries=["充电桩", "charging_station"])

            report = check_unit_ugv_artifact_target_map(
                artifact_root=artifact_root,
                target_map_path=target_map_path,
                platform_id="ugv_0",
                index=1,
                max_move_base_distance_m=1.0,
            )

            self.assertTrue(report.ok, report.validation_errors)
            self.assertEqual("UnitUgvArtifactTargetMapPreflight.v1", report.schema)
            self.assertEqual("ugv_0", report.platform_id)
            self.assertEqual("task_002", report.task_id)
            self.assertEqual("充电桩", report.object_query)
            self.assertEqual("target_01", report.selected_target_id)
            self.assertEqual("target_01", report.target_map_check["selected_target_id"])
            self.assertTrue(report.command_ack["accepted"])
            self.assertEqual("target_id", report.command_ack["local_check"]["target_resolution_source"])
            self.assertFalse(report.command_ack["local_check"]["motion_attempted"])
            self.assertFalse(report.ros_connected)
            self.assertFalse(report.dispatch_performed)

    def test_preflight_rejects_artifact_object_query_missing_from_target_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = _run_single_ugv_object_approach_artifact(Path(tmp))
            target_map_path = _write_target_map(Path(tmp), object_queries=["显示器", "monitor"])

            report = check_unit_ugv_artifact_target_map(
                artifact_root=artifact_root,
                target_map_path=target_map_path,
                platform_id="ugv_0",
                index=1,
                max_move_base_distance_m=1.0,
            )

            self.assertFalse(report.ok)
            self.assertIn(
                "target_map:object_query is not mapped on this unit UGV: 充电桩",
                report.validation_errors,
            )
            self.assertEqual("", report.selected_target_id)
            self.assertEqual({}, report.command_ack)
            self.assertFalse(report.ros_connected)
            self.assertFalse(report.dispatch_performed)

    def test_preflight_rejects_command_target_id_that_disagrees_with_object_query_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = _run_single_ugv_object_approach_artifact(Path(tmp))
            target_map_path = _write_target_map(Path(tmp), object_queries=["other"], extra_targets={
                "target_02": {
                    "capability": "confirm_target",
                    "action": "manual_confirm",
                    "operator_confirmed_mapping": True,
                    "object_queries": ["充电桩", "charging_station"],
                    "description": "operator-confirmed but mismatched target",
                },
            })

            report = check_unit_ugv_artifact_target_map(
                artifact_root=artifact_root,
                target_map_path=target_map_path,
                platform_id="ugv_0",
                index=1,
                max_move_base_distance_m=1.0,
            )

            self.assertFalse(report.ok)
            self.assertIn(
                "task_command target_id target_01 does not match object_query-selected target target_02",
                report.validation_errors,
            )
            self.assertEqual("target_02", report.target_map_check["selected_target_id"])
            self.assertEqual("target_01", report.selected_target_id)


def _run_single_ugv_object_approach_artifact(tmp: Path) -> Path:
    profile = EnvironmentProfile.from_mapping({
        "MISSION_PROFILE": "dev_mock",
        "MODEL_PROVIDER": "mock",
        "PLANNER_BACKEND": "mock",
        "PLATFORM_BACKEND": "mock",
        "MISSION_STATE_STORE": "json",
        "MISSION_ARTIFACT_ROOT": str(tmp / "runs"),
    })
    runner = MissionManagerRunner(
        state_store=JsonMissionOpsStateStore(tmp / "state"),
        model_client=MockLLMClient(),
        gateway=MockPlatformGateway(),
    )

    result = runner.run(golden_case_by_id("single_ugv_object_approach").run_input(), profile.as_env_dict())

    return Path(result.artifact_bundle_path)


def _write_target_map(tmp: Path, *, object_queries, extra_targets=None):
    target_map_path = tmp / "unit_ugv_targets.json"
    targets = {
        "target_01": {
            "capability": "confirm_target",
            "action": "manual_confirm",
            "operator_confirmed_mapping": True,
            "object_queries": list(object_queries),
            "description": "operator-confirmed local object approach target",
        },
    }
    targets.update(extra_targets or {})
    target_map_path.write_text(json.dumps({
        "schema": "UnitUgvTargetMap.v1",
        "platform_id": "ugv_0",
        "targets": targets,
    }, ensure_ascii=False), encoding="utf-8")
    return target_map_path


if __name__ == "__main__":
    unittest.main()
