# Distributed Fleet Phase 2 To LangGraph Roadmap

Date: 2026-06-02

## Baseline

This roadmap starts from the user-supplied Phase 1 closure baseline recorded in
`docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md`.

- Final status: `next_phase_ready`
- Goal evidence: `13 total / 13 passed / 0 missing / 0 failed`
- Final archive: `D:\changxin\final-archives\changxin-distributed-fleet-final-proof-20260602.tar.gz`
- SHA256: `66465e2a1377e9f2dd11dc4136db9b92fa5d6e369f9f1c06c4a8a4c0ca850366`
- Hardware proof semantics: `ugv_0 confirm_target(target_01)`, `manual_confirm`, no motion
- Negative proof claims: no `/move_base` call, no `/cmd_vel` publish, no LLM direct ROS control

This Mac-side roadmap does not inspect the Windows archive, does not connect to
ROS, and does not re-run dispatch. The archive is treated as immutable Phase 1
closure unless a verifier rejects the file or checksum.

## Stable Architecture

Preserve the current control chain:

```text
operator intent
-> command / CLI / agent-issued local call
-> ModelClient backed by MockLLMClient now, local_http/remote_http adapter later
-> TaskSchema / MissionRequest
-> schema validator
-> mission blackboard
-> PDDL problem generator
-> PDDL planner
-> plan validator
-> PDDL-to-BT/state-machine compiler
-> platform gateway
-> each platform local ROS1 master
```

Hard rules:

- ROS1 remains the runtime stack.
- Keep one ROS master per platform.
- The independent ground station remains the only global planner.
- PDDL remains the mission-level planning authority.
- Platform side executes validated `TaskCommand.v1` only.
- No edge LLM runs on UAV or UGV platforms.
- The home RTX 5090 remains model-lab only, not a runtime dependency.
- LangGraph, if introduced later, is only a ground-station Mission Ops shell.
- No LangGraph node may publish ROS topics, call raw ROS services, or bypass validators, PDDL, BT/runtime, gateway, or local ROS1.
- All real motion requires a separate local operator approval and evidence plan.

## Phase 2: No-Hardware Operations Hardening

Objective: turn the completed no-motion proof into repeatable repo-level
operations without touching live ROS or hardware.

Phase 2 is split so the first implementation slice stays small and testable.

### Phase 2A: Runtime, Ledger, Feedback, Approval

Scope:

- Add a deterministic `BehaviorTreeRuntime` for existing `BehaviorTree.v1` artifacts.
- Add a mission run ledger that records run metadata and execution events.
- Ingest `CommandAck`, `TaskProgress`, `FailureReport`, `Heartbeat`, and `PlatformState` into mission state or ledger events.
- Make operator approval first-class mission state with scope and freshness checks.
- Keep all Phase 2A execution against `MockPlatformGateway` or in-memory fixtures.
- Update artifacts so no-motion acceptance runs include command acks, progress, failure/replan records, and an event log.

Exit gate:

- Unit tests pass.
- `dev_mock` golden suite passes.
- No-model/no-hardware lane matrix passes.
- A no-motion acceptance artifact contains `execution_events.json`, non-empty command ack records, progress records for accepted commands, and approval state.
- No ROS service lookup, ROS publish, `/move_base`, `/cmd_vel`, `/mavros/*`, or `/setpoints_cmd` path is introduced.

Mac-side implementation result:

- Implemented in the repo on `2026-06-02`.
- Verified with Python compile, `296` task-planning unit tests, `dev_mock` golden suite, lane matrix, and one artifact replay.
- New artifacts include `execution_events.json` and `_ledger/<run_id>.ledger.json`.
- Verification stayed no-hardware and mock-only on the Mac side; it did not verify the unit archive, connect ROS, or perform real gateway/hardware dispatch.

### Phase 2B: Reports And Operator-Facing Operations

Scope:

- Add a repeatable no-motion acceptance command or report that summarizes BT runtime state, ledger events, approval state, and artifact health.
- Improve replay diagnostics so rejected ack, failure report, and central replan paths are visible without reading raw JSON by hand.
- Keep model-lab use optional and bounded to schema drafting, validator explanation, failure summary, and experiment logs.
- Prepare Qt/operator-view integration requirements without adding raw ROS controls.

Exit gate:

