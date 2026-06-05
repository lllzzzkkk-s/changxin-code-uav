# Phase 3G Same-Case Goal Evidence Alignment Plan

Date: 2026-06-05

Goal: make the already recorded Phase 3F no-motion hardware artifact count in
`unit_hardware_execution_artifact_verified` by supplying matching same-case lane
matrix evidence and same-machine ROS1 signature evidence.

This phase does not redo Phase 3F recorder and does not call gateway
`dry_run` or `dispatch`.

## Root Cause

`tools/check_distributed_fleet_goal_evidence.py` intentionally requires a
hardware execution artifact to align with other accepted proof:

- hardware artifact `case_id` must be in an OK lane matrix case set
- hardware artifact `machine_id` must match an OK ROS1 signature report
  `machine_id`
- the hardware dispatch service must be one of the signed `/gateway/dispatch`
  services for that same machine id

Phase 3F recorder succeeded for:

```text
case_id=single_ugv_inspection
mission_id=golden_single_ugv_inspection
task_id=task_002
platform_id=ugv_0
```

The remaining goal-evidence blocker is that current OK lane-matrix evidence is
for `uav_ugv_coordination`, and current OK ROS1 signature evidence has a
different `machine_id` than the Phase 3F hardware artifact.

## Boundaries

Allowed:

- generate a no-ROS lane matrix report for `single_ugv_inspection`
- run read-only ROS1 service signature observation on the current 4060 machine
- start the ROS1 gateway wrapper only for service registration if needed
- stop the wrapper after read-only capture
- run goal-evidence checker with the Phase 3F hardware artifact and new reports

Not allowed:

- gateway `dry_run`
- gateway `dispatch`
- controlled motion
- `move_base_goal`
- `--unit-ugv-enable-move-base`
- `rostopic pub`
- raw `/cmd_vel`, `/move_base_simple/goal`, `/setpoints_cmd`, or similar direct
  controls from the center
- hand-written `TaskCommand` JSON
- changing repo architecture
- non-convex alpha document edits
- committing machine-specific ROS env/IP values

## Stage 0: Pull Latest Repo

Owner: 4060 Codex.

```bash
cd /mnt/d/changxin/changxin-code
git fetch origin
git checkout codex/phase2b-no-hardware-reporting
git pull --ff-only origin codex/phase2b-no-hardware-reporting
git log -2 --oneline
git status --short
mkdir -p /tmp/changxin-phase3g
```

Exit gate:

- head includes the Mac commit recording this Phase 3G plan
- worktree is clean

## Stage 1: Reconfirm Phase 3F Hardware Artifact

Owner: 4060 Codex.

```bash
PHASE3F_HW=/tmp/changxin-phase3f/hardware_artifacts/phase3f-ugv0-manual-confirm-dispatch
test -d "$PHASE3F_HW"
python3 -m json.tool /tmp/changxin-phase3f/record_unit_hardware_dispatch_artifact.json \
  > /tmp/changxin-phase3g/phase3f_record_unit_hardware_dispatch_artifact.pretty.json
python3 -m json.tool /tmp/changxin-phase3f/generated_hardware_artifact_precheck.json \
  > /tmp/changxin-phase3g/generated_hardware_artifact_precheck.pretty.json
sha256sum /tmp/changxin-phase3f/record_unit_hardware_dispatch_artifact.json
sha256sum /tmp/changxin-phase3f/generated_hardware_artifact_precheck.json
```

Exit gate:

- recorder report still has `record_rc=0` equivalent / `ok=true`
- generated hardware artifact precheck still has `ok=true`
- hardware artifact path is unchanged

## Stage 2: Generate Same-Case Lane Matrix

Owner: 4060 Codex.

This is no-ROS and no-hardware. It proves the same case is comparable across
mock-first lanes and that `work_hardware` stops at `OPERATOR_APPROVAL`.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_lane_matrix.py \
  --artifact-root /tmp/changxin-phase3g/single_ugv_lane_matrix_artifacts \
  --case single_ugv_inspection \
  | tee /tmp/changxin-phase3g/lane_matrix_single_ugv_inspection.json
python3 -m json.tool /tmp/changxin-phase3g/lane_matrix_single_ugv_inspection.json \
  > /tmp/changxin-phase3g/lane_matrix_single_ugv_inspection.pretty.json
