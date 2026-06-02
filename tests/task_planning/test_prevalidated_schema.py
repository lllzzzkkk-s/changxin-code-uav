import json
import tempfile
import unittest
from pathlib import Path

from task_planning.contracts import TaskSchema
from task_planning.mission_ops.replay import load_artifact_bundle
from task_planning.migration.prevalidated_schema import run_prevalidated_task_schema


class PrevalidatedSchemaTest(unittest.TestCase):
    def test_work_hardware_replays_prevalidated_schema_to_operator_approval_artifact(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            schema_path = Path(tmp) / "model_task_schema.json"
            schema_path.write_text(json.dumps(_schema().as_dict()), encoding="utf-8")

            result = run_prevalidated_task_schema(
                profile_path=repo_root / "profiles/work_hardware.env",
                task_schema_path=schema_path,
                artifact_root=Path(tmp) / "runs",
                case_id="uav_ugv_coordination",
            )

            bundle = load_artifact_bundle(result.artifact_bundle_path)
            gateway_trace = json.loads((Path(result.artifact_bundle_path) / "gateway_trace.json").read_text(encoding="utf-8"))
            validation = json.loads((Path(result.artifact_bundle_path) / "validation_report.json").read_text(encoding="utf-8"))
            mission_input = json.loads((Path(result.artifact_bundle_path) / "mission_input.json").read_text(encoding="utf-8"))
            self.assertTrue(result.ok, result.as_dict())
            self.assertEqual("uav_ugv_coordination", result.case_id)
            self.assertEqual("approval_required", result.status)
            self.assertEqual("OPERATOR_APPROVAL", result.current_state)
            self.assertTrue(bundle.ok, bundle.as_dict())
            self.assertEqual([], gateway_trace["records"])
            self.assertEqual("OPERATOR_APPROVAL", validation["current_state"])
            self.assertEqual("uav_ugv_coordination", mission_input["run_input"]["case_id"])

    def test_dev_mock_replays_prevalidated_schema_through_mock_gateway(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            model_lab_dir = Path(tmp) / "model-lab"
            model_lab_dir.mkdir()
            schema_path = model_lab_dir / "model_task_schema.json"
            schema_path.write_text(json.dumps(_schema().as_dict()), encoding="utf-8")
            (model_lab_dir / "mission_input.json").write_text(json.dumps({
                "schema": "ModelLabMissionInput.v1",
                "case_id": "uav_ugv_coordination",
            }), encoding="utf-8")

            result = run_prevalidated_task_schema(
                profile_path=repo_root / "profiles/dev_mock.env",
                task_schema_path=schema_path,
                artifact_root=Path(tmp) / "runs",
            )

            gateway_trace = json.loads((Path(result.artifact_bundle_path) / "gateway_trace.json").read_text(encoding="utf-8"))
            self.assertTrue(result.ok, result.as_dict())
            self.assertEqual("uav_ugv_coordination", result.case_id)
            self.assertEqual("dry_run_complete", result.status)
            self.assertEqual(3, len(gateway_trace["records"]))
            self.assertEqual([False, False, False], [record["publish_attempted"] for record in gateway_trace["records"]])

    def test_prevalidated_schema_requires_case_id_for_loose_schema_file(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            schema_path = Path(tmp) / "model_task_schema.json"
            schema_path.write_text(json.dumps(_schema().as_dict()), encoding="utf-8")

            result = run_prevalidated_task_schema(
                profile_path=repo_root / "profiles/dev_mock.env",
                task_schema_path=schema_path,
                artifact_root=Path(tmp) / "runs",
            )

            self.assertFalse(result.ok)
            self.assertIn("requires case_id", "\n".join(result.validation_errors))

    def test_prevalidated_schema_rejects_real_ros1_gateway_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            schema_path = tmp_path / "model_task_schema.json"
            schema_path.write_text(json.dumps(_schema().as_dict()), encoding="utf-8")
            profile_path = tmp_path / "work_hardware_ros1.env"
            profile_path.write_text("\n".join([
                "MISSION_PROFILE=work_hardware",
                "MODEL_PROVIDER=mock",
                "MODEL_BASE_URL=",
                "MODEL_NAME=",
                "PLANNER_BACKEND=mock",
                "PLATFORM_BACKEND=ros1_gateway",
                "MISSION_STATE_STORE=json",
                f"MISSION_ARTIFACT_ROOT={tmp_path / 'runs'}",
                "ROS_MASTER_URI=http://127.0.0.1:11311",
                "ROS_IP=127.0.0.1",
                "HARDWARE_APPROVAL_REQUIRED=true",
                "ROS_GATEWAY_DISPATCH_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dispatch",
                "ROS_GATEWAY_DRY_RUN_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dry_run",
            ]), encoding="utf-8")

            result = run_prevalidated_task_schema(
                profile_path=profile_path,
                task_schema_path=schema_path,
                case_id="uav_ugv_coordination",
            )

            self.assertFalse(result.ok)
            self.assertIn("prevalidated schema replay must use PLATFORM_BACKEND=mock|sim", "\n".join(result.validation_errors))


def _schema():
    return TaskSchema.from_intent(
        mission_id="golden_uav_ugv_coordination",
        intent="搜索 A 区，发现目标后派无人车接近确认，无人机继续中继或观察",
        area_id="area_A",
        target_id="target_01",
        context_snapshot={"mission_id": "golden_uav_ugv_coordination"},
    )


if __name__ == "__main__":
    unittest.main()
