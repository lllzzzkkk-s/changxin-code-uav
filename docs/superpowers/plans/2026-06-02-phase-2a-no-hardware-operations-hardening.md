# Phase 2A No-Hardware Operations Hardening Implementation Plan

> **For agentic workers:** Current instruction forbids dispatch. Use `superpowers:executing-plans` inline only after the user explicitly approves implementation. Do not use subagent dispatch unless the user explicitly lifts that constraint. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first Phase 2 operations slice: deterministic BT runtime, mission run ledger, structured feedback ingestion, operator approval state, and no-motion acceptance artifacts.

**Architecture:** Keep the existing ground-station chain: `TaskSchema -> validator -> blackboard -> PDDL -> plan validator -> BT artifact -> BT runtime -> platform gateway abstraction -> feedback ingestion -> central replan`. Phase 2A uses `MockPlatformGateway` and fixture feedback only; it does not instantiate `Ros1ServiceGateway`, run `rosservice`, publish ROS topics, or touch hardware.

**Tech Stack:** Python dataclasses, `unittest`, JSON artifact files, existing `MissionManagerRunner`, existing contract models, existing mock gateway, existing dev_mock golden suite and lane matrix.

---

## Scope Check

Phase 2A implements one subsystem: no-hardware mission execution hardening. It does not add LangGraph, ROS2, edge LLMs, ROS1 gateway lifecycle commands, controlled motion, Qt UI behavior, or platform-local replanning.

Stop before implementation if a proposed step needs any of these:

- `PLATFORM_BACKEND=ros1_gateway`
- `rosservice`, `rostopic`, `rosnode`, or a sourced ROS workspace
- `/cmd_vel`, `/move_base`, `/mavros/*`, `/setpoints_cmd`, or any raw ROS topic path as an executable target
- hardware dispatch
- subagent dispatch

## File Structure

- Create: `task_planning/execution/bt_runtime.py`
  - Responsibility: execute existing `BehaviorTree.v1` task commands against a gateway abstraction, produce a deterministic `BehaviorTreeRunResult.v1`, event log, command acks, task progress, and failure report or central replan request.
- Modify: `task_planning/execution/__init__.py`
  - Responsibility: export `BehaviorTreeRuntime`, `BehaviorTreeRunResult`, and event dataclasses.
- Create: `task_planning/mission_ops/run_ledger.py`
  - Responsibility: define `MissionRunRecord.v1`, `MissionRunEvent.v1`, `OperatorApprovalState.v1`, and a JSON ledger store.
- Modify: `task_planning/mission_ops/state.py`
  - Responsibility: add approval metadata and execution event refs without changing the `MissionOpsRunner` public port.
- Modify: `task_planning/mission_ops/mission_manager.py`
  - Responsibility: preserve current planning states, add first-class approval metadata, and add a resume path for structured feedback if the runner provides it.
- Modify: `task_planning/mission_ops/runner.py`
  - Responsibility: wire `BehaviorTreeRuntime` and run ledger for non-hardware profiles while preserving current status behavior for `dev_mock`, `server_sim`, and approval-gated `work_hardware`.
- Modify: `task_planning/mission_ops/artifacts.py`
  - Responsibility: write `execution_events.json`, populated `task_progress.json`, populated `command_acks.json`, approval state, and ledger metadata into artifact bundles.
- Modify: `task_planning/mission_ops/replay.py`
  - Responsibility: load and compare new artifact files while keeping existing artifact bundles backward compatible.
- Modify: `task_planning/migration/golden_suite.py`
  - Responsibility: require Phase 2A event-log fields for `dev_mock` golden cases.
- Modify: `task_planning/migration/lane_matrix.py`
  - Responsibility: compare Phase 2A event artifacts across `dev_mock`, `server_sim`, and `work_hardware` pre-dispatch lanes with the existing work-hardware allowance.
- Create: `tests/task_planning/test_bt_runtime.py`
  - Responsibility: unit-test happy path, rejected ack, failure report, disconnect continuation, and raw ROS boundary.
- Create: `tests/task_planning/test_run_ledger.py`
  - Responsibility: unit-test mission run record creation, event append, approval scope, stale approval rejection, and JSON reload.
