#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import collect_distributed_fleet_evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect local baseline evidence for the distributed fleet testing goal.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--case", default="uav_ugv_coordination")
    args = parser.parse_args()

    result = collect_distributed_fleet_evidence(
        repo_root=REPO_ROOT,
        output_dir=args.output_dir,
        case_id=args.case,
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
