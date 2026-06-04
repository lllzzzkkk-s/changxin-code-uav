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

4060 no-dispatch receipt:

- Received on `2026-06-03` from the unit RTX 4060 Codex session.
- The 4060 side synchronized GitHub branch `codex/phase2a-no-hardware-ops` and confirmed head `1f55373`.
- The 4060 side reported `296` task-planning tests passed.
- The 4060 side reported `work_hardware` readiness `ok=True`, site acceptance `ok=True`, `acceptance_level='work_hardware_pre_dispatch_ready'`, and `platform_backend='mock'`.
- The 4060 side reported no non-convex alpha document work, no repo architecture rewrite, no dispatch, no real ROS connection, and no ROS read-only stage.
- Evidence receipt: `docs/superpowers/evidence/2026-06-03-ugv-phase-2a-4060-no-dispatch-receipt.md`.

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

Mac-side implementation result on 2026-06-03:

- Implemented `Phase2NoMotionAcceptanceReport.v1` and
  `tools/check_phase2_no_motion_acceptance.py`.
- Implemented `ArtifactReplayDiagnosticSummary.v1` and
  `tools/replay_task_planning_artifact.py --summary`.
- Added read-only operator-view signal requirements in
  `docs/superpowers/specs/2026-06-03-phase-2b-operator-view-signals.md`.
- Added Phase 2 roadmap, Phase 2B plan/spec, and the Phase 2B acceptance CLI to
  the task-planning migration bundle.
- Verified on Mac with `302` task-planning tests, a fresh `dev_mock`
  `single_ugv_inspection` artifact, `Phase2NoMotionAcceptanceReport.v1`
  `ok=true`, and `ArtifactReplayDiagnosticSummary.v1` `ok=true`.

Boundary:

- Mac-side Phase 2B did not access `D:\changxin`.
- Mac-side Phase 2B did not verify the unit archive.
- Mac-side Phase 2B did not connect to ROS or run `rosservice`, `rostopic`, or
  `rosnode`.
- Mac-side Phase 2B did not run gateway `dry_run`, gateway `dispatch`, hardware
  proof, or controlled motion.

4060 no-dispatch receipt:

- Received on `2026-06-03` from the unit RTX 4060 Codex session.
- The 4060 side synchronized GitHub branch
  `codex/phase2b-no-hardware-reporting` and confirmed head `f506515`.
- The 4060 side reported `12` focused Phase 2B tests passed and `302` full
  task-planning tests passed.
- The 4060 side generated
  `/tmp/changxin-phase2b-no-motion-acceptance/phase2_no_motion_acceptance.json`
  with `schema='Phase2NoMotionAcceptanceReport.v1'`, `ok=True`,
  `platform_backend='mock'`, `ros_connected=False`,
  `dispatch_performed=False`, `hardware_proof=False`,
  `controlled_motion_authorized=False`, and `validation_errors=[]`.
- The 4060 side generated
  `/tmp/changxin-phase2b-no-motion-acceptance/replay_summary.json` with
  `schema='ArtifactReplayDiagnosticSummary.v1'`, `ok=True`,
  `current_state='DISPATCH_OR_HOLD'`, `accepted_commands=3`,
  `rejected_commands=0`, `progress_count=3`, `replan_requested=False`,
  `approval_required=False`, and `validation_errors=[]`.
- The 4060 side reported the Phase 1 archive existed on the unit machine and
  matched SHA256
  `66465e2a1377e9f2dd11dc4136db9b92fa5d6e369f9f1c06c4a8a4c0ca850366`.
- The 4060 side reported no non-convex alpha document work, no
  `rosservice`/`rostopic`/`rosnode`, no real ROS connection, no ROS gateway
  `dry_run`, no ROS gateway `dispatch`, and `gateway_trace publish_attempted=false`
  for all `3` records.
- Evidence receipt:
  `docs/superpowers/evidence/2026-06-03-ugv-phase-2b-4060-no-dispatch-receipt.md`.

Phase 2B exit status:

- Phase 2B no-hardware reporting is accepted on the Mac implementation lane and
  on the unit 4060 receiving lane.
- This is still not ROS1 signature proof, gateway `dry_run` proof, gateway
  `dispatch` proof, hardware proof, or controlled-motion authorization.

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

Prepare Phase 3 as an explicit-authorization gate. Do not implement all
remaining phases at once.

Mac-side next task:

- draft the Phase 3 read-only ROS1 service signature plan and file-by-file
  implementation plan
