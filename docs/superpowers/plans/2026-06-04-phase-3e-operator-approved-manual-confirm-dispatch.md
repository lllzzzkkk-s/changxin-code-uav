# Phase 3E Operator-Approved Manual-Confirm Dispatch Plan

Date: 2026-06-04

Goal: prove one explicitly approved `/fleet/ugv_0/gateway/dispatch` call can
complete the no-motion `manual_confirm` UGV path and write matching
`TaskProgressSet.v1` evidence.

This is an approved dispatch/progress gate, but it is still a no-motion gate. It
must not enable `move_base`, use `move_base_goal`, or authorize controlled
motion.

Architecture: keep `center PDDL -> task-level BT/state machine -> platform
gateway -> local ROS1`. The center still sends only validated
`TaskCommand.v1`; the platform gateway and local UGV executor enforce approval,
target mapping, progress, and no raw ROS publish.

## Starting Evidence

Phase 3D completed:

- evidence:
  `docs/superpowers/evidence/2026-06-04-ugv-phase-3d-4060-pre-approval-dispatch-rejection-success.md`
- `dispatch_called_once=true`
- `dispatch_accepted=false`
- `ack_reason=operator approval required for unit UGV dispatch`
- `motion_attempted=false`
- `raw_ros_publish_attempted=false`
- `progress_file_exists=false`
- wrapper stopped after capture

Phase 3C validated inputs to reuse or regenerate:

```text
/tmp/changxin-phase3c/unit_ugv_targets.manual_confirm.json
sha256=62aac9e2a391793b01ed434eb02b7d52aebcbb4f1eb7e331e74c414a8298740e

/tmp/changxin-phase3c/extracted_task_command.report.json
sha256=bd5b762fe057ed8c12d4c4b354fab6f8f924d288cb43d1b5f6e81eefc59c0d80

/tmp/changxin-phase3c/task_command.rosservice.json
sha256=8c04ce46c3d2f5fde6b57d0335b09d64ebd5f3854bb253f9617f128fe6faf3e5
```

## Hard Boundary

Phase 3E requires explicit local operator authorization because it calls
`dispatch` with `--unit-ugv-operator-approved`.

Authorized only for Phase 3E:

- verify or regenerate the Phase 3C no-motion inputs
- start the gateway wrapper with `--unit-ugv-target-map`
- pass `--unit-ugv-operator-approved`
- pass `--unit-ugv-progress-output`
- do not pass `--unit-ugv-enable-move-base`
- call `/fleet/ugv_0/gateway/dispatch` once
- capture `GatewayServiceResponse.v1` / `CommandAck.v1`
- capture `TaskProgressSet.v1`
- stop the wrapper after evidence capture

Expected dispatch response:

- `schema=GatewayServiceResponse.v1`
- `mode=dispatch`
- `platform_id=ugv_0`
- `ack.schema=CommandAck.v1`
- `ack.accepted=true`
- `ack.reason=manual_confirm_completed`
- `motion_attempted=false`
- `raw_ros_publish_attempted=false`
- `ack.local_check.dispatch_action=manual_confirm`

Expected progress evidence:

- `schema=TaskProgressSet.v1`
- exactly one `TaskProgress.v1` item for the selected command
- `status=completed`
- `progress_ratio=1.0`
- `message=manual_confirm_completed`
- `platform_id=ugv_0`
- `observations.target_id=target_01`
- `observations.unit_ugv_action=manual_confirm`
- `observations.motion_attempted=false`

Still prohibited:

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

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3d-4060-pre-approval-dispatch-rejection-success.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3d-4060-pre-approval-dispatch-rejection-success.json`
- `docs/superpowers/plans/2026-06-04-phase-3e-operator-approved-manual-confirm-dispatch.md`
- `docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md`
- `docs/superpowers/specs/2026-06-02-distributed-fleet-phase-2-to-langgraph-roadmap.md`

Exit gate:

- Phase 3D pre-approval dispatch rejection receipt recorded
- Phase 3E approved manual-confirm dispatch plan and 4060 prompt written
- no Mac-side ROS access

## Stage 1: Re-Verify Inputs

Owner: 4060 Codex after explicit authorization.

Use the existing Phase 3C files if present. Do not hand-write a new
`TaskCommand`.

```bash
mkdir -p /tmp/changxin-phase3e
sha256sum /tmp/changxin-phase3c/unit_ugv_targets.manual_confirm.json
sha256sum /tmp/changxin-phase3c/extracted_task_command.report.json
sha256sum /tmp/changxin-phase3c/task_command.rosservice.json
python3 -m json.tool /tmp/changxin-phase3c/unit_ugv_targets.manual_confirm.json \
  > /tmp/changxin-phase3e/unit_ugv_targets.manual_confirm.pretty.json
