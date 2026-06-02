# Next Phase: Mission Execution Hardening

## Baseline

The distributed-fleet proof chain is treated as closed:

- `phase_gate.status=next_phase_ready`
- goal evidence: `13 total / 13 passed / 0 missing / 0 failed`
- final proof archive and SHA256 are stored outside the repo
- final hardware proof was `unit_hardware_execution_artifact_verified`
- execution semantics were `ugv_0 confirm_target(target_01)`, `manual_confirm`, no motion
- no `/move_base` call, no `/cmd_vel` publish, no LLM direct ROS control

Do not keep dispatching just to make the proof feel stronger. The next phase starts from this archived baseline.

## Phase 2 Objective

Turn the one-time verified proof path into a repeatable mission execution loop:

```text
MissionRequest / TaskSchema
-> validator
-> mission blackboard
-> PDDL problem
-> PDDL plan
-> plan validator
-> task-level BT/state-machine runtime
-> platform gateway
-> CommandAck / TaskProgress / FailureReport
-> persisted mission run ledger
```

The core change is moving from "we can prove a validated command reached a safe gateway boundary" to "we can repeatedly run, monitor, pause, resume, and diagnose a mission without violating the safety boundary."

## Non-Goals

- Do not add ROS2.
- Do not put an LLM on UGV/UAV platforms.
- Do not let any model publish ROS topics or replace PDDL, BT/state-machine execution, platform gateway checks, or local ROS1.
- Do not add LangGraph as the production runtime in this phase.
- Do not use `/cmd_vel`, `/move_base`, `/mavros/*`, or raw ROS topic publication from the center.
- Do not perform another hardware dispatch unless a later, separately approved phase asks for it.

## Workstreams

### 1. Baseline Lock

Owner files:

- archived proof under the 4060 WSL evidence archive location
- `reports/phase_gate.json` or the final goal evidence report in the external evidence directory
- this spec

Actions:

- Keep the final proof archive and SHA256 outside git.
- Do not re-import or mutate final proof evidence unless a verifier rejects it.
- Add a short run note in future reports saying Phase 1 proof is closed and Phase 2 starts from `next_phase_ready`.

### 2. BT Runtime, Not Just BT Artifact

Current code can compile a PDDL plan into a `BehaviorTree.v1` artifact. Phase 2 needs a deterministic runtime that can execute that artifact against a gateway abstraction.

Target module:

- `task_planning/execution/bt_runtime.py`

Expected behavior:

- load a `BehaviorTree.v1`
- dispatch each `TaskCommand.v1` through the configured gateway
- wait for `CommandAck`
- ingest `TaskProgress`
- stop on rejected ack
- turn failures into `FailureReport`
- request central replan instead of platform-local replanning
- write a complete mission-run event log

First tests:

- sequential happy path with mock gateway
- rejected command creates a failure record and stops the tree
- failure report triggers `REQUEST_REPLAN`
- disconnected platform can continue only an already accepted subtree
- no runtime path publishes raw ROS topics

### 3. Mission Run Ledger

Current artifacts prove individual runs. Phase 2 needs a searchable run ledger.

Target modules:

- `task_planning/mission_ops/run_ledger.py`
- or an extension of `task_planning/mission_ops/state_store.py`

Minimum record:

```json
{
  "schema": "MissionRunRecord.v1",
  "run_id": "...",
  "case_id": "...",
  "mission_id": "...",
  "profile": "dev_mock|server_sim|work_hardware",
  "model_provider": "mock|local_http|remote_http",
  "platform_backend": "mock|sim|ros1_gateway",
  "phase_baseline": "next_phase_ready",
  "artifact_bundle_path": "...",
  "current_state": "...",
  "operator_approval": {
    "required": true,
    "approved": false,
    "source": null
  },
  "events": []
}
```

The ledger is not chat history. It is the mission blackboard/run history source for debugging and later replay.

### 4. Platform Feedback Ingestion

Phase 2 should consume structured platform feedback instead of treating gateway dispatch as the end of execution.

Contracts already available:

- `CommandAck`
- `TaskProgress`
- `FailureReport`
- `Heartbeat`
- `PlatformState`

Required behavior:

- accepted ack updates the task state
- progress updates the mission blackboard
- failure report triggers central triage and replan request
- heartbeat loss marks the platform degraded
- platform-local code must not invent a new mission or rebuild a PDDL plan

### 5. Operator Approval As A First-Class State

Operator approval should be represented in the mission state, not as an informal shell convention.

Target behavior:

- approval is required before any real `ros1_gateway` dispatch
- approval source is recorded
- approval has scope: mission id, task id, platform id, target id, timestamp, operator note
- stale approval is rejected
- dry-run and read-only checks remain possible without approval

### 6. Model-Lab Use Is Optional And Bounded

The 5090 lane can be used again only as a model-capability lane:

- draft `TaskSchema`
- explain validator errors
- summarize failure reports
- propose operator-review text

It must not:

- publish ROS
- bypass validators
- replace PDDL
- replace BT/runtime
- be required by the work hardware lane

### 7. Qt / Operator View Integration

The Qt side should remain an operator view and command surface, not a raw controller.

Good Phase 2 UI signals:

- current mission id and task id
- current BT node/state
- platform state
- gateway ack/reject reason
- progress/failure messages
- planned path/status if the local platform publishes them
- operator approval prompts

Forbidden UI behavior:

- direct `/cmd_vel`
- unvalidated free-form ROS topic publishing
- sending a target that bypasses TaskCommand / gateway safety checks

## First Sprint

Implement only the no-hardware deterministic slice:

1. Add tests for `BehaviorTreeRuntime`.
2. Implement `task_planning/execution/bt_runtime.py`.
3. Add a mission-run ledger or extend the existing JSON state store.
4. Wire the runner so a golden case can produce both:
   - the existing artifact bundle
   - a chronological execution event log
5. Add tests for rejected ack, failure-to-replan, and disconnect-continuation.
6. Re-run the no-hardware gates.

Suggested commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  task_planning/execution/*.py \
  task_planning/mission_ops/*.py \
  platform_gateway/*.py

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests/task_planning

PYTHONDONTWRITEBYTECODE=1 python3 tools/run_dev_mock_golden_suite.py \
  --artifact-root /tmp/changxin-phase2-dev-mock-golden-suite

PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_lane_matrix.py \
  --artifact-root /tmp/changxin-phase2-lane-matrix \
  --case uav_ugv_coordination
```

These commands must not call hardware dispatch.

## Phase 2 Acceptance Gates

Phase 2 is ready for the next hardware discussion only when:

- all task-planning unit tests pass
- dev_mock golden suite still passes
- lane matrix still passes without real model or hardware dependency
- BT runtime writes an event log for every dispatched task
- rejected gateway ack creates a structured failure path
- failure report requests central replan
- operator approval is represented in state
- no center-side raw ROS topic publication is introduced

## Stop Conditions

Stop and ask before proceeding if:

- a proposed change would use ROS2
- a proposed change would put a model on a platform
- a proposed change would let the center publish raw ROS topics
- a test requires real hardware dispatch
- final proof evidence appears inconsistent with `next_phase_ready`
- the dirty worktree contains unrelated user edits in files that the next code slice must modify
