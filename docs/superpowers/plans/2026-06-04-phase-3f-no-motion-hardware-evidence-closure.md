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

## Phase 3F Source-Artifact Blocker

The first Phase 3F recorder attempt correctly stopped because the planned
source artifact was the Phase 2B `dev_mock` artifact:

```text
/tmp/changxin-phase2b-dev-mock-single/8d783b73-f8f2-488c-9d53-6b3881806784
```

That artifact contains the exact Phase 3E task command, but it does not satisfy
the hardware recorder's pre-dispatch source gate:

- source `mission_profile` must be `work_hardware`
- source `hardware_approval_required` must be `true`
- source `validation_report.current_state` must be `OPERATOR_APPROVAL`

4060 also found local artifacts that satisfy those hard gates but belong to the
wrong case (`golden_uav_ugv_coordination`), so the recorder correctly rejected
their ack/progress alignment.

The corrected Phase 3F chain is:

```text
Phase 2B exact task_schema.json
-> run_prevalidated_task_schema.py with profiles/work_hardware.env
-> source artifact: work_hardware + mock + OPERATOR_APPROVAL
-> record_unit_hardware_dispatch_artifact.py with Phase 3E ack/progress
```

This keeps the source artifact in the exact `golden_single_ugv_inspection /
task_002 / ugv_0` command lineage while still preserving the pre-dispatch
operator-approval gate.

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

## Stage 1.5: Generate Exact Work-Hardware Pre-Approval Source Artifact

Owner: 4060 Codex.

Do not reuse the Phase 2B `dev_mock` run as the recorder source artifact. It is
only the source for the exact `task_schema.json`.

Do not use a `work_hardware` artifact from another case. The source artifact
must contain the same selected `TaskCommand` later proven by Phase 3E:

- `mission_id=golden_single_ugv_inspection`
- `task_id=task_002`
- `platform_id=ugv_0`

This stage does not call ROS. `profiles/work_hardware.env` uses
`PLATFORM_BACKEND=mock` and stops before dispatch at `OPERATOR_APPROVAL`.

```bash
PHASE3E_SCHEMA=/tmp/changxin-phase2b-dev-mock-single/8d783b73-f8f2-488c-9d53-6b3881806784/task_schema.json
test -f "$PHASE3E_SCHEMA"

PYTHONDONTWRITEBYTECODE=1 python3 tools/run_prevalidated_task_schema.py \
  --profile profiles/work_hardware.env \
  --task-schema "$PHASE3E_SCHEMA" \
  --case single_ugv_inspection \
  --artifact-root /tmp/changxin-phase3f/work_hardware_preapproval_source \
  | tee /tmp/changxin-phase3f/prevalidated_work_hardware_source.json

python3 -m json.tool /tmp/changxin-phase3f/prevalidated_work_hardware_source.json \
  > /tmp/changxin-phase3f/prevalidated_work_hardware_source.pretty.json

SOURCE_ARTIFACT="$(
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("/tmp/changxin-phase3f/prevalidated_work_hardware_source.json").read_text(encoding="utf-8"))
errors = []
if report.get("ok") is not True:
    errors.append(f"prevalidated source report ok={report.get('ok')}")
if report.get("status") != "approval_required":
    errors.append(f"status={report.get('status')}")
if report.get("current_state") != "OPERATOR_APPROVAL":
    errors.append(f"current_state={report.get('current_state')}")
if report.get("case_id") != "single_ugv_inspection":
    errors.append(f"case_id={report.get('case_id')}")
artifact = Path(str(report.get("artifact_bundle_path") or ""))
if not artifact.is_dir():
    errors.append(f"artifact_bundle_path missing: {artifact}")
if errors:
    raise SystemExit("\n".join(errors))
print(artifact)
PY
)"
printf '%s\n' "$SOURCE_ARTIFACT" > /tmp/changxin-phase3f/source_artifact.path

python3 - <<'PY' "$SOURCE_ARTIFACT" \
  | tee /tmp/changxin-phase3f/source_artifact_precheck.json
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
profile = json.loads((root / "environment_profile.json").read_text(encoding="utf-8"))
validation = json.loads((root / "validation_report.json").read_text(encoding="utf-8"))
bt = json.loads((root / "bt_artifact.json").read_text(encoding="utf-8"))
commands = bt.get("task_commands") or []
matches = [
    command for command in commands
    if command.get("mission_id") == "golden_single_ugv_inspection"
    and command.get("task_id") == "task_002"
    and command.get("platform_id") == "ugv_0"
]
precheck = {
    "schema": "Phase3FSourceArtifactPrecheck.v1",
    "ok": (
        profile.get("mission_profile") == "work_hardware"
        and profile.get("platform_backend") == "mock"
        and profile.get("hardware_approval_required") is True
        and validation.get("status") == "passed"
        and validation.get("current_state") == "OPERATOR_APPROVAL"
        and validation.get("errors") == []
        and len(matches) == 1
    ),
    "source_artifact": str(root),
    "mission_profile": profile.get("mission_profile"),
    "platform_backend": profile.get("platform_backend"),
    "hardware_approval_required": profile.get("hardware_approval_required"),
    "validation_status": validation.get("status"),
    "current_state": validation.get("current_state"),
    "validation_errors": validation.get("errors"),
    "matching_task_command_count": len(matches),
    "selected_task_command": matches[0] if len(matches) == 1 else None,
}
print(json.dumps(precheck, indent=2, sort_keys=True))
if not precheck["ok"]:
    raise SystemExit(1)
PY

sha256sum /tmp/changxin-phase3f/prevalidated_work_hardware_source.json
sha256sum /tmp/changxin-phase3f/source_artifact_precheck.json
```