- Modify: `tests/task_planning/test_mission_ops_dry_run.py`
  - Responsibility: assert runner output includes execution events, progress, approval metadata, and replan behavior.
- Modify: `tests/task_planning/test_profiles_artifacts_golden_cases.py`
  - Responsibility: assert artifacts include Phase 2A files and no-motion acceptance data.
- Modify: `docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md`
  - Responsibility: append Phase 2A implementation result and commands after implementation succeeds.

## Public Interfaces To Preserve

- Keep `MissionOpsRunner.run(input, config) -> MissionOpsResult`.
- Keep `MissionOpsRunner.resume(run_id, input) -> MissionOpsResult`.
- Keep `MissionOpsRunner.get_state(run_id) -> MissionOpsState`.
- Keep `ModelClient` as the only model boundary.
- Keep `TaskCommand.v1` as the only center-to-gateway command payload.
- Keep `MockPlatformGateway.dispatch(command) -> CommandAck` as the Phase 2A gateway dependency.

## New Schemas

Use these schema names consistently in tests and artifacts:

- `BehaviorTreeRunResult.v1`
- `MissionRunEvent.v1`
- `MissionRunRecord.v1`
- `OperatorApprovalState.v1`
- `ExecutionEventLog.v1`

Minimum `MissionRunEvent.v1` fields:

- `schema`
- `run_id`
- `mission_id`
- `task_id`
- `platform_id`
- `event_type`
- `timestamp`
- `payload`

Allowed Phase 2A event types:

- `bt_runtime_started`
- `task_dispatch_requested`
- `command_ack_accepted`
- `command_ack_rejected`
- `task_progress_observed`
- `failure_report_recorded`
- `central_replan_requested`
- `operator_approval_required`
- `operator_approval_recorded`
- `heartbeat_observed`
- `platform_state_observed`
- `bt_runtime_completed`

Minimum `OperatorApprovalState.v1` fields:

- `schema`
- `required`
- `approved`
- `source`
- `mission_id`
- `task_id`
- `platform_id`
- `target_id`
- `approved_at`
- `expires_at`
- `operator_note`

## Task 1: Add BT Runtime Tests First

**Files:**
- Create: `tests/task_planning/test_bt_runtime.py`

- [ ] **Step 1: Write `test_runtime_dispatches_bt_commands_and_records_progress_without_ros`**

Test setup:

- Build a `TaskSchema` with `MockLLMClient`.
- Build PDDL problem, mock plan, and BT artifact through existing helpers.
- Run `BehaviorTreeRuntime(gateway=MockPlatformGateway()).run(bt, run_id="run_phase2a_001")`.

Expected assertions:

- result schema is `BehaviorTreeRunResult.v1`.
- result status is `completed`.
- three command acks are accepted.
- three progress items exist with statuses ending in `completed`.
- every gateway trace record has `publish_attempted is False`.
- event types include `bt_runtime_started`, `task_dispatch_requested`, `command_ack_accepted`, `task_progress_observed`, and `bt_runtime_completed`.

- [ ] **Step 2: Write `test_runtime_stops_on_rejected_ack_and_records_failure`**

Test setup:

- Create a valid BT artifact, then replace one command platform id with an unknown platform id.
- Run the runtime with `MockPlatformGateway`.

Expected assertions:

- result status is `failed`.
- rejected ack reason includes `unknown platform_id`.
- a `FailureReport.v1` exists.
- event types include `command_ack_rejected`, `failure_report_recorded`, and `central_replan_requested`.
- no later task is dispatched after the rejected command.

- [ ] **Step 3: Write `test_runtime_disconnect_policy_does_not_create_new_platform_plan`**

Test setup:

- Run a BT artifact whose commands keep `disconnect_policy="continue_current_task"`.
- Inject a heartbeat fixture with `gateway_status="alive"` and then a degraded fixture for the already accepted platform.

Expected assertions:

- runtime records heartbeat/platform-state events.
- result does not include any event type named `platform_replan_created`.
- result does not include any new `TaskCommand` that was not present in the original BT artifact.