- plan file:
  `docs/superpowers/plans/2026-06-03-phase-3a-read-only-ros1-signature-gate.md`
- keep the plan limited to service discovery, service type/args capture,
  service-signature validation, and evidence recording
- do not write gateway lifecycle code until the plan is accepted
- do not connect to ROS from the Mac side

4060-side next task after explicit user authorization:

- source the local ROS1 environment on the unit/workplace machine
- run read-only service discovery only
- capture `rosservice list`, service type, and service args evidence
- run the existing site-acceptance/audit tooling against captured or live
  read-only service-signature evidence
- do not call gateway `dry_run`
- do not call gateway `dispatch`
- do not authorize controlled motion

Phase 3 must not start as a live 4060 ROS step until the user explicitly asks
for ROS1 gateway lifecycle or read-only service signature work.

## Current Phase 3A Status

Status as of 2026-06-04: attempted on the unit 4060 lane, but not accepted.

Evidence:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-ros-master-unreachable-receipt.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-ros-master-unreachable-receipt.json`

4060 reported:

- branch head `a9951f8`
- clean repo worktree
- `source /opt/ros/noetic/setup.bash: ok`
- `source ~/catkin_ws/devel/setup.bash: missing`
- `ROS_MASTER_URI=http://localhost:11311`
- `ROS_IP=` and `ROS_HOSTNAME=` empty
- `rosservice list` returned `RC=2` with
  `ERROR: Unable to communicate with master!`
- captured service list/type/args files were present but `0` bytes
- `TaskPlanningSiteAcceptance.v1 ok=False`
- `platform_backend='ros1_gateway'`
- `rosservice_audit.observed_service_count=0`
- no matched gateway services

Boundary was preserved:

- no gateway `dry_run`
- no gateway `dispatch`
- no controlled motion
- no gateway service call
- no `rostopic` publish
- no repo architecture change
- no non-convex alpha document changes

Interpretation:

- Phase 3A did not fail because a gateway service signature mismatched.
- Phase 3A failed earlier: the 4060 WSL2 ROS environment could not communicate
  with its configured master.
- Do not proceed to gateway `dry_run` planning until the ROS master URI,
  catkin workspace source path, and port `11311` reachability are understood.

Next 4060 task:

- run only the read-only ROS master reachability diagnosis in
  `docs/superpowers/plans/2026-06-03-phase-3a-read-only-ros1-signature-gate.md`
  under `Failure Branch A: ROS Master Unreachable`
- report environment, candidate catkin setup paths, process/socket evidence,
  and TCP reachability
- do not retry service-signature capture until the correct ROS master and
  workspace are confirmed

Reachability diagnosis received on 2026-06-04:

- Evidence:
  `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-ros-master-reachability-diagnosis.md`
- branch head `81b88ad`
- clean repo worktree
- `ROS_MASTER_URI=http://localhost:11311`
- `ROS_IP=` and `ROS_HOSTNAME=` empty
- `roscore`, `rosmaster`, and `rosservice` binaries exist under
  `/opt/ros/noetic/bin`
- `/home/uavdev/catkin_ws`, `/home/uavdev/catkin_ws/devel`, and
  `/home/uavdev/catkin_ws/devel/setup.bash` are missing
- no `devel/setup.bash` was found under `/home/uavdev` with max depth `4`
- no listener/process evidence for `roscore`, `rosmaster`, `roslaunch`,
  `platform_gateway`, or `run_ros1_platform_gateway_node`
- TCP connect to `localhost:11311` failed with connection refused

Updated interpretation:

- Phase 3A remains open.
- The current blocker is not service-signature validation; it is missing live
  ROS master/gateway environment on this WSL2 session.
- Before any retry, identify the correct unit ROS workspace, launch files, or
  gateway startup scripts with read-only file inventory.

Updated next 4060 task:

- run only the read-only workspace/startup inventory in
  `docs/superpowers/plans/2026-06-03-phase-3a-read-only-ros1-signature-gate.md`
  under `4060 Read-Only Workspace And Startup Inventory`
- do not start `roscore`
- do not start a gateway process
- do not retry `rosservice list/type/args`
- do not call gateway `dry_run` or `dispatch`

Workspace/startup inventory received on 2026-06-04:

- Evidence:
  `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-workspace-startup-inventory.md`
- branch head `34cdfcb`
- clean repo worktree
- inventory file:
  `/tmp/changxin-phase3a-workspace-inventory.txt` with `101` lines
