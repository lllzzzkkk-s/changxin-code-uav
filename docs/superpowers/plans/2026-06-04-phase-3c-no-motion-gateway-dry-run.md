# Phase 3C No-Motion Gateway Dry-Run Plan

Date: 2026-06-04

Goal: perform one explicitly authorized, no-motion call to
`/fleet/ugv_0/gateway/dry_run` using a validated `TaskCommand.v1` and an
operator-confirmed `UnitUgvTargetMap.v1` manual-confirm mapping.

Architecture: keep `center PDDL -> task-level BT/state machine -> platform
gateway -> local ROS1`. The gateway remains the only ROS1 task interface. This
phase may call only the gateway `dry_run` service. It must not call
`dispatch`, publish raw ROS topics, or authorize motion.

## Starting Evidence

Phase 3B completed:

- evidence:
  `docs/superpowers/evidence/2026-06-04-ugv-phase-3b-4060-signatures-observed-success.md`
- `TaskPlanningSiteAcceptance.v1 ok=true`
- `acceptance_level=work_hardware_ros1_signatures_observed`
- matched services:
  - `/fleet/ugv_0/gateway/dry_run`
  - `/fleet/ugv_0/gateway/dispatch`
- service type:
  `platform_gateway_msgs/TaskCommandJson`
- service arg:
  `task_command_json`
- wrapper stopped after read-only evidence capture
- no `dry_run`, `dispatch`, controlled motion, or `rostopic pub` occurred

## Hard Boundary

Phase 3C requires explicit local operator authorization because it calls a ROS
service, even though the service is `/gateway/dry_run`.

Authorized only for Phase 3C:

- create or validate a local `UnitUgvTargetMap.v1` with `action=manual_confirm`
- extract a validated `TaskCommand.v1` for `ugv_0` / `confirm_target`
- start the gateway wrapper with the target map
- call `/fleet/ugv_0/gateway/dry_run` once
- capture the returned `GatewayServiceResponse.v1` / `CommandAck.v1`
- stop the wrapper after evidence capture unless the operator explicitly keeps
  it running

Still prohibited:

- `/fleet/ugv_0/gateway/dispatch`
- `--unit-ugv-operator-approved`
- `--unit-ugv-enable-move-base`
- `move_base_goal` target maps
- controlled motion
- `rostopic pub`
- raw `/cmd_vel`, `/move_base_simple/goal`, `/setpoints_cmd`, or similar direct
  controls from the center
- model calls on the unit execution lane
- committed machine-specific ROS profiles or IPs
- non-convex alpha document edits

## Stage 0: Mac-Side Receipt And Plan

Owner: Mac Codex.

Files:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3b-4060-signatures-observed-success.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3b-4060-signatures-observed-success.json`
- `docs/superpowers/plans/2026-06-04-phase-3c-no-motion-gateway-dry-run.md`
- `docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md`
- `docs/superpowers/specs/2026-06-02-distributed-fleet-phase-2-to-langgraph-roadmap.md`

Exit gate:

- Phase 3B signature success receipt recorded
- Phase 3C dry-run plan and 4060 prompt written
- no Mac-side ROS access

## Stage 1: Prepare No-Motion Inputs

Owner: 4060 Codex after explicit authorization.

Create or validate a local target map. This file is unit-local configuration,
not repo architecture:

```bash
mkdir -p /tmp/changxin-phase3c
cat > /tmp/changxin-phase3c/unit_ugv_targets.manual_confirm.json <<'JSON'
{
  "schema": "UnitUgvTargetMap.v1",
  "platform_id": "ugv_0",
  "targets": {
    "target_01": {
      "capability": "confirm_target",
      "action": "manual_confirm",
      "operator_confirmed_mapping": true,
      "description": "operator-confirmed no-motion target check"
    }
  }
}
JSON
python3 -m json.tool /tmp/changxin-phase3c/unit_ugv_targets.manual_confirm.json \
  > /tmp/changxin-phase3c/unit_ugv_targets.manual_confirm.pretty.json
