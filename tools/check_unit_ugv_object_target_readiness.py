#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.unit_ugv_object_target_readiness import (
    check_unit_ugv_object_target_readiness,
    write_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check whether a UGV object query is bound to current target evidence. "
            "Current supported backend is an operator-confirmed target map; YOLO is a future backend."
        ),
    )
    parser.add_argument("--target-map", required=True, type=Path)
    parser.add_argument("--object-query", required=True)
    parser.add_argument("--platform-id", default="ugv_0")
    parser.add_argument("--target-id", default="target_01")
    parser.add_argument(
        "--perception-backend",
        choices=["operator_confirmed_target_map", "yolo"],
        default="operator_confirmed_target_map",
    )
    parser.add_argument("--write-missing-template", action="store_true")
    parser.add_argument("--max-move-base-distance-m", type=float)
    parser.add_argument("--output", type=Path, help="Optional path to also write the JSON report.")
    args = parser.parse_args()

    report = check_unit_ugv_object_target_readiness(
        target_map_path=args.target_map,
        object_query=args.object_query,
        platform_id=args.platform_id,
        target_id=args.target_id,
        perception_backend=args.perception_backend,
        write_missing_template=args.write_missing_template,
        max_move_base_distance_m=args.max_move_base_distance_m,
    )
    if args.output:
        write_report(args.output, report)
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
