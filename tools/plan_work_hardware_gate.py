#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.config import load_profile
from task_planning.hardware import build_hardware_gate_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the staged unit/work hardware gate plan without executing ROS commands.")
    parser.add_argument("--profile", required=True, type=Path, help="Path to a work_hardware profile.")
    parser.add_argument(
        "--through-stage",
        default="read_only_observation",
        choices=[
            "read_only_observation",
            "mock_gateway_dispatch",
            "bench_dry_run_no_motion",
            "constrained_real_gateway_command",
            "controlled_mission_dry_run",
            "failure_injection_recovery",
        ],
        help="Include stages from the beginning through this gate.",
    )
    args = parser.parse_args()

    profile = load_profile(args.profile)
    plan = build_hardware_gate_plan(profile, through_stage=args.through_stage)
    print(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
    return 0 if plan.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