- startup-reference file:
  `/tmp/changxin-phase3a-ros-startup-references.txt` with `5962` lines
- no `*/devel/setup.bash` was found under `/mnt/d/changxin` or `/home/uavdev`
- no `*.launch` or `*.service` files were found by the max-depth inventory scan
- repo scripts were found under `tools/`, `ugv/01-scripts/`, and
  `uav/01-scripts/`
- duplicate/home repo copies were found under `/home/uavdev/changxin-code-sync`
  and `/home/uavdev/changxin-code`
- dependency CMake trees were found under `/home/uavdev/uav-deps`
- repo references include the gateway profile template, gateway node runner,
  and ROS1 service gateway wrapper code
- historical evidence references include prior `uav-g3*` ROS logs, but those
  are text hits and not running processes

Updated interpretation:

- Phase 3A remains open.
- The current evidence does not identify a ready unit ROS workspace or startup
  launch/service file.
- Repo gateway code exists but is not proof that the unit ROS master/gateway is
  installed, built, sourced, or running.
- The next step is no longer another blind scan. A local operator must either
  provide the actual unit ROS workspace/startup path or explicitly authorize
  preparing/starting the ROS1 master and gateway environment.

Decision gate before further 4060 action:

- provide actual ROS workspace path and startup command, or
- authorize preparing a ROS1 gateway catkin workspace from repo sources, or
- authorize starting a local ROS master and gateway wrapper for read-only
  service-signature capture

Until that decision is made, do not retry service-signature capture and do not
start ROS processes.

## Phase 3A Update: Local Operator Reports Master Started

Status as of 2026-06-04: the user reports that the UGV-side ROS master on port
`11311` has been started. This is recorded as operator-reported status, not as
Mac-verified or 4060-verified ROS reachability.

Evidence:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-local-operator-master-started-note.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-local-operator-master-started-note.json`

Updated interpretation:

- Phase 3A remains open.
- The next action is no longer another broad workspace scan.
- The 4060 side should retry only read-only ROS master reachability against the
  active `ROS_MASTER_URI`.
- If the active URI is empty, wrong, or points to `localhost` while the master
  is actually on a vehicle/IPC IP, the 4060 side should stop and ask the
  operator for the exact URI.
- Only after TCP reachability succeeds should the 4060 side run
  `rosservice list` and then type/args capture for discovered gateway services.
- Gateway `dry_run`, gateway `dispatch`, controlled motion, and `rostopic`
  publish remain out of scope.

Current next gate:

1. 4060 read-only ROS master reachability retry.
2. Conditional read-only service-name capture.
3. Conditional read-only service type/args capture for gateway services.
4. File-based Phase 3A site-acceptance verifier.
5. Mac-side receipt recording after the 4060 returns output.

## Phase 3A Retry Result: Gateway Services Missing

Status as of 2026-06-04: the 4060 read-only retry reached the UGV ROS master
but did not find the expected gateway services.

Evidence:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-master-reachable-gateway-missing-retry.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-master-reachable-gateway-missing-retry.json`

4060 reported:

- `ROS_MASTER_URI=http://192.168.0.201:11311`
- TCP connect to `192.168.0.201:11311` succeeded
- `rosservice list` observed `65` services
- `/fleet/ugv_0/gateway/dry_run` was missing
- `/fleet/ugv_0/gateway/dispatch` was missing
- `TaskPlanningSiteAcceptance.v1 ok=False`
- validation errors were the expected missing-service and missing-type/args
  errors

Updated interpretation:

- Phase 3A remains open.
- The current blocker is no longer master reachability.
- The current blocker is gateway wrapper service registration.
- The next phase of work is Phase 3B gateway lifecycle preparation, documented
  in
  `docs/superpowers/plans/2026-06-04-phase-3b-ros1-gateway-lifecycle-prep.md`.

Current next gate:

1. 4060 confirms or creates the intended catkin workspace only with operator
   authorization.
2. 4060 installs/builds the `platform_gateway_msgs` package only with operator
   authorization.
3. 4060 starts the gateway wrapper only with operator authorization.
4. 4060 reruns read-only service-signature verification.
5. Mac records the Phase 3B/Phase 3A signature receipt after output returns.

Still out of scope:

- gateway `dry_run` service calls
- gateway `dispatch` service calls
- controlled motion
- `rostopic` publish
- model calls on the unit execution lane

