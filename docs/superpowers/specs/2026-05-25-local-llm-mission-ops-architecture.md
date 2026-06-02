# Mock/HTTP Model Mission Ops Architecture

Date: 2026-05-25

## Final Decision

For the first implementation version, use:

```text
Command-driven Mission Ops
+ MockLLMClient now / local_http or remote_http ModelClient adapter later
+ Deterministic MissionManager
+ PDDL / Validator / BT / Platform Gateway / ROS1 Core
```

Do **not** add LangGraph as a phase-1 production runtime dependency.

LangGraph remains a later upgrade option if Mission Ops becomes a long-running, checkpointed, multi-agent, human-in-the-loop workflow. It must never become the planner, BT executor, gateway, or local ROS controller.

This also does not require a real model endpoint in phase 1. The first version is command-driven and uses `MockLLMClient`. When a real model endpoint is available, replace only the model adapter behind `ModelClient`; do not change PDDL, validation, BT/state-machine execution, platform gateways, or ROS1 wrappers.

This does not mean ignoring LangGraph now. Phase 1 must be LangGraph-ready by design:

- typed tools for every Mission Ops step
- a runtime-neutral `MissionOpsRunner` interface
- persistent `MissionOpsState`
- model calls isolated behind `model_client.py`
- no core dependency on Mission Ops runtime internals

## Why This Version

The current system still needs the deterministic robotics core:

- contracts
- `TaskSchema` / `MissionRequest`
- capability registry
- blackboard
- PDDL domain/problem generator
- validators
- PDDL planner adapter
- PDDL-to-BT/state-machine compiler
- platform gateway
- `FailureReport` to replan loop

Adding LangGraph before these exist adds a workflow runtime before there is a stable workflow to run. A real model endpoint may be useful later, but the current first slice can be built with local commands and `MockLLMClient`.

## System Shape

```text
Operator
  -> MissionManager
      -> retrieve architecture/context
      -> call MockLLMClient for TaskSchema draft
      -> validate TaskSchema
      -> update mission blackboard
      -> generate PDDL problem
      -> validate problem
      -> run PDDL planner
      -> validate plan
      -> compile plan to BT/state machine
      -> operator approval
      -> dry-run or dispatch through platform gateway
      -> monitor TaskProgress / FailureReport / Heartbeat
      -> trigger local recovery or central replan
  -> Platform Gateway
  -> Local ROS1 Master
```

## Model Placement

Phase 1 model is a mock implementation running in the ground-station code path. Future real model endpoints run on the independent ground station, home model-lab server, or an approved remote endpoint only as semantic compilers.

Recommended adapter:

```text
task_planning/mission_ops/
  model_client.py
  mock_llm_client.py
  http_model_client.py
  mission_manager.py
  runner.py
  state_store.py
  prompts/
  tools.py
  state.py
```

Recommended configuration:

```text
MODEL_PROVIDER=mock|local_http|remote_http
MODEL_BASE_URL=http://127.0.0.1:<port>/v1
MODEL_NAME=<model-name>
MODEL_LAB_EVIDENCE_KIND=unspecified|mock_endpoint|home_5090_live
```

The adapter should hide whether the backend is a mock, vLLM, llama.cpp, LM Studio, or another OpenAI-compatible local/remote server. The home 5090 lane is model capability testing only; the unit/work hardware lane must not depend on that endpoint for execution.

## Allowed Model Calls

```text
compile_task_schema(intent, context_snapshot)
  -> TaskSchema | NeedsClarification

explain_validator_error(error, schema, context_snapshot)
  -> Explanation

triage_failure(failure_report, blackboard_snapshot)
  -> ReplanAdvice

write_experiment_summary(trace, decision)
  -> ExperimentLogDraft
```

Every output must be schema validated before entering the deterministic core.

`MockLLMClient` must use the same return schemas as future HTTP-backed `ModelClient` adapters.

## MissionManager States

```text
DRAFT_INTENT
RETRIEVE_CONTEXT
CALL_MODEL_CLIENT_FOR_TASK_SCHEMA
VALIDATE_TASK_SCHEMA
NEEDS_CLARIFICATION
UPDATE_BLACKBOARD
GENERATE_PDDL_PROBLEM
VALIDATE_PROBLEM
RUN_PDDL_PLANNER
VALIDATE_PLAN
COMPILE_PLAN_TO_BT
OPERATOR_APPROVAL
DRY_RUN_GATEWAY
DISPATCH_OR_HOLD
MONITOR_PROGRESS
TRIAGE_FAILURE
REQUEST_REPLAN
```

