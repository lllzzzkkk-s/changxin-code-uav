from __future__ import annotations

from typing import List

from uav.llm_control.schemas.models import ToolContract


def tool_catalog() -> List[ToolContract]:
    return [
        ToolContract(
            name="query_battery",
            description="Read the latest MAVROS battery snapshot.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"voltage": "float", "percentage": "float"},
            risk_class="read_only",
            preconditions=["battery_fresh"],
            confirmation_policy="none",
            executor_binding={"kind": "state_query", "source": "/mavros/battery"},
        ),
        ToolContract(
            name="query_fcu_state",
            description="Read the latest MAVROS FCU connection, arming, and mode state.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"connected": "bool", "armed": "bool", "mode": "string"},
            risk_class="read_only",
            preconditions=["fcu_fresh"],
            confirmation_policy="none",
            executor_binding={"kind": "state_query", "source": "/mavros/state"},
        ),
        ToolContract(
            name="query_localization",
            description="Read the selected LIO/VIO localization snapshot.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"source": "string", "position": "xyz", "velocity": "xyz", "yaw": "float"},
            risk_class="read_only",
            preconditions=["localization_fresh"],
            confirmation_policy="none",
            executor_binding={"kind": "state_query", "source": ["/ekf/ekf_odom", "/vins/imu_propagate"]},
        ),
        ToolContract(
            name="query_rc_state",
            description="Read the latest RC channel snapshot.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"channels": "list[int]"},
            risk_class="read_only",
            preconditions=["rc_fresh"],
            confirmation_policy="none",
            executor_binding={"kind": "state_query", "source": "/mavros/rc/in"},
        ),
        ToolContract(
            name="takeoff",
            description="Prepare a dry-run takeoff command for px4ctrl.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"topic": "/px4ctrl/takeoff_land", "takeoff_land_cmd": 1},
            risk_class="high",
            preconditions=["fcu_fresh", "rc_fresh", "fcu_connected"],
            confirmation_policy="always",
            executor_binding={"kind": "ros_topic", "topic": "/px4ctrl/takeoff_land"},
        ),
        ToolContract(
            name="land",
            description="Prepare a dry-run land command for px4ctrl.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"topic": "/px4ctrl/takeoff_land", "takeoff_land_cmd": 2},
            risk_class="high",
            preconditions=["fcu_fresh", "rc_fresh", "fcu_connected"],
            confirmation_policy="always",
            executor_binding={"kind": "ros_topic", "topic": "/px4ctrl/takeoff_land"},
        ),
        ToolContract(
            name="return_home",
            description="Prepare a dry-run return/back trigger command.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"topic": "/back_trigger", "message_type": "geometry_msgs/PoseStamped"},
            risk_class="high",
            preconditions=["fcu_fresh", "rc_fresh", "localization_fresh", "fcu_connected"],
            confirmation_policy="always",
            executor_binding={"kind": "ros_topic", "topic": "/back_trigger"},
        ),
        ToolContract(
            name="move_relative",
            description="Compile a relative movement request into a dry-run single planning goal.",
            input_schema={
                "type": "object",
                "required": ["frame", "direction", "distance_m"],
                "properties": {
                    "frame": {"enum": ["body", "world"]},
                    "direction": {"enum": ["forward", "back", "backward", "left", "right", "up", "down"]},
                    "distance_m": {"type": "number", "exclusiveMinimum": 0, "maximum": 5.0},
                },
                "additionalProperties": False,
            },
            output_schema={"topic": "/goal", "message_type": "geometry_msgs/PoseStamped"},
            risk_class="high",
            preconditions=[
                "fcu_fresh",
                "battery_fresh",
                "rc_fresh",
                "localization_fresh",
                "fcu_connected",
                "localization_source_supported",
            ],
            confirmation_policy="always",
            executor_binding={"kind": "ros_topic", "topic": "/goal"},
        ),
    ]


def tool_by_name(name: str) -> ToolContract | None:
    for tool in tool_catalog():
        if tool.name == name:
            return tool
    return None