python3 -m json.tool /tmp/changxin-phase3c/extracted_task_command.report.json \
  > /tmp/changxin-phase3e/extracted_task_command.report.pretty.json
```

Exit gate:

- target map JSON parses
- target action is `manual_confirm`
- target map has `operator_confirmed_mapping=true`
- extracted command report has `ok=true`
- extracted command has `platform_id=ugv_0`
- extracted command has `capability=confirm_target`
- extracted command has `parameters.target_id=target_01`

## Stage 2: Start Wrapper With Approval But Without Move-Base

Owner: 4060 Codex after explicit authorization.

Start the wrapper with `--unit-ugv-operator-approved` and progress output. Do
not pass `--unit-ugv-enable-move-base`.

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
      --unit-ugv-operator-approved \
      --unit-ugv-progress-output /tmp/changxin-phase3e/task_progress_after_dispatch.json \
      --node-name platform_gateway_ugv_0_phase3e
) > /tmp/changxin-phase3e/gateway-wrapper.log 2>&1 &
GATEWAY_PID=$!
echo "$GATEWAY_PID" > /tmp/changxin-phase3e/gateway-wrapper.pid
sleep 5
ps -p "$GATEWAY_PID" -o pid=,cmd=
```

Exit gate:

- wrapper stays alive
- `/fleet/ugv_0/gateway/dispatch` exists
- wrapper command includes `--unit-ugv-operator-approved`
- wrapper command includes `--unit-ugv-progress-output`
- wrapper command does not include `--unit-ugv-enable-move-base`
- target map remains `manual_confirm`
- no service call has happened yet

## Stage 3: Call Approved Manual-Confirm Dispatch Once

Owner: 4060 Codex after explicit authorization.

```bash
rosservice call /fleet/ugv_0/gateway/dispatch \
  "$(cat /tmp/changxin-phase3c/task_command.rosservice.json)" \
  | tee /tmp/changxin-phase3e/gateway-dispatch-response.txt
DISPATCH_RC=${PIPESTATUS[0]}
echo "$DISPATCH_RC" > /tmp/changxin-phase3e/gateway-dispatch.rc
sha256sum /tmp/changxin-phase3e/gateway-dispatch-response.txt
sha256sum /tmp/changxin-phase3e/gateway-dispatch.rc
```

Parse the returned `response_json` field:

```bash
python3 - <<'PY'
import json
from pathlib import Path

text = Path("/tmp/changxin-phase3e/gateway-dispatch-response.txt").read_text(encoding="utf-8")
try:
    import yaml  # type: ignore
    outer = yaml.safe_load(text)
except Exception as exc:
    raise SystemExit(f"failed to parse rosservice response as YAML: {exc}")

if not isinstance(outer, dict) or "response_json" not in outer:
    raise SystemExit("rosservice response did not contain response_json")
response = json.loads(str(outer["response_json"]))
Path("/tmp/changxin-phase3e/gateway-dispatch-response.parsed.json").write_text(
    json.dumps(response, indent=2, sort_keys=True),
    encoding="utf-8",
)
summary = {
    "schema": response.get("schema"),
    "mode": response.get("mode"),
    "platform_id": response.get("platform_id"),
    "ack_schema": response.get("ack", {}).get("schema"),
    "ack_accepted": response.get("ack", {}).get("accepted"),
    "ack_reason": response.get("ack", {}).get("reason"),
    "motion_attempted": response.get("motion_attempted"),
    "raw_ros_publish_attempted": response.get("raw_ros_publish_attempted"),
    "local_check_dispatch_action": response.get("ack", {}).get("local_check", {}).get("dispatch_action"),
    "local_check_motion_attempted": response.get("ack", {}).get("local_check", {}).get("motion_attempted"),
    "local_check_raw_ros_publish_attempted": response.get("ack", {}).get("local_check", {}).get("raw_ros_publish_attempted"),
}
Path("/tmp/changxin-phase3e/gateway-dispatch-response.summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True),
    encoding="utf-8",
)
print(json.dumps(summary, indent=2, sort_keys=True))
PY
sha256sum /tmp/changxin-phase3e/gateway-dispatch-response.parsed.json
sha256sum /tmp/changxin-phase3e/gateway-dispatch-response.summary.json
```

Exit gate:

- `DISPATCH_RC=0`
- parsed response schema is `GatewayServiceResponse.v1`
- `mode=dispatch`
- `platform_id=ugv_0`
- `ack.schema=CommandAck.v1`
- `ack.accepted=true`
- `ack.reason=manual_confirm_completed`
- `motion_attempted=false`
- `raw_ros_publish_attempted=false`
- `ack.local_check.dispatch_action=manual_confirm`

