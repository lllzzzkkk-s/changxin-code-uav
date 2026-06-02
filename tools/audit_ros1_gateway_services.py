#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.ros1_service_audit import (
    audit_ros1_gateway_services,
    make_rosservice_command_runner,
    parse_service_args_file,
    parse_service_signature_file,
)
from task_planning.config import load_profile


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of expected ROS1 platform gateway service names.",
    )
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--platform-id", action="append", default=[])
    parser.add_argument("--service-list-file", type=Path)
    parser.add_argument("--service-type-file", type=Path, help="Lines of '<service> <type>' or JSON mapping from service to type.")
    parser.add_argument("--service-args-file", type=Path, help="Lines of '<service> <args>' or JSON mapping from service to args.")
    parser.add_argument("--run-rosservice-list", action="store_true", help="Run read-only `rosservice list` on this machine.")
    parser.add_argument("--run-service-signatures", action="store_true", help="Run read-only `rosservice type` and `rosservice args` for expected services.")
    parser.add_argument("--require-service-signatures", action="store_true", help="Fail unless expected services have TaskCommandJson type and task_command_json args evidence.")
    args = parser.parse_args()

    observed_services = None
    observed_service_types = None
    observed_service_args = None
    command_runner = None
    command_environment_source = None
    if args.service_list_file:
        observed_services = args.service_list_file.read_text(encoding="utf-8").splitlines()
    elif args.run_rosservice_list:
        command_runner = make_rosservice_command_runner(load_profile(args.profile))
        command_environment_source = "profile"
    if args.service_type_file:
        observed_service_types = parse_service_signature_file(args.service_type_file)
    if args.service_args_file:
        observed_service_args = parse_service_args_file(args.service_args_file)
    if args.run_service_signatures:
        command_runner = make_rosservice_command_runner(load_profile(args.profile))
        command_environment_source = "profile"

    report = audit_ros1_gateway_services(
        profile_path=args.profile,
        platform_ids=args.platform_id,
        observed_services=observed_services,
        observed_service_types=observed_service_types,
        observed_service_args=observed_service_args,
        command_runner=command_runner,
        run_service_signature_checks=args.run_service_signatures,
        require_service_signatures=args.require_service_signatures,
        command_environment_source=command_environment_source,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
