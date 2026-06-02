#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import verify_migration_archive


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract and verify a portable task-planning migration bundle.",
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--skip-checks", action="store_true")
    parser.add_argument(
        "--verification-context",
        default="unspecified",
        choices=["unspecified", "source_machine", "receiving_machine", "unit_workplace_receiving"],
        help=(
            "Where this verification was performed; receiving_machine or unit_workplace_receiving is required "
            "for transfer-completion evidence and is rejected when the hashed source/verifier machine ids match."
        ),
    )
    args = parser.parse_args()

    result = verify_migration_archive(
        archive_path=args.archive,
        work_dir=args.work_dir,
        run_checks=not args.skip_checks,
        verification_context=args.verification_context,
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
