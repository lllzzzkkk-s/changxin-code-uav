# 三车三机 PDDL/BT 大系统架构设计

日期：2026-05-19

## 1. 目标与边界

本设计面向后续三车三机异构协同系统。当前阶段仍基于 ROS1，每个平台保留自己的 ROS master，不共享一个大的 ROS master。系统目标不是让大模型直接控制车和机，而是建立一套可审计、可恢复、可逐步实机验证的任务级控制框架。

第一阶段明确不在车端或机端部署小模型。无人车的 NVIDIA 工控机暂时只作为平台算力余量，不进入首版能力假设。所有 LLM、PDDL、任务分解、全局调度、重规划和任务记忆都运行在独立地面站。

核心边界：

- 中心地面站是唯一全局任务规划权威。
- PDDL 负责 mission-level symbolic planning，不负责底层控制。
- PDDL plan 编译为任务级 BT 或状态机后再下发。
- 车端和机端只执行受控任务、回传状态、做本地规则检查和安全兜底。
- 平台本地可以继续当前已接收任务，但不能离线生成新任务或扩展全局计划。
- 大模型只做任务理解、PDDL problem 草案、失败解释和复盘建议，不能直接 publish ROS topic。

## 2. 当前事实基线

### 已完成或已验证

- 当前无人机实机链路已打通 MAVROS、LIO、EKF、Diff-planner、px4ctrl。
- MAVROS 工作链路使用 `/dev/ttyTHS1:921600`。
- `/mavros/state`、`/mavros/rc/in`、`/laserMapping/odometry`、`/ekf/ekf_odom` 可读。
- 起飞和降落已经实机成功。
- C1 直接发布小距离 `/goal` 曾触发轨迹和运动。
- `safe_bringup_lio.sh` 的 staged bringup 方向已经验证过：planner-only 和 control-standby 是合理分层。
- Mac、WSL2、实机三端协作链路已初步跑通。

### 当前未完成或仍阻塞

- C2 multipoint 正常入口触发后没有稳定观察到 `/goal` 或 `/setpoints_cmd`，需要继续做只读诊断。
- `uav/llm_control` 相关实现仍存在 worktree 和主线收敛问题，主线应成为唯一可信源码。
- 当前还没有三车三机级别的 platform gateway、任务黑板、PDDL domain、PDDL-to-BT compiler。
- 当前还没有统一的 `failure_report` schema。
- 当前还没有 NATS/MQTT 类消息总线接入。

### 当前高优先级待办

1. 固化 C2 multipoint 诊断脚本和 runbook。
2. 建立单平台 capability profile。
3. 建立 `state_update`、`task_command`、`failure_report`、`heartbeat` 的消息协议。
4. 设计第一版侦察确认 PDDL domain。
5. 实现 PDDL plan 到任务级 BT 的编译和 dry-run。
6. 做一机一车侦察确认闭环，再扩到三车三机。

## 3. 总体架构

推荐架构为独立地面站中心规划，六个平台本地执行：

```text
Operator / LLM Task Entry
        |
        v
Ground Mission Station
  - Mission Manager
  - PDDL Problem Generator
  - PDDL Planner
  - Plan Validator
  - PDDL-to-BT Compiler
  - Mission Blackboard
  - Event / Failure Log
        |
        v
NATS or MQTT Message Bus
        |
        v
Platform Gateway per robot
  - Task receiver
  - State reporter
  - Failure reporter
  - Local rule checker
  - Local safety gate
        |
        v
Local ROS1 Master
  - UAV: MAVROS / LIO / EKF / Diff-planner / px4ctrl
  - UGV: chassis control / local planner / perception / safety nodes
```

中心和平台之间只交换任务级消息，不交换原始 ROS topic。每个平台内部保留自己的 ROS graph，平台 gateway 是中心进入本机 ROS1 的唯一入口。

## 4. 中心地面站职责

中心地面站承担系统智能和全局协调：

