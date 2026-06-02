from __future__ import annotations

from task_planning.contracts.models import (
    CommandAck,
    FailureReport,
    MissionBlackboard,
    PlatformState,
    TaskCommand,
    TaskSchema,
)


def task_schema_example() -> TaskSchema:
    return TaskSchema.from_intent(
        mission_id="mission_001",
        intent="搜索 A 区并派无人车确认目标",
        area_id="area_A",
        target_id="target_01",
    )


def platform_state_examples() -> list:
    return [
        PlatformState.example("uav_0", "uav", ["inspect_area", "relay_or_overwatch", "hold_position"]),
        PlatformState.example("ugv_0", "ugv", ["move_to_region", "confirm_target", "hold_position"]),
    ]


def task_command_example() -> TaskCommand:
    return TaskCommand(
        mission_id="mission_001",
        task_id="task_001",
        platform_id="uav_0",
        capability="inspect_area",
        parameters={"area_id": "area_A", "max_duration_s": 120},
    )


def command_ack_example() -> CommandAck:
    return CommandAck.accepted("mission_001", "task_001", "uav_0")


def failure_report_example() -> FailureReport:
    return FailureReport(
        mission_id="mission_001",
        task_id="task_002",
        platform_id="ugv_0",
        failure_type="path_blocked",
        recoverable=True,
        reason="local_planner_no_path",
        recommended_actions=["request_uav_rescan"],
    )


def blackboard_example() -> MissionBlackboard:
    schema = task_schema_example()
    return MissionBlackboard(
        mission_id=schema.mission_request.mission_id,
        open_tasks=list(schema.mission_request.required_capabilities),
        targets={"target_01": {"status": "unknown", "position": None}},
    )
