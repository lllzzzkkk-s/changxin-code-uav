# Phase 3B ROS1 Gateway Lifecycle Prep Plan

Date: 2026-06-04

Goal: prepare the unit 4060/UGV ROS1 gateway lifecycle so the expected
`/fleet/ugv_0/gateway/dry_run` and `/fleet/ugv_0/gateway/dispatch` services can
be registered and then verified with read-only service-signature capture.

Architecture: keep `center PDDL -> task-level BT/state machine -> platform
gateway -> local ROS1`. The gateway remains the boundary. The center must not
publish raw ROS topics and must not call low-level motion interfaces.

## Starting Evidence

Phase 3A retry result:

- evidence:
  `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-master-reachable-gateway-missing-retry.md`
- `ROS_MASTER_URI=http://192.168.0.201:11311`
- TCP connect to `192.168.0.201:11311`: OK
- `rosservice list`: `65` services
- `/fleet/ugv_0/gateway/dry_run`: missing
- `/fleet/ugv_0/gateway/dispatch`: missing
- verifier: `TaskPlanningSiteAcceptance.v1 ok=False`
- failure class: `ros_master_reachable_gateway_services_missing`

Phase 3B is needed because another Phase 3A retry will still fail until the
gateway wrapper registers the expected services.

## Hard Boundary

Phase 3B may prepare, build, start, and observe the gateway service lifecycle
only after the matching local operator authorization.

Still prohibited in Phase 3B:

- gateway `dry_run` service call
- gateway `dispatch` service call
- controlled motion
- `rostopic pub`
- raw `/cmd_vel`, `/move_base_simple/goal`, `/setpoints_cmd`, or similar direct
  control from the center
- model calls on the unit execution lane
- committed machine-specific ROS addresses or credentials
- non-convex alpha document edits

## Stage 0: Mac-Side Receipt And Plan

Owner: Mac Codex.

Files:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-master-reachable-gateway-missing-retry.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-master-reachable-gateway-missing-retry.json`
- `docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md`
- `docs/superpowers/specs/2026-06-02-distributed-fleet-phase-2-to-langgraph-roadmap.md`

Exit gate:

- 4060 retry receipt recorded as a failed Phase 3A gate
- failure reason captured as missing gateway services, not master reachability
- Phase 3B plan and 4060 prompt written

## Stage 1: 4060 Workspace Target Confirmation

Owner: 4060 Codex with local operator input.

Purpose: identify the intended catkin workspace before installing or building
anything.

Required local input:

- the catkin workspace root, for example `/home/uavdev/catkin_ws` or a
  site-specific gateway workspace
- the corresponding `src` directory
- whether the operator authorizes creating the workspace if it does not exist

Read-only commands allowed:

```bash
pwd
whoami
echo "HOME=$HOME"
echo "ROS_MASTER_URI=${ROS_MASTER_URI:-}"
test -d "$CATKIN_WS" && find "$CATKIN_WS" -maxdepth 3 -type f -name setup.bash -print || true
test -d "$CATKIN_SRC" && find "$CATKIN_SRC" -maxdepth 2 -type f \( -name package.xml -o -name CMakeLists.txt \) -print || true
```

Stop condition:

- no operator-confirmed `CATKIN_WS` and `CATKIN_SRC`
- no authorization to create missing workspace directories

## Stage 2: Gateway Message Package Dry-Run

Owner: 4060 Codex.

Purpose: prove the repo package source is available and the target catkin path
is valid before applying changes.

Command:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py \
  --catkin-src "$CATKIN_SRC" \
  > /tmp/changxin-phase3b-gateway-workspace-dry-run.json
python3 -m json.tool /tmp/changxin-phase3b-gateway-workspace-dry-run.json \
  > /tmp/changxin-phase3b-gateway-workspace-dry-run.pretty.json
```

Exit gate:

- dry-run JSON parses
- `schema=Ros1GatewayWorkspacePlan.v1`
- `ok=True`
- `dry_run=True`
- `installed=False`
- target package path is the operator-confirmed catkin workspace

If the dry-run reports `catkin src path does not exist`, stop and ask the
operator whether to create the workspace.

### Stage 2 Result: Dry-Run Passed, Stopped For Stage 3 Authorization

On 2026-06-04, the 4060 side reported that it completed Stage 2 and stopped
before Stage 3 apply/build.

