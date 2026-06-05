#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.unit_ugv_object_approach_pipeline import (
    prepare_unit_ugv_object_approach_pipeline,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a ROS-ready single-UGV object-approach handoff from operator intent. "
            "This runs the Mac/source-side artifact and gateway planning chain only; it does "
            "not connect ROS, call rosservice, or dispatch."
        ),
    )
    parser.add_argument("--profile", required=True, type=Path, help="Non-ROS profile, usually profiles/dev_mock.env.")
    parser.add_argument("--intent", required=True, help="Operator natural-language object approach intent.")
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--target-map", required=True, type=Path, help="Local UnitUgvTargetMap.v1 JSON.")
    parser.add_argument("--ros1-gateway-profile", required=True, type=Path, help="Local work_hardware ros1_gateway profile.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--platform-id", default="ugv_0")
    parser.add_argument("--capability", default="confirm_target")
    parser.add_argument("--index", type=int, default=1, help="0-based command index after platform/capability filtering.")
    parser.add_argument("--max-move-base-distance-m", type=float)
    args = parser.parse_args()

    report = prepare_unit_ugv_object_approach_pipeline(
        profile_path=args.profile,
        intent=args.intent,
        mission_id=args.mission_id,
        case_id=args.case_id,
        target_map_path=args.target_map,
        ros1_gateway_profile_path=args.ros1_gateway_profile,
        output_dir=args.output_dir,
        platform_id=args.platform_id,
        capability=args.capability,
        index=args.index,
        max_move_base_distance_m=args.max_move_base_distance_m,
        repo_root=REPO_ROOT,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