Exit gate:

- `prevalidated_work_hardware_source.json` has `ok=true`
- `status=approval_required`
- `current_state=OPERATOR_APPROVAL`
- `case_id=single_ugv_inspection`
- `source_artifact_precheck.json` has `ok=true`
- source `environment_profile.mission_profile=work_hardware`
- source `environment_profile.platform_backend=mock`
- source `environment_profile.hardware_approval_required=true`
- source `validation_report.status=passed`
- source `validation_report.current_state=OPERATOR_APPROVAL`
- source selected TaskCommand matches `golden_single_ugv_inspection`,
  `task_002`, `ugv_0`
- no ROS command is run during this stage

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
SOURCE_ARTIFACT="$(cat /tmp/changxin-phase3f/source_artifact.path)"
test -d "$SOURCE_ARTIFACT"

PYTHONDONTWRITEBYTECODE=1 python3 tools/record_unit_hardware_dispatch_artifact.py \
  --source-artifact "$SOURCE_ARTIFACT" \
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
- `source_artifact` equals the Stage 1.5 `work_hardware` pre-approval artifact
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
- Stage 1.5 source artifact path and source-precheck hash
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

## Phase 3F Result And Phase 3G Handoff

Status as of 2026-06-05: the corrected Phase 3F recorder chain passed.

4060 generated an exact `work_hardware + OPERATOR_APPROVAL` source artifact for
`golden_single_ugv_inspection / task_002 / ugv_0`, then recorded the Phase 3E
accepted manual-confirm dispatch and matching progress into the standard
hardware artifact:

```text
root=/tmp/changxin-phase3f/hardware_artifacts/phase3f-ugv0-manual-confirm-dispatch
record_rc=0
validation_errors=[]
generated_hardware_artifact_precheck_ok=true
```

Goal-evidence aggregation still reported:

```text
unit_hardware_execution_artifact_verified=missing
```

This is a cross-proof alignment issue, not a Phase 3F recorder failure:

- the hardware artifact is for `single_ugv_inspection`
- existing OK lane matrix evidence is for `uav_ugv_coordination`
- existing OK ROS1 signature evidence has a different `machine_id` from the
  Phase 3F hardware artifact

The next gate is Phase 3G same-case/same-machine goal-evidence alignment:

```text
docs/superpowers/plans/2026-06-05-phase-3g-same-case-goal-evidence-alignment.md
```

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
- generate an exact `work_hardware` + `OPERATOR_APPROVAL` source artifact from
  the Phase 2B exact `task_schema.json`
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
- the exact `work_hardware` pre-approval source artifact cannot be generated
- source artifact precheck does not match `golden_single_ugv_inspection/task_002/ugv_0`
- record_unit_hardware_dispatch_artifact.py returns not ok
- generated artifact does not contain accepted CommandAck and matching TaskProgress

Report:
- Phase 3E input hashes
- source artifact report path/sha256, source artifact path, and source precheck path/sha256
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
