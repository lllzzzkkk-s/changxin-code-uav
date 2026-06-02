from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from task_planning.config import EnvironmentProfile
from task_planning.contracts import CapabilityRegistry, CommandAck, TaskCommand, validate_task_command


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class Ros1GatewayConfig:
    ros_master_uri: str
    ros_ip: str
    dispatch_service_template: str = "/fleet/{platform_id}/gateway/dispatch"
    dry_run_service_template: str = "/fleet/{platform_id}/gateway/dry_run"
    use_dry_run_service: bool = True
    require_operator_approval: bool = True

    @classmethod
    def from_profile(cls, profile: EnvironmentProfile) -> "Ros1GatewayConfig":
        return cls(
            ros_master_uri=profile.ros_master_uri,
            ros_ip=profile.ros_ip,
            dispatch_service_template=profile.ros_gateway_dispatch_service_template,
            dry_run_service_template=profile.ros_gateway_dry_run_service_template,
            use_dry_run_service=profile.hardware_approval_required,
            require_operator_approval=profile.hardware_approval_required,
        )


class Ros1ServiceGateway:
    """Capability-level ROS1 gateway adapter.

    This adapter calls a platform gateway service with a validated TaskCommand
    JSON payload. It never publishes raw ROS topics from the center.
    """

    def __init__(
        self,
        config: Ros1GatewayConfig,
        *,
        registry: Optional[CapabilityRegistry] = None,
        command_runner: Optional[Callable[[Sequence[str], Mapping[str, str]], CommandResult]] = None,
        operator_approved: bool = False,
    ) -> None:
        self.config = config
        self.registry = registry or CapabilityRegistry.scout_and_confirm_default()
        self.command_runner = command_runner or _run_command
        self.operator_approved = operator_approved
        self.dispatch_log: list[Dict[str, Any]] = []

    @classmethod
    def from_profile(
        cls,
        profile: EnvironmentProfile,
        *,
        registry: Optional[CapabilityRegistry] = None,
    ) -> "Ros1ServiceGateway":
        return cls(Ros1GatewayConfig.from_profile(profile), registry=registry)

    def dispatch(self, command: TaskCommand) -> CommandAck:
        errors = validate_task_command(command, self.registry)
        if errors:
            ack = CommandAck.rejected(command.mission_id, command.task_id, command.platform_id, errors[0])
            self._log(command, ack, service="", rosservice_called=False)
            return ack
        if self.config.require_operator_approval and not self.operator_approved:
            ack = CommandAck.rejected(
                command.mission_id,
                command.task_id,
                command.platform_id,
                "operator approval is required before ROS1 gateway dispatch",
            )
            self._log(command, ack, service=self._service_for(command), rosservice_called=False)
            return ack

        service = self._service_for(command)
        result = self.command_runner(self._rosservice_call(service, command), self._ros_env())
        ack = self._ack_from_result(command, result)
        self._log(command, ack, service=service, rosservice_called=True, returncode=result.returncode)
        return ack

    def _service_for(self, command: TaskCommand) -> str:
        template = self.config.dry_run_service_template if self.config.use_dry_run_service else self.config.dispatch_service_template
        return template.format(platform_id=command.platform_id)

    def _rosservice_call(self, service: str, command: TaskCommand) -> list[str]:
        payload = json.dumps(command.as_dict(), ensure_ascii=False, sort_keys=True)
        return ["rosservice", "call", service, payload]

    def _ros_env(self) -> Dict[str, str]:
        env = dict(os.environ)
        env["ROS_MASTER_URI"] = self.config.ros_master_uri
        env["ROS_IP"] = self.config.ros_ip
        return env

    def _ack_from_result(self, command: TaskCommand, result: CommandResult) -> CommandAck:
        parsed = _try_parse_json(result.stdout)
        if parsed:
            accepted = bool(parsed.get("accepted", result.returncode == 0))
            reason = str(parsed.get("reason", result.stderr if result.returncode else ""))
            if accepted:
                return CommandAck.accepted(command.mission_id, command.task_id, command.platform_id)
            return CommandAck.rejected(command.mission_id, command.task_id, command.platform_id, reason or "ros1_gateway_rejected")
        if result.returncode == 0:
            return CommandAck.accepted(command.mission_id, command.task_id, command.platform_id)
        return CommandAck.rejected(
            command.mission_id,
            command.task_id,
            command.platform_id,
            result.stderr or result.stdout or "rosservice call failed",
        )

    def _log(
        self,
        command: TaskCommand,
        ack: CommandAck,
        *,
        service: str,
        rosservice_called: bool,
        returncode: Optional[int] = None,
    ) -> None:
        self.dispatch_log.append({
            "mission_id": command.mission_id,
            "task_id": command.task_id,
            "platform_id": command.platform_id,
            "capability": command.capability,
            "accepted": ack.accepted,
            "reason": ack.reason,
            "service": service,
            "rosservice_called": rosservice_called,
            "returncode": returncode,
            "publish_attempted": False,
        })


def _run_command(args: Sequence[str], env: Mapping[str, str]) -> CommandResult:
    completed = subprocess.run(
        list(args),
        env=dict(env),
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _try_parse_json(text: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
