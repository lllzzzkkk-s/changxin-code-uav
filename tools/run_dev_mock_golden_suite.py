#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import run_dev_mock_golden_suite


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run every dev_mock golden mission case and verify portable artifacts.",
    )
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--profile", default=REPO_ROOT / "profiles/dev_mock.env", type=Path)
    args = parser.parse_args()

    report = run_dev_mock_golden_suite(
        repo_root=REPO_ROOT,
        profile_path=args.profile,
        artifact_root=args.artifact_root,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
