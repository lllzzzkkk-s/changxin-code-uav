# Phase 2 Proof-To-Operations Plan

Date: 2026-06-02

## Final Proof Baseline

The distributed-fleet Phase 1 proof is closed from the unit RTX 4060 lane.

- Final status: `next_phase_ready`
- Goal evidence: `13 total / 13 passed / 0 missing / 0 failed`
- Archive: `D:\changxin\final-archives\changxin-distributed-fleet-final-proof-20260602.tar.gz`
- SHA256: `66465e2a1377e9f2dd11dc4136db9b92fa5d6e369f9f1c06c4a8a4c0ca850366`
- Execution semantics: `ugv_0 confirm_target(target_01)`, `manual_confirm`, no motion
- Negative proof claims: no `/move_base` call, no `/cmd_vel` publish, no LLM direct ROS control

This Mac-side note records the user-supplied final proof summary. It does not
claim live access to `D:\changxin`, does not reconnect to ROS, and does not
re-run dispatch.

## Verified Capability Boundary

The verified Phase 1 capability is a complete evidence chain for a bounded,
operator-approved, no-motion UGV `confirm_target` command through the mission
planning stack:

```text
operator intent or prevalidated schema
-> ModelClient boundary or mock output
-> TaskSchema / MissionRequest validator
-> mission blackboard
-> PDDL problem and plan
-> plan validator
-> PDDL-to-BT/state-machine artifact
-> platform gateway
-> local ROS1 gateway boundary
-> CommandAck / TaskProgress / hardware proof artifact
```

The proof validates the safety architecture, not general navigation authority.
It proves that the unit lane can close the evidence requirements while keeping
motion disabled for `manual_confirm`.

The home RTX 5090 lane remains a model-lab lane only. Its output may improve
`TaskSchema` drafts or explanations, but it is not a runtime dependency for the
unit hardware lane.

## Do Not Continue

Do not continue chasing Phase 1 proof by repeating dispatches. The closure
artifact is the baseline unless a verifier rejects the archive or SHA256.

Do not do any of the following as Phase 2 default work:

- no raw `/cmd_vel`, `/move_base`, `/mavros/*`, `/setpoints_cmd`, or arbitrary ROS topic publication from the center
- no ROS2 migration
- no LLM on UAV or UGV platforms
- no model replacement of PDDL, BT/state-machine execution, validator, gateway checks, or local ROS1 safety
- no home 5090 live dependency for unit execution
- no platform-local mission creation or PDDL replanning during disconnect
- no inferred or chat-derived target maps
- no controlled motion trial without a new local operator approval and a separate evidence plan
- no claim that this Mac can inspect `D:\changxin` or unit ROS state

## 4060 Unit Runbook

Use the unit RTX 4060 as the receiving and execution-evidence lane. Prefer
`D:\changxin\...` for durable Windows-side paths and WSL `/tmp` only for
ephemeral evidence work.

1. Confirm the final archive is present on the unit Windows machine:

```powershell
Get-FileHash `
  -Algorithm SHA256 `
  D:\changxin\final-archives\changxin-distributed-fleet-final-proof-20260602.tar.gz
```

Expected SHA256:

```text
66465e2a1377e9f2dd11dc4136db9b92fa5d6e369f9f1c06c4a8a4c0ca850366
```

2. Keep a local note that the final proof is no-motion:

```text
ugv_0 confirm_target(target_01)
action=manual_confirm
no /move_base
no /cmd_vel
no LLM direct ROS control
```

3. If receiving future handoff or artifact packages, use the Windows-safe entry
   point. It converts drive-letter paths such as `D:\...` into WSL paths such as
   `/mnt/d/...`, stages inputs, and lets WSL2 run repo verifiers:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\tools\windows_unit_receiving_entry.ps1 `
  -HandoffPackage D:\changxin\incoming\distributed-fleet-handoff-package.tar.gz `
  -HandoffSha256 <64-char-sha256> `
  -ArtifactPackage D:\changxin\incoming\task-planning-artifacts.tar.gz `
  -ArtifactSha256 <64-char-sha256>
```

4. For Phase 2 repo work on the unit lane, start with no-hardware checks:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_readiness.py \
  --profile profiles/work_hardware.env

PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
  --profile profiles/work_hardware.env

PYTHONDONTWRITEBYTECODE=1 python3 tools/plan_work_hardware_gate.py \
  --profile profiles/work_hardware.env \
  --through-stage mock_gateway_dispatch
```

5. Treat the next implementation target as operations hardening:
   BT runtime, run ledger, structured feedback ingestion, approval state, and
   repeatable evidence import. Do not turn the final no-motion proof into a
   motion test.