- A new agent can run no-hardware Phase 2 acceptance from docs.
- The report states Phase 1 archive identity and Phase 2 no-hardware run identity separately.
- Operator approval prompts and stale-approval rejection are visible in machine-readable output.

## Phase 3: Controlled ROS1 Gateway Execution Hardening

Objective: make ROS1 gateway lifecycle repeatable without uncontrolled motion.

Deliverables:

- Gateway start/stop lifecycle runbook or script.
- Signature audit automation for service name, type, and args.
- Dry-run response parsing.
- Manual-confirm gateway proof flow.
- Operator-approved no-motion proof reproducible on the unit 4060.
- Gateway trace schema stabilized across dry-run and dispatch evidence.

Exit gate:

- Gateway `dry_run` and `dispatch` signatures are visible.
- Manual-confirm proof is repeatable.
- No `/cmd_vel`, `/move_base`, `/mavros/*`, or raw topic command is issued by the center.
- Evidence archive is generated and hashable.

## Phase 4: Controlled Motion Validation

Objective: only after Phase 2 and Phase 3 pass, design and run the first
bounded motion test.

Deliverables:

- Controlled motion preflight checklist.
- Emergency stop and abort procedure.
- Minimal low-speed, short-distance motion case.
- Operator approval record scoped to mission, task, platform, target, and time window.
- Motion artifact with `CommandAck`, `TaskProgress`, and `FailureReport` if any.
- Proof that the center still sends only `TaskCommand.v1` through the gateway.

Exit gate:

- One bounded motion test passes.
- No raw ROS bypass occurs.
- Failure or abort path is tested or explicitly simulated.
- Hardware artifact is accepted by the goal evidence checker.

## Phase 5: Multi-Platform Fleet Expansion

Objective: extend from UGV-only proof toward UAV/UGV coordination while
preserving one ROS master per platform.

Deliverables:

- Platform registry for UGV and UAV platforms.
- Per-platform gateway contracts.
- PDDL-to-BT multi-platform execution.
- Disconnect handling: continue authorized subtree only.
- `FailureReport` to central replan path.
- Sim-first UAV lane before real UAV hardware.

Exit gate:

- Multi-platform `dev_mock` and `server_sim` pass.
- At least one real UGV gateway path remains valid.
- UAV path is simulated or read-only until separately approved.

## Phase 6: Optional LangGraph Orchestration

Objective: evaluate whether LangGraph is useful as a ground-station Mission Ops
shell after deterministic tools and state are stable.

Allowed LangGraph responsibilities:

- Intake operator intent.
- Call mock or model-lab `ModelClient`.
- Run validator tools.
- Call PDDL planner tools.
- Call BT runtime tools.
- Request operator approval.
- Record ledger events.
- Route `FailureReport` to central replan.
- Replay traces.

Forbidden LangGraph responsibilities:

- Direct ROS publish.
- Direct `/cmd_vel`, `/move_base`, `/mavros/*`, or raw ROS service calls.
- Bypass validator, PDDL, BT/runtime, gateway, or local ROS1.
- Platform-local mission planning.
- Edge LLM control.

Exit gate:

- LangGraph prototype passes `dev_mock` only.
- Shadow-mode replay matches existing ledger.
- No production runtime switch occurs until parity is proven.
- Existing non-LangGraph runner remains available.

## Phase 7: Operationalization

Objective: turn the validated system into maintainable operations.

Deliverables:

- CI test suite.
- Evidence archive checklist.
- Operator runbook.
- Incident and failure playbook.
- Dashboard or report for mission runs.
- Model-lab evaluation schedule.
- Release gates for future hardware motion.

Exit gate:

- A new agent can run the workflow from docs.
- Evidence can be reproduced and archived.
- Hardware actions remain gated and auditable.

## Immediate Next Task

Start only Phase 2A. Do not implement all phases at once.

Required Phase 2A planning artifact:

- `docs/superpowers/plans/2026-06-02-phase-2a-no-hardware-operations-hardening.md`

Phase 2A must produce a file-by-file implementation plan before code edits.
The plan must keep Phase 2A limited to no-hardware operations hardening:

- `BehaviorTreeRuntime`
- mission run ledger
- ack, progress, failure, heartbeat, and platform-state ingestion
- operator approval state
- no-motion acceptance tests

Do not dispatch subagents, do not connect to ROS, and do not run hardware or
gateway dispatch while preparing this roadmap and plan.