If dispatch rejects, motion is attempted, or parsing fails, stop after evidence
capture. Do not retry with altered flags or hand-written command JSON.

## Stage 4: Validate Progress And Stop Wrapper

Owner: 4060 Codex.

```bash
python3 -m json.tool /tmp/changxin-phase3e/task_progress_after_dispatch.json \
  > /tmp/changxin-phase3e/task_progress_after_dispatch.pretty.json
python3 - <<'PY'
import json
from pathlib import Path

progress = json.loads(Path("/tmp/changxin-phase3e/task_progress_after_dispatch.json").read_text(encoding="utf-8"))
items = progress.get("items", [])
summary = {
    "schema": progress.get("schema"),
    "item_count": len(items),
}
if items:
    item = items[0]
    summary.update({
        "item_schema": item.get("schema"),
        "mission_id": item.get("mission_id"),
        "task_id": item.get("task_id"),
        "platform_id": item.get("platform_id"),
        "status": item.get("status"),
        "progress_ratio": item.get("progress_ratio"),
        "message": item.get("message"),
        "observations_target_id": item.get("observations", {}).get("target_id"),
        "observations_unit_ugv_action": item.get("observations", {}).get("unit_ugv_action"),
        "observations_motion_attempted": item.get("observations", {}).get("motion_attempted"),
    })
Path("/tmp/changxin-phase3e/task_progress_after_dispatch.summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True),
    encoding="utf-8",
)
print(json.dumps(summary, indent=2, sort_keys=True))
PY
sha256sum /tmp/changxin-phase3e/task_progress_after_dispatch.json
sha256sum /tmp/changxin-phase3e/task_progress_after_dispatch.summary.json

kill "$GATEWAY_PID" || true
wait "$GATEWAY_PID" || true
sha256sum /tmp/changxin-phase3e/gateway-wrapper.log
sha256sum /tmp/changxin-phase3e/gateway-wrapper.pid
```

Exit gate:

- progress file exists
- progress schema is `TaskProgressSet.v1`
- exactly one progress item exists
- item schema is `TaskProgress.v1`
- item status is `completed`
- item message is `manual_confirm_completed`
- item platform is `ugv_0`
- item target is `target_01`
- item action is `manual_confirm`
- item `motion_attempted=false`
- wrapper is stopped after capture

## 4060 Prompt

Use this prompt only after the user/operator explicitly authorizes Phase 3E
operator-approved no-motion manual-confirm dispatch.

```text
Continue UGV Phase 3E operator-approved manual-confirm dispatch.

You are on the unit 4060 WSL2 side. Phase 3D passed: dispatch was called once
without operator approval and was rejected with reason "operator approval
required for unit UGV dispatch", motion_attempted=false.

Authorization scope:
- re-verify or regenerate Phase 3C validated no-motion inputs
- start gateway wrapper with --unit-ugv-target-map
- start gateway wrapper with --unit-ugv-operator-approved
- start gateway wrapper with --unit-ugv-progress-output
- do not pass --unit-ugv-enable-move-base
- call /fleet/ugv_0/gateway/dispatch once
- capture response/logs
- validate TaskProgressSet.v1
- stop wrapper after capture

Expected result:
- dispatch service call returns rc=0
- parsed response schema=GatewayServiceResponse.v1
- mode=dispatch
- platform_id=ugv_0
- ack.schema=CommandAck.v1
- ack.accepted=true
- ack.reason=manual_confirm_completed
- motion_attempted=false
- raw_ros_publish_attempted=false
- progress schema=TaskProgressSet.v1
- progress item status=completed
- progress item observations.unit_ugv_action=manual_confirm
- progress item observations.motion_attempted=false

Not authorized:
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
docs/superpowers/plans/2026-06-04-phase-3e-operator-approved-manual-confirm-dispatch.md

Stop if:
- validated input hashes cannot be verified or regenerated
- command is not ugv_0 confirm_target target_01
- target action is not manual_confirm
- ROS master TCP preflight fails
- wrapper does not stay alive
- wrapper command includes enable-move-base or move_base_goal
- dispatch response is not GatewayServiceResponse.v1
- dispatch rejects
- motion_attempted is true
- progress file is missing or invalid

Report:
- input artifact paths/sha256
- wrapper pid/log/sha256
- dispatch rc and response path/sha256
- parsed response path/sha256
- progress path/sha256
- parsed response key fields
- progress summary key fields
- whether wrapper stopped
- boundary confirmation:
  dispatch_called_once=true
  dispatch_accepted=true
  operator_approved=true
  enable_move_base=false
  target_action=manual_confirm
  controlled_motion_authorized=false
  motion_attempted=false
  rostopic_pub=false
  repo_architecture_changed=false
  non_convex_alpha_docs_touched=false
```
