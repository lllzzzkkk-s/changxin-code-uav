# 开发导航页

## 我想改什么，应该看哪里

- 想改起飞高度 -> `01-developer-guide.md` 的参数入口章节 + `ctrl_param_fpv.yaml`
- 想改低压阈值 -> `01-developer-guide.md` 的参数入口章节 + `ctrl_param_fpv.yaml`
- 想改航点格式 -> `points.yaml` + `multipointplan_exp_lio.launch`
- 想改 LIO 规划参数 -> `run_exp_single_lio.launch`
- 想改 VIO 规划参数或相机内参 -> `run_exp_single_vio.launch`
- 想接上层 Agent / MQTT / HTTP 桥接 -> `02-interface-table.csv` 的状态接口和动作接口 + `01-developer-guide.md` 的“二开建议与扩展边界”
- 想知道任务是怎么开始的 -> `run_single_lio.sh` / `run_single_vio.sh` + `/move_base_simple/goal`
- 想看返航和降落怎么触发 -> `/back_trigger` + `/px4ctrl/takeoff_land` + `RC Channel 8`
- 想看电量、位置、姿态 -> `/mavros/battery`、`/mavros/local_position/pose`、`/ekf/ekf_odom`、`/vins/imu_propagate`
- 想判断问题在脚本、定位、规划还是控制 -> `01-developer-guide.md` 的“状态观测与排障路径”
- 想判断 Elastic / FUEL / 集群是否当前能直接用 -> `03-feature-deployment-matrix.csv`
- 想决定新功能应该插在哪一层 -> `01-developer-guide.md` 的“接口说明”与“二开建议与扩展边界”
