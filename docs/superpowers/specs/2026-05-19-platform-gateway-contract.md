# Platform Gateway 消息协议设计

日期：2026-05-19

## 1. 目标

Platform Gateway 是中心地面站和每个平台本地 ROS1 master 之间的唯一任务接口。它的目标是隔离中心系统和本地 ROS 图，让中心只看到平台级状态、任务、进度和失败事件，而不是看到整套 ROS topic。

第一阶段协议基于 NATS 或 MQTT 类消息总线设计。实现时可先用 NATS，消息体使用 JSON 或 YAML 等可读结构，后续再根据性能和类型安全需求切到 protobuf。

## 2. 命名约定

每个平台使用稳定 `platform_id`：

- `uav_0`
- `uav_1`
- `uav_2`
- `ugv_0`
- `ugv_1`
- `ugv_2`

推荐 topic：

```text
fleet.<platform_id>.state
fleet.<platform_id>.task
fleet.<platform_id>.progress
fleet.<platform_id>.failure
fleet.<platform_id>.heartbeat
fleet.<platform_id>.command_ack
```

中心广播类 topic：

```text
fleet.mission.blackboard
fleet.mission.abort
fleet.mission.pause
fleet.mission.resume
```

## 3. PlatformState

平台状态由 gateway 周期上报。中心只依赖这些字段做任务分配和健康判断。

```yaml
schema: PlatformState.v1
platform_id: uav_0
platform_type: uav
timestamp: "2026-05-19T10:00:00+08:00"
comm_status: online
task_status: idle
current_task_id: null
pose:
  frame_id: world
  x: 0.0
  y: 0.0
  z: 0.0
  yaw: 0.0
velocity:
  vx: 0.0
  vy: 0.0
  vz: 0.0
battery:
  voltage: 24.0
  percentage: 0.8
localization:
  source: lio
  ok: true
  quality: nominal
safety:
  state: normal
  reason: ""
capabilities:
  - inspect_area
  - hold_position
  - return_home
```

必填字段：

- `schema`
- `platform_id`
- `platform_type`
- `timestamp`
- `comm_status`
- `task_status`
- `localization.ok`
- `safety.state`

## 4. TaskCommand

中心下发任务级命令，不下发原始 ROS topic。

```yaml
schema: TaskCommand.v1
mission_id: mission_001
task_id: task_003
platform_id: uav_0
capability: inspect_area
parameters:
  area_id: area_A
  altitude_m: 1.0
  max_duration_s: 120
preconditions:
  localization_ok: true
  min_battery_percentage: 0.3
abort_policy: hold_position
disconnect_policy: continue_current_task
timeout_s: 180
requires_operator_confirm: false
```

首版 allowlist capability：

- `inspect_area`
- `move_to_region`
- `confirm_target`
- `relay_or_overwatch`
- `hold_position`
- `return_home`
- `land_or_stop`

禁止 capability：

- 任何原始 `/mavros/*` topic 发布。
- 原始速度控制。
- 原始 setpoint stream。
- 任意未在 allowlist 中登记的本地 ROS action。

## 5. CommandAck

平台收到任务后必须明确接受或拒绝。

```yaml
schema: CommandAck.v1
mission_id: mission_001
task_id: task_003
platform_id: uav_0
accepted: true
reason: ""
local_check:
  capability_known: true
  localization_ok: true
  battery_ok: true
  safety_ok: true
```

拒绝示例：

```yaml
schema: CommandAck.v1
mission_id: mission_001
task_id: task_004
platform_id: ugv_1
accepted: false
reason: path_not_reachable
local_check:
  capability_known: true
  localization_ok: true
  battery_ok: true
  safety_ok: true
  path_reachable: false
```

## 6. TaskProgress

任务执行期间周期上报。

```yaml
schema: TaskProgress.v1
mission_id: mission_001
task_id: task_003
platform_id: uav_0
status: running
progress_ratio: 0.45
message: scanning area_A
observations:
  target_candidates:
    - target_id: target_01
      confidence: 0.72
      position:
        frame_id: world
        x: 2.3
        y: -1.1
        z: 0.0
```

允许的 `status`：

- `queued`
- `running`
- `waiting`
- `completed`
- `failed`
- `aborted`

## 7. FailureReport

失败必须结构化，不能只返回自由文本。中心重规划只消费 failure report 和 blackboard。

```yaml
schema: FailureReport.v1
mission_id: mission_001
task_id: task_004
platform_id: ugv_1
failure_type: path_blocked
recoverable: true
reason: local_planner_no_path
timestamp: "2026-05-19T10:03:00+08:00"
state_ref: state_ugv_1_00042
recommended_actions:
  - request_uav_rescan
  - try_alternate_region_entry
  - wait_for_operator
evidence:
  log_path: ""
  ros_topic_snapshot: ""
```

首版 `failure_type`：

- `localization_unstable`
- `battery_low`
- `path_blocked`
- `target_not_found`
- `task_timeout`
- `safety_gate_reject`
- `ros_bridge_error`
- `operator_interrupt`
- `comm_lost`

## 8. Heartbeat

```yaml
schema: Heartbeat.v1
platform_id: uav_0
timestamp: "2026-05-19T10:00:01+08:00"
gateway_status: alive
ros_master_ok: true
last_state_seq: 42
last_task_id: task_003
```

中心超时策略：

- 短超时：标记平台 `degraded`，不分配新任务。
- 长超时：标记平台 `offline`，触发中心局部重规划。
- 对已经下发的任务，按 `disconnect_policy` 处理。

## 9. 本地 Gateway 执行边界

Gateway 可以做：

- 订阅本地 ROS 状态。
- 调用本地已登记 action 或 service。
- 发布本地 allowlist topic。
- 汇总本地规则检查结果。
- 将 ROS 错误转为 `FailureReport`。

Gateway 不可以做：

- 接受中心传来的任意 ROS topic 名称并转发。
- 执行中心传来的任意 shell 命令。
- 在断联后生成新 mission。
- 绕过本地 Safety Gate。
- 在实机证据目录外乱写日志。
