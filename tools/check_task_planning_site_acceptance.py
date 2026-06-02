#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import check_task_planning_site_acceptance


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a machine-readable task-planning site acceptance report without sending ROS control commands.",
    )
    parser.add_argument("--profile", required=True, type=Path, help="Profile for the lane being accepted.")
    parser.add_argument(
        "--artifact-package",
        action="append",
        default=[],
        type=Path,
        help="Transferred artifact package to verify. Repeat for multiple packages.",
    )
    parser.add_argument("--artifact-work-dir", type=Path, help="Directory used to extract artifact packages.")
    parser.add_argument("--require-artifact-package", action="store_true", help="Fail if no verified artifact package is provided.")
    parser.add_argument("--case", default="", help="Expected mission case_id for received artifact packages.")
    parser.add_argument("--through-stage", default="mock_gateway_dispatch", help="Hardware gate stage to include for work_hardware.")
    parser.add_argument("--platform-id", action="append", default=[], help="Platform id for ROS1 gateway service audit.")
    parser.add_argument("--rosservice-list-file", type=Path, help="Captured output from `rosservice list`.")
    parser.add_argument("--require-rosservice-audit", action="store_true", help="Fail unless a captured ROS1 service list proves gateway services.")
    parser.add_argument("--service-type-file", type=Path, help="Captured '<service> <type>' evidence from `rosservice type`.")
    parser.add_argument("--service-args-file", type=Path, help="Captured '<service> <args>' evidence from `rosservice args`.")
    parser.add_argument("--run-rosservice-list", action="store_true", help="Run read-only `rosservice list` on this machine.")
    parser.add_argument("--run-service-signatures", action="store_true", help="Run read-only `rosservice type` and `rosservice args` for expected services.")
    parser.add_argument("--require-service-signatures", action="store_true", help="Fail unless gateway services have TaskCommandJson type and task_command_json args.")
    args = parser.parse_args()

    report = check_task_planning_site_acceptance(
        profile_path=args.profile,
        repo_root=REPO_ROOT,
        artifact_packages=args.artifact_package,
        artifact_work_dir=args.artifact_work_dir,
        require_artifact_package=args.require_artifact_package,
        case_id=args.case,
        through_stage=args.through_stage,
        platform_ids=args.platform_id,
        rosservice_list_file=args.rosservice_list_file,
        require_rosservice_audit=args.require_rosservice_audit,
        service_type_file=args.service_type_file,
        service_args_file=args.service_args_file,
        run_rosservice_list=args.run_rosservice_list,
        run_service_signatures=args.run_service_signatures,
        require_service_signatures=args.require_service_signatures,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
