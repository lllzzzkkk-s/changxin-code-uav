#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.lane_matrix import DEFAULT_LANES, run_lane_matrix


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the same mission case across mock-first lanes and compare portable artifacts.",
    )
    parser.add_argument("--case", default="uav_ugv_coordination")
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--repo-root", default=REPO_ROOT, type=Path)
    parser.add_argument(
        "--lane",
        action="append",
        dest="lanes",
        choices=DEFAULT_LANES,
        help="Lane to run. Repeat to select a subset; omit for dev_mock, server_sim, and work_hardware.",
    )
    args = parser.parse_args()

    report = run_lane_matrix(
        repo_root=args.repo_root,
        artifact_root=args.artifact_root,
        case_id=args.case,
        lanes=args.lanes,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
