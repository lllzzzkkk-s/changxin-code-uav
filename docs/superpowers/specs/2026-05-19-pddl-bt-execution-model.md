# PDDL 到任务级 BT 执行模型

日期：2026-05-19

## 1. 目标

本设计定义中心地面站如何将自然语言任务转成 PDDL，再将 PDDL plan 编译为任务级 BT 或状态机，最后通过 platform gateway 下发给三车三机。

PDDL 和 BT 的分工：

- PDDL 负责 mission-level planning：任务依赖、平台能力、目标状态、顺序约束。
- BT 负责 reactive execution：前置检查、等待、重试、失败分支、人工确认、局部恢复。
- ROS1 负责本地执行：导航、飞控、底盘、感知和控制。

## 2. 任务入口

自然语言任务先收敛为 mission schema，再进入 PDDL problem generator。

示例任务：

```text
搜索 A 区，发现目标后派无人车接近确认，无人机保持观察或中继。
```

Mission schema：

```yaml
schema: MissionRequest.v1
mission_id: mission_001
mission_type: scout_and_confirm
areas:
  - area_id: area_A
    boundary: []
targets:
  - target_type: unknown_object
platform_requirements:
  aerial_scan: required
  ground_confirm: required
constraints:
  require_operator_before_motion: false
  max_mission_duration_s: 600
```

LLM 可以生成 mission schema 草案，但必须由规则 validator 校验。

## 3. PDDL Domain 首版动作

首版 PDDL domain 聚焦侦察确认，不覆盖所有未来任务。

动作集合：

- `scan-area(?uav ?area)`
- `detect-target(?uav ?area ?target)`
- `assign-ground-confirm(?ugv ?target)`
- `confirm-target(?ugv ?target)`
- `relay-or-overwatch(?uav ?target)`
- `hold-platform(?robot)`
- `return-platform(?robot ?base)`

关键谓词：

- `(available ?robot)`
- `(is-uav ?robot)`
- `(is-ugv ?robot)`
- `(area-known ?area)`
- `(target-detected ?target)`
- `(target-confirmed ?target)`
- `(can-scan ?uav ?area)`
- `(can-confirm ?ugv ?target)`
- `(platform-safe ?robot)`
- `(localization-ok ?robot)`
- `(battery-ok ?robot)`

PDDL 不表达底层路径、姿态、速度、飞控模式。这些由平台本地 Safety Gate 和 local planner 判断。

## 4. Plan Validator

PDDL planner 输出 plan 后，中心必须验证：

- 所有 action 都在允许 domain 内。
- 所有平台都在 capability registry 内。
- 每个 action 的平台类型正确。
- 任务没有分配给 offline 或 degraded 平台。
- 任务不违反禁区、最低电量和人工确认策略。
- plan 中没有要求平台直接执行原始 ROS topic。

不通过 validator 的 plan 不得编译为 BT。

## 5. PDDL-to-BT 编译规则

每个 PDDL action 编译为一个 BT subtree。

通用结构：

```text
Sequence
  PreconditionCheck
  DispatchTaskCommand
  WaitForCommandAck
  MonitorTaskProgress
  SuccessOrFailureBranch
```

失败分支：

```text
Fallback
  LocalRepairAction
  RequestReplan
  RequestOperatorIntervention
  AbortOrHold
```

示例：`scan-area(uav_0, area_A)`

```text
Sequence scan_area_area_A
  CheckPlatformOnline(uav_0)
  CheckCapability(uav_0, inspect_area)
  CheckLocalization(uav_0)
  DispatchTaskCommand(uav_0, inspect_area, area_A)
  WaitAck(uav_0, task_001)
  MonitorProgress(uav_0, task_001)
  OnFailure:
    ReportFailureToBlackboard
    RequestReplan
```

示例：`confirm-target(ugv_0, target_01)`

```text
Sequence confirm_target_01
  CheckPlatformOnline(ugv_0)
  CheckCapability(ugv_0, confirm_target)
  DispatchTaskCommand(ugv_0, confirm_target, target_01)
  WaitAck(ugv_0, task_002)
  MonitorProgress(ugv_0, task_002)
  OnFailure:
    If path_blocked -> request_uav_rescan
    Else -> request_operator_or_replan
```

## 6. Mission Blackboard

BT 执行器只通过 blackboard 和 gateway 消息更新状态。

Blackboard 最小字段：

```yaml
schema: MissionBlackboard.v1
mission_id: mission_001
status: running
open_tasks: []
in_progress:
  task_001:
    platform_id: uav_0
    capability: inspect_area
completed_tasks: []
failed_tasks: []
platform_states:
  uav_0:
    task_status: running
    safety_state: normal
targets:
  target_01:
    status: candidate
    position: null
events: []
```

Blackboard 是中心重规划的事实来源。大模型不得直接从长对话历史推断任务状态。

## 7. 断联和局部继续策略

用户已确认首版策略为平台断联后继续当前任务。该策略必须被严格限制：

- 平台只继续已经接收并 ack 的当前 BT 子树。
- 平台不得领取新任务。
- 平台不得本地生成 PDDL plan。
- 平台不得改变全局任务 owner。
- 超过任务 timeout 后按本地 `abort_policy` 进入 hold、return 或 stop。

无人机建议默认：

- 悬停或继续当前短任务。
- 超时后 hold 或 return home。

无人车建议默认：

- 继续当前短任务。
- 路径不可达或超时后停车驻留并回传失败。

## 8. LangGraph 的位置

LangGraph 不是执行模型主干。可选用法：

```text
Natural language intake
  -> mission schema draft
  -> human confirmation
  -> call PDDL generator
  -> summarize validator errors
  -> summarize failure reports
```

禁止用法：

- LangGraph 节点直接 publish ROS topic。
- LangGraph 节点直接选择底层 setpoint。
- LangGraph 节点绕过 Plan Validator 或 Safety Gate。

## 9. 第一阶段验收

Dry-run 验收：

- 给定一机一车能力画像和侦察确认 mission schema。
- 生成 PDDL problem。
- PDDL planner 输出包含 `scan-area` 和 `confirm-target` 的 plan。
- validator 通过。
- compiler 生成任务级 BT。
- BT dry-run 生成 `TaskCommand`，但不连接实机。

半实机验收：

- UAV 和 UGV gateway 可分别上报 fake 或真实 `PlatformState`。
- 中心可下发 `inspect_area` 和 `confirm_target`。
- 平台能 ack、progress、failure。
- 中心 blackboard 正确更新。

实机验收：

- 不共享 ROS master。
- 中心不能直接访问平台 ROS topic。
- 平台 gateway 接收任务后由本地 Safety Gate 决定是否执行。
- 任一失败都能生成 `FailureReport.v1`。
