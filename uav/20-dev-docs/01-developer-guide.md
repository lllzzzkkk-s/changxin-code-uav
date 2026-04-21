# 非凸α开发者文档

## 1. 机器现状总览

- 当前资料来源由实机快照、机上源码快照、PDF、wiki 和本地知识库组成。
- 事实优先级按“实机快照 > 机上源码快照 > 本地知识库 > PDF > wiki”执行。
- 当前主链是单机 LIO / VIO + Diff-planner + px4ctrl + mavros + multipoint。
- D435 + VINS 是当前视觉定位主链假设，不以 Elastic 为默认链路。
- Elastic 不属于当前实机默认部署链路。
- 当前必须区分“实机已部署”“源码存在但非主链”“产品线文档提到但未落机”三种状态。

### 1.1 当前机器画像

- 机载电脑：Jetson Orin NX 16GB。
- 系统：Ubuntu 20.04.6。
- ROS：Noetic。
- 视觉主硬件：Intel RealSense D435。
- 雷达主硬件：Livox MID360。
- 主工作空间：Diff-planner。
- 当前主入口脚本：`run_single_lio.sh`、`run_single_vio.sh`、`takeoff.sh`、`pub_trigger.sh`、`back.sh`、`land.sh`。

### 1.2 与产品线文档的关键偏差

- wiki / PDF 会展示目标跟踪、集群、YOLO 等扩展能力。
- 当前实机文档主路径只写 LIO、VIO、单机规划、多点任务、自动起降、状态观测和接管安全。
- Elastic、FUEL、Formation、YOLO 只能出现在部署矩阵和扩展附录中。

## 2. 当前已部署功能清单

### 2.1 当前主路径功能

- 单机 LIO：通过 `run_single_lio.sh` 拉起 `mavros + faster_lio + ekf + diff_planner + px4ctrl + multipoint`。
- 单机 VIO：通过 `run_single_vio.sh` 拉起 `mavros + realsense2_camera + vins + diff_planner + px4ctrl + multipoint`。
- 单机规划：由 `diff_planner` 输出轨迹，`traj_server` 送入 `/setpoints_cmd`。
- 多点任务：由 `multipoint` 读取 `points.yaml`，触发方式为脚本或 RC 8 通映射。
- 自动起降：通过 `/px4ctrl/takeoff_land` 的 `takeoff_land_cmd=1/2`。
- 状态观测：依赖 `/mavros/state`、`/mavros/battery`、`/mavros/rc/in`、`/ekf/ekf_odom`、`/vins/imu_propagate` 等接口。

### 2.2 扩展能力边界

- Elastic / 目标跟踪：当前不作为实机默认链路。
- FUEL / 自主探索：当前不作为实机默认链路。
- Formation / 集群：当前不作为实机默认链路。
- YOLO 检测：当前不作为实机默认链路。

## 3. 启动链与运行链

### 3.1 LIO 启动链

`run_single_lio.sh`
-> `roslaunch mavros px4.launch`
-> `rosrun mavros mavcmd long ...`
-> `roslaunch faster_lio mapping_mid360.launch`
-> `roslaunch ekf ekf_lidar.launch`
-> `roslaunch diff_planner run_exp_single_lio.launch`
-> `roslaunch px4ctrl run_ctrl_lio.launch`
-> `roslaunch multipoint multipointplan_exp_lio.launch`
-> `roslaunch diff_planner exp_rviz.launch`

### 3.2 VIO 启动链

`run_single_vio.sh`
-> `roslaunch mavros px4.launch`
-> `rosrun mavros mavcmd long ...`
-> `roslaunch realsense2_camera rs_camera.launch`
-> `roslaunch vins vins_d435.launch`
-> `roslaunch diff_planner run_exp_single_vio.launch`
-> `roslaunch px4ctrl run_ctrl_vio.launch`
-> `roslaunch multipoint multipointplan_exp_vio.launch`
-> `roslaunch diff_planner exp_rviz.launch`

### 3.3 动作触发链

- 起飞：`takeoff.sh` 或 RC 8 通下->中 -> `/px4ctrl/takeoff_land`
- 开始任务：`pub_trigger.sh` 或 RC 8 通中->上 -> `/move_base_simple/goal`
- 返程：`back.sh` 或 RC 8 通上->中 -> `/back_trigger`
- 降落：`land.sh` 或 RC 8 通中->下 -> `/px4ctrl/takeoff_land`

## 4. 接口说明