## 5090 Model-Lab Runbook

Use the RTX 5090 lane only to evaluate model output quality behind the same
`ModelClient` contract.

Allowed model-lab work:

- smoke-test an OpenAI-compatible local HTTP endpoint
- draft `TaskSchema.v1`
- compare output against the mock/golden baseline
- explain validator errors
- summarize failure reports
- package artifacts for transfer

Required constraints:

- `MISSION_PROFILE=home_model_lab`
- `MODEL_PROVIDER=local_http`
- `PLATFORM_BACKEND=mock`
- `MODEL_LAB_EVIDENCE_KIND=home_5090_live` only for a real 5090 run
- report includes baseline comparison fields, empty validation errors, hashed `machine_id`, and an accelerator probe showing RTX 5090

Typical commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_model_lab_endpoint.py \
  --profile profiles/home_model_lab.env

PYTHONDONTWRITEBYTECODE=1 python3 tools/evaluate_model_lab_case.py \
  --profile profiles/home_model_lab.env \
  --case uav_ugv_coordination \
  --output-dir /tmp/changxin-model-lab

PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_artifacts.py \
  --artifact /tmp/changxin-model-lab/uav_ugv_coordination \
  --output-dir /tmp/changxin-artifact-packages
```

The 5090 result is not hardware proof and must not be treated as a dispatch
dependency. Unit execution must remain runnable with mock or prevalidated
schemas when the home server is offline.

## ROS1 Gateway Lifecycle

The gateway lifecycle is staged. Each stage must leave machine-readable
evidence before the next one is considered.

1. Profile preparation
   - copy `profiles/work_hardware_ros1_gateway.env.template` to a local,
     uncommitted profile
   - fill real unit ROS values only on the unit machine
   - keep `HARDWARE_APPROVAL_REQUIRED=true`

2. Workspace preparation
   - run `tools/prepare_ros1_gateway_workspace.py` dry-run first
   - apply only to the intended unit catkin workspace
   - rebuild and source the workspace using the unit's normal ROS1 procedure

3. Read-only service audit
   - collect service names, service types, and service args
   - require `TaskCommandJson` and `task_command_json`
   - record hashed `machine_id`
   - no dispatch and no raw ROS topic publication

4. Artifact-derived command extraction
   - extract `TaskCommand.v1` from a validated artifact
   - do not hand-write ROS payloads

5. Gateway dry-run
   - dry-run proves service contract and local gateway checks
   - dry-run is a prerequisite, not final hardware proof

6. Approved dispatch
   - only after explicit local operator approval
   - final Phase 1 proof already used this for no-motion `manual_confirm`
   - future controlled motion requires a new plan and cannot inherit this approval

7. Evidence recording and import
   - capture dispatch response, accepted `CommandAck`, and matching `TaskProgress`
   - record a standard hardware artifact
   - import with `tools/import_distributed_fleet_external_evidence.py`
   - aggregate with `tools/check_distributed_fleet_goal_evidence.py`

## Artifact And Evidence Archive Verification

The final archive should be treated as immutable Phase 1 closure evidence.

Verification flow:

1. On the unit Windows machine, verify the archive SHA256 with `Get-FileHash`.
2. If the archive is transferred, verify the transferred copy again on the
   receiving machine before using it.
3. Do not unpack and mutate the closure evidence as a normal working directory.
4. For future model-lab or replay artifacts, package them with
   `tools/package_task_planning_artifacts.py`.
5. On the unit receiving side, verify artifact packages with:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py \
  <task-planning-artifacts.tar.gz> \
  --work-dir /tmp/changxin-artifact-verify \
  --verification-context unit_workplace_receiving
```

6. Reject package proof when source and verifier machine ids match under a
   receiving-machine context.
7. Prefer importing external proof through
   `tools/import_distributed_fleet_external_evidence.py` instead of manual copy.
8. After import, run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py \
  --evidence-dir /tmp/changxin-distributed-fleet-evidence
