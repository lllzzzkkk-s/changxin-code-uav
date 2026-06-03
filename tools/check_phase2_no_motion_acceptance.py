#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.mission_ops.acceptance_report import (  # noqa: E402
    build_phase2_no_motion_acceptance_report,
    write_phase2_no_motion_acceptance_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Phase 2 no-motion acceptance report from task-planning artifacts.",
    )
    parser.add_argument("--artifact-root", action="append", required=True, type=Path)
    parser.add_argument("--phase1-archive-path", required=True)
    parser.add_argument("--phase1-archive-sha256", required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    report = build_phase2_no_motion_acceptance_report(
        artifact_roots=args.artifact_root,
        phase1_archive_path=args.phase1_archive_path,
        phase1_archive_sha256=args.phase1_archive_sha256,
    )
    if args.output_dir:
        if args.json_only:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / "phase2_no_motion_acceptance.json").write_text(
                json.dumps(report.as_dict(), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        else:
            write_phase2_no_motion_acceptance_outputs(report, output_dir=args.output_dir)

    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