### 4.1 人工物理层

- RC 5 通：光流 / 姿态 / onboard 模式切换，是上层控制能否真正接管 `px4ctrl` 的前置门。
- RC 6 通：悬停 / 轨迹模式切换，异常时优先上拨 6 通回到安全兜底状态。
- RC 7 通：解锁 / 锁桨 / 急停，是最高优先级安全通道。
- RC 8 通：起飞 / 开始任务 / 返程 / 降落动作触发，`multipoint` 会直接读取 `/mavros/rc/in` 中该通道的变化。

### 4.2 脚本编排层

- `run_single_lio.sh`：LIO 全栈入口，负责把 `mavros`、`faster_lio`、`ekf`、`diff_planner`、`px4ctrl`、`multipoint` 依次拉起。
- `run_single_vio.sh`：VIO 全栈入口，负责把 `mavros`、`realsense2_camera`、`vins`、`diff_planner`、`px4ctrl`、`multipoint` 依次拉起。
- `takeoff.sh`：向 `/px4ctrl/takeoff_land` 发布起飞命令。
- `pub_trigger.sh`：向 `/move_base_simple/goal` 发布开始任务触发。
- `back.sh`：向 `/back_trigger` 发布返程触发。
- `land.sh`：向 `/px4ctrl/takeoff_land` 发布降落命令。

### 4.3 ROS 动作层

- `/px4ctrl/takeoff_land`：`quadrotor_msgs/TakeoffLand`，通过 `takeoff_land_cmd=1/2` 表示起飞 / 降落。
- `/move_base_simple/goal`：`geometry_msgs/PoseStamped`，被 `multipoint` 用作开始任务触发。
- `/back_trigger`：`geometry_msgs/PoseStamped`，被 `multipoint` 用作返程触发。
- `/goal`：`geometry_msgs/PoseStamped`，由 `multipoint` 向规划器逐点发送任务目标。
- `/planning/yaw`：`quadrotor_msgs/PositionCommand`，在带 yaw 的多点模式中补充偏航命令。
- `/setpoints_cmd`：`quadrotor_msgs/PositionCommand`，`traj_server` 输出给 `px4ctrl` 的核心控制通道。

### 4.4 ROS 状态观测层

- `/mavros/state`：飞控连接、模式、解锁状态的第一入口。
- `/mavros/battery`：电压、电流、电量百分比的常用入口。
- `/mavros/rc/in`：遥控器原始通道输入，既是安全门又是动作映射源。
- `/mavros/imu/data`：飞控 IMU 输入，`px4ctrl` 明确依赖该 topic。
- `/mavros/local_position/pose`：PX4 本地位姿输出。
- `/ekf/ekf_odom`：LIO 主链下的融合定位输出。
- `/laserMapping/odometry`：`faster_lio` 原始里程计输出。
- `/laserMapping/cloud_registered`：规划器和 rviz 常看的配准点云。
- `/vins/imu_propagate`：VIO 主链下的惯导融合定位输出。
- `/drone_0_planning/trajectory`：规划器发布的轨迹结果。

### 4.5 配置入口层

- `points.yaml`：定义 `test1`、`test2`、`test3`、`test4` 和 `test_back`，决定多点任务的格式和返程点。
- `ctrl_param_fpv.yaml`：定义低压阈值、自动起飞高度、自动起降速度、手动接管速度上限等飞控侧关键参数。
- `multipointplan_exp_lio.launch`：定义 `fligt_type`、`next_distance`、`start_plan`、`back_plan`。
- `run_exp_single_lio.launch`：定义 LIO 规划链的速度、加速度、jerk、地图分辨率、膨胀半径等参数。
- `run_exp_single_vio.launch`：定义 VIO 规划链的视觉输入、相机内参和规划参数。

### 4.6 扩展接入层

- 桥接型接入：外部系统订阅状态 topic，发布动作 topic，不直接碰控制器内部状态机。
- 任务层接入：替换 `points.yaml` 或 `multipoint` 的任务来源，把上层任务转成航点或动作原语。
- 深改型接入：修改 `diff_planner`、`traj_server`、`px4ctrl`，适合算法级改造，不适合作为第一接入点。

## 5. 关键参数入口

### 5.1 `points.yaml`