sha256sum /tmp/changxin-phase3c/unit_ugv_targets.manual_confirm.json
```

Select a previously verified artifact root. Prefer the latest Phase 2B or
prevalidated artifact already generated on the 4060 side. Do not use a
model-lab artifact directly until it has passed unit-side artifact verification.

Extract the UGV `confirm_target` command:

```bash
export ARTIFACT_ROOT=<operator-confirmed-artifact-root>
PYTHONDONTWRITEBYTECODE=1 python3 tools/extract_task_command_from_artifact.py \
  "$ARTIFACT_ROOT" \
  --platform-id ugv_0 \
  --capability confirm_target \
  --format report \
  > /tmp/changxin-phase3c/extracted_task_command.report.json
python3 -m json.tool /tmp/changxin-phase3c/extracted_task_command.report.json \
  > /tmp/changxin-phase3c/extracted_task_command.report.pretty.json
PYTHONDONTWRITEBYTECODE=1 python3 tools/extract_task_command_from_artifact.py \
  "$ARTIFACT_ROOT" \
  --platform-id ugv_0 \
  --capability confirm_target \
  --format rosservice-yaml \
  > /tmp/changxin-phase3c/task_command.rosservice.json
sha256sum /tmp/changxin-phase3c/extracted_task_command.report.json
sha256sum /tmp/changxin-phase3c/task_command.rosservice.json
```

Exit gate:

- target map JSON parses
- target map has `operator_confirmed_mapping=true`
- target action is `manual_confirm`
- extracted command report has `ok=true`
- extracted command has `platform_id=ugv_0`
- extracted command has `capability=confirm_target`
- extracted command has `parameters.target_id=target_01`

## Stage 2: Start Wrapper For No-Motion Dry-Run

Owner: 4060 Codex after explicit authorization.

Start the wrapper with the manual-confirm target map. Do not pass
`--unit-ugv-operator-approved` or `--unit-ugv-enable-move-base`.

```bash
export CATKIN_WS=/home/uavdev/catkin_ws
source /opt/ros/noetic/setup.bash
source "$CATKIN_WS/devel/setup.bash"
export ROS_MASTER_URI=http://192.168.0.201:11311
if [ -z "${ROS_IP:-}" ] && [ -z "${ROS_HOSTNAME:-}" ]; then
  ROS_IP="$(ip route get 192.168.0.201 | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
  export ROS_IP
fi

python3 - <<'PY'
import os, socket, urllib.parse
uri = os.environ.get("ROS_MASTER_URI", "")
parsed = urllib.parse.urlparse(uri)
host = parsed.hostname
port = parsed.port or 11311
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

(
  cd /mnt/d/changxin/changxin-code
  source /opt/ros/noetic/setup.bash
  source "$CATKIN_WS/devel/setup.bash"
  export ROS_MASTER_URI=http://192.168.0.201:11311
  export ROS_IP="${ROS_IP:-}"
  exec env PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/mnt/d/changxin/changxin-code:$PYTHONPATH \
    python3 tools/run_ros1_platform_gateway_node.py \
      --platform-id ugv_0 \
      --platform-type ugv \
      --capability confirm_target \
      --service-symbol platform_gateway_msgs.srv:TaskCommandJson \
      --unit-ugv-target-map /tmp/changxin-phase3c/unit_ugv_targets.manual_confirm.json \
      --unit-ugv-progress-output /tmp/changxin-phase3c/task_progress_after_dry_run.json \
      --node-name platform_gateway_ugv_0_phase3c
) > /tmp/changxin-phase3c/gateway-wrapper.log 2>&1 &
GATEWAY_PID=$!
echo "$GATEWAY_PID" > /tmp/changxin-phase3c/gateway-wrapper.pid
sleep 5
ps -p "$GATEWAY_PID" -o pid=,cmd=
```

Exit gate:

- wrapper stays alive
- `/fleet/ugv_0/gateway/dry_run` exists
- `/fleet/ugv_0/gateway/dispatch` exists
- no service call has happened yet

## Stage 3: Call Dry-Run Once

Owner: 4060 Codex after explicit authorization.

Call only the dry-run service:

```bash
rosservice call /fleet/ugv_0/gateway/dry_run \
  "$(cat /tmp/changxin-phase3c/task_command.rosservice.json)" \
  | tee /tmp/changxin-phase3c/gateway-dry-run-response.txt
