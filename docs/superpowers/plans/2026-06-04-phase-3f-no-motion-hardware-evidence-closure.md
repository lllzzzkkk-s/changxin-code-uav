# Phase 3F No-Motion Hardware Evidence Closure Plan

Date: 2026-06-04

Goal: convert the completed Phase 3E operator-approved no-motion dispatch into
the repo's standard hardware dispatch artifact and goal-evidence reports,
without making any new ROS service calls.

This phase is evidence closure. It is not a new dispatch, not `move_base`, and
not controlled motion.

## Starting Evidence

Phase 3E completed:

- evidence:
  `docs/superpowers/evidence/2026-06-04-ugv-phase-3e-4060-approved-manual-confirm-dispatch-success.md`
- `dispatch_called_once=true`
- `dispatch_accepted=true`
- `operator_approved=true`
- `enable_move_base=false`
- `target_action=manual_confirm`
- `GatewayServiceResponse.v1`
- `CommandAck.v1 accepted=true`
- `ack_reason=manual_confirm_completed`
- `TaskProgressSet.v1`
- one `TaskProgress.v1` item for `task_002`, `ugv_0`, `target_01`
- `observations_unit_ugv_action=manual_confirm`
- `observations_motion_attempted=false`
- wrapper stopped after capture

Input files reported by 4060:

```text
/tmp/changxin-phase3e/gateway-dispatch-response.txt
sha256=0b65969c2ff4a1e1f432f4e33dd3bbeab8117684d148540563461a16554f82a2

/tmp/changxin-phase3e/gateway-dispatch-response.parsed.json
sha256=e2e848e8d867e45b0090253eb6703df96c246750ed725386b542cbe2d3aae7b4

/tmp/changxin-phase3e/task_progress_after_dispatch.json
sha256=95d38d4e8876e4592bd0ab6d6f58b1c48d359bdad6b42cd625e96287b0ba436f
```

## Hard Boundary

Phase 3F does not call ROS.

Authorized only for Phase 3F:

- verify the existing Phase 3E response/progress file hashes
- create or reuse a local `work_hardware` + `ros1_gateway` profile in `/tmp`
- run `tools/record_unit_hardware_dispatch_artifact.py`
- run goal-evidence checks with the generated hardware artifact
- optionally import the hardware artifact into the standard evidence directory
- package/copy evidence under `/tmp`

Still prohibited:

- any `rosservice call`
- gateway `dry_run`
- gateway `dispatch`
- `--unit-ugv-enable-move-base`
- `move_base_goal` target maps
- controlled motion
- `rostopic pub`
- raw `/cmd_vel`, `/move_base_simple/goal`, `/setpoints_cmd`, or similar direct
  controls from the center
- hand-written `TaskCommand` JSON
- model calls on the unit execution lane
- committed machine-specific ROS profiles or IPs
- non-convex alpha document edits

## Stage 0: Mac-Side Receipt And Plan

Owner: Mac Codex.

Files:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3e-4060-approved-manual-confirm-dispatch-success.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3e-4060-approved-manual-confirm-dispatch-success.json`
- `docs/superpowers/plans/2026-06-04-phase-3f-no-motion-hardware-evidence-closure.md`
- `docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md`
- `docs/superpowers/specs/2026-06-02-distributed-fleet-phase-2-to-langgraph-roadmap.md`

Exit gate:

- Phase 3E approved manual-confirm dispatch receipt recorded
- Phase 3F evidence closure plan and 4060 prompt written
- no Mac-side ROS access

## Stage 1: Verify Existing Captures

Owner: 4060 Codex.

```bash
mkdir -p /tmp/changxin-phase3f
sha256sum /tmp/changxin-phase3e/gateway-dispatch-response.txt
sha256sum /tmp/changxin-phase3e/gateway-dispatch-response.parsed.json
sha256sum /tmp/changxin-phase3e/task_progress_after_dispatch.json
python3 -m json.tool /tmp/changxin-phase3e/gateway-dispatch-response.parsed.json \
  > /tmp/changxin-phase3f/gateway-dispatch-response.parsed.pretty.json
