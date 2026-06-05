from __future__ import annotations

import argparse
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from platform_gateway.ros1_service_node_template import Ros1ServiceBinding, register_gateway_services
from platform_gateway.service_core import PlatformGatewayServiceCore
from platform_gateway.unit_ugv_executor import Ros1MoveBaseBridge, UnitUgvExecutor, UnitUgvTargetMap
from task_planning.contracts import PlatformState


@dataclass(frozen=True)
class Ros1GatewayNodeConfig:
    platform_id: str
    platform_type: str
    capabilities: list[str]
    service_symbol: str
    dry_run_service_name: str
    dispatch_service_name: str
    node_name: str
    comm_status: str = "online"
    task_status: str = "idle"
    localization_ok: bool = True
    safety_state: str = "normal"
    battery_percentage: float = 0.80
    unit_ugv_target_map: Path | None = None
    unit_ugv_operator_approved: bool = False
    unit_ugv_enable_move_base: bool = False
    unit_ugv_move_base_action: str = "/move_base"
    unit_ugv_move_base_server_timeout_s: float = 5.0
    unit_ugv_max_move_base_distance_m: float | None = None
    unit_ugv_progress_output: Path | None = None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a ROS1 platform gateway service node.")
    parser.add_argument("--platform-id", required=True)
    parser.add_argument("--platform-type", required=True, choices=["uav", "ugv"])
    parser.add_argument("--capability", action="append", required=True)
    parser.add_argument(
        "--service-symbol",
        required=True,
        help="Generated ROS service symbol, for example gateway_msgs.srv:TaskCommandJson.",
    )
    parser.add_argument("--dry-run-service", default="/fleet/{platform_id}/gateway/dry_run")
    parser.add_argument("--dispatch-service", default="/fleet/{platform_id}/gateway/dispatch")
    parser.add_argument("--node-name", default="")
    parser.add_argument("--comm-status", default="online")
    parser.add_argument("--task-status", default="idle")
    parser.add_argument("--localization-ok", default="true", choices=["true", "false"])
    parser.add_argument("--safety-state", default="normal")
    parser.add_argument("--battery", type=float, default=0.80)
    parser.add_argument(
        "--unit-ugv-target-map",
        type=Path,
        help=(
            "JSON UnitUgvTargetMap.v1 file for a real unit UGV executor. "
            "Omit this to keep dispatch on the default safe reject executor."
        ),
    )
    parser.add_argument(
        "--unit-ugv-operator-approved",
        action="store_true",
        help="Enable real unit UGV dispatch after local operator approval has been recorded.",
    )
    parser.add_argument(
        "--unit-ugv-enable-move-base",
        action="store_true",
        help="Allow target-map entries with action=move_base_goal to call the local move_base action.",
    )
    parser.add_argument("--unit-ugv-move-base-action", default="/move_base")
    parser.add_argument("--unit-ugv-move-base-server-timeout-s", type=float, default=5.0)
    parser.add_argument(
        "--unit-ugv-max-move-base-distance-m",
        type=float,
        help="Required maximum target-map max_distance_m allowed for move_base_goal dispatch.",
    )
    parser.add_argument(
        "--unit-ugv-progress-output",
        type=Path,
        help="Optional TaskProgressSet.v1 JSON output path for the most recent unit UGV dispatch.",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> Ros1GatewayNodeConfig:
    node_name = args.node_name or f"platform_gateway_{args.platform_id}"
    return Ros1GatewayNodeConfig(
        platform_id=args.platform_id,
        platform_type=args.platform_type,
        capabilities=list(args.capability),
        service_symbol=args.service_symbol,
        dry_run_service_name=_format_service_name(args.dry_run_service, args.platform_id),
        dispatch_service_name=_format_service_name(args.dispatch_service, args.platform_id),
        node_name=node_name,
        comm_status=args.comm_status,
        task_status=args.task_status,
        localization_ok=args.localization_ok == "true",
        safety_state=args.safety_state,
        battery_percentage=args.battery,
        unit_ugv_target_map=args.unit_ugv_target_map,
        unit_ugv_operator_approved=args.unit_ugv_operator_approved,
        unit_ugv_enable_move_base=args.unit_ugv_enable_move_base,
        unit_ugv_move_base_action=args.unit_ugv_move_base_action,
        unit_ugv_move_base_server_timeout_s=args.unit_ugv_move_base_server_timeout_s,
        unit_ugv_max_move_base_distance_m=args.unit_ugv_max_move_base_distance_m,
        unit_ugv_progress_output=args.unit_ugv_progress_output,
    )


def run_gateway_node(rospy: Any, config: Ros1GatewayNodeConfig) -> None:
    service_type = _load_symbol(config.service_symbol)
    binding = Ros1ServiceBinding(
        dry_run_service_name=config.dry_run_service_name,
        dispatch_service_name=config.dispatch_service_name,
        service_type=service_type,
        response_factory=_response_factory(service_type),
    )
    executor = _build_executor(rospy, config)
    core = PlatformGatewayServiceCore(
        platform_state=PlatformState(
            platform_id=config.platform_id,
            platform_type=config.platform_type,
            capabilities=config.capabilities,
            comm_status=config.comm_status,
            task_status=config.task_status,
            localization_ok=config.localization_ok,
            safety_state=config.safety_state,
            battery_percentage=config.battery_percentage,
        ),
        executor=executor,
    )
    rospy.init_node(config.node_name)
    register_gateway_services(rospy, core, binding)
    rospy.spin()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    config = config_from_args(parser.parse_args(argv))
    rospy = importlib.import_module("rospy")
    run_gateway_node(rospy, config)
    return 0


def _format_service_name(template: str, platform_id: str) -> str:
    if "{platform_id}" not in template:
        raise ValueError("service name template must include {platform_id}")
    return template.format(platform_id=platform_id)


def _load_symbol(symbol: str) -> Any:
    if ":" not in symbol:
        raise ValueError("service symbol must use module.path:Symbol")
    module_name, attr_name = symbol.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def _response_factory(service_type: Any) -> Callable[[str], Any]:
    response_type = getattr(service_type, "_response_class", None)
    if response_type is None:
        raise ValueError("service type must expose _response_class")

    def factory(response_json: str) -> Any:
        try:
            return response_type(response_json=response_json)
        except TypeError:
            return response_type(response_json)

    return factory


def _build_executor(rospy: Any, config: Ros1GatewayNodeConfig) -> Any:
    if config.unit_ugv_target_map is None:
        return None
    if config.platform_type != "ugv":
        raise ValueError("--unit-ugv-target-map can only be used with --platform-type ugv")
    target_map = UnitUgvTargetMap.from_path(config.unit_ugv_target_map)
    bridge = None
    if config.unit_ugv_enable_move_base:
        bridge = Ros1MoveBaseBridge(
            rospy=rospy,
            action_name=config.unit_ugv_move_base_action,
            wait_for_server_s=config.unit_ugv_move_base_server_timeout_s,
        )
    return UnitUgvExecutor(
        target_map=target_map,
        operator_approved=config.unit_ugv_operator_approved,
        bridge=bridge,
        progress_output=config.unit_ugv_progress_output,
        max_move_base_distance_m=config.unit_ugv_max_move_base_distance_m,
    )


if __name__ == "__main__":
    raise SystemExit(main())
