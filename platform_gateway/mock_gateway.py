from __future__ import annotations

from typing import Any, Dict, List, Optional

from task_planning.contracts import CapabilityRegistry, CommandAck, TaskCommand, validate_task_command


class MockPlatformGateway:
    """Simulated gateway boundary; never publishes raw ROS topics."""

    def __init__(self, registry: Optional[CapabilityRegistry] = None) -> None:
        self.registry = registry or CapabilityRegistry.scout_and_confirm_default()
        self.dispatch_log: List[Dict[str, Any]] = []

    def dispatch(self, command: TaskCommand) -> CommandAck:
        errors = validate_task_command(command, self.registry)
        accepted = not errors
        ack = (
            CommandAck.accepted(command.mission_id, command.task_id, command.platform_id)
            if accepted
            else CommandAck.rejected(command.mission_id, command.task_id, command.platform_id, errors[0])
        )
        self.dispatch_log.append({
            "mission_id": command.mission_id,
            "task_id": command.task_id,
            "platform_id": command.platform_id,
            "capability": command.capability,
            "accepted": accepted,
            "reason": ack.reason,
            "publish_attempted": False,
        })
        return ack
