#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.prevalidated_schema import run_prevalidated_task_schema


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a prevalidated TaskSchema JSON through validator, PDDL, BT, and mock/pre-dispatch gateway artifacts.",
    )
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--task-schema", required=True, type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument(
        "--case",
        default="",
        help="Mission case id to preserve in mission_input.run_input.case_id; inferred from sibling model-lab mission_input.json when omitted.",
    )
    args = parser.parse_args()

    result = run_prevalidated_task_schema(
        profile_path=args.profile,
        task_schema_path=args.task_schema,
        artifact_root=args.artifact_root,
        case_id=args.case or None,
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
