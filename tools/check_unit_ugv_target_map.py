#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.unit_ugv_target_map import (
    check_unit_ugv_target_map,
    write_unit_ugv_target_map_template,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate or create a local UnitUgvTargetMap.v1 without connecting ROS or dispatching.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--target-map", type=Path, help="Existing UnitUgvTargetMap.v1 JSON to validate.")
    mode.add_argument("--write-template", type=Path, help="Write a starter UnitUgvTargetMap.v1 JSON template.")
    parser.add_argument("--platform-id", default="ugv_0")
    parser.add_argument("--target-id", default="target_01", help="Template target id.")
    parser.add_argument(
        "--object-query",
        action="append",
        default=[],
        help="Object alias to put into a generated template. May be repeated.",
    )
    parser.add_argument("--select-object-query", help="Require this object query to resolve to exactly one target.")
    parser.add_argument("--require-object-queries", action="store_true")
    parser.add_argument(
        "--allow-unconfirmed",
        action="store_true",
        help="Allow operator_confirmed_mapping=false during early template review.",
    )
    parser.add_argument("--max-move-base-distance-m", type=float)
    parser.add_argument("--action", choices=["manual_confirm", "move_base_goal"], default="manual_confirm")
    parser.add_argument("--operator-confirmed", action="store_true", help="Set operator_confirmed_mapping=true in a generated template.")
    parser.add_argument("--description", default="TODO: replace with a local operator-confirmed UGV target")
    parser.add_argument("--frame-id", default="map")
    parser.add_argument("--x", type=float)
    parser.add_argument("--y", type=float)
    parser.add_argument("--yaw", type=float, default=0.0)
    parser.add_argument("--max-distance-m", type=float)
    args = parser.parse_args()

    if args.write_template:
        report = write_unit_ugv_target_map_template(
            args.write_template,
            platform_id=args.platform_id,
            target_id=args.target_id,
            object_queries=args.object_query,
            action=args.action,
            operator_confirmed=args.operator_confirmed,
            description=args.description,
            frame_id=args.frame_id,
            x=args.x,
            y=args.y,
            yaw=args.yaw,
            max_distance_m=args.max_distance_m,
        )
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    report = check_unit_ugv_target_map(
        args.target_map,
        expected_platform_id=args.platform_id,
        object_query=args.select_object_query,
        require_operator_confirmed=not args.allow_unconfirmed,
        require_object_queries=args.require_object_queries,
        max_move_base_distance_m=args.max_move_base_distance_m,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