DRY_RUN_RC=${PIPESTATUS[0]}
echo "$DRY_RUN_RC" > /tmp/changxin-phase3c/gateway-dry-run.rc
sha256sum /tmp/changxin-phase3c/gateway-dry-run-response.txt
sha256sum /tmp/changxin-phase3c/gateway-dry-run.rc
```

Parse the returned `response_json` field:

```bash
python3 - <<'PY'
import json
from pathlib import Path

text = Path("/tmp/changxin-phase3c/gateway-dry-run-response.txt").read_text(encoding="utf-8")
try:
    import yaml  # type: ignore
    outer = yaml.safe_load(text)
except Exception as exc:
    raise SystemExit(f"failed to parse rosservice response as YAML: {exc}")

if not isinstance(outer, dict) or "response_json" not in outer:
    raise SystemExit("rosservice response did not contain response_json")
response = json.loads(str(outer["response_json"]))
Path("/tmp/changxin-phase3c/gateway-dry-run-response.parsed.json").write_text(
    json.dumps(response, indent=2, sort_keys=True),
    encoding="utf-8",
)
print(json.dumps({
    "schema": response.get("schema"),
    "mode": response.get("mode"),
    "platform_id": response.get("platform_id"),
    "ack_accepted": response.get("ack", {}).get("accepted"),
    "ack_reason": response.get("ack", {}).get("reason"),
    "motion_attempted": response.get("motion_attempted"),
    "raw_ros_publish_attempted": response.get("raw_ros_publish_attempted"),
}, indent=2, sort_keys=True))
PY
sha256sum /tmp/changxin-phase3c/gateway-dry-run-response.parsed.json
```

Expected parsed response:

- response JSON schema is `GatewayServiceResponse.v1`
- `mode=dry_run`
- `platform_id=ugv_0`
- `ack.schema=CommandAck.v1`
- `ack.accepted=true`
- `ack.reason=unit_ugv_dry_run_ok`
- `motion_attempted=false`
- `raw_ros_publish_attempted=false`

If the ack rejects or parsing fails, record the response and stop. Do not retry
with a hand-written command.

## Stage 4: Stop Wrapper And Report

Owner: 4060 Codex.

```bash
kill "$GATEWAY_PID" || true
wait "$GATEWAY_PID" || true
sha256sum /tmp/changxin-phase3c/gateway-wrapper.log
sha256sum /tmp/changxin-phase3c/gateway-wrapper.pid
test -f /tmp/changxin-phase3c/task_progress_after_dry_run.json && \
  sha256sum /tmp/changxin-phase3c/task_progress_after_dry_run.json || true
```

Dry-run should not create task-progress evidence because the unit UGV executor
only writes progress on dispatch. If a progress file exists, record and inspect
it as an unexpected condition.

## 4060 Prompt

Use this prompt only after the user/operator explicitly authorizes Phase 3C
no-motion gateway dry-run.

```text
Continue UGV Phase 3C no-motion gateway dry-run.

You are on the unit 4060 WSL2 side. Phase 3B read-only signatures passed:
/fleet/ugv_0/gateway/dry_run and /fleet/ugv_0/gateway/dispatch both use
platform_gateway_msgs/TaskCommandJson with task_command_json arg.

