#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import build_migration_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a portable task-planning migration bundle.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--bundle-name", default="task-planning-migration-bundle")
    parser.add_argument(
        "--source-machine-id",
        help="Override the 64-character hashed source machine id recorded in the migration manifest.",
    )
    args = parser.parse_args()

    bundle = build_migration_bundle(
        repo_root=REPO_ROOT,
        output_dir=args.output_dir,
        bundle_name=args.bundle_name,
        source_machine_id=args.source_machine_id,
    )
    print(json.dumps(bundle.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