Evidence:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3b-4060-workspace-dry-run-auth-stop.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3b-4060-workspace-dry-run-auth-stop.json`

Reported state:

```text
CATKIN_WS=/home/uavdev/catkin_ws
CATKIN_SRC=/home/uavdev/catkin_ws/src
/home/uavdev/catkin_ws/devel/setup.bash exists
/home/uavdev/catkin_ws/src contains only catkin top-level CMakeLists.txt symlink
platform_gateway_msgs installed: no
```

Reported dry-run:

```text
/tmp/changxin-phase3b-gateway-workspace-dry-run.json
schema='Ros1GatewayWorkspacePlan.v1'
ok=True
dry_run=True
installed=False
mode='copy'
catkin_src='/home/uavdev/catkin_ws/src'
validation_errors=[]
warnings=[]
sha256=948c362139e7b5337d5f16b6d8006c512b395b5969bfe695026156bb111a4f62
```

Boundary preserved:

- Stage 3 `apply/build` not run
- gateway wrapper not started
- gateway `dry_run` not called
- gateway `dispatch` not called
- controlled motion not authorized
- `rostopic pub` not run
- repo architecture not changed
- non-convex alpha documents not touched

Next authorization point:

```text
Authorize Phase 3B Stage 3 apply/build only:
install platform_gateway_msgs into /home/uavdev/catkin_ws/src and run
catkin_make. Do not start the gateway wrapper yet.
```

## Stage 3: Apply Package And Build

Owner: 4060 Codex, only after explicit operator authorization.

This stage changes the local unit catkin workspace. It does not modify repo
architecture and does not call gateway services.

Commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py \
  --catkin-src "$CATKIN_SRC" \
  --apply \
  > /tmp/changxin-phase3b-gateway-workspace-apply.json
python3 -m json.tool /tmp/changxin-phase3b-gateway-workspace-apply.json \
  > /tmp/changxin-phase3b-gateway-workspace-apply.pretty.json

cd "$CATKIN_WS"
catkin_make | tee /tmp/changxin-phase3b-catkin-make.log
source devel/setup.bash
PYTHONPATH=/mnt/d/changxin/changxin-code:$PYTHONPATH python3 - <<'PY'
from platform_gateway_msgs.srv import TaskCommandJson
print(TaskCommandJson)
PY
```

Exit gate:

- apply JSON parses and reports `installed=True`
- `catkin_make` exits `0`
- `source devel/setup.bash` succeeds
- Python can import `platform_gateway_msgs.srv.TaskCommandJson`

Stop condition:

- missing build dependencies
- wrong workspace
- generated service import fails

Stage 3 does not start the gateway wrapper. If Stage 3 passes, stop and return
the apply JSON, build log, import result, and boundary confirmation. Stage 4
requires separate authorization.

## Stage 4: Start Gateway Wrapper For Service Registration

Owner: 4060 Codex, only after explicit operator authorization.

This stage starts a ROS node and registers services. It still must not call
gateway `dry_run`, gateway `dispatch`, or motion interfaces.

Recommended no-motion registration command:

```bash
cd /mnt/d/changxin/changxin-code
source /opt/ros/noetic/setup.bash
source "$CATKIN_WS/devel/setup.bash"
export ROS_MASTER_URI=http://192.168.0.201:11311

PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/mnt/d/changxin/changxin-code:$PYTHONPATH \
python3 tools/run_ros1_platform_gateway_node.py \
  --platform-id ugv_0 \
  --platform-type ugv \
  --capability confirm_target \
  --service-symbol platform_gateway_msgs.srv:TaskCommandJson \
  --node-name platform_gateway_ugv_0
```

Run it in a dedicated terminal/session so it stays alive for read-only
observation.

Exit gate:

- node stays running
- no service call is made
- no motion is attempted

## Stage 5: Read-Only Signature Verification

Owner: 4060 Codex.

Once the gateway node is running, rerun the Phase 3A service-signature gate.

Direct verifier path:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
  --profile /tmp/changxin-work-hardware-ros1-gateway-retry.env \
  --platform-id ugv_0 \
  --run-rosservice-list \
  --run-service-signatures \
  --require-rosservice-audit \
  --require-service-signatures \
  > /tmp/changxin-phase3b-site-acceptance-ros1-gateway.json
python3 -m json.tool /tmp/changxin-phase3b-site-acceptance-ros1-gateway.json \
  > /tmp/changxin-phase3b-site-acceptance-ros1-gateway.pretty.json
```

Supplemental raw capture:

```bash
rosservice list | tee /tmp/changxin-phase3b-rosservice-list.txt
for s in /fleet/ugv_0/gateway/dry_run /fleet/ugv_0/gateway/dispatch; do
  printf "%s " "$s"
  rosservice type "$s"