python3 -m json.tool /tmp/changxin-phase3e/task_progress_after_dispatch.json \
  > /tmp/changxin-phase3f/task_progress_after_dispatch.pretty.json
```

Exit gate:

- response hash matches Phase 3E receipt or drift is explicitly reported
- progress hash matches Phase 3E receipt or drift is explicitly reported
- parsed response has `ack.accepted=true`
- parsed response has `ack.reason=manual_confirm_completed`
- parsed response has `motion_attempted=false`
- progress has one `TaskProgress.v1` item
- progress item matches `task_002`, `ugv_0`, `target_01`
- progress item has `observations.motion_attempted=false`

## Stage 2: Prepare Local ROS1 Gateway Profile For Artifact Recording

Owner: 4060 Codex.

This profile is a local evidence input. Do not commit it.

```bash
cat > /tmp/changxin-phase3f/work_hardware_ros1_gateway.env <<'ENV'
MISSION_PROFILE=work_hardware
MODEL_PROVIDER=mock
MODEL_BASE_URL=
MODEL_NAME=
PLANNER_BACKEND=mock
PLATFORM_BACKEND=ros1_gateway
MISSION_STATE_STORE=json
MISSION_ARTIFACT_ROOT=/tmp/changxin-work-hardware-runs
ROS_MASTER_URI=http://192.168.0.201:11311
ROS_IP=172.20.26.179
HARDWARE_APPROVAL_REQUIRED=true
ROS_GATEWAY_DISPATCH_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dispatch
ROS_GATEWAY_DRY_RUN_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dry_run
ENV
```

Exit gate:

- profile loads as `MISSION_PROFILE=work_hardware`
- profile loads as `PLATFORM_BACKEND=ros1_gateway`
- `HARDWARE_APPROVAL_REQUIRED=true`
- profile stays under `/tmp`
- no machine-specific profile is committed

## Stage 3: Record Standard Hardware Dispatch Artifact

Owner: 4060 Codex.

This command only reads already captured evidence and writes a standard artifact.
It does not call ROS.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/record_unit_hardware_dispatch_artifact.py \
  --source-artifact /tmp/changxin-phase2b-dev-mock-single/8d783b73-f8f2-488c-9d53-6b3881806784 \
  --profile /tmp/changxin-phase3f/work_hardware_ros1_gateway.env \
  --output-dir /tmp/changxin-phase3f/hardware_artifacts \
  --platform-id ugv_0 \
  --task-id task_002 \
  --dispatch-service /fleet/ugv_0/gateway/dispatch \
  --dispatch-returncode 0 \
  --dispatch-stdout-file /tmp/changxin-phase3e/gateway-dispatch-response.txt \
  --command-ack-file /tmp/changxin-phase3e/gateway-dispatch-response.parsed.json \
  --task-progress-file /tmp/changxin-phase3e/task_progress_after_dispatch.json \
  --execution-context unit_workplace_hardware \
  --operator-approved \
  --run-id phase3f-ugv0-manual-confirm-dispatch \
  --overwrite \
  | tee /tmp/changxin-phase3f/record_unit_hardware_dispatch_artifact.json
python3 -m json.tool /tmp/changxin-phase3f/record_unit_hardware_dispatch_artifact.json \
  > /tmp/changxin-phase3f/record_unit_hardware_dispatch_artifact.pretty.json
sha256sum /tmp/changxin-phase3f/record_unit_hardware_dispatch_artifact.json
```

Exit gate:

- report schema is `UnitHardwareDispatchArtifactRecord.v1`
- `ok=true`
- `validation_errors=[]`
- artifact root is
  `/tmp/changxin-phase3f/hardware_artifacts/phase3f-ugv0-manual-confirm-dispatch`
- generated artifact contains `environment_profile.json`,
  `validation_report.json`, `gateway_trace.json`, `command_acks.json`,
  `task_progress.json`, and `run_summary.md`
- generated `validation_report.current_state=HARDWARE_DISPATCH_RECORDED`
- generated `environment_profile.operator_approved=true`
- generated `environment_profile.operator_approval_source=local_unit_operator`
- generated `environment_profile.execution_context=unit_workplace_hardware`
- generated `gateway_trace.records[0].rosservice_called=true`
- generated `gateway_trace.records[0].publish_attempted=false`
- generated `command_acks.items[0].accepted=true`
- generated `task_progress.items[0]` matches the selected command