## Phase 3B Stage 2 Result: Workspace Dry-Run Ready

Status as of 2026-06-04: the 4060 side has completed Phase 3B Stage 2 and is
stopped at the Stage 3 apply/build authorization point.

Evidence:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3b-4060-workspace-dry-run-auth-stop.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3b-4060-workspace-dry-run-auth-stop.json`

4060 reported:

- `CATKIN_WS=/home/uavdev/catkin_ws`
- `CATKIN_SRC=/home/uavdev/catkin_ws/src`
- `/home/uavdev/catkin_ws/devel/setup.bash` exists
- `/home/uavdev/catkin_ws/src` currently contains only the catkin top-level
  `CMakeLists.txt` symlink
- `platform_gateway_msgs` has not been installed
- dry-run report `Ros1GatewayWorkspacePlan.v1 ok=True`
- `dry_run=True`
- `installed=False`
- `validation_errors=[]`
- `warnings=[]`

Updated next gate:

1. User/operator explicitly authorizes Phase 3B Stage 3 apply/build.
2. 4060 installs `platform_gateway_msgs` into `/home/uavdev/catkin_ws/src`.
3. 4060 runs `catkin_make`.
4. 4060 verifies import of `platform_gateway_msgs.srv.TaskCommandJson`.
5. 4060 stops and returns logs; gateway wrapper startup is not part of Stage 3.

Stage 4 remains separate:

- start the gateway wrapper for service registration only after a second
  explicit authorization
- then rerun read-only service-signature verification

Still out of scope:

- gateway `dry_run` service calls
- gateway `dispatch` service calls
- controlled motion
- `rostopic pub`
- committed machine-specific ROS profiles

## Phase 3B Stage 3 Result: Gateway Message Build Ready

Status as of 2026-06-04: the 4060 side has completed Phase 3B Stage 3 and is
stopped at the Stage 4 gateway-wrapper authorization point.

Evidence:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3b-4060-apply-build-auth-stop.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3b-4060-apply-build-auth-stop.json`

4060 reported:

- `Ros1GatewayWorkspacePlan.v1 ok=True`
- `dry_run=False`
- `installed=True`
- `mode='copy'`
- `package_target='/home/uavdev/catkin_ws/src/platform_gateway_msgs'`
- `catkin_make_rc=0`
- `taskcommandjson_import_rc=0`
- import output:
  `<class 'platform_gateway_msgs.srv._TaskCommandJson.TaskCommandJson'>`

Updated next gate:

1. User/operator explicitly authorizes Phase 3B Stage 4 wrapper startup.
2. 4060 starts the gateway wrapper for service registration only.
3. 4060 runs read-only service-signature verification.
4. 4060 stops or cleans up the wrapper after capture unless the local operator
   explicitly keeps it running.
5. Mac records the Stage 4/Stage 5 receipt after output returns.

Still out of scope:

- gateway `dry_run` service calls
- gateway `dispatch` service calls
- controlled motion
- `rostopic pub`
- model calls on the unit execution lane
- committed machine-specific ROS profiles

## Phase 3B Stage 4 Preflight Result: Master Refused

Status as of 2026-06-04: the 4060 side attempted Phase 3B Stage 4 but stopped
before wrapper startup because `192.168.0.201:11311` refused TCP connection.

Evidence:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3b-4060-wrapper-preflight-master-refused.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3b-4060-wrapper-preflight-master-refused.json`

4060 reported:

- `ROS_MASTER_URI=http://192.168.0.201:11311`
- `ROS_IP=172.20.26.179`
- `tcp_connect=FAIL:[Errno 111] Connection refused`
- `gateway_wrapper_started=false`
- `verifier_run=false`
- no valid matched/missing service set

Updated interpretation:

- Phase 3B Stage 3 remains complete.
- Phase 3B Stage 4 remains pending.
- The current blocker is ROS master reachability.
- The gateway wrapper should not start until TCP preflight succeeds.

Updated next gate:

1. Local operator restores or confirms UGV ROS master at
   `http://192.168.0.201:11311`.
2. 4060 runs TCP preflight.
3. If TCP fails, stop before wrapper startup.
4. If TCP succeeds, start wrapper for service registration only and run
   read-only service-signature verification.
5. Mac records the receipt after output returns.

Still out of scope:

- gateway `dry_run` service calls
- gateway `dispatch` service calls
- controlled motion
- `rostopic pub`
- model calls on the unit execution lane
- committed machine-specific ROS profiles
