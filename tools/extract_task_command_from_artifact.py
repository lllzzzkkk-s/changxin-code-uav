#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.task_command_extraction import extract_task_command_from_artifact


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract a validated TaskCommand.v1 JSON from a task-planning artifact bundle without sending ROS commands.",
    )
    parser.add_argument("artifact_root", type=Path, help="Mission artifact bundle root.")
    parser.add_argument("--platform-id")
    parser.add_argument("--capability")
    parser.add_argument("--task-id")
    parser.add_argument("--index", type=int, default=0, help="0-based index after filters are applied.")
    parser.add_argument(
        "--format",
        choices=["report", "command-json", "rosservice-yaml"],
        default="report",
        help="Output a full report, raw TaskCommand JSON, or a rosservice YAML argument.",
    )
    args = parser.parse_args()

    result = extract_task_command_from_artifact(
        artifact_root=args.artifact_root,
        platform_id=args.platform_id,
        capability=args.capability,
        task_id=args.task_id,
        index=args.index,
    )
    data = result.as_dict()
    if args.format == "command-json":
        print(data["task_command_json"])
    elif args.format == "rosservice-yaml":
        print(json.dumps({"task_command_json": data["task_command_json"]}, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