- 负责定义 `test1`、`test2`、`test3`、`test4` 和 `test_back`。
- `fligt_type=1` 时每个点必须是 `[x, y, z]`。
- `fligt_type=2` 时每个点必须是 `[x, y, z, time]`。
- `fligt_type=3` 时每个点必须是 `[x, y, z, yaw]`。
- `fligt_type=4` 时每个点必须是 `[x, y, z, yaw, time]`。
- `test_back` 固定为三元组 `[x, y, z]`，格式不对会被 `multipoint` 直接判错。

### 5.2 `ctrl_param_fpv.yaml`

- `low_voltage`：低压阈值，当前为 21.0V。
- `auto_takeoff_land.takeoff_height`：自动起飞高度，当前为 0.8m。
- `auto_takeoff_land.takeoff_land_speed`：自动起降速度，当前为 0.2m/s。
- `max_manual_vel`：手动接管速度上限，当前为 1.0m/s。
- `msg_timeout.odom/rc/cmd/imu/bat`：各类输入超时门槛，超时会直接影响控制器接管和执行。

### 5.3 `multipointplan_exp_lio.launch`

- `fligt_type`：多点模式选择，源码中保留该拼写，不要擅自更名。
- `next_distance`：判定到达当前点并切下一个点的阈值。
- `start_plan`：是否启用开始任务逻辑。
- `back_plan`：是否启用返程逻辑。

### 5.4 `run_exp_single_lio.launch`

- `max_vel`
- `max_acc`
- `max_jer`
- `planning_horizon`
- `map_resolution`
- `inflation_size`
- `virtual_ceil`
- `virtual_ground`

### 5.5 `run_exp_single_vio.launch`

- 视觉模式下的规划参数入口与 LIO 基本一致。
- 相机内参通过 `cx`、`cy`、`fx`、`fy` 提供，错误内参会直接破坏 VIO 规划效果。
- 深度输入来自 `/camera/depth/image_rect_raw`，odom 输入来自 `/vins/imu_propagate`。

## 6. 状态观测与排障路径

### 6.1 日常观测最短路径

- 看电量：`/mavros/battery`
- 看飞控连接和模式：`/mavros/state`
- 看 RC 输入：`/mavros/rc/in`
- 看 PX4 本地位姿：`/mavros/local_position/pose`
- 看 LIO 融合定位：`/ekf/ekf_odom`
- 看 VIO 定位：`/vins/imu_propagate`
- 看点云质量：`/laserMapping/cloud_registered`
- 看规划轨迹：`/drone_0_planning/trajectory`

### 6.2 排障顺序

1. 先确认入口脚本是否完整拉起，不要只看到 `px4ctrl` 在就误判全链在线。
2. 再确认 `mavros` 是否在线，优先看 `/mavros/state`、`/mavros/battery`、`/mavros/rc/in`。
3. 再确认定位链是否正常输出，LIO 看 `/ekf/ekf_odom` 和点云，VIO 看 `/vins/imu_propagate` 和相机链。
4. 再确认动作 topic 是否被正确触发，尤其是 `/px4ctrl/takeoff_land`、`/move_base_simple/goal`、`/back_trigger`。
5. 最后确认 RC 档位、安全门和超时参数，避免把人为状态门限问题误判成算法问题。

### 6.3 常见误判

- `run_ctrl_lio.launch` 不是全栈入口，它只起 `px4ctrl`。
- wiki 上出现的功能不等于当前机器已经可直接启动。
- 有规划轨迹不等于 `px4ctrl` 一定在执行，还要看飞控模式、RC 档位和控制器状态。

## 7. 二开建议与扩展边界

### 7.1 推荐接入顺序

1. 先做桥接型接入，不碰底层控制。
2. 再做任务层改造，把上层任务映射成航点或动作原语。
3. 最后才考虑深改规划器或控制器。

### 7.2 最小上层系统接入方案

- 订阅：`/mavros/state`、`/mavros/battery`、`/mavros/rc/in`、`/ekf/ekf_odom`、`/vins/imu_propagate`
- 发布：`/px4ctrl/takeoff_land`、`/move_base_simple/goal`、`/back_trigger`
- 如果要保留现有任务逻辑，就不要直接绕过 `multipoint` 写 `/goal` 或 `/setpoints_cmd`。

### 7.3 不推荐的第一刀

- 不要第一步就直接从 `/setpoints_cmd` 控制器注入高频命令。
- 不要第一步就改 `px4ctrl` 状态机。
- 不要把 Elastic / 集群 / YOLO 写进当前实机默认能力。
- 不要把产品线文档里的能力边界和当前机上边界混在一起。
