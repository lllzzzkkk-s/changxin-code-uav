from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from platform_gateway.service_core import PlatformGatewayServiceCore


@dataclass(frozen=True)
class Ros1ServiceBinding:
    dry_run_service_name: str
    dispatch_service_name: str
    service_type: object
    response_factory: Callable[[str], object]


def register_gateway_services(rospy, core: PlatformGatewayServiceCore, binding: Ros1ServiceBinding) -> None:
    """Register ROS1 services that delegate to PlatformGatewayServiceCore.

    The expected service shape is:

        string task_command_json
        ---
        string response_json

    Keep ROS package-specific imports outside this module so the core remains
    importable on non-ROS development machines.
    """

    def dry_run_handler(request):
        return binding.response_factory(core.dry_run_json(request.task_command_json))

    def dispatch_handler(request):
        return binding.response_factory(core.dispatch_json(request.task_command_json))

    rospy.Service(binding.dry_run_service_name, binding.service_type, dry_run_handler)
    rospy.Service(binding.dispatch_service_name, binding.service_type, dispatch_handler)
