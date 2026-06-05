#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.unit_ugv_ros_gateway_dry_run import (
    run_unit_ugv_ros_gateway_dry_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the 4060-side UGV ROS1 gateway dry_run from a ROS-ready handoff report. "
            "This calls only /gateway/dry_run and never dispatches or publishes raw ROS topics."
        ),
    )
    parser.add_argument(
        "--handoff-report",
        required=True,
        type=Path,
        help="UnitUgvObjectApproachRosReadyHandoff.v1 report.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for dry-run stdout, parsed response, and structured report.",
    )
    args = parser.parse_args()

    report = run_unit_ugv_ros_gateway_dry_run(
        handoff_report_path=args.handoff_report,
        output_dir=args.output_dir,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