done | tee /tmp/changxin-phase3b-rosservice-types.txt
for s in /fleet/ugv_0/gateway/dry_run /fleet/ugv_0/gateway/dispatch; do
  printf "%s " "$s"
  rosservice args "$s"
done | tee /tmp/changxin-phase3b-rosservice-args.txt
```

Exit gate:

- `TaskPlanningSiteAcceptance.v1 ok=True`
- `platform_backend=ros1_gateway`
- `rosservice_audit.missing_services=[]`
- matched services include:
  - `/fleet/ugv_0/gateway/dry_run`
  - `/fleet/ugv_0/gateway/dispatch`
- observed type ends with `TaskCommandJson`
- observed args include `task_command_json`
- no gateway service calls were made

## 4060 Prompt

Use this prompt after the Mac receipt commit is available on GitHub:

```text
Continue UGV Phase 3B gateway lifecycle prep.

You are on the unit 4060 WSL2 side. Mac has recorded that Phase 3A retry now
reaches ROS master http://192.168.0.201:11311, but gateway services are missing.

Stay within these boundaries:
- do not call /fleet/ugv_0/gateway/dry_run
- do not call /fleet/ugv_0/gateway/dispatch
- do not authorize controlled motion
- do not run rostopic pub
- do not edit repo architecture
- do not touch non-convex alpha docs
- do not commit machine-specific ROS IPs

Work in /mnt/d/changxin/changxin-code:
git fetch origin
git checkout codex/phase2b-no-hardware-reporting
git pull --ff-only origin codex/phase2b-no-hardware-reporting
git log -2 --oneline
git status --short

First ask/confirm with the local operator:
1. What is the intended catkin workspace root?
2. What is the intended catkin src path?
3. Are you authorized to create/install/build the gateway message package if
   missing?
4. Are you authorized to start the gateway wrapper process for service
   registration only?

Set variables only after operator confirmation:
export CATKIN_WS=<operator-confirmed-catkin-workspace>
export CATKIN_SRC="$CATKIN_WS/src"

Stage 1: inspect only, no changes:
pwd
whoami
echo "HOME=$HOME"
echo "CATKIN_WS=$CATKIN_WS"
echo "CATKIN_SRC=$CATKIN_SRC"
echo "ROS_MASTER_URI=${ROS_MASTER_URI:-}"
test -d "$CATKIN_WS" && find "$CATKIN_WS" -maxdepth 3 -type f -name setup.bash -print || true
test -d "$CATKIN_SRC" && find "$CATKIN_SRC" -maxdepth 2 -type f \( -name package.xml -o -name CMakeLists.txt \) -print || true

Stage 2: run dry-run only:
PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py \
  --catkin-src "$CATKIN_SRC" \
  > /tmp/changxin-phase3b-gateway-workspace-dry-run.json
python3 -m json.tool /tmp/changxin-phase3b-gateway-workspace-dry-run.json \
  > /tmp/changxin-phase3b-gateway-workspace-dry-run.pretty.json

If dry-run ok=false or catkin src is missing, stop and report. Do not create
directories unless the operator explicitly authorizes that in this turn.

Only if authorized, apply/build:
PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py \
  --catkin-src "$CATKIN_SRC" \
  --apply \
  > /tmp/changxin-phase3b-gateway-workspace-apply.json
python3 -m json.tool /tmp/changxin-phase3b-gateway-workspace-apply.json \
  > /tmp/changxin-phase3b-gateway-workspace-apply.pretty.json
cd "$CATKIN_WS"
catkin_make | tee /tmp/changxin-phase3b-catkin-make.log
source devel/setup.bash
PYTHONPATH=/mnt/d/changxin/changxin-code:$PYTHONPATH python3 - <<'PY'
from platform_gateway_msgs.srv import TaskCommandJson
print(TaskCommandJson)
PY

Only if authorized to start the wrapper for service registration, run in a
dedicated long-lived terminal/session:
cd /mnt/d/changxin/changxin-code
source /opt/ros/noetic/setup.bash
source "$CATKIN_WS/devel/setup.bash"
export ROS_MASTER_URI=http://192.168.0.201:11311
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/mnt/d/changxin/changxin-code:$PYTHONPATH \
python3 tools/run_ros1_platform_gateway_node.py \
  --platform-id ugv_0 \
  --platform-type ugv \
  --capability confirm_target \
  --service-symbol platform_gateway_msgs.srv:TaskCommandJson \
  --node-name platform_gateway_ugv_0

