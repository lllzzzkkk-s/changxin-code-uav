#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.unit_ugv_ros_gateway_dry_run import (
    parse_unit_ugv_ros_gateway_dry_run_response_stdout,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Parse an existing UGV gateway dry_run rosservice stdout file without calling ROS again. "
            "This is for evidence recovery when rosservice returned YAML-wrapped response_json."
        ),
    )
    parser.add_argument("--response-stdout", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-platform-id", default="ugv_0")
    parser.add_argument("--service-name", default="/fleet/ugv_0/gateway/dry_run")
    args = parser.parse_args()

    report = parse_unit_ugv_ros_gateway_dry_run_response_stdout(
        response_stdout_path=args.response_stdout,
        output_dir=args.output_dir,
        expected_platform_id=args.expected_platform_id,
        service_name=args.service_name,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
