#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import build_distributed_fleet_handoff_package


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a transfer-ready package containing the migration bundle and baseline evidence."
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--package-name", default="distributed-fleet-handoff-package")
    parser.add_argument("--case", default="uav_ugv_coordination")
    parser.add_argument(
        "--source-machine-id",
        help="Override the 64-character hashed source machine id recorded in the handoff and embedded migration bundle.",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        help="Use an existing evidence directory instead of collecting a fresh local baseline.",
    )
    args = parser.parse_args()

    package = build_distributed_fleet_handoff_package(
        repo_root=REPO_ROOT,
        output_dir=args.output_dir,
        package_name=args.package_name,
        case_id=args.case,
        evidence_dir=args.evidence_dir,
        source_machine_id=args.source_machine_id,
    )
    print(json.dumps(package.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