- [ ] **Step 4: Run only the new test and verify it fails before implementation**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.task_planning.test_bt_runtime -v
```

Expected before implementation: import failure for `task_planning.execution.bt_runtime` or missing runtime symbols.

## Task 2: Implement `BehaviorTreeRuntime`

**Files:**
- Create: `task_planning/execution/bt_runtime.py`
- Modify: `task_planning/execution/__init__.py`

- [ ] **Step 1: Add runtime dataclasses**

Define frozen dataclasses:

- `MissionRunEvent`
- `BehaviorTreeRunResult`

Include `as_dict()` methods on both. Use `task_planning.contracts.utc_timestamp` for timestamps.

- [ ] **Step 2: Add `BehaviorTreeRuntime.__init__`**

Constructor inputs:

- `gateway`
- optional `run_id`
- optional `heartbeat_events`
- optional `platform_state_events`

The gateway object only needs a `dispatch(TaskCommand) -> CommandAck` method.

- [ ] **Step 3: Add `BehaviorTreeRuntime.run`**

Behavior:

- Accept a `BehaviorTreeArtifact` or `BehaviorTree.v1` mapping.
- Convert mapping commands with `TaskCommand.from_dict`.
- Record `bt_runtime_started`.
- For each command:
  - record `task_dispatch_requested`.
  - call `gateway.dispatch(command)`.
  - record accepted or rejected ack.
  - on accepted ack, create one deterministic `TaskProgress.v1` with `status="completed"`, `progress_ratio=1.0`, and message `mock gateway completed capability <capability>`.
  - on rejected ack, create `FailureReport.v1` with `failure_type="safety_gate_reject"`, `recoverable=True`, and reason from the ack; stop the loop and record `central_replan_requested`.
- Record heartbeat and platform-state fixture events without creating new commands.
- Return `BehaviorTreeRunResult`.

- [ ] **Step 4: Export runtime symbols**

Update `task_planning/execution/__init__.py` so tests can import:

```python
from task_planning.execution import BehaviorTreeRuntime, BehaviorTreeRunResult, MissionRunEvent
```

- [ ] **Step 5: Run BT runtime tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.task_planning.test_bt_runtime -v
```

Expected after implementation: all tests in `test_bt_runtime.py` pass.

## Task 3: Add Run Ledger Tests First

**Files:**
- Create: `tests/task_planning/test_run_ledger.py`

- [ ] **Step 1: Write `test_ledger_creates_record_and_appends_events`**

Test setup:

- Create a temp directory.
- Create `JsonMissionRunLedger(root)`.
- Create a `MissionRunRecord` with run id, case id, mission id, profile, model provider, platform backend, phase baseline `next_phase_ready`, and artifact path.
- Append a `bt_runtime_started` event.
- Reload the record.

Expected assertions:

- schema is `MissionRunRecord.v1`.
- event count is one after reload.
- `phase_baseline` is `next_phase_ready`.
- `artifact_bundle_path` matches the input path.

- [ ] **Step 2: Write `test_operator_approval_scope_and_expiration_are_validated`**

Test setup:

- Create one approval with matching mission/task/platform/target and a future expiration.
- Create one approval with a mismatched task id.
- Create one approval with an expired `expires_at`.

Expected assertions:

- matching approval validates with no errors.
- mismatched task approval returns an error mentioning task scope.
- expired approval returns an error mentioning stale approval.

- [ ] **Step 3: Run only ledger tests and verify they fail before implementation**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.task_planning.test_run_ledger -v
```

Expected before implementation: import failure for `task_planning.mission_ops.run_ledger`.

## Task 4: Implement Mission Run Ledger

**Files:**
- Create: `task_planning/mission_ops/run_ledger.py`

- [ ] **Step 1: Add approval dataclass**

Define `OperatorApprovalState` with schema `OperatorApprovalState.v1`, `as_dict()`, and `from_dict()`.

- [ ] **Step 2: Add approval validation**

Define `validate_operator_approval(approval, *, mission_id, task_id, platform_id, target_id, now=None) -> List[str]`.

Rules:

- If `approval.required` is false, return no errors.
- If required and not approved, return `operator approval is required`.
- If approved, `source` must be non-empty.
- If scoped fields are provided, they must match the expected mission/task/platform/target values.
- If `expires_at` is earlier than `now`, return `operator approval is stale`.

- [ ] **Step 3: Add record and store**

Define:

- `MissionRunRecord`
- `JsonMissionRunLedger`

Store each run as `<run_id>.ledger.json`. Save JSON with sorted keys and indentation, matching `JsonMissionOpsStateStore` style.

- [ ] **Step 4: Run ledger tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.task_planning.test_run_ledger -v
```