```

For Phase 1 closure, the expected aggregate result is already:

```text
13 total / 13 passed / 0 missing / 0 failed
```

## Controlled Motion Preconditions

No controlled motion is authorized by this document.

Before any future motion trial is even proposed, all of the following must be
true:

- local unit operator approves the exact mission, task, platform, target, time window, and abort plan
- target map is local, current, and operator-confirmed
- `confirm_target(target_01)` changes from `manual_confirm` to a bounded motion action only after a separate target-map update
- pose fields are explicit: frame id, x, y, yaw, max distance, and safety radius
- local UGV localization, battery, obstacle, E-stop, and recovery state are verified
- `/move_base` action server availability is verified locally if move_base is the selected executor
- read-only service audit and gateway dry-run pass for the same platform and command
- extracted `TaskCommand.v1` comes from a validated artifact, not from chat text
- operator approval is recorded as first-class mission state with scope and timestamp
- a stop/abort path is ready and assigned to a local operator
- expected evidence files are defined before execution: dispatch response, ack, progress, failure report if any, and archive hash
- final evidence must still show no center-side raw ROS topic publication

If any precondition is missing, the correct Phase 2 action is to stay in
no-hardware operations hardening.

## Open Risks

- The final archive and SHA256 are user-provided in this Mac session; this repo
  update does not independently inspect `D:\changxin`.
- Phase 2 BT runtime and run ledger are not yet implemented as repeatable
  operations infrastructure.
- Operator approval is still partly procedural and should become mission state.
- Gateway dry-run, dispatch, ack, and progress evidence must remain tied to the
  same `mission_id`, `task_id`, and `platform_id`.
- Model-lab prompt quality can regress; `http_model_client.py` must continue to
  enforce non-empty `TaskSchema.v1` fields and validators must reject weak model
  outputs.
- Future controlled motion may require site-specific UGV maps and executor
  wiring that should stay out of committed profiles.
- Dirty worktree state must be handled carefully before any PR or release
  closure; do not overwrite unrelated document, platform, profile, tool, or test
  changes already present in the repo.

## Immediate Phase 2 Next Step

Keep Phase 1 closed and implement the no-hardware operations slice:

1. add `BehaviorTreeRuntime` tests
2. implement deterministic BT artifact execution against a gateway abstraction
3. add a mission run ledger
4. ingest `CommandAck`, `TaskProgress`, `FailureReport`, `Heartbeat`, and `PlatformState`
5. make operator approval first-class state
6. re-run no-hardware unit tests, dev_mock golden suite, and lane matrix

## Phase 2A Mac-Side Implementation Result

Status: implemented and verified on the Mac Codex side only.

Changed scope:

- Added deterministic `BehaviorTreeRuntime` for existing `BehaviorTree.v1` artifacts.
- Added mission run ledger records under `<MISSION_ARTIFACT_ROOT>/_ledger/`.
- Added first-class operator approval state to persisted `MissionOpsState`.
- Added `execution_events.json` to new artifact bundles.
- Populated `command_acks.json` and `task_progress.json` from runtime output.
- Kept legacy artifact packages readable when they do not yet contain `execution_events.json`.
- Updated golden suite and lane matrix checks for Phase 2A event logs.

Verification run on this Mac:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  task_planning/execution/*.py \
  task_planning/mission_ops/*.py \
  platform_gateway/*.py

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests/task_planning

PYTHONDONTWRITEBYTECODE=1 python3 tools/run_dev_mock_golden_suite.py \
  --artifact-root /tmp/changxin-phase2a-dev-mock-golden-suite

PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_lane_matrix.py \
  --artifact-root /tmp/changxin-phase2a-lane-matrix \
  --case uav_ugv_coordination

PYTHONDONTWRITEBYTECODE=1 python3 tools/replay_task_planning_artifact.py \
  /tmp/changxin-phase2a-dev-mock-golden-suite/aef73297-9c6b-48bb-91f3-d6179f9d54e0
```

Observed results:

- `python3 -m unittest discover tests/task_planning`: `296` tests passed.
- `DevMockGoldenSuite.v1`: `ok=true`, all five required cases passed.
- `TaskPlanningLaneMatrix.v1`: `ok=true`, `dev_mock`, `server_sim`, and `work_hardware` pre-dispatch lanes passed.
- Replay of one Phase 2A artifact returned `ok=true`.
- Sample artifact had `ExecutionEventLog.v1`, `11` execution events, `3` command acks, `3` task progress records, and an accompanying ledger file.

Boundary statement:

- This verification did not access `D:\changxin`.
- This verification did not verify the unit final archive SHA256.
- This verification did not connect to ROS.
- This verification did not run `rosservice`, `rostopic`, or a ROS workspace.
- This verification did not perform real gateway or hardware dispatch.
- The only gateway calls were Python unit-test calls to `MockPlatformGateway.dispatch()`.

Remaining Phase 2B work:

- Add a dedicated no-motion acceptance report command.
- Improve replay diagnostics for operator-facing summaries.
- Define Qt/operator-view signals without adding raw ROS controls.
- Leave ROS1 gateway lifecycle hardening for Phase 3 on the unit 4060 side.
