from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Tuple

from uav.llm_control.schemas.models import (
    SUPPORTED_LOCALIZATION_SOURCES,
    CommandResult,
    StateSnapshot,
    ToolContract,
)
from uav.llm_control.tools.catalog import tool_by_name


MAX_RELATIVE_DISTANCE_M = 5.0
MIN_TARGET_Z_M = 0.5
MAX_TARGET_Z_M = 3.0


def process_command(envelope: Mapping[str, Any], snapshot: StateSnapshot, *, now: float) -> CommandResult:
    meta = dict(envelope.get("meta") or {})
    intent = dict(envelope.get("intent") or {})
    arguments = dict(envelope.get("arguments") or {})
    name = intent.get("name")
    trace = [{"stage": "input", "intent": name, "arguments": arguments}]

    if not isinstance(name, str) or not name:
        return _failure(meta, intent, arguments, "validation_failure", "intent.name is required", trace)

    tool = tool_by_name(name)
    if tool is None:
        return _failure(meta, intent, arguments, "validation_failure", f"unsupported intent: {name}", trace)

    trace.append({"stage": "tool_contract", "tool": tool.as_dict()})

    if name.startswith("query_"):
        return _process_query(tool, meta, intent, arguments, snapshot, now, trace)
    if name == "move_relative":
        return _process_move_relative(tool, meta, intent, arguments, snapshot, now, trace)
    if name in {"takeoff", "land", "return_home"}:
        return _process_action(tool, meta, intent, arguments, snapshot, now, trace)

    return _failure(meta, intent, arguments, "validation_failure", f"unhandled intent: {name}", trace)


def _process_query(
    tool: ToolContract,
    meta: Dict[str, Any],
    intent: Dict[str, Any],
    arguments: Dict[str, Any],
    snapshot: StateSnapshot,
    now: float,
    trace: list,
) -> CommandResult:
    field_by_intent = {
        "query_battery": "battery",
        "query_fcu_state": "fcu",
        "query_localization": "localization",
        "query_rc_state": "rc",
    }
    field = field_by_intent[tool.name]
    stale = snapshot.stale_fields(now, [field])
    if stale:
        return _failure(meta, intent, arguments, "precheck_failure", f"{field}_stale", trace)

    data = getattr(snapshot, field).as_dict()
    if tool.name == "query_battery":
        data = {"voltage": data["voltage"], "percentage": data["percentage"]}
    trace.append({"stage": "query", "field": field, "data": data})
    return CommandResult(
        status="succeeded",
        meta=meta,
        intent=intent,
        arguments=arguments,
        data=data,
        safety={"risk_class": tool.risk_class, "confirmation_policy": tool.confirmation_policy, "reasons": []},
        execution={"dry_run": True, "publish_attempted": False, "ros_payload": None},
        message="query succeeded",
        trace=trace,
    )


def _process_action(
    tool: ToolContract,
    meta: Dict[str, Any],
    intent: Dict[str, Any],
    arguments: Dict[str, Any],
    snapshot: StateSnapshot,
    now: float,
    trace: list,
) -> CommandResult:
    precheck = _check_action_preconditions(snapshot, now, require_localization=tool.name == "return_home")
    if precheck:
        return _failure(meta, intent, arguments, "precheck_failure", precheck, trace)

    if tool.name == "takeoff":
        payload = _takeoff_land_payload(1)
    elif tool.name == "land":
        payload = _takeoff_land_payload(2)
    else:
        payload = {
            "topic": "/back_trigger",
            "message_type": "geometry_msgs/PoseStamped",
            "message": _pose_stamped(snapshot.localization.position, frame_id="world"),
        }

    return _needs_confirmation(tool, meta, intent, arguments, {}, payload, trace)


def _process_move_relative(
    tool: ToolContract,
    meta: Dict[str, Any],
    intent: Dict[str, Any],
    arguments: Dict[str, Any],
    snapshot: StateSnapshot,
    now: float,
    trace: list,
) -> CommandResult:
    validation_error = _validate_move_relative_args(arguments)
    if validation_error:
        return _failure(meta, intent, arguments, "validation_failure", validation_error, trace)

    precheck = _check_action_preconditions(snapshot, now, require_localization=True)
    if precheck:
        return _failure(meta, intent, arguments, "precheck_failure", precheck, trace)

    offset = _relative_offset(
        frame=arguments["frame"],
        direction=arguments["direction"],
        distance_m=float(arguments["distance_m"]),
        yaw=float(snapshot.localization.yaw),
    )
    current = snapshot.localization.position
    target = {
        "x": _clean_float(current["x"] + offset[0]),
        "y": _clean_float(current["y"] + offset[1]),
        "z": _clean_float(current["z"] + offset[2]),
    }
    resolution = {
        "source_position": dict(current),
        "target_position": target,
        "frame": arguments["frame"],
        "direction": arguments["direction"],
        "distance_m": float(arguments["distance_m"]),
        "localization_source": snapshot.localization.source,
    }
    trace.append({"stage": "resolution", **resolution})

    if target["z"] < MIN_TARGET_Z_M or target["z"] > MAX_TARGET_Z_M:
        return CommandResult(
            status="safety_rejected",
            meta=meta,
            intent=intent,
            arguments=arguments,
            resolution=resolution,
            safety={
                "risk_class": tool.risk_class,
                "confirmation_policy": tool.confirmation_policy,
                "reasons": ["target_z_out_of_bounds"],
                "limits": {"min_z_m": MIN_TARGET_Z_M, "max_z_m": MAX_TARGET_Z_M},
            },
            execution={"dry_run": True, "publish_attempted": False, "ros_payload": None},
            failure_code="safety_failure",
            message="target_z_out_of_bounds",
            trace=trace,
        )

    payload = {
        "topic": "/goal",
        "message_type": "geometry_msgs/PoseStamped",
        "message": _pose_stamped(target, frame_id="world"),
    }
    return _needs_confirmation(tool, meta, intent, arguments, resolution, payload, trace)


