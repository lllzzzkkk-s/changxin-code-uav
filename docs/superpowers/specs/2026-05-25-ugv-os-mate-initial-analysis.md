# UGV OS-mate Initial Analysis

Date: 2026-05-25

Source: `OS-mate 机器人开发平台 用户使用手册 V1.0.2`, copied to `ugv/02-pdf-source/`.

## Architecture Impact

The UGV should be modeled as a ROS1 Navigation platform, not as a MAVROS/PX4-like platform. The platform gateway should prefer task-level navigation commands over direct velocity control.

Recommended control chain:

```text
center PDDL
  -> task-level BT
  -> platform gateway
  -> UGV local ROS1 master
  -> move_base action
  -> local planner
  -> /smoother_cmd_vel
  -> CAN chassis driver
```

## High-Value Interfaces

- `move_base` action: primary task-level navigation control.
- `/move_base_simple/goal`: simple pose goal entry.
- `/smoother_cmd_vel`: low-level velocity command, high-risk.
- `/odom`: odometry state.
- `/imu_data`: IMU state.
- `/tmlidar_points`: 3D lidar point cloud.
- `/chassis_info_fb`: chassis feedback, message type needs code validation.
- `/recharge`, `/dis_recharge`: optional docking services, service types need code validation.

## Next Investigation

Run `ugv/01-scripts/probe_ugv_readonly.sh` on the vehicle, then analyze:

- workspace package list
- launch files
- `yhs_nav_param.yaml`
- topic/service runtime graph
- `move_base` action availability
- Rviz multipoint plugin implementation
- chassis feedback message definition
- recharge service definition

