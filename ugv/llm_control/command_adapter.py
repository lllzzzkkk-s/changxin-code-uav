from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional


def build_task_command_dry_run(command: Mapping[str, Any], platform_state: Mapping[str, Any]) -> Dict[str, Any]:
    meta = dict(command.get("meta") or {})
    intent = dict(command.get("intent") or {})
    arguments = dict(command.get("arguments") or {})
    intent_name = intent.get("name")

    if not isinstance(intent_name, str) or not intent_name:
        return _failure(meta, intent, arguments, "intent.name is required")

    if intent_name == "report_state":
        return _report(
            status="succeeded",
            meta=meta,
            intent=intent,
            arguments=arguments,
            safety=_safety("read_only", "none", []),
            ros_instruction=None,
            data={"platform_state": platform_state},
        )

    if intent_name == "cancel_navigation":
        reasons = _local_navigation_reasons(platform_state)
        if reasons:
            return _safety_rejected(meta, intent, arguments, reasons)
        return _report(
            status="succeeded",
            meta=meta,
            intent=intent,
            arguments=arguments,
            safety=_safety("safety_stop", "none", []),
            ros_instruction={
                "kind": "ros_topic",
                "topic": "/move_base/cancel",
                "message_type": "actionlib_msgs/GoalID",
                "message": {},
            },
        )

    if intent_name == "navigate_to_pose":
        validation_error = _validate_navigate_to_pose(arguments)
        if validation_error:
            return _failure(meta, intent, arguments, validation_error)

        if not _mapping(platform_state.get("safety")).get("motion_ready"):
            reasons = list(_mapping(platform_state.get("safety")).get("reasons") or [])
            return _safety_rejected(meta, intent, arguments, reasons)

        return _report(
            status="needs_confirmation",
            meta=meta,
            intent=intent,
            arguments=arguments,
            safety=_safety("motion", "always", []),
            ros_instruction={
                "kind": "ros_action",
                "action_server": "/move_base",
                "action_type": "move_base_msgs/MoveBaseAction",
                "goal": {
                    "target_pose": {
                        "header": {"frame_id": "map"},
                        "pose": {
                            "position": {
                                "x": float(arguments["x"]),
                                "y": float(arguments["y"]),
                                "z": 0.0,
                            },
                            "orientation": _yaw_to_quaternion(float(arguments.get("yaw", 0.0))),
                        },
                    }
                },
            },
        )

    return _failure(meta, intent, arguments, f"unsupported intent: {intent_name}")


def _report(
    *,
    status: str,
    meta: Mapping[str, Any],
    intent: Mapping[str, Any],
    arguments: Mapping[str, Any],
    safety: Mapping[str, Any],
    ros_instruction: Optional[Mapping[str, Any]],
    data: Optional[Mapping[str, Any]] = None,
    failure_code: Optional[str] = None,
    message: str = "",
) -> Dict[str, Any]:
    return {
        "schema": "TaskCommandDryRun.v1",
        "status": status,
        "meta": dict(meta),
        "intent": dict(intent),
        "arguments": dict(arguments),
        "publish_attempted": False,
        "ros_instruction": dict(ros_instruction) if ros_instruction is not None else None,
        "safety": dict(safety),
        "data": dict(data) if data is not None else None,
        "failure_code": failure_code,
        "message": message,
    }


def _failure(
    meta: Mapping[str, Any],
    intent: Mapping[str, Any],
    arguments: Mapping[str, Any],
    message: str,
) -> Dict[str, Any]:
    return _report(
        status="failed",
        meta=meta,
        intent=intent,
        arguments=arguments,
        safety=_safety("unknown", "none", []),
        ros_instruction=None,
        failure_code="validation_failure",
        message=message,
    )


def _safety_rejected(
    meta: Mapping[str, Any],
    intent: Mapping[str, Any],
    arguments: Mapping[str, Any],
    reasons: Any,
) -> Dict[str, Any]:
    return _report(
        status="safety_rejected",
        meta=meta,
        intent=intent,
        arguments=arguments,
        safety=_safety("motion", "always", list(reasons or [])),
        ros_instruction=None,
        failure_code="safety_failure",
        message=";".join(str(reason) for reason in reasons or []),
    )


def _safety(risk_class: str, confirmation_policy: str, reasons: Any) -> Dict[str, Any]:
    return {
        "risk_class": risk_class,
        "confirmation_policy": confirmation_policy,
        "reasons": list(reasons or []),
    }


def _validate_navigate_to_pose(arguments: Mapping[str, Any]) -> Optional[str]:
    if arguments.get("frame_id") != "map":
        return "frame_id must be map"
    for field_name in ("x", "y"):
        if not _is_number(arguments.get(field_name)):
            return f"{field_name} must be numeric"
    if "yaw" in arguments and not _is_number(arguments.get("yaw")):
        return "yaw must be numeric"
    return None


def _local_navigation_reasons(platform_state: Mapping[str, Any]) -> list:
    reasons = []
    diagnostics = _mapping(platform_state.get("diagnostics"))
    local_navigation = _mapping(platform_state.get("local_navigation"))
    if not diagnostics.get("ros_master_reachable"):
        reasons.append("ros_master_unreachable")
    if not local_navigation.get("move_base_present"):
        reasons.append("move_base_missing")
    return reasons


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _is_number(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _yaw_to_quaternion(yaw: float) -> Dict[str, float]:
    half_yaw = yaw / 2.0
    return {
        "x": 0.0,
        "y": 0.0,
        "z": math.sin(half_yaw),
        "w": math.cos(half_yaw),
    }