def _validate_move_relative_args(arguments: Mapping[str, Any]) -> Optional[str]:
    frame = arguments.get("frame")
    if frame not in {"body", "world"}:
        return "frame must be one of: body, world"
    direction = arguments.get("direction")
    if direction not in {"forward", "back", "backward", "left", "right", "up", "down"}:
        return "direction must be one of: forward, back, backward, left, right, up, down"
    try:
        distance = float(arguments.get("distance_m"))
    except (TypeError, ValueError):
        return "distance_m must be numeric"
    if distance <= 0 or distance > MAX_RELATIVE_DISTANCE_M:
        return f"distance_m must be > 0 and <= {MAX_RELATIVE_DISTANCE_M}"
    return None


def _check_action_preconditions(snapshot: StateSnapshot, now: float, *, require_localization: bool) -> Optional[str]:
    fields = ["fcu", "battery", "rc"]
    if require_localization:
        fields.append("localization")
    stale = snapshot.stale_fields(now, fields)
    if stale:
        return f"{stale[0]}_stale"
    if not snapshot.fcu.connected:
        return "fcu_not_connected"
    if len(snapshot.rc.channels) < 8:
        return "rc_channels_missing"
    if require_localization and snapshot.localization.source not in SUPPORTED_LOCALIZATION_SOURCES:
        return "unsupported_localization_source"
    return None


def _relative_offset(frame: str, direction: str, distance_m: float, yaw: float) -> Tuple[float, float, float]:
    direction = "back" if direction == "backward" else direction
    if direction == "up":
        return (0.0, 0.0, distance_m)
    if direction == "down":
        return (0.0, 0.0, -distance_m)

    world_vectors = {
        "forward": (1.0, 0.0),
        "back": (-1.0, 0.0),
        "left": (0.0, -1.0),
        "right": (0.0, 1.0),
    }
    if frame == "world":
        dx, dy = world_vectors[direction]
        return (dx * distance_m, dy * distance_m, 0.0)

    forward = (math.cos(yaw), math.sin(yaw))
    right = (math.sin(yaw), -math.cos(yaw))
    body_vectors = {
        "forward": forward,
        "back": (-forward[0], -forward[1]),
        "right": right,
        "left": (-right[0], -right[1]),
    }
    dx, dy = body_vectors[direction]
    return (dx * distance_m, dy * distance_m, 0.0)


def _pose_stamped(position: Mapping[str, float], *, frame_id: str) -> Dict[str, Any]:
    return {
        "header": {"frame_id": frame_id},
        "pose": {
            "position": {
                "x": _clean_float(position["x"]),
                "y": _clean_float(position["y"]),
                "z": _clean_float(position["z"]),
            },
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        },
    }


def _takeoff_land_payload(command: int) -> Dict[str, Any]:
    return {
        "topic": "/px4ctrl/takeoff_land",
        "message_type": "quadrotor_msgs/TakeoffLand",
        "message": {"takeoff_land_cmd": command},
    }


def _needs_confirmation(
    tool: ToolContract,
    meta: Dict[str, Any],
    intent: Dict[str, Any],
    arguments: Dict[str, Any],
    resolution: Dict[str, Any],
    payload: Dict[str, Any],
    trace: list,
) -> CommandResult:
    trace.append({"stage": "execution_plan", "dry_run": True, "ros_payload": payload})
    return CommandResult(
        status="needs_confirmation",
        meta=meta,
        intent=intent,
        arguments=arguments,
        resolution=resolution,
        safety={
            "risk_class": tool.risk_class,
            "confirmation_policy": tool.confirmation_policy,
            "reasons": ["confirmation_required"],
        },
        execution={"dry_run": True, "publish_attempted": False, "ros_payload": payload},
        message="high-risk command requires explicit confirmation; no ROS publish attempted",
        trace=trace,
    )


def _failure(
    meta: Dict[str, Any],
    intent: Dict[str, Any],
    arguments: Dict[str, Any],
    failure_code: str,
    message: str,
    trace: list,
) -> CommandResult:
    trace.append({"stage": "failure", "failure_code": failure_code, "message": message})
    return CommandResult(
        status="failed",
        meta=meta,
        intent=intent,
        arguments=arguments,
        safety={"risk_class": "unknown", "confirmation_policy": "none", "reasons": []},
        execution={"dry_run": True, "publish_attempted": False, "ros_payload": None},
        failure_code=failure_code,
        message=message,
        trace=trace,
    )


def _clean_float(value: float) -> float:
    if abs(value) < 1e-12:
        return 0.0
    return round(float(value), 10)
