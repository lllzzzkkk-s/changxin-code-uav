#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.unit_ugv_object_approach_bundle import (
    prepare_unit_ugv_object_approach_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a no-ROS UGV object-approach handoff bundle from a validated "
            "mission artifact and a local UnitUgvTargetMap.v1."
        ),
    )
    parser.add_argument("artifact_root", type=Path, help="Validated mission artifact bundle root.")
    parser.add_argument("--target-map", required=True, type=Path, help="Local UnitUgvTargetMap.v1 JSON.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory to write the prep bundle.")
    parser.add_argument("--platform-id", default="ugv_0")
    parser.add_argument("--capability", default="confirm_target")
    parser.add_argument("--task-id")
    parser.add_argument("--index", type=int, default=0, help="0-based index after platform/capability/task filters.")
    parser.add_argument("--max-move-base-distance-m", type=float)
    args = parser.parse_args()

    report = prepare_unit_ugv_object_approach_bundle(
        artifact_root=args.artifact_root,
        target_map_path=args.target_map,
        output_dir=args.output_dir,
        platform_id=args.platform_id,
        capability=args.capability,
        task_id=args.task_id,
        index=args.index,
        max_move_base_distance_m=args.max_move_base_distance_m,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