Expected after implementation: all ledger tests pass.

## Task 5: Wire Runtime And Ledger Into Runner

**Files:**
- Modify: `task_planning/mission_ops/runner.py`
- Modify: `task_planning/mission_ops/mission_manager.py`
- Modify: `task_planning/mission_ops/state.py`
- Modify: `tests/task_planning/test_mission_ops_dry_run.py`

- [ ] **Step 1: Extend state with approval metadata**

Add optional `approval_state` and `execution_event_refs` fields to `MissionOpsState`. Preserve backward compatibility in `from_dict()` by defaulting missing fields.

- [ ] **Step 2: Keep current planning path intact**

`MissionManager.start()` should still:

- compile task schema
- validate schema
- update blackboard
- generate and validate PDDL problem
- run and validate PDDL plan
- compile BT
- stop at `OPERATOR_APPROVAL` for approval-gated work hardware
- run no-hardware dry-run for non-approval profiles

- [ ] **Step 3: Replace ad hoc dry-run output with runtime output for non-hardware profiles**

In `MissionManagerRunner.run()` after BT compilation and before artifact writing:

- For `dev_mock` and `server_sim`, run `BehaviorTreeRuntime`.
- For `work_hardware` with `HARDWARE_APPROVAL_REQUIRED=true`, do not run runtime dispatch; record `operator_approval_required` and keep gateway trace empty.
- Preserve existing statuses:
  - `dev_mock` and `server_sim`: `dry_run_complete`
  - `work_hardware`: `approval_required`
  - rejected ack: `failed`

- [ ] **Step 4: Create or update ledger records**

Use `JsonMissionRunLedger` under `<MISSION_ARTIFACT_ROOT>/_ledger` when artifact root is configured. Store profile, case id, mission id, model provider, platform backend, artifact bundle path, approval state, and runtime events.

- [ ] **Step 5: Update mission ops dry-run tests**

Add assertions:

- result state includes approval state.
- output refs include `execution_events`.
- output refs include `task_progress`.
- output refs include runtime-generated `gateway_acks`.
- work hardware profile still stops at approval and has empty gateway trace.

- [ ] **Step 6: Run mission ops tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.task_planning.test_mission_ops_dry_run -v
```

Expected: existing and new mission ops tests pass.

## Task 6: Update Artifacts And Replay

**Files:**
- Modify: `task_planning/mission_ops/artifacts.py`
- Modify: `task_planning/mission_ops/replay.py`
- Modify: `tests/task_planning/test_profiles_artifacts_golden_cases.py`

- [ ] **Step 1: Add artifact filename**

Add `execution_events.json` to `ARTIFACT_FILENAMES`.

- [ ] **Step 2: Write populated Phase 2A artifacts**

`write_artifact_bundle()` should write:

- `command_acks.json` from output ref `gateway_acks`.
- `task_progress.json` from output ref `task_progress`.
- `failure_report.json` from output ref `failure_report`.
- `replan_decision.json` from output ref `replan_request`.
- `execution_events.json` from output ref `execution_events`.
- `run_summary.md` lines for approval state and event count.

- [ ] **Step 3: Keep old bundles loadable**

`load_artifact_bundle()` should not fail when an older bundle lacks `execution_events.json`. It should report the missing file as acceptable only for pre-Phase-2A bundles, while new golden runs must require it.

- [ ] **Step 4: Update artifact tests**

Add assertions that a `dev_mock` artifact bundle contains:

- `execution_events.json`
- `command_acks.json` with accepted items
- `task_progress.json` with completed items
- `run_summary.md` mentioning approval state

- [ ] **Step 5: Run artifact tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.task_planning.test_profiles_artifacts_golden_cases -v
```

