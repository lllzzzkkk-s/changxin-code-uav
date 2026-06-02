#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.ros1_workspace import prepare_ros1_gateway_workspace


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan or install the platform_gateway_msgs catkin package into a ROS1 workspace src directory.",
    )
    parser.add_argument("--catkin-src", required=True, type=Path, help="Target catkin workspace src directory, for example ~/catkin_ws/src.")
    parser.add_argument("--mode", choices=["copy", "symlink"], default="copy")
    parser.add_argument("--apply", action="store_true", help="Actually install the package. Omit for dry-run planning.")
    parser.add_argument("--force", action="store_true", help="Replace an existing platform_gateway_msgs package.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()

    plan = prepare_ros1_gateway_workspace(
        repo_root=args.repo_root,
        catkin_src=args.catkin_src,
        mode=args.mode,
        apply=args.apply,
        force=args.force,
    )
    print(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
    return 0 if plan.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
