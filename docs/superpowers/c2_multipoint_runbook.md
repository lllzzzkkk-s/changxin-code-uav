# C2 Multipoint 只读诊断 Runbook

日期：2026-05-19

## 目的

这份 runbook 用于诊断实机 C2 阶段：`multipoint` 正常入口触发后，为什么没有稳定观察到 `/goal` 或 `/setpoints_cmd`。

诊断脚本 `uav/01-scripts/diagnose_c2_multipoint.sh` 本身只读：

- 不 publish ROS topic
- 不 arm
- 不改 rosparam
- 不启动或停止节点
- 只抓 ROS graph、参数、状态、日志和 action topic 监听窗口

触发 `pub_trigger.sh` 是操作员的独立动作，只能在你已经确认允许做 C2 触发测试时执行。

## 前置条件

实机上应已经通过现有流程拉起至少以下节点：

- `/mavros`
- `/laserMapping`
- `/ekf`
- `/drone_0_diff_planner_node`
- `/drone_0_traj_server`
- `/multipointplan`

如果要观察 `/setpoints_cmd`，还需要 `/px4ctrl` 和相关控制链已经按当前试验阶段启动。

进入实机仓库：

```bash
cd ~/changxin-code-sync
git pull
source /opt/ros/noetic/setup.zsh
source ~/Diff-planner/devel/setup.zsh
```

## Baseline：不触发，只读抓当前状态

这一步用于确认脚本和 ROS 环境正常，不做 C2 触发。

```bash
cd ~/changxin-code-sync

bash uav/01-scripts/diagnose_c2_multipoint.sh \
  --trigger-window-s 5 \
  --diff-planner-dir ~/Diff-planner
```

完成后复制输出里的 evidence 目录，例如：

```bash
cat ~/uav-g3e-real-evidence/c2-diag-*/summary.txt
```

## C2 触发观察：先开监听，再触发

这一步是关键。必须先启动监听窗口，再在另一个终端触发 `pub_trigger.sh`。

Terminal A：

```bash
cd ~/changxin-code-sync
source /opt/ros/noetic/setup.zsh
source ~/Diff-planner/devel/setup.zsh

bash uav/01-scripts/diagnose_c2_multipoint.sh \
  --trigger-window-s 20 \
  --diff-planner-dir ~/Diff-planner
```

等 Terminal A 打印：

```text
===== ACTION MONITORS ARMED =====
```

Terminal B 再执行：

```bash
cd ~/Diff-planner
source /opt/ros/noetic/setup.zsh
source devel/setup.zsh

./sh_files/pub_trigger.sh
```

不要反过来执行。如果先触发再开监听，短消息可能已经错过。

## 需要贴回来的内容

优先贴：

```bash
cat <evidence-dir>/summary.txt
cat <evidence-dir>/05-action-topic-passive-echo.txt
cat <evidence-dir>/06-multipoint-log-keywords.txt
cat <evidence-dir>/03-rosparam-multipoint.txt
```

如果 summary 显示 `/goal` 收到了但 `/setpoints_cmd` 没收到，再补：

```bash
cat <evidence-dir>/02-topic-info.txt
cat <evidence-dir>/02b-rosnode-info-diff-planner.txt
cat <evidence-dir>/02c-rosnode-info-traj-server.txt
```

如果 summary 显示 trigger 都没收到，再补：

```bash
cat <evidence-dir>/02a-rosnode-info-multipointplan.txt
```

## 如何解释结果

### 1. `operator_trigger_message_received=true` 但 `goal_message_received=false`

说明触发消息被监听到，但 `multipoint` 没有发出 `/goal`。

优先看：

- `06-multipoint-log-keywords.txt`
- `03-rosparam-multipoint.txt`
- `points.yaml`
- `yaml_path`
- `next_distance`
- `start_plan`
- `back_plan`
- `fligt_type` / `flight_type`

下一步通常是生成候选 `points.yaml`，但不要直接覆盖当前配置。

### 2. `goal_message_received=true` 但 `setpoints_cmd_message_received=false`

说明 `multipoint` 已经发出 `/goal`，问题转到 planner 或 traj_server。

优先看：

- `/drone_0_diff_planner_node` 是否订阅 `/goal`
- `/drone_0_planning/trajectory` 是否有输出
- `/drone_0_traj_server` 是否订阅轨迹并发布 `/setpoints_cmd`
- planner 是否因为地图、目标高度、障碍或状态机拒绝目标

### 3. `goal_message_received=true` 且 `setpoints_cmd_message_received=true`

说明 C2 在监听窗口内已经产生 planner 输出。

下一步不要扩大动作幅度，先保存 evidence，再做小距离、低高度、人工确认的重复性验证。

### 4. 所有 action topic 都没消息

说明监听窗口没有抓到触发。先排除操作顺序问题：

- 是否先看到 `ACTION MONITORS ARMED`
- 是否在 20 秒窗口内执行了 `pub_trigger.sh`
- 当前 `/multipointplan` 是否存在
- `/move_base_simple/goal` 是否有 publisher/subscriber

## 安全边界

- 这个脚本不能替代飞行前检查。
- 不要在未确认场地、遥控器档位、降落策略前触发 C2。
- 不要把诊断脚本改成自动执行 `pub_trigger.sh`。
- 不要让脚本自动覆盖 `points.yaml`。
- 实机 evidence 继续写到 `~/uav-g3e-real-evidence/`，不要写进 git 仓库。
