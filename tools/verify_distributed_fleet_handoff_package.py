#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import verify_distributed_fleet_handoff_package
from task_planning.migration.verify import ALLOWED_MIGRATION_VERIFICATION_CONTEXTS


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a distributed fleet handoff package after transfer."
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument(
        "--verification-context",
        choices=sorted(ALLOWED_MIGRATION_VERIFICATION_CONTEXTS),
        default="unspecified",
        help=(
            "Use source_machine for local sanity checks. receiving_machine or unit_workplace_receiving "
            "requires the hashed source/verifier machine ids to differ."
        ),
    )
    parser.add_argument(
        "--run-migration-checks",
        action="store_true",
        help="Also run the embedded migration bundle's first checks after manifest verification.",
    )
    args = parser.parse_args()

    verification = verify_distributed_fleet_handoff_package(
        archive_path=args.archive,
        work_dir=args.work_dir,
        verification_context=args.verification_context,
        run_migration_checks=args.run_migration_checks,
    )
    print(json.dumps(verification.as_dict(), indent=2, sort_keys=True))
    return 0 if verification.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