Authorization scope:
- create/validate local UnitUgvTargetMap.v1 with action=manual_confirm
- extract a validated TaskCommand.v1 for ugv_0 confirm_target from a verified artifact
- start gateway wrapper with --unit-ugv-target-map only
- call /fleet/ugv_0/gateway/dry_run once
- capture response/logs
- stop wrapper after capture

Not authorized:
- do not call /fleet/ugv_0/gateway/dispatch
- do not use --unit-ugv-operator-approved
- do not use --unit-ugv-enable-move-base
- do not use move_base_goal target maps
- do not authorize controlled motion
- do not run rostopic pub
- do not hand-write TaskCommand JSON
- do not edit repo architecture
- do not touch non-convex alpha docs
- do not commit machine-specific ROS IP/env

Work in /mnt/d/changxin/changxin-code:
git fetch origin
git checkout codex/phase2b-no-hardware-reporting
git pull --ff-only origin codex/phase2b-no-hardware-reporting
git log -2 --oneline
git status --short

Then follow:
docs/superpowers/plans/2026-06-04-phase-3c-no-motion-gateway-dry-run.md

Stop if:
- no verified artifact root is available
- extracted command is not ok=true
- command is not ugv_0 confirm_target target_01
- ROS master TCP preflight fails
- wrapper does not stay alive
- dry_run response is not GatewayServiceResponse.v1

Report:
- artifact root used
- target map path/sha256
- extracted command report key fields/sha256
- task_command.rosservice.json sha256
- wrapper pid/log/sha256
- dry_run rc and response path/sha256
- parsed response path/sha256
- parsed response key fields
- whether wrapper stopped
- boundary confirmation:
  dispatch_called=false
  controlled_motion_authorized=false
  rostopic_pub=false
  repo_architecture_changed=false
  non_convex_alpha_docs_touched=false
```

## Phase 3C Result: No-Motion Dry-Run Passed

On 2026-06-04, the 4060 side completed Phase 3C. The wrapper started, one
`/fleet/ugv_0/gateway/dry_run` call was made, the gateway returned an accepted
`GatewayServiceResponse.v1` / `CommandAck.v1`, and the wrapper was stopped
after capture.

Evidence:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3c-4060-no-motion-dry-run-success.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3c-4060-no-motion-dry-run-success.json`

Reported result:

```text
artifact_root=/tmp/changxin-phase2b-dev-mock-single/8d783b73-f8f2-488c-9d53-6b3881806784
ROS_MASTER_URI=http://192.168.0.201:11311
ROS_IP=172.20.26.179
tcp_connect=OK
gateway_wrapper_pid=2502
dry_run_rc=0
progress_file_exists=false
wrapper_stopped_after_capture=true
```

Parsed response:

```text
schema=GatewayServiceResponse.v1
mode=dry_run
platform_id=ugv_0
ack_schema=CommandAck.v1
ack_accepted=true
ack_reason=unit_ugv_dry_run_ok
motion_attempted=false
raw_ros_publish_attempted=false
local_check_target_mapped=true
local_check_mapping_operator_confirmed=true
local_check_motion_attempted=false
local_check_raw_ros_publish_attempted=false
```

Boundary preserved:

- only one `/fleet/ugv_0/gateway/dry_run` call
- no `/fleet/ugv_0/gateway/dispatch` call
- wrapper command did not include `--unit-ugv-operator-approved`
- wrapper command did not include `--unit-ugv-enable-move-base`
- no `move_base` target map
- no progress-output
- no controlled motion
- no `rostopic pub`
- no hand-written `TaskCommand` JSON
- repo architecture not changed
- non-convex alpha documents not touched

Interpretation:

- Phase 3C no-motion gateway `dry_run` objective is complete.
- This is not dispatch proof, dispatch rejection proof, controlled-motion
  proof, task-progress proof, or final hardware execution proof.
- The next gate is Phase 3D pre-approval dispatch rejection:
  `docs/superpowers/plans/2026-06-04-phase-3d-pre-approval-dispatch-rejection.md`.
