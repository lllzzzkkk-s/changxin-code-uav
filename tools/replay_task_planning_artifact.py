#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.mission_ops.replay import compare_artifact_bundles, load_artifact_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate or compare task-planning mission artifact bundles.")
    parser.add_argument("artifact_root", type=Path, help="Artifact bundle directory created under MISSION_ARTIFACT_ROOT/<run_id>.")
    parser.add_argument("--compare-to", type=Path, help="Optional second artifact bundle directory for structured comparison.")
    parser.add_argument("--allow-differences", action="store_true", help="Return success even if structured comparison finds diffs.")
    args = parser.parse_args()

    if args.compare_to:
        comparison = compare_artifact_bundles(args.artifact_root, args.compare_to)
        print(json.dumps(comparison.as_dict(), indent=2, sort_keys=True))
        if comparison.validation_errors:
            return 1
        if comparison.diffs and not args.allow_differences:
            return 2
        return 0

    bundle = load_artifact_bundle(args.artifact_root)
    print(json.dumps(bundle.as_dict(), indent=2, sort_keys=True))
    return 0 if bundle.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