Each state reads and writes typed artifacts. Free-form text is allowed only inside explanation fields, never as an executable command.

## Runtime Port

Define the runtime boundary before implementing the state machine:

```text
MissionOpsRunner.run(input, config) -> MissionOpsResult
MissionOpsRunner.resume(run_id, input) -> MissionOpsResult
MissionOpsRunner.get_state(run_id) -> MissionOpsState
```

Phase 1 implementation:

```text
MissionManagerRunner
```

Future implementation, if needed:

```text
LangGraphMissionOpsRunner
```

External callers must depend on `MissionOpsRunner`, not directly on LangGraph or MissionManager internals.

## Persistent State

Persist mission workflow state from the first version, even without LangGraph:

```text
run_id
mission_id
current_state
input_artifact_refs
output_artifact_refs
approval_required
error
created_at
updated_at
```

Use JSON files or SQLite. This prevents a future LangGraph migration from requiring a new state model.

## Forbidden Paths

The model client, whether mock or real local model, must not:

- publish ROS topics
- call ROS services/actions directly
- output `/mavros/*`, `/cmd_vel`, or `/setpoints_cmd`
- choose low-level setpoints
- replace PDDL planning
- replace BT/state-machine execution
- replace platform gateway safety checks
- run on UAV/UGV platforms in phase 1
- use chat history as the mission blackboard

## LangGraph Comparison

| Topic | Use LangGraph in phase 1 production runtime | Use MissionManager in phase 1 |
| --- | --- | --- |
| Runtime complexity | higher | lower |
| Debugging | graph/checkpoint layer to inspect | direct Python state/logs |
| Human approval | built-in interrupt/resume is strong | explicit approval state is enough |
| Multi-agent roles | easy to add too early | delayed until needed |
| Safety boundary | requires discipline around tool nodes | easier to enforce in deterministic states |
| Current fit | premature | recommended |

Decision: use MissionManager now, keep tools and state LangGraph-ready.

## Dev-Only LangGraph Spike

After typed tools exist, a small non-production LangGraph spike is allowed:

```text
intent
-> compile_task_schema
-> validate_task_schema
-> generate_pddl_problem
```

The spike is only to verify that the tool boundary can be wrapped by a graph runtime. It must not dispatch to hardware and must not become required for the first working task-planning slice.

## When To Add LangGraph Later

Reconsider LangGraph if at least two are true:

- mission workflows must pause and resume across processes or days
- there are more than two human approval checkpoints
- execution trace replay becomes important
- multiple specialist agents are needed
- MissionManager state/log handling becomes hard to debug
- a UI needs live workflow state streaming

When added, LangGraph wraps `mission_ops` typed tools only:

```text
LangGraph Mission Ops Shell
-> typed tools
-> deterministic core
-> PDDL / validator / BT / gateway / ROS1
```

## First Build Slice

Implement this before any hardware dispatch:

1. `contracts/` with examples and validators
2. `ModelClient` interface
3. `MockLLMClient` backend for tests and command-driven phase 1
4. `MissionOpsRunner` interface
5. persistent `MissionOpsState` store
6. `MissionManager` state machine
7. minimal PDDL domain with 3 actions
8. mock planner output
9. plan-to-BT/state-machine artifact
10. mock platform gateway accepting `TaskCommand`
11. one synthetic `FailureReport` producing a replan request

## Agent Prompt

Use this prompt in a new agent interface:

```text
Read AGENTS.md first. Then read docs/superpowers/specs/2026-05-25-local-llm-mission-ops-architecture.md and the 2026-05-19 PDDL/BT/gateway specs.

Implement the first deterministic task-planning slice:
contracts -> ModelClient -> MockLLMClient -> MissionOpsRunner -> persistent MissionOpsState -> MissionManager -> minimal PDDL problem -> mock planner -> plan-to-BT -> mock gateway -> FailureReport to replan.

Do not add LangGraph as a phase-1 production dependency. Keep the tools LangGraph-ready and optionally add a dev-only spike after the typed tools exist. Do not touch vehicle-side ROS execution except through mock gateway tests. Keep ROS1, per-platform ROS masters, central PDDL authority, and no edge LLMs on UAV/UGV.
```
