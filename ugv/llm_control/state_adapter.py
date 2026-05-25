from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional


def build_platform_state(
    runtime: Mapping[str, Any],
    *,
    platform_id: str,
    min_battery_percentage: float = 0.30,
    max_tf_age_s: float = 1.0,
) -> Dict[str, Any]:
    captured_at = _float(runtime.get("captured_at"), 0.0)
    map_tf = runtime.get("map_to_base_link")
    pose = _pose_from_map_tf(map_tf if isinstance(map_tf, Mapping) else None)
    localization = _localization_state(
        map_tf if isinstance(map_tf, Mapping) else None,
        captured_at=captured_at,
        max_tf_age_s=max_tf_age_s,
    )
    chassis_info = _mapping(runtime.get("chassis_info_fb"))
    io_fb = _mapping(chassis_info.get("io_fb"))
    ctrl_fb = _mapping(chassis_info.get("ctrl_fb"))
    bms_flag_fb = _mapping(chassis_info.get("bms_flag_fb"))
    bms_fb = _mapping(chassis_info.get("bms_fb"))
    battery_percentage = _float(bms_flag_fb.get("bms_flag_fb_soc"), 0.0) / 100.0

    safety = _safety_state(
        runtime=runtime,
        localization_ok=bool(localization["ok"]),
        is_unlocked=_bool(io_fb.get("io_fb_unlock")),
        estop_active=_bool(io_fb.get("io_fb_estop")),
        charge_state=_bool(io_fb.get("io_fb_charge_state")),
        battery_percentage=battery_percentage,
        min_battery_percentage=min_battery_percentage,
    )

    return {
        "schema": "PlatformState.v1",
        "platform_id": platform_id,
        "platform_type": "ugv",
        "captured_at": captured_at,
        "pose": pose,
        "velocity": _velocity_from_odom(_mapping(runtime.get("odom"))),
        "localization": localization,
        "safety": safety,
        "battery": {
            "percentage": battery_percentage,
            "voltage": _float(bms_fb.get("bms_fb_voltage"), 0.0),
            "current": _float(bms_fb.get("bms_fb_current"), 0.0),
            "remaining_capacity": _float(bms_fb.get("bms_fb_remaining_capacity"), 0.0),
            "charging": _bool(bms_flag_fb.get("bms_flag_fb_charge_flag")),
        },
        "local_navigation": {
            "move_base_present": _move_base_present(runtime),
            "task_state": _task_state(_mapping(runtime.get("move_base_status"))),
            "move_base_status": list(_mapping(runtime.get("move_base_status")).get("status_list") or []),
            "cmd_vel": runtime.get("cmd_vel"),
            "smoother_cmd_vel": runtime.get("smoother_cmd_vel"),
        },
        "chassis": {
            "gear": int(_float(ctrl_fb.get("ctrl_fb_gear"), 0.0)),
            "linear_feedback": _float(ctrl_fb.get("ctrl_fb_linear"), 0.0),
            "angular_feedback": _float(ctrl_fb.get("ctrl_fb_angular"), 0.0),
            "slipangle_feedback": _float(ctrl_fb.get("ctrl_fb_slipangle"), 0.0),
        },
        "diagnostics": {
            "ignored_tf_failures": _ignored_tf_failures(runtime),
            "ros_master_reachable": _bool(runtime.get("ros_master_reachable")),
            "nodes": list(runtime.get("nodes") or []),
        },
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    return bool(value)


def _pose_from_map_tf(map_tf: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if map_tf is None:
        return {
            "source": None,
            "frame_id": None,
            "child_frame_id": "base_link",
            "transform": None,
            "x": None,
            "y": None,
            "z": None,
            "yaw": None,
        }

    translation = _mapping(map_tf.get("translation"))
    rotation = _mapping(map_tf.get("rotation"))
    return {
        "source": "tf",
        "frame_id": "map",
        "child_frame_id": "base_link",
        "transform": "map->base_link",
        "x": _float(translation.get("x"), 0.0),
        "y": _float(translation.get("y"), 0.0),
        "z": _float(translation.get("z"), 0.0),
        "yaw": _float(rotation.get("yaw"), 0.0),
    }


def _velocity_from_odom(odom: Mapping[str, Any]) -> Dict[str, Any]:
    twist = _mapping(odom.get("twist"))
    linear = _mapping(twist.get("linear"))
    angular = _mapping(twist.get("angular"))
    return {
        "source": "/odom.twist.twist",
        "linear": {
            "x": _float(linear.get("x"), 0.0),
            "y": _float(linear.get("y"), 0.0),
            "z": _float(linear.get("z"), 0.0),
        },
        "angular": {
            "x": _float(angular.get("x"), 0.0),
            "y": _float(angular.get("y"), 0.0),
            "z": _float(angular.get("z"), 0.0),
        },
    }


def _localization_state(
    map_tf: Optional[Mapping[str, Any]],
    *,
    captured_at: float,
    max_tf_age_s: float,
) -> Dict[str, Any]:
    if map_tf is None:
        return {
            "source": "ndt",
            "ok": False,
            "frame_id": "map",
            "transform": "map->base_link",
            "reason": "missing_map_to_base_link_tf",
        }

    updated_at = _float(map_tf.get("updated_at"), captured_at)
    age_s = max(0.0, captured_at - updated_at)
    if age_s > max_tf_age_s:
        return {
            "source": "ndt",
            "ok": False,
            "frame_id": "map",
            "transform": "map->base_link",
            "age_s": age_s,
            "reason": "stale_map_to_base_link_tf",
        }
    return {
        "source": "ndt",
        "ok": True,
        "frame_id": "map",
        "transform": "map->base_link",
        "age_s": age_s,
        "reason": None,
    }


def _safety_state(
    *,
    runtime: Mapping[str, Any],
    localization_ok: bool,
    is_unlocked: bool,
    estop_active: bool,
    charge_state: bool,
    battery_percentage: float,
    min_battery_percentage: float,
) -> Dict[str, Any]:
    reasons: List[str] = []
    if not _bool(runtime.get("ros_master_reachable")):
        reasons.append("ros_master_unreachable")
    if not _move_base_present(runtime):
        reasons.append("move_base_missing")
    if not localization_ok:
        reasons.append("localization_unavailable")
    if estop_active:
        reasons.append("estop_active")
    if not is_unlocked:
        reasons.append("chassis_locked")
    if battery_percentage < min_battery_percentage:
        reasons.append("battery_below_threshold")

    return {
        "is_unlocked": is_unlocked,
        "estop_active": estop_active,
        "charge_state": charge_state,
        "motion_ready": not reasons,
        "reasons": reasons,
        "gateway_may_unlock": False,
        "min_battery_percentage": min_battery_percentage,
    }


def _move_base_present(runtime: Mapping[str, Any]) -> bool:
    return "/move_base" in set(runtime.get("nodes") or [])


def _task_state(move_base_status: Mapping[str, Any]) -> str:
    statuses = list(move_base_status.get("status_list") or [])
    if not statuses:
        return "idle"

    latest = statuses[-1]
    if isinstance(latest, Mapping):
        status_code = latest.get("status")
    else:
        status_code = latest

    if status_code in (1, "ACTIVE"):
        return "running"
    if status_code in (2, "PREEMPTED", 3, "SUCCEEDED"):
        return "completed"
    if status_code in (4, "ABORTED", 5, "REJECTED", 9, "LOST"):
        return "failed"
    return "unknown"


def _ignored_tf_failures(runtime: Mapping[str, Any]) -> List[str]:
    failure = runtime.get("odom_to_base_link_error")
    if failure:
        return [str(failure)]
    return []
