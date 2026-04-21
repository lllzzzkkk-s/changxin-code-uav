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

## 5. 关键参数入口

## 6. 状态观测与排障路径

## 7. 二开建议与扩展边界
