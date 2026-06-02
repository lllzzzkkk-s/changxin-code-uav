#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from platform_gateway.service_core import PlatformGatewayServiceCore
from task_planning.contracts import PlatformState


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the platform gateway service core without ROS.")
    parser.add_argument("--mode", choices=["dry_run", "dispatch"], required=True)
    parser.add_argument("--platform-id", required=True)
    parser.add_argument("--platform-type", choices=["uav", "ugv"], required=True)
    parser.add_argument("--capability", action="append", required=True, help="Capability exposed by this local platform.")
    parser.add_argument("--battery", type=float, default=0.80)
    parser.add_argument("--localization-ok", action="store_true", default=True)
    parser.add_argument("--safety-state", default="normal")
    parser.add_argument("--task-command-json", help="TaskCommand.v1 JSON. If omitted, stdin is used.")
    args = parser.parse_args()

    command_json = args.task_command_json if args.task_command_json is not None else sys.stdin.read()
    core = PlatformGatewayServiceCore(
        platform_state=PlatformState(
            platform_id=args.platform_id,
            platform_type=args.platform_type,
            capabilities=list(args.capability),
            battery_percentage=args.battery,
            localization_ok=args.localization_ok,
            safety_state=args.safety_state,
        )
    )
    response = core.handle_json(command_json, mode=args.mode)
    print(response.to_json())
    return 0 if response.ack.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
