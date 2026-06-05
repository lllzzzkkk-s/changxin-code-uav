import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from task_planning.migration.unit_ugv_target_map import (
    build_unit_ugv_target_map_template,
    check_unit_ugv_target_map,
)


class UnitUgvTargetMapToolTest(unittest.TestCase):
    def test_check_accepts_unique_operator_confirmed_object_query_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target_map_path = Path(tmp) / "targets.json"
            target_map_path.write_text(json.dumps({
                "schema": "UnitUgvTargetMap.v1",
                "platform_id": "ugv_0",
                "targets": {
                    "target_01": {
                        "capability": "confirm_target",
                        "action": "manual_confirm",
                        "operator_confirmed_mapping": True,
                        "object_queries": ["充电桩", "charging station"],
                        "description": "operator-confirmed local charging station",
                    },
                },
            }, ensure_ascii=False), encoding="utf-8")

            report = check_unit_ugv_target_map(
                target_map_path,
                expected_platform_id="ugv_0",
                object_query="charging station",
                require_object_queries=True,
            )

            self.assertTrue(report.ok, report.validation_errors)
            self.assertEqual("UnitUgvTargetMapCheckReport.v1", report.schema)
            self.assertEqual("target_01", report.selected_target_id)
            self.assertEqual([], report.validation_errors)
            self.assertEqual([{
                "normalized_object_query": "charging station",
                "object_query": "charging station",
                "target_id": "target_01",
            }], [
                item for item in report.object_query_index
                if item["normalized_object_query"] == "charging station"
            ])

    def test_check_rejects_duplicate_object_aliases_across_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            target_map_path = Path(tmp) / "targets.json"
            target_map_path.write_text(json.dumps({
                "schema": "UnitUgvTargetMap.v1",
                "platform_id": "ugv_0",
                "targets": {
                    "target_01": {
                        "capability": "confirm_target",
                        "action": "manual_confirm",
                        "operator_confirmed_mapping": True,
                        "object_queries": ["charging station"],
                    },
                    "target_02": {
                        "capability": "confirm_target",
                        "action": "manual_confirm",
                        "operator_confirmed_mapping": True,
                        "object_queries": ["Charging   Station"],
                    },
                },
            }), encoding="utf-8")

            report = check_unit_ugv_target_map(
                target_map_path,
                expected_platform_id="ugv_0",
                object_query="charging station",
                require_object_queries=True,
            )

            self.assertFalse(report.ok)
            self.assertIn(
                "object_query maps to multiple targets: charging station: target_01, target_02",
                report.validation_errors,
            )
            self.assertEqual("", report.selected_target_id)

    def test_check_rejects_move_base_target_over_site_distance_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            target_map_path = Path(tmp) / "targets.json"
            target_map_path.write_text(json.dumps({
                "schema": "UnitUgvTargetMap.v1",
                "platform_id": "ugv_0",
                "targets": {
                    "target_01": {
                        "capability": "confirm_target",
                        "action": "move_base_goal",
                        "operator_confirmed_mapping": True,
                        "object_queries": ["nearby monitor"],
                        "frame_id": "map",
                        "x": 2.0,
                        "y": 0.0,
                        "yaw": 0.0,
                        "max_distance_m": 2.0,
                    },
                },
            }), encoding="utf-8")

            report = check_unit_ugv_target_map(
                target_map_path,
                expected_platform_id="ugv_0",
                object_query="nearby monitor",
                max_move_base_distance_m=1.0,
            )

            self.assertFalse(report.ok)
            self.assertIn(
                "target target_01 max_distance_m 2.0 exceeds site limit 1.0",
                report.validation_errors,
            )

    def test_template_keeps_operator_confirmation_false_by_default(self):
        template = build_unit_ugv_target_map_template(
            platform_id="ugv_0",
            target_id="target_01",
            object_queries=["桌子", "table"],
            action="manual_confirm",
        )

        target = template["targets"]["target_01"]
        self.assertEqual("UnitUgvTargetMap.v1", template["schema"])
        self.assertEqual(["桌子", "table"], target["object_queries"])
        self.assertFalse(target["operator_confirmed_mapping"])

    def test_cli_writes_report_when_template_path_cannot_be_created(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            blocked_parent = tmp_path / "not_a_directory"
            blocked_parent.write_text("blocks child path creation", encoding="utf-8")
            target_map_path = blocked_parent / "unit_ugv_targets.json"
            report_path = tmp_path / "target-map-write.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "check_unit_ugv_target_map.py"),
                    "--write-template", str(target_map_path),
                    "--platform-id", "ugv_0",
                    "--target-id", "target_01",
                    "--object-query", "显示器",
                    "--output", str(report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertEqual("UnitUgvTargetMapTemplateWriteReport.v1", report["schema"])
        self.assertFalse(report["ok"])
        self.assertFalse(report["operator_confirmed_mapping"])
        self.assertFalse(report["ros_connected"])
        self.assertFalse(report["gateway_dry_run_called"])
        self.assertFalse(report["dispatch_called"])
        self.assertEqual(["显示器"], report["object_queries"])
        self.assertTrue(any(
            "target map template write failed" in item
            for item in report["validation_errors"]
        ))


if __name__ == "__main__":
    unittest.main()
