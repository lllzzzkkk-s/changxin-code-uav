#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import check_task_planning_readiness


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check which distributed task-planning lane this machine/profile can run without sending ROS commands.",
    )
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()

    report = check_task_planning_readiness(args.profile, repo_root=args.repo_root)
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