sha256sum /tmp/changxin-phase3g/lane_matrix_single_ugv_inspection.json
```

Exit gate:

- report schema is `TaskPlanningLaneMatrix.v1`
- `ok=true`
- `case_id=single_ugv_inspection`
- `dev_mock` and `server_sim` reach `DISPATCH_OR_HOLD`
- `work_hardware` reaches `OPERATOR_APPROVAL`
- comparisons are equivalent / pre-dispatch compatible

## Stage 3: Generate Same-Machine ROS1 Signature Report

Owner: 4060 Codex.

This stage is read-only with respect to gateway services. The wrapper may be
started only to register the `ugv_0` gateway services, then stopped after
capture. Do not call `/fleet/ugv_0/gateway/dry_run` or
`/fleet/ugv_0/gateway/dispatch`.

Prepare a local profile in `/tmp`:

```bash
cat > /tmp/changxin-phase3g/work_hardware_ros1_gateway.env <<'ENV'
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
PROFILE=/tmp/changxin-phase3g/work_hardware_ros1_gateway.env
```

If the current local ROS IP is different, update only this `/tmp` profile and
report the value. Do not commit it.

Preflight:

```bash
source /opt/ros/noetic/setup.bash
source /home/uavdev/catkin_ws/devel/setup.bash
export ROS_MASTER_URI=http://192.168.0.201:11311
export ROS_IP="${ROS_IP:-172.20.26.179}"
python3 - <<'PY'
import os, socket, urllib.parse
uri = os.environ.get("ROS_MASTER_URI", "")
parsed = urllib.parse.urlparse(uri)
host = parsed.hostname
port = parsed.port or 11311
print(f"parsed_ros_master_host={host}")
print(f"parsed_ros_master_port={port}")
sock = socket.socket()
sock.settimeout(3)
try:
    sock.connect((host, port))
except OSError as exc:
    print(f"tcp_connect=FAIL:{exc}")
    raise SystemExit(20)
else:
    print("tcp_connect=OK")
finally:
    sock.close()
PY
```

If TCP preflight fails, stop and report. Do not start wrapper.

Start wrapper for registration only:

```bash
(
  cd /mnt/d/changxin/changxin-code
  source /opt/ros/noetic/setup.bash
  source /home/uavdev/catkin_ws/devel/setup.bash
  export ROS_MASTER_URI=http://192.168.0.201:11311
  export ROS_IP="${ROS_IP:-172.20.26.179}"
  export ROS_HOSTNAME=
  exec env PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/mnt/d/changxin/changxin-code:$PYTHONPATH \
    python3 tools/run_ros1_platform_gateway_node.py \
      --platform-id ugv_0 \
      --platform-type ugv \
      --capability confirm_target \
      --service-symbol platform_gateway_msgs.srv:TaskCommandJson \
      --node-name platform_gateway_ugv_0
) > /tmp/changxin-phase3g/gateway-wrapper.log 2>&1 &
GATEWAY_PID=$!
echo "$GATEWAY_PID" > /tmp/changxin-phase3g/gateway-wrapper.pid
sleep 5
ps -p "$GATEWAY_PID" -o pid=,cmd= \
  || { echo "gateway_wrapper_not_running"; cat /tmp/changxin-phase3g/gateway-wrapper.log; exit 1; }
```

Run read-only signature report:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
  --profile "$PROFILE" \
  --platform-id ugv_0 \
  --run-rosservice-list \
  --run-service-signatures \
  --require-rosservice-audit \
  --require-service-signatures \
  > /tmp/changxin-phase3g/site_acceptance_ros1_signature_same_machine.json
python3 -m json.tool /tmp/changxin-phase3g/site_acceptance_ros1_signature_same_machine.json \
  > /tmp/changxin-phase3g/site_acceptance_ros1_signature_same_machine.pretty.json
sha256sum /tmp/changxin-phase3g/site_acceptance_ros1_signature_same_machine.json
```

Supplemental raw read-only capture:

```bash
rosservice list | tee /tmp/changxin-phase3g/rosservice-list.txt
for s in /fleet/ugv_0/gateway/dry_run /fleet/ugv_0/gateway/dispatch; do
  printf "%s " "$s"
  rosservice type "$s"
done | tee /tmp/changxin-phase3g/rosservice-types.txt
for s in /fleet/ugv_0/gateway/dry_run /fleet/ugv_0/gateway/dispatch; do
  printf "%s " "$s"
  rosservice args "$s"
done | tee /tmp/changxin-phase3g/rosservice-args.txt
sha256sum /tmp/changxin-phase3g/gateway-wrapper.log
sha256sum /tmp/changxin-phase3g/rosservice-list.txt
sha256sum /tmp/changxin-phase3g/rosservice-types.txt
sha256sum /tmp/changxin-phase3g/rosservice-args.txt
```

Stop wrapper:

```bash
kill "$GATEWAY_PID" || true
wait "$GATEWAY_PID" || true
echo "gateway_wrapper_stopped_after_capture=true"
```

Exit gate:

- site acceptance schema is `TaskPlanningSiteAcceptance.v1`
- `ok=true`
- `acceptance_level=work_hardware_ros1_signatures_observed`
- `platform_backend=ros1_gateway`
- `machine_id` is present and hashed
- matched services include `/fleet/ugv_0/gateway/dry_run` and
  `/fleet/ugv_0/gateway/dispatch`
- service signatures have type `platform_gateway_msgs/TaskCommandJson`
- service args are `task_command_json`
- wrapper stopped after capture
- no gateway dry-run or dispatch call occurred

## Stage 4: Check Goal Evidence With Same-Case And Same-Machine Inputs

Owner: 4060 Codex.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py \
  --lane-matrix-report /tmp/changxin-phase3g/lane_matrix_single_ugv_inspection.json \
  --site-acceptance-report /tmp/changxin-phase3g/site_acceptance_ros1_signature_same_machine.json \
  --hardware-run-artifact /tmp/changxin-phase3f/hardware_artifacts/phase3f-ugv0-manual-confirm-dispatch \
  --summary \
  --print-discovered-inputs \
  | tee /tmp/changxin-phase3g/goal_evidence_same_case_same_machine_summary.json
python3 -m json.tool /tmp/changxin-phase3g/goal_evidence_same_case_same_machine_summary.json \
  > /tmp/changxin-phase3g/goal_evidence_same_case_same_machine_summary.pretty.json
sha256sum /tmp/changxin-phase3g/goal_evidence_same_case_same_machine_summary.json

PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py \
  --lane-matrix-report /tmp/changxin-phase3g/lane_matrix_single_ugv_inspection.json \
  --site-acceptance-report /tmp/changxin-phase3g/site_acceptance_ros1_signature_same_machine.json \
  --hardware-run-artifact /tmp/changxin-phase3f/hardware_artifacts/phase3f-ugv0-manual-confirm-dispatch \
  --print-discovered-inputs \
  | tee /tmp/changxin-phase3g/goal_evidence_same_case_same_machine_full.json
python3 -m json.tool /tmp/changxin-phase3g/goal_evidence_same_case_same_machine_full.json \
  > /tmp/changxin-phase3g/goal_evidence_same_case_same_machine_full.pretty.json
sha256sum /tmp/changxin-phase3g/goal_evidence_same_case_same_machine_full.json
```

Exit gate:

- `unit_hardware_execution_artifact_verified` becomes `pass`
- if the overall goal evidence remains not `ok=true`, remaining unrelated
  external gaps are reported separately
- no new gateway `dry_run` or `dispatch` was called

## Stage 5: Report

Report:

- `git log -2 --oneline`
- `git status --short`
- Phase 3F hardware artifact root and precheck hash
- same-case lane matrix report path/hash and `ok`
- same-machine ROS1 signature report path/hash, machine_id, and matched services
- goal evidence summary/full paths and hashes
- `unit_hardware_execution_artifact_verified` status
- remaining goal-evidence gaps, if any
- boundary confirmation:
  - `gateway_dry_run_called=false`
  - `gateway_dispatch_called=false`
  - `controlled_motion_authorized=false`
  - `move_base_used=false`
  - `rostopic_pub=false`
  - `repo_architecture_changed=false`
  - `non_convex_alpha_docs_touched=false`
  - `committed_machine_specific_ros_env=false`