- 接收操作员指令或大模型生成的任务意图。
- 将自然语言任务收敛为 mission schema。
- 根据 capability registry 和当前 blackboard 生成 PDDL problem。
- 调用 PDDL planner 生成全局 symbolic plan。
- 校验 plan 是否满足平台能力、任务依赖、禁区和安全约束。
- 将 PDDL plan 编译为任务级 BT。
- 通过消息总线向平台 gateway 下发 capability-level task。
- 维护 mission blackboard、事件日志和失败记录。
- 根据 `failure_report` 做局部重规划，优先修补当前任务，不默认重启整场 mission。

中心地面站可以使用 LLM 或 LangGraph，但它们只是辅助层：

- LLM 可生成 mission schema 草案。
- LLM 可解释失败报告并提出候选修复。
- LangGraph 可编排人机确认、工具调用和长流程状态。
- LLM/LangGraph 输出必须经过 PDDL validator、BT compiler 和 Safety Gate。

## 5. 平台本地职责

平台本地只承担执行和安全边界，不承担全局智能。

无人机本地职责：

- 接收任务级命令，例如 `inspect_area`、`hold_position`、`return_home`。
- 将任务映射到本机已验证 ROS 接口。
- 持续上报飞控状态、定位状态、电池、当前任务进度。
- 执行本地 Safety Gate，例如飞控连接、模式、armed、定位健康、速度稳定、禁发 topic。
- 断联后继续当前已接收 BT 子树或进入任务定义的安全策略。
- 不部署小模型，不做本地 PDDL，不做全局重规划。

无人车本地职责：

- 接收任务级命令，例如 `move_to_region`、`confirm_target`、`hold_position`。
- 将任务映射到本机底盘控制、局部规划或导航栈。
- 用规则和现有 planner 做可达性检查。
- 回传路径不可达、障碍、定位不稳、执行超时等失败原因。
- 第一阶段不部署小模型，不做本地 PDDL，不做全局重规划。

## 6. 第一版验证场景

第一版大系统验证场景为一机一车侦察确认。

任务流程：

1. 操作员下发“搜索 A 区并确认目标”。
2. 中心生成 mission schema。
3. PDDL planner 输出任务序列：
   - UAV 执行 `inspect_area(A)`。
   - 若发现目标，中心分配 UGV 执行 `confirm_target(target)`。
   - UAV 执行 `relay_or_overwatch(target)`。
   - 所有平台回传 completion。
4. 任一平台失败时回传 `failure_report`。
5. 中心优先做局部修复，例如 UAV 复查、UGV 换路径、任务等待或人工确认。

三车三机扩展时保持同一接口，只增加平台数量、任务分配和冲突处理，不改变主干架构。

## 7. 安全原则

- 中心不得直接 publish `/mavros/*`、底盘速度、原始 setpoint stream。
- 所有中心下发都是 capability-level task。
- 平台 gateway 必须做 topic allowlist 和 action allowlist。
- 平台必须能拒绝任务，并给出结构化原因。
- 断联后平台只能继续当前已接收任务或进入安全策略，不能领取新任务。
- 实机证据写入仓库外目录，例如 `~/uav-g3e-real-evidence/`。
- 实机 Git checkout 只允许 pull，不允许 commit/push。

## 8. 后续演进

阶段 A：单 UAV 稳定化。

- 继续完成 C2 multipoint 诊断。
- 固化无人机 capability profile。
- 完成状态读取、任务命令和 failure report 的最小协议。

阶段 B：一机一车侦察确认。

- 接入一台 UGV 的 platform gateway。
- 完成中心任务黑板。
- 完成第一版 PDDL domain 和 PDDL-to-BT dry-run。
- 做一机一车实机或半实机闭环。

阶段 C：多平台仿真。

- 扩到二车二机，再扩到三车三机。
- 增加任务分配、等待、冲突、掉线、拒绝任务和局部重规划。

阶段 D：三车三机实机。

- 接入完整平台。
- 加入通信质量、电量、禁区、区域冲突和人工接管策略。
- 可选接入车端模型作为感知增强，但不改变全局架构。
