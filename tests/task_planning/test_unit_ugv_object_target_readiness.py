import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from task_planning.migration.unit_ugv_object_target_readiness import (
    check_unit_ugv_object_target_readiness,
)


class UnitUgvObjectTargetReadinessTest(unittest.TestCase):
    def test_missing_target_map_writes_unconfirmed_template_and_stops_before_ros(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_map_path = tmp_path / "unit_ugv_targets.json"

            report = check_unit_ugv_object_target_readiness(
                target_map_path=target_map_path,
                object_query="显示器",
                platform_id="ugv_0",
                write_missing_template=True,
            )

            written = json.loads(target_map_path.read_text(encoding="utf-8"))

        self.assertFalse(report.ok)
        self.assertEqual("UnitUgvObjectTargetReadiness.v1", report.schema)
        self.assertFalse(report.target_binding_ready)
        self.assertFalse(report.target_map_exists)
        self.assertTrue(report.target_map_template_written)
        self.assertEqual("operator_confirmed_target_map", report.perception_backend)
        self.assertFalse(report.yolo_connected)
        self.assertFalse(report.ros_connected)
        self.assertFalse(report.gateway_dry_run_called)
        self.assertFalse(report.dispatch_called)
        self.assertEqual("local_operator_confirm_target_map", report.next_runtime_stage)
        self.assertIn("target map is missing; wrote an unconfirmed operator target-map template", report.validation_errors)
        self.assertFalse(written["targets"]["target_01"]["operator_confirmed_mapping"])
        self.assertEqual(["显示器"], written["targets"]["target_01"]["object_queries"])

    def test_confirmed_target_map_is_ready_for_ros_handoff_without_yolo(self):
        with tempfile.TemporaryDirectory() as tmp:
            target_map_path = Path(tmp) / "unit_ugv_targets.json"
            target_map_path.write_text(json.dumps({
                "schema": "UnitUgvTargetMap.v1",
                "platform_id": "ugv_0",
                "targets": {
                    "target_01": {
                        "capability": "confirm_target",
                        "action": "manual_confirm",
                        "operator_confirmed_mapping": True,
                        "object_queries": ["显示器", "monitor"],
                        "description": "operator-confirmed monitor target",
                    },
                },
            }, ensure_ascii=False), encoding="utf-8")

            report = check_unit_ugv_object_target_readiness(
                target_map_path=target_map_path,
                object_query="显示器",
                platform_id="ugv_0",
            )

        self.assertTrue(report.ok, report.validation_errors)
        self.assertTrue(report.target_binding_ready)
        self.assertTrue(report.target_map_exists)
        self.assertFalse(report.target_map_template_written)
        self.assertEqual("target_01", report.selected_target_id)
        self.assertEqual("operator_confirmed_target_map", report.perception_backend)
        self.assertFalse(report.yolo_connected)
        self.assertEqual("4060_ros1_gateway_handoff", report.next_runtime_stage)
        self.assertEqual("UnitUgvTargetMapCheckReport.v1", report.target_map_check["schema"])

    def test_yolo_backend_request_is_explicitly_not_ready_yet(self):
        with tempfile.TemporaryDirectory() as tmp:
            target_map_path = Path(tmp) / "unit_ugv_targets.json"

            report = check_unit_ugv_object_target_readiness(
                target_map_path=target_map_path,
                object_query="桌子",
                platform_id="ugv_0",
                perception_backend="yolo",
                write_missing_template=True,
            )

        self.assertFalse(report.ok)
        self.assertEqual("yolo", report.perception_backend)
        self.assertFalse(report.yolo_connected)
        self.assertIn("YOLO perception backend is not integrated yet", report.validation_errors)
        self.assertEqual("wait_for_yolo_integration_or_operator_target_map", report.next_runtime_stage)

    def test_cli_writes_report_and_unconfirmed_template_for_missing_map(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_map_path = tmp_path / "unit_ugv_targets.json"
            report_path = tmp_path / "readiness.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "check_unit_ugv_object_target_readiness.py"),
                    "--target-map", str(target_map_path),
                    "--object-query", "显示器",
                    "--platform-id", "ugv_0",
                    "--write-missing-template",
                    "--output", str(report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(target_map_path.exists())

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertEqual("UnitUgvObjectTargetReadiness.v1", report["schema"])
        self.assertFalse(report["ok"])
        self.assertTrue(report["target_map_template_written"])

    def test_cli_writes_report_when_template_path_cannot_be_created(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            blocked_parent = tmp_path / "not_a_directory"
            blocked_parent.write_text("blocks child path creation", encoding="utf-8")
            target_map_path = blocked_parent / "unit_ugv_targets.json"
            report_path = tmp_path / "readiness.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "check_unit_ugv_object_target_readiness.py"),
                    "--target-map", str(target_map_path),
                    "--object-query", "显示器",
                    "--platform-id", "ugv_0",
                    "--write-missing-template",
                    "--output", str(report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertEqual("UnitUgvObjectTargetReadiness.v1", report["schema"])
        self.assertFalse(report["ok"])
        self.assertFalse(report["target_map_template_written"])
        self.assertFalse(report["target_binding_ready"])
        self.assertTrue(any(
            "failed to write unconfirmed operator target-map template" in item
            for item in report["validation_errors"]
        ))


if __name__ == "__main__":
    unittest.main()