## Stage 4: Run Goal-Evidence Check With Hardware Artifact

Owner: 4060 Codex.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py \
  --hardware-run-artifact /tmp/changxin-phase3f/hardware_artifacts/phase3f-ugv0-manual-confirm-dispatch \
  --summary \
  --print-discovered-inputs \
  | tee /tmp/changxin-phase3f/goal_evidence_with_phase3f_hardware_summary.json
python3 -m json.tool /tmp/changxin-phase3f/goal_evidence_with_phase3f_hardware_summary.json \
  > /tmp/changxin-phase3f/goal_evidence_with_phase3f_hardware_summary.pretty.json
sha256sum /tmp/changxin-phase3f/goal_evidence_with_phase3f_hardware_summary.json
```

Exit gate:

- `unit_hardware_execution_artifact_verified` is `pass`
- if overall goal evidence is not `ok=true`, remaining gaps are listed without
  treating them as Phase 3F failures
- no ROS command is run during this stage

## Stage 5: Report

Owner: 4060 Codex.

Report:

- all Phase 3E input file hashes
- local profile path and confirmation that it was not committed
- `record_unit_hardware_dispatch_artifact.py` rc and report path/hash
- generated hardware artifact root
- generated hardware artifact key files and hashes
- goal-evidence summary path/hash
- whether `unit_hardware_execution_artifact_verified=pass`
- remaining goal-evidence gaps, if any
- boundary confirmation:
  - no new rosservice call
  - no gateway dry_run
  - no gateway dispatch
  - no move_base
  - no controlled motion
  - no rostopic pub
  - no repo architecture change
  - no non-convex alpha document edits
  - no committed machine-specific ROS env

## 4060 Prompt

Use this prompt to close Phase 3F. It does not authorize ROS calls.

```text
Continue UGV Phase 3F no-motion hardware evidence closure.

You are on the unit 4060 WSL2 side. Phase 3E passed with one approved
manual_confirm dispatch: ack.accepted=true, reason=manual_confirm_completed,
TaskProgressSet.v1 written, motion_attempted=false, enable_move_base=false.

Authorization scope:
- do not call ROS services
- verify the existing Phase 3E response/progress file hashes
- create a local /tmp work_hardware ros1_gateway profile for artifact recording only
- run tools/record_unit_hardware_dispatch_artifact.py on the captured Phase 3E response/progress
- run tools/check_distributed_fleet_goal_evidence.py with the generated hardware artifact
- report generated artifact paths, hashes, and remaining evidence gaps

Not authorized:
- no rosservice call
- no gateway dry_run
- no gateway dispatch
- no --unit-ugv-enable-move-base
- no move_base_goal
- no controlled motion
- no rostopic pub
- no hand-written TaskCommand JSON
- no repo architecture edits
- no non-convex alpha docs
- no committed machine-specific ROS IP/env

Work in /mnt/d/changxin/changxin-code:
git fetch origin
git checkout codex/phase2b-no-hardware-reporting
git pull --ff-only origin codex/phase2b-no-hardware-reporting
git log -2 --oneline
git status --short

Then follow:
docs/superpowers/plans/2026-06-04-phase-3f-no-motion-hardware-evidence-closure.md

Stop if:
- Phase 3E captured files are missing
- parsed response/progress fails validation
- record_unit_hardware_dispatch_artifact.py returns not ok
- generated artifact does not contain accepted CommandAck and matching TaskProgress

Report:
- Phase 3E input hashes
- hardware artifact recorder report path/sha256 and ok/errors
- generated hardware artifact root
- generated key files and hashes
- goal-evidence summary path/sha256
- unit_hardware_execution_artifact_verified status
- remaining goal-evidence gaps
- boundary confirmation:
  new_rosservice_call=false
  gateway_dry_run_called=false
  gateway_dispatch_called=false
  controlled_motion_authorized=false
  move_base_used=false
  rostopic_pub=false
  repo_architecture_changed=false
  non_convex_alpha_docs_touched=false
```
