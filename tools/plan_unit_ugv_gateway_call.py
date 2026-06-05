#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.unit_ugv_gateway_call_plan import plan_unit_ugv_gateway_call


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Plan the next UGV ROS1 gateway service call from a no-ROS prep bundle. "
            "This command does not run rosservice, connect ROS, or dispatch."
        ),
    )
    parser.add_argument("--prep-report", required=True, type=Path, help="UnitUgvObjectApproachPrepBundle.v1 JSON.")
    parser.add_argument("--profile", required=True, type=Path, help="Local work_hardware ros1_gateway profile.")
    parser.add_argument("--mode", choices=["dry_run", "dispatch"], default="dry_run")
    parser.add_argument(
        "--operator-approved",
        action="store_true",
        help="Allow planning a dispatch command. This still does not execute it.",
    )
    args = parser.parse_args()

    report = plan_unit_ugv_gateway_call(
        prep_report_path=args.prep_report,
        profile_path=args.profile,
        mode=args.mode,
        operator_approved=args.operator_approved,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