In another terminal, still read-only:
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
  --profile /tmp/changxin-work-hardware-ros1-gateway-retry.env \
  --platform-id ugv_0 \
  --run-rosservice-list \
  --run-service-signatures \
  --require-rosservice-audit \
  --require-service-signatures \
  > /tmp/changxin-phase3b-site-acceptance-ros1-gateway.json
python3 -m json.tool /tmp/changxin-phase3b-site-acceptance-ros1-gateway.json \
  > /tmp/changxin-phase3b-site-acceptance-ros1-gateway.pretty.json

Report:
- git log -2 and git status
- CATKIN_WS/CATKIN_SRC
- dry-run JSON key fields
- apply/build/import key fields if authorized and run
- whether gateway wrapper was started
- verifier JSON key fields if run
- matched/missing gateway services
- boundary confirmation:
  dry_run_called=false
  dispatch_called=false
  controlled_motion_authorized=false
  rostopic_publish=false
  repo_architecture_changed=false
  non_convex_alpha_docs_touched=false
```

## 4060 Prompt: Continue From Stage 3 Authorization Point

Use this prompt only after the user/operator explicitly authorizes Stage 3
apply/build. It still does not authorize starting the gateway wrapper.

```text
Continue UGV Phase 3B from the Stage 3 apply/build authorization point.

You are on the unit 4060 WSL2 side. Stage 2 already passed:
CATKIN_WS=/home/uavdev/catkin_ws
CATKIN_SRC=/home/uavdev/catkin_ws/src
dry-run ok=True
platform_gateway_msgs is not installed yet.

Authorization scope for this prompt:
- install platform_gateway_msgs into /home/uavdev/catkin_ws/src
- run catkin_make
- source devel/setup.bash
- verify Python can import platform_gateway_msgs.srv.TaskCommandJson

Not authorized in this prompt:
- do not start gateway wrapper
- do not call /fleet/ugv_0/gateway/dry_run
- do not call /fleet/ugv_0/gateway/dispatch
- do not authorize controlled motion
- do not run rostopic pub
- do not edit repo architecture
- do not touch non-convex alpha docs
- do not commit machine-specific ROS IP/env

Work in /mnt/d/changxin/changxin-code:
git fetch origin
git checkout codex/phase2b-no-hardware-reporting
git pull --ff-only origin codex/phase2b-no-hardware-reporting
git log -2 --oneline
git status --short

export CATKIN_WS=/home/uavdev/catkin_ws
export CATKIN_SRC=/home/uavdev/catkin_ws/src

Confirm starting state:
test -d "$CATKIN_WS" && echo "catkin_ws_exists=true"
test -d "$CATKIN_SRC" && echo "catkin_src_exists=true"
test -f "$CATKIN_WS/devel/setup.bash" && echo "setup_bash_exists=true"
find "$CATKIN_SRC" -maxdepth 2 -mindepth 1 -print | sort

Apply the gateway message package:
PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py \
  --catkin-src "$CATKIN_SRC" \
  --apply \
  > /tmp/changxin-phase3b-gateway-workspace-apply.json
python3 -m json.tool /tmp/changxin-phase3b-gateway-workspace-apply.json \
  > /tmp/changxin-phase3b-gateway-workspace-apply.pretty.json
sha256sum /tmp/changxin-phase3b-gateway-workspace-apply.json

Build:
cd "$CATKIN_WS"
catkin_make | tee /tmp/changxin-phase3b-catkin-make.log
echo "catkin_make_rc=${PIPESTATUS[0]}"
sha256sum /tmp/changxin-phase3b-catkin-make.log

Verify generated service import:
source "$CATKIN_WS/devel/setup.bash"
PYTHONPATH=/mnt/d/changxin/changxin-code:$PYTHONPATH python3 - <<'PY' \
  | tee /tmp/changxin-phase3b-task-command-json-import.txt
from platform_gateway_msgs.srv import TaskCommandJson
print(TaskCommandJson)
PY
echo "import_rc=${PIPESTATUS[0]}"
sha256sum /tmp/changxin-phase3b-task-command-json-import.txt

Stop here. Do not start the gateway wrapper.

Report:
- git log -2 and git status
- apply JSON key fields and sha256
- catkin_make rc and log sha256
- TaskCommandJson import rc and output
- final CATKIN_WS/CATKIN_SRC tree summary
- boundary confirmation:
  gateway_wrapper_started=false
  dry_run_called=false
  dispatch_called=false
  controlled_motion_authorized=false
  rostopic_pub=false
  repo_architecture_changed=false
  non_convex_alpha_docs_touched=false
```
