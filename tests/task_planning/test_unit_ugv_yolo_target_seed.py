import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from task_planning.migration.unit_ugv_yolo_target_seed import (
    seed_unit_ugv_target_map_from_yolo_detection,
)


class UnitUgvYoloTargetSeedTest(unittest.TestCase):
    def test_yolo_detection_seeds_unconfirmed_target_map_without_ros_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            detections_path = _write_yolo_detections(tmp_path, label="显示器", confidence=0.91)
            target_map_path = tmp_path / "unit_ugv_targets.json"

            report = seed_unit_ugv_target_map_from_yolo_detection(
                detections_path=detections_path,
                target_map_path=target_map_path,
                object_query="显示器",
                platform_id="ugv_0",
            )
            target_map = json.loads(target_map_path.read_text(encoding="utf-8"))

        self.assertFalse(report.ok)
        self.assertEqual("UnitUgvYoloTargetSeed.v1", report.schema)
        self.assertEqual("ObjectDetectionSet.v1", report.detection_schema)
        self.assertTrue(report.yolo_detection_observed)
        self.assertTrue(report.target_map_template_written)
        self.assertFalse(report.target_binding_ready)
        self.assertFalse(report.ros_connected)
        self.assertFalse(report.gateway_dry_run_called)
        self.assertFalse(report.dispatch_called)
        self.assertEqual("local_operator_confirm_target_map", report.next_runtime_stage)
        self.assertIn("YOLO detection observed but target map remains operator-unconfirmed", report.validation_errors)
        target = target_map["targets"]["target_01"]
        self.assertFalse(target["operator_confirmed_mapping"])
        self.assertEqual("manual_confirm", target["action"])
        self.assertIn("显示器", target["object_queries"])

    def test_yolo_detection_with_no_matching_object_does_not_write_target_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            detections_path = _write_yolo_detections(tmp_path, label="椅子", confidence=0.93)
            target_map_path = tmp_path / "unit_ugv_targets.json"

            report = seed_unit_ugv_target_map_from_yolo_detection(
                detections_path=detections_path,
                target_map_path=target_map_path,
                object_query="显示器",
                platform_id="ugv_0",
                min_confidence=0.5,
            )

        self.assertFalse(report.ok)
        self.assertFalse(report.yolo_detection_observed)
        self.assertFalse(report.target_map_template_written)
        self.assertFalse(target_map_path.exists())
        self.assertIn("no YOLO detection matched object_query above min_confidence: 显示器", report.validation_errors)

    def test_invalid_detection_schema_does_not_seed_target_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            detections_path = tmp_path / "bad_detections.json"
            detections_path.write_text(json.dumps({
                "schema": "WrongSchema.v1",
                "detections": [{"label": "显示器", "confidence": 0.91}],
            }, ensure_ascii=False), encoding="utf-8")
            target_map_path = tmp_path / "unit_ugv_targets.json"

            report = seed_unit_ugv_target_map_from_yolo_detection(
                detections_path=detections_path,
                target_map_path=target_map_path,
                object_query="显示器",
                platform_id="ugv_0",
            )

        self.assertFalse(report.ok)
        self.assertFalse(report.yolo_detection_observed)
        self.assertFalse(report.target_map_template_written)
        self.assertFalse(target_map_path.exists())
        self.assertIn("detections schema must be ObjectDetectionSet.v1", report.validation_errors)

    def test_cli_writes_seed_report(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            detections_path = _write_yolo_detections(tmp_path, label="monitor", confidence=0.82)
            target_map_path = tmp_path / "unit_ugv_targets.json"
            report_path = tmp_path / "seed-report.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "seed_unit_ugv_target_map_from_yolo_detection.py"),
                    "--detections", str(detections_path),
                    "--target-map", str(target_map_path),
                    "--object-query", "monitor",
                    "--platform-id", "ugv_0",
                    "--output", str(report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(target_map_path.exists())

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertEqual("UnitUgvYoloTargetSeed.v1", report["schema"])
        self.assertTrue(report["yolo_detection_observed"])
        self.assertFalse(report["target_binding_ready"])

    def test_cli_writes_report_when_target_map_template_cannot_be_created(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            detections_path = _write_yolo_detections(tmp_path, label="monitor", confidence=0.82)
            blocked_parent = tmp_path / "not_a_directory"
            blocked_parent.write_text("blocks child path creation", encoding="utf-8")
            target_map_path = blocked_parent / "unit_ugv_targets.json"
            report_path = tmp_path / "seed-report.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "seed_unit_ugv_target_map_from_yolo_detection.py"),
                    "--detections", str(detections_path),
                    "--target-map", str(target_map_path),
                    "--object-query", "monitor",
                    "--platform-id", "ugv_0",
                    "--output", str(report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertEqual("UnitUgvYoloTargetSeed.v1", report["schema"])
        self.assertTrue(report["yolo_detection_observed"])
        self.assertFalse(report["target_map_template_written"])
        self.assertFalse(report["target_binding_ready"])
        self.assertTrue(any(
            "failed to write unconfirmed operator target-map template" in item
            for item in report["validation_errors"]
        ))


def _write_yolo_detections(tmp: Path, *, label: str, confidence: float) -> Path:
    path = tmp / "yolo_detections.json"
    path.write_text(json.dumps({
        "schema": "ObjectDetectionSet.v1",
        "source": "future_yolo",
        "image_ref": "/tmp/frame.jpg",
        "detections": [
            {
                "label": label,
                "confidence": confidence,
                "bbox_xyxy": [10, 20, 110, 160],
            },
        ],
    }, ensure_ascii=False), encoding="utf-8")
    return path


if __name__ == "__main__":
    unittest.main()
