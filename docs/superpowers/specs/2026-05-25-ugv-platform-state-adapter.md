# UGV PlatformState Adapter

Date: 2026-05-25

Scope: UGV-1 OS-mate runtime evidence and first fleet-gateway state contract.

## Confirmed Runtime Chain

UGV-1 runs ROS1 Noetic with one local ROS master. The confirmed task and control chain is:

```text
move_base
  -> /cmd_vel
  -> velocity_smoother
  -> /smoother_cmd_vel
  -> yhs_can_control_node
  -> can0
```

The gateway must treat `move_base` as the primary task interface. Direct velocity topics are reserved for local safety stop behavior and diagnostics, not center-level mission commands.

## Confirmed Topics

| Purpose | Topic | Type | Use |
|---|---|---|---|
| Navigation goal | `/move_base_simple/goal` | `geometry_msgs/PoseStamped` | Simple map-frame goal entry |
| Navigation action | `/move_base/goal` | `move_base_msgs/MoveBaseActionGoal` | Full action interface |
| Navigation cancel | `/move_base/cancel` | `actionlib_msgs/GoalID` | Cancel current goal |
| Navigation status | `/move_base/status` | `actionlib_msgs/GoalStatusArray` | Task state |
| Raw planner velocity | `/cmd_vel` | `geometry_msgs/Twist` | Input to velocity smoother |
| Smoothed velocity | `/smoother_cmd_vel` | `geometry_msgs/Twist` | Input to chassis driver |
| Odometry topic | `/odom` | `nav_msgs/Odometry` | Wheel/driver odometry topic |
| Chassis feedback | `/chassis_info_fb` | `yhs_msgs/FwChassisInfoFb` | Safety, battery, gear, feedback velocities |
| IMU | `/imu_data` | `sensor_msgs/Imu` | IMU state |

In the confirmed 3D/NDT launch, `/yhs_can_control/tfUsed` is false. `odom -> base_link` TF is not present. Use `map -> base_link` for gateway pose.

## PlatformState Mapping

```yaml
schema: PlatformState.v1
platform_type: ugv
pose:
  source: tf
  frame_id: map
  transform: map->base_link
velocity:
  source: /odom.twist.twist
safety:
  is_unlocked: /chassis_info_fb.io_fb.io_fb_unlock
  estop_active: /chassis_info_fb.io_fb.io_fb_estop
  charge_state: /chassis_info_fb.io_fb.io_fb_charge_state
battery:
  percentage: /chassis_info_fb.bms_flag_fb.bms_flag_fb_soc / 100.0
  voltage: /chassis_info_fb.bms_fb.bms_fb_voltage
  current: /chassis_info_fb.bms_fb.bms_fb_current
local_navigation:
  move_base_status: /move_base/status.status_list
  cmd_vel: /cmd_vel
  smoother_cmd_vel: /smoother_cmd_vel
chassis:
  gear: /chassis_info_fb.ctrl_fb.ctrl_fb_gear
  linear_feedback: /chassis_info_fb.ctrl_fb.ctrl_fb_linear
  angular_feedback: /chassis_info_fb.ctrl_fb.ctrl_fb_angular
```

## Safety Gate Defaults

The gateway must reject motion commands unless all are true:

- ROS master is reachable.
- `move_base` is present.
- `map -> base_link` TF is available.
- `estop_active` is false.
- Battery percentage is above the configured threshold.
- Operator has explicitly put the platform into an allowed autonomous state.
- The task capability is allowlisted.

The gateway should not unlock the chassis in phase 1. Unlock remains an operator-controlled step until the full hardware procedure is documented.

## First Capabilities

Allow in phase 1:

- `report_state`
- `cancel_navigation`
- `navigate_to_pose` after safety gate passes
- `dock` only when `recharge_node` is launched and charger geometry is verified
- `undock` only when `recharge_node` is launched and front path is clear

Do not allow:

- Arbitrary `/smoother_cmd_vel` commands from the center.
- Arbitrary `/cmd_vel` streaming from the center.
- Arbitrary ROS topic publish relays.
- Gateway-side chassis unlock.

## Evidence

- UGV-E004: filtered UGV-1 source snapshot.
- UGV-E005: C0 runtime graph and TF evidence.
- UGV-E006: C1 cancel/status safety evidence.
