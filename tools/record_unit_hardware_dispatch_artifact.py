#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import (
    parse_command_ack_file,
    parse_task_progress_file,
    record_unit_hardware_dispatch_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Record a unit/workplace ROS1 dispatch proof artifact from already captured dispatch, "
            "local operator approval, execution machine id, ack, and progress evidence."
        ),
    )
    parser.add_argument("--source-artifact", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path, help="Local work_hardware ros1_gateway profile used on the unit/workplace machine.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--platform-id", required=True)
    parser.add_argument("--task-id")
    parser.add_argument("--dispatch-service")
    parser.add_argument("--dispatch-returncode", type=int, default=0)
    parser.add_argument("--dispatch-stdout-file", type=Path)
    parser.add_argument("--dispatch-stderr-file", type=Path)
    parser.add_argument("--command-ack-file", type=Path)
    parser.add_argument("--task-progress-file", required=True, type=Path)
    parser.add_argument("--execution-context", default="unit_workplace_hardware")
    parser.add_argument("--run-id")
    parser.add_argument("--operator-approved", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    command_ack = parse_command_ack_file(args.command_ack_file) if args.command_ack_file else None
    task_progress = parse_task_progress_file(args.task_progress_file)
    stdout = args.dispatch_stdout_file.read_text(encoding="utf-8") if args.dispatch_stdout_file else ""
    stderr = args.dispatch_stderr_file.read_text(encoding="utf-8") if args.dispatch_stderr_file else ""
    report = record_unit_hardware_dispatch_artifact(
        source_artifact=args.source_artifact,
        profile_path=args.profile,
        output_dir=args.output_dir,
        platform_id=args.platform_id,
        task_id=args.task_id,
        dispatch_service=args.dispatch_service,
        dispatch_returncode=args.dispatch_returncode,
        dispatch_stdout=stdout,
        dispatch_stderr=stderr,
        command_ack=command_ack,
        task_progress=task_progress,
        operator_approved=args.operator_approved,
        execution_context=args.execution_context,
        run_id=args.run_id,
        overwrite=args.overwrite,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
