#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.unit_ugv_yolo_target_seed import (
    seed_unit_ugv_target_map_from_yolo_detection,
    write_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Seed an unconfirmed UnitUgvTargetMap.v1 template from a future YOLO ObjectDetectionSet.v1. "
            "This never authorizes ROS handoff, gateway dry_run, dispatch, or motion."
        ),
    )
    parser.add_argument("--detections", required=True, type=Path, help="ObjectDetectionSet.v1 JSON.")
    parser.add_argument("--target-map", required=True, type=Path, help="Target map template to write.")
    parser.add_argument("--object-query", required=True)
    parser.add_argument("--platform-id", default="ugv_0")
    parser.add_argument("--target-id", default="target_01")
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--output", type=Path, help="Optional path to also write the JSON report.")
    args = parser.parse_args()

    report = seed_unit_ugv_target_map_from_yolo_detection(
        detections_path=args.detections,
        target_map_path=args.target_map,
        object_query=args.object_query,
        platform_id=args.platform_id,
        target_id=args.target_id,
        min_confidence=args.min_confidence,
    )
    if args.output:
        write_report(args.output, report)
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
