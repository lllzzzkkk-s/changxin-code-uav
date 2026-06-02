#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import verify_artifact_package


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a transferred task-planning artifact package before replay or hardware gating.")
    parser.add_argument("archive", type=Path, help="Artifact package .tar.gz to verify.")
    parser.add_argument("--work-dir", type=Path, help="Directory used for extraction and verification.")
    parser.add_argument(
        "--verification-context",
        default="unspecified",
        choices=["unspecified", "source_machine", "receiving_machine", "unit_workplace_receiving"],
        help=(
            "Where this verification was performed. source_machine is for local sanity checks. "
            "receiving_machine or unit_workplace_receiving requires the artifact package source/verifier "
            "machine ids to differ; unit_workplace_receiving is required for work-hardware artifact-consumption evidence."
        ),
    )
    args = parser.parse_args()

    result = verify_artifact_package(
        archive_path=args.archive,
        work_dir=args.work_dir,
        verification_context=args.verification_context,
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