Expected: updated artifact tests pass.

## Task 7: Update Golden Suite And Lane Matrix Validation

**Files:**
- Modify: `task_planning/migration/golden_suite.py`
- Modify: `task_planning/migration/lane_matrix.py`
- Modify: `tests/task_planning/test_golden_suite.py`
- Modify: `tests/task_planning/test_lane_matrix.py`

- [ ] **Step 1: Require Phase 2A fields for `dev_mock`**

Golden suite validation should require:

- `execution_events.json.schema == "ExecutionEventLog.v1"`
- at least one `bt_runtime_completed` event for normal cases
- accepted ack records for normal cases
- task progress records for normal cases
- failure and central replan events for `failure_and_replan`

- [ ] **Step 2: Preserve work hardware pre-dispatch behavior**

Lane matrix should continue to allow `work_hardware` to stop at `OPERATOR_APPROVAL` with empty gateway trace. It should require an `operator_approval_required` event instead of task dispatch events for that lane.

- [ ] **Step 3: Run focused migration tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.task_planning.test_golden_suite \
  tests.task_planning.test_lane_matrix \
  -v
```

Expected: golden suite and lane matrix tests pass.

## Task 8: Run No-Hardware Acceptance Gates

**Files:**
- No code file changes in this task.
- Output goes to `/tmp/changxin-phase2-*`.

- [ ] **Step 1: Run syntax gate**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  task_planning/execution/*.py \
  task_planning/mission_ops/*.py \
  platform_gateway/*.py
```

Expected: command exits `0`.

- [ ] **Step 2: Run all task-planning unit tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests/task_planning
```

Expected: command exits `0`.

- [ ] **Step 3: Run dev_mock golden suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_dev_mock_golden_suite.py \
  --artifact-root /tmp/changxin-phase2a-dev-mock-golden-suite
```

Expected: report has `"ok": true`.

- [ ] **Step 4: Run no-model/no-hardware lane matrix**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_lane_matrix.py \
  --artifact-root /tmp/changxin-phase2a-lane-matrix \
  --case uav_ugv_coordination
```

Expected: report has `"ok": true`; `work_hardware` remains approval-gated and does not dispatch.

- [ ] **Step 5: Inspect one no-motion artifact**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/replay_task_planning_artifact.py \
  /tmp/changxin-phase2a-dev-mock-golden-suite/<run_id>
```

Expected: replay validates the artifact and includes Phase 2A files. Replace `<run_id>` with a run id printed by the golden suite.

## Task 9: Update Phase 2 Docs After Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md`
- Modify: `docs/superpowers/specs/2026-06-02-distributed-fleet-phase-2-to-langgraph-roadmap.md`

- [ ] **Step 1: Add implementation result section**

Append a concise Phase 2A result section after all acceptance gates pass. Include:

- changed files
- test commands
- artifact root paths
- proof that no ROS commands were run
- proof that no hardware dispatch occurred
- remaining Phase 2B work

- [ ] **Step 2: Do not mark Phase 3 started**

Keep Phase 3 as pending until the user explicitly asks for ROS1 gateway lifecycle hardening.

## Final Acceptance Criteria

Phase 2A is complete only when all are true:

- `BehaviorTreeRuntime` executes existing `BehaviorTree.v1` artifacts against mock gateway.
- Runtime records deterministic events, command acks, progress, and failure/replan records.
- Run ledger persists and reloads `MissionRunRecord.v1`.
- Operator approval state is scoped and stale approvals are rejected.
- `dev_mock` and `server_sim` can run the runtime path without model or hardware dependencies.
- `work_hardware` pre-dispatch still stops at operator approval.
- Artifact bundles include `execution_events.json`, populated `command_acks.json`, populated `task_progress.json`, approval metadata, and existing contract files.
- Unit tests, dev_mock golden suite, and lane matrix pass.
- No code path in Phase 2A connects ROS, calls `rosservice`, publishes raw ROS topics, or performs hardware dispatch.
