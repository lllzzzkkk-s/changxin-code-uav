# Phase 3A Read-Only ROS1 Signature Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the first Phase 3 gate for read-only ROS1 gateway service-signature evidence without calling gateway `dry_run`, gateway `dispatch`, or controlled motion.

**Architecture:** Phase 3A keeps the existing chain `center PDDL -> task-level BT -> platform gateway -> local ROS1`. The Mac lane owns repo documentation, evidence schemas, and receipt recording; the unit 4060 lane owns live read-only ROS1 observation after explicit user authorization. Phase 3A observes service names, service types, and service args only; it does not call ROS services.

**Tech Stack:** Existing Python `unittest`, `tools/audit_ros1_gateway_services.py`, `tools/check_task_planning_site_acceptance.py`, JSON/Markdown evidence receipts, ROS1 `rosservice list/type/args` on the unit 4060 lane only after explicit authorization.

---

## Scope Check

Phase 3A is read-only service-signature evidence.

Do not implement or run these in Phase 3A:

- gateway `dry_run`
- gateway `dispatch`
- controlled motion
- raw `/cmd_vel`, `/move_base`, `/mavros/*`, or `/setpoints_cmd`
- ROS topic publication
- ROS action calls
- platform-local mission planning
- Qt/operator UI
- LangGraph runtime
- non-convex alpha document work

## Current Entry Evidence

Phase 3A may start only after these Phase 2 receipts exist:

- `docs/superpowers/evidence/2026-06-03-ugv-phase-2a-4060-no-dispatch-receipt.md`
- `docs/superpowers/evidence/2026-06-03-ugv-phase-2b-4060-no-dispatch-receipt.md`

The Phase 2B 4060 receipt records `302` tests passed, `Phase2NoMotionAcceptanceReport.v1 ok=True`, `ArtifactReplayDiagnosticSummary.v1 ok=True`, and no ROS connection or dispatch.

## File Structure

- Create after 4060 Phase 3A output arrives:
  `docs/superpowers/evidence/2026-06-03-ugv-phase-3a-4060-read-only-ros1-signature-receipt.md`
  - Responsibility: record the user-pasted 4060 read-only ROS1 service-signature result.
- Create after 4060 Phase 3A output arrives:
  `docs/superpowers/evidence/2026-06-03-ugv-phase-3a-4060-read-only-ros1-signature-receipt.json`
  - Responsibility: machine-readable receipt with reported commands, service names, service types, service args, validation result, and explicit non-dispatch boundary.
- Modify after 4060 Phase 3A output arrives:
  `docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md`
  - Responsibility: append the Phase 3A receipt and update the next gate.
- Modify after 4060 Phase 3A output arrives:
  `docs/superpowers/specs/2026-06-02-distributed-fleet-phase-2-to-langgraph-roadmap.md`
  - Responsibility: mark Phase 3A read-only service-signature gate status and keep gateway `dry_run`/`dispatch` in later phases.

No runtime code changes are required for the first Phase 3A run because the repo already contains:

- `tools/audit_ros1_gateway_services.py`
- `tools/check_task_planning_site_acceptance.py`
- `profiles/work_hardware_ros1_gateway.env.template`
- `platform_gateway/ros/catkin_pkg/platform_gateway_msgs/srv/TaskCommandJson.srv`

## Task 1: Mac-Side Preflight Before Asking 4060 To Touch ROS

**Files:**
- Read: `docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md`
- Read: `docs/superpowers/specs/2026-05-19-platform-gateway-contract.md`
- Read: `profiles/work_hardware_ros1_gateway.env.template`
- Read: `tools/audit_ros1_gateway_services.py`
- Read: `tools/check_task_planning_site_acceptance.py`

- [ ] **Step 1: Confirm Phase 2 receipts exist**

Run:

```bash
test -f docs/superpowers/evidence/2026-06-03-ugv-phase-2a-4060-no-dispatch-receipt.md
test -f docs/superpowers/evidence/2026-06-03-ugv-phase-2b-4060-no-dispatch-receipt.md
```

Expected: both commands exit `0`.

- [ ] **Step 2: Confirm existing audit tools are importable**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  tools/audit_ros1_gateway_services.py \
  tools/check_task_planning_site_acceptance.py \
  task_planning/migration/ros1_service_audit.py \
  task_planning/migration/site_acceptance.py
```

Expected: command exits `0`.

- [ ] **Step 3: Confirm no Mac-side ROS command is required**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
  --profile profiles/work_hardware.env
```

Expected: JSON report uses `platform_backend="mock"` and does not include a ROS service audit.

## Task 2: 4060 Read-Only ROS1 Signature Capture After Explicit Authorization

**Files on 4060 WSL2:**
- Read: `/mnt/d/changxin/changxin-code/profiles/work_hardware_ros1_gateway.env.template`
- Create locally only, not in repo: `/tmp/changxin-rosservice-list.txt`
- Create locally only, not in repo: `/tmp/changxin-rosservice-types.txt`
- Create locally only, not in repo: `/tmp/changxin-rosservice-args.txt`
- Create locally only, not in repo: `/tmp/changxin-phase3a-read-only-ros1-signature.json`

- [ ] **Step 1: Confirm branch and clean worktree**

Run on 4060 WSL2:

```bash
cd /mnt/d/changxin/changxin-code
git fetch origin codex/phase2b-no-hardware-reporting
git checkout -B codex/phase2b-no-hardware-reporting origin/codex/phase2b-no-hardware-reporting
git log -2 --oneline
git status --short
```

Expected:

```text
a9951f8 docs: record ugv phase2b 4060 receipt
f506515 feat: add phase2b no-motion reporting
```

`git status --short` must be empty.

- [ ] **Step 2: Source local ROS1 environment**

Run only after the user explicitly authorizes Phase 3A read-only ROS1 service-signature work:

```bash
source /opt/ros/noetic/setup.bash
source ~/catkin_ws/devel/setup.bash
env | grep -E '^(ROS_MASTER_URI|ROS_IP|ROS_HOSTNAME)='
```

Expected: the unit operator confirms the environment points at the intended local ROS1 master for the UGV/gateway lane.

- [ ] **Step 3: Capture service list without calling services**

Run:

```bash
rosservice list | tee /tmp/changxin-rosservice-list.txt
```

Expected: the file exists and includes any available `/fleet/{platform_id}/gateway/dry_run` and `/fleet/{platform_id}/gateway/dispatch` service names if the gateway is running. This command lists services only; it does not call them.

- [ ] **Step 4: Capture service types and args without calling services**

Replace `<service>` with each gateway service name found in Step 3:

```bash
: > /tmp/changxin-rosservice-types.txt
: > /tmp/changxin-rosservice-args.txt
while read -r service; do
  case "$service" in
    /fleet/*/gateway/dry_run|/fleet/*/gateway/dispatch)
      {
        echo "### $service"
        rosservice type "$service"
      } >> /tmp/changxin-rosservice-types.txt
      {
        echo "### $service"
        rosservice args "$service"
      } >> /tmp/changxin-rosservice-args.txt
      ;;
  esac
done < /tmp/changxin-rosservice-list.txt
```

Expected: service type and args files are populated for discovered gateway services. These commands inspect signatures only; they do not call services.

- [ ] **Step 5: Run repo verifier against captured files**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
  --profile profiles/work_hardware.env \
  --platform-id ugv_0 \
  --rosservice-list-file /tmp/changxin-rosservice-list.txt \
  --service-type-file /tmp/changxin-rosservice-types.txt \
  --service-args-file /tmp/changxin-rosservice-args.txt \
  --require-rosservice-audit \
  --require-service-signatures \
  > /tmp/changxin-phase3a-read-only-ros1-signature.json
```

Expected:

- report schema is the existing site-acceptance schema
- `rosservice_audit` is present
- service names are tied to gateway-style services
- service signatures are captured
- no gateway `dry_run` service call occurs
- no gateway `dispatch` service call occurs
- no controlled motion occurs

If `PLATFORM_BACKEND=ros1_gateway` is required for this exact acceptance level,
copy `profiles/work_hardware_ros1_gateway.env.template` to a local, uncommitted
profile and fill real `ROS_MASTER_URI`/`ROS_IP`; do not commit that profile.

## Failure Branch A: ROS Master Unreachable

The 4060 Phase 3A attempt on 2026-06-04 did not pass because the ROS master was
not reachable:

```text
ROS_MASTER_URI=http://localhost:11311
source ~/catkin_ws/devel/setup.bash: missing
rosservice list RC=2
ERROR: Unable to communicate with master!
observed_service_count=0
```

Evidence:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-ros-master-unreachable-receipt.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-ros-master-unreachable-receipt.json`

Interpretation:

- This is not a service-signature mismatch yet.
- This is not a gateway contract failure yet.
- This does not prove gateway services exist or do not exist.
- This only proves the current 4060 WSL2 ROS environment could not communicate
  with its configured ROS master.

### 4060 Read-Only Reachability Diagnosis

Run these on the 4060 side before retrying service-signature capture. These
commands inspect files, environment, processes, and TCP listeners only; they do
not call gateway `dry_run`, gateway `dispatch`, or publish ROS topics.

```bash
cd /mnt/d/changxin/changxin-code
git fetch origin codex/phase2b-no-hardware-reporting
git checkout -B codex/phase2b-no-hardware-reporting origin/codex/phase2b-no-hardware-reporting
git log -2 --oneline
git status --short

source /opt/ros/noetic/setup.bash
echo "ROS_MASTER_URI=${ROS_MASTER_URI:-}"
echo "ROS_IP=${ROS_IP:-}"
echo "ROS_HOSTNAME=${ROS_HOSTNAME:-}"
command -v roscore || true
command -v rosmaster || true
command -v rosservice || true

ls -ld ~/catkin_ws ~/catkin_ws/devel ~/catkin_ws/devel/setup.bash 2>&1 || true
find ~ -maxdepth 4 -path '*/devel/setup.bash' -print 2>/dev/null | sort

python3 - <<'PY'
from urllib.parse import urlparse
import os
uri = os.environ.get("ROS_MASTER_URI", "")
parsed = urlparse(uri)
print(f"parsed_ros_master_scheme={parsed.scheme}")
print(f"parsed_ros_master_host={parsed.hostname}")
print(f"parsed_ros_master_port={parsed.port}")
PY

ss -ltnp 2>/dev/null | grep -E '(:11311|rosmaster|roscore)' || true
ps -ef | grep -E '[r]oscore|[r]osmaster|[r]oslaunch|platform_gateway|run_ros1_platform_gateway_node' || true

python3 - <<'PY'
import os
import socket
from urllib.parse import urlparse
uri = os.environ.get("ROS_MASTER_URI", "http://localhost:11311")
parsed = urlparse(uri)
host = parsed.hostname or "localhost"
port = parsed.port or 11311
sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect((host, port))
except OSError as exc:
    print(f"tcp_connect={host}:{port}:FAIL:{exc}")
else:
    print(f"tcp_connect={host}:{port}:OK")
finally:
    sock.close()
PY
```

Report back:

```text
git log -2 --oneline
git status --short
ROS_MASTER_URI / ROS_IP / ROS_HOSTNAME
whether ~/catkin_ws/devel/setup.bash exists
candidate setup.bash paths from find
whether port 11311 is listening
whether roscore/rosmaster/roslaunch processes exist
tcp_connect result
boundary confirmation:
  dry_run_called=false
  dispatch_called=false
  controlled_motion_authorized=false
  rostopic_publish=false
  repo_architecture_changed=false
  non_convex_alpha_docs_touched=false
```

Do not retry Phase 3A service-signature capture until the user confirms which
ROS master URI and catkin workspace are correct for the unit UGV gateway lane.

### Reachability Diagnosis Result

The 4060 read-only reachability diagnosis on 2026-06-04 confirmed:

```text
ROS_MASTER_URI=http://localhost:11311
ROS_IP=
ROS_HOSTNAME=
roscore=/opt/ros/noetic/bin/roscore
rosmaster=/opt/ros/noetic/bin/rosmaster
rosservice=/opt/ros/noetic/bin/rosservice
/home/uavdev/catkin_ws: missing
/home/uavdev/catkin_ws/devel: missing
/home/uavdev/catkin_ws/devel/setup.bash: missing
find ~ -maxdepth 4 -path '*/devel/setup.bash': no results
parsed_ros_master_host=localhost
parsed_ros_master_port=11311
ss :11311 / rosmaster / roscore listener: no output
tcp_connect=localhost:11311:FAIL:[Errno 111] Connection refused
proc_pattern_match_count=0
```

Evidence:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-ros-master-reachability-diagnosis.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-ros-master-reachability-diagnosis.json`

Interpretation:

- No ROS master is currently reachable at `http://localhost:11311`.
- No `roscore`, `rosmaster`, `roslaunch`, `platform_gateway`, or
  `run_ros1_platform_gateway_node` process was detected.
- No catkin workspace setup file was found under `/home/uavdev` at depth `4`.
- This is still not a gateway service-signature mismatch.
- Phase 3A remains open.

### 4060 Read-Only Workspace And Startup Inventory

Run these on the 4060 side before starting any ROS process or retrying
service-signature capture. These commands only inspect paths and text files;
they do not start `roscore`, run `rosservice list/type/args`, call gateway
`dry_run`, call gateway `dispatch`, or publish ROS topics.

```bash
cd /mnt/d/changxin/changxin-code
git fetch origin codex/phase2b-no-hardware-reporting
git checkout -B codex/phase2b-no-hardware-reporting origin/codex/phase2b-no-hardware-reporting
git log -2 --oneline
git status --short

echo "HOME=$HOME"
echo "USER=$USER"
pwd

find /mnt/d/changxin -maxdepth 5 \( \
  -path '*/devel/setup.bash' -o \
  -name 'setup.bash' -o \
  -name 'CMakeLists.txt' -o \
  -name 'package.xml' -o \
  -name '*.launch' -o \
  -name '*.service' -o \
  -name '*.sh' \
\) -print 2>/dev/null | sort | tee /tmp/changxin-phase3a-workspace-inventory.txt

find /home/uavdev -maxdepth 6 \( \
  -path '*/devel/setup.bash' -o \
  -name 'setup.bash' -o \
  -name 'CMakeLists.txt' -o \
  -name 'package.xml' -o \
  -name '*.launch' -o \
  -name '*.service' -o \
  -name '*.sh' \
\) -print 2>/dev/null | sort | tee -a /tmp/changxin-phase3a-workspace-inventory.txt

rg -n "ROS_MASTER_URI|ROS_IP|ROS_HOSTNAME|roscore|roslaunch|rosmaster|run_ros1_platform_gateway_node|platform_gateway|gateway/dry_run|gateway/dispatch" \
  /mnt/d/changxin /home/uavdev \
  --glob '!**/.git/**' \
  --glob '!**/__pycache__/**' \
  --glob '!**/*.pyc' \
  --glob '!**/*.tar.gz' \
  --glob '!**/*.zip' \
  --glob '!**/*.bag' \
  2>/dev/null | tee /tmp/changxin-phase3a-ros-startup-references.txt

wc -l /tmp/changxin-phase3a-workspace-inventory.txt /tmp/changxin-phase3a-ros-startup-references.txt
```

Report back:

```text
git log -2 --oneline
git status --short
workspace inventory path and first 80 lines
startup references path and first 120 matching lines
whether any devel/setup.bash exists
whether any launch/service/script references roscore or gateway node
boundary confirmation:
  ros_process_started=false
  service_signature_capture_retried=false
  rosservice_list_type_args_run=false
  gateway_dry_run_called=false
  gateway_dispatch_called=false
  controlled_motion_authorized=false
  rostopic_list_echo_pub_run=false
  repo_architecture_changed=false
  non_convex_alpha_docs_touched=false
```

After this inventory, a local operator must decide whether starting a ROS
master/gateway is in scope. Do not start it from this plan without explicit
operator authorization.

### Workspace And Startup Inventory Result

The 4060 read-only workspace/startup inventory on 2026-06-04 confirmed:

```text
HOME=/home/uavdev
USER=uavdev
pwd=/mnt/d/changxin/changxin-code
/tmp/changxin-phase3a-workspace-inventory.txt: 101 lines
/tmp/changxin-phase3a-ros-startup-references.txt: 5962 lines
No */devel/setup.bash found under /mnt/d/changxin or /home/uavdev scan roots.
No *.launch or *.service files found by the maxdepth inventory scan.
Repo scripts found:
  /mnt/d/changxin/changxin-code/tools/unit_receiving_wsl2.sh
  /mnt/d/changxin/changxin-code/ugv/01-scripts/probe_ugv_readonly.sh
  /mnt/d/changxin/changxin-code/ugv/01-scripts/probe_ugv_runtime_readonly.sh
  /mnt/d/changxin/changxin-code/uav/01-scripts/*.sh
Duplicate/home copies found:
  /home/uavdev/changxin-code-sync/...
  /home/uavdev/changxin-code/...
Dependency tree CMake files found under:
  /home/uavdev/uav-deps/...
Repo startup references include:
  profiles/work_hardware_ros1_gateway.env.template
  tools/run_ros1_platform_gateway_node.py
  platform_gateway/ros1_service_gateway.py
  platform_gateway/ros1_service_node.py
  platform_gateway/ros1_service_node_template.py
Historical evidence references include:
  /home/uavdev/uav-g3*-evidence/...
```

Evidence:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-workspace-startup-inventory.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-workspace-startup-inventory.json`

Interpretation:

- The repo contains gateway wrapper code and read-only probe scripts, but the
  4060 inventory did not find a ready local catkin workspace setup file,
  launch file, or service file under the scanned roots.
- Duplicate repo copies under `/home/uavdev` and dependency CMake trees under
  `/home/uavdev/uav-deps` are not proof of a live ROS master/gateway runtime.
- Historical `uav-g3*` evidence can guide investigation, but it must not be
  treated as the current runtime.
- Phase 3A remains open until a real ROS master and gateway services are made
  reachable under explicit local operator control.

### Operator Decision Gate

Stop before any command that starts ROS processes or prepares/builds a gateway
workspace. The next step needs one of these operator decisions:

1. Provide the actual unit ROS workspace path and startup command used for the
   UGV gateway lane.
2. Authorize preparing a ROS1 gateway catkin workspace from repo sources.
3. Authorize starting a local ROS master and gateway wrapper for read-only
   service-signature capture.

Without one of those decisions, do not retry service-signature capture.

### Local Operator Master Started Note

On 2026-06-04, the user reported that the UGV-side ROS master on port `11311`
has been started.

Evidence note:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-local-operator-master-started-note.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-local-operator-master-started-note.json`

This satisfies only the operator status update that a master has been started.
It does not prove Mac reachability, 4060 reachability, gateway wrapper
availability, gateway service names, gateway service signatures, or Phase 3A
acceptance.

The next 4060 action is a read-only reachability retry. Do not start gateway
services, do not call gateway `dry_run`, do not call gateway `dispatch`, and do
not authorize controlled motion.

Use this prompt for the 4060 Codex:

```text
We are continuing UGV Phase 3A. The local operator reports that the UGV-side
ROS master on port 11311 has been started.

Stay read-only. Do not call gateway dry_run. Do not call gateway dispatch. Do
not authorize controlled motion. Do not run rostopic publish. Do not edit repo
architecture. Do not touch non-convex alpha docs.

Work in /mnt/d/changxin/changxin-code on branch
codex/phase2b-no-hardware-reporting.

1. Sync and report:
   git fetch origin
   git checkout codex/phase2b-no-hardware-reporting
   git pull --ff-only origin codex/phase2b-no-hardware-reporting
   git log -2 --oneline
   git status --short

2. Source ROS Noetic only:
   source /opt/ros/noetic/setup.bash
   echo "ROS_MASTER_URI=${ROS_MASTER_URI:-}"
   echo "ROS_IP=${ROS_IP:-}"
   echo "ROS_HOSTNAME=${ROS_HOSTNAME:-}"
   command -v roscore || true
   command -v rosmaster || true
   command -v rosservice || true

3. Parse the active ROS master URI and run only a bounded TCP reachability
   check. If ROS_MASTER_URI is empty, wrong, or still points to localhost while
   the running master is on a vehicle/IPC IP, stop and ask the operator for the
   exact ROS_MASTER_URI. Do not guess.

   python3 - <<'PY'
import os, socket, urllib.parse
uri = os.environ.get("ROS_MASTER_URI", "")
print(f"active_ros_master_uri={uri}")
parsed = urllib.parse.urlparse(uri)
host = parsed.hostname
port = parsed.port or 11311
print(f"parsed_ros_master_host={host}")
print(f"parsed_ros_master_port={port}")
if not host:
    raise SystemExit("NO_ACTIVE_ROS_MASTER_URI")
sock = socket.socket()
sock.settimeout(3)
try:
    sock.connect((host, port))
except OSError as exc:
    print(f"tcp_connect={host}:{port}:FAIL:{exc}")
    raise SystemExit(20)
else:
    print(f"tcp_connect={host}:{port}:OK")
finally:
    sock.close()
PY

4. If the TCP check fails, stop. Report the failure and do not run
   rosservice list/type/args.

5. If the TCP check succeeds, capture read-only service evidence:
   set -o pipefail
   timeout 8s rosservice list | tee /tmp/changxin-rosservice-list.txt
   echo "rosservice_list_rc=${PIPESTATUS[0]}"
   grep -E '^/fleet/.*/gateway/(dry_run|dispatch)$' \
     /tmp/changxin-rosservice-list.txt | sort -u \
     > /tmp/changxin-gateway-services.txt || true
   cat /tmp/changxin-gateway-services.txt

6. If no gateway dry_run/dispatch services are found, stop and report the
   captured list path and service count. Do not call any service.

7. If gateway services are found, capture only type and args:
   : > /tmp/changxin-rosservice-types.txt
   : > /tmp/changxin-rosservice-args.txt
   while IFS= read -r s; do
     printf "%s " "$s" >> /tmp/changxin-rosservice-types.txt
     rosservice type "$s" >> /tmp/changxin-rosservice-types.txt
     printf "%s " "$s" >> /tmp/changxin-rosservice-args.txt
     rosservice args "$s" >> /tmp/changxin-rosservice-args.txt
   done < /tmp/changxin-gateway-services.txt

8. Run the existing file-based verifier only. Use the existing 4060 profile if
   present:
   PROFILE=/tmp/changxin-work-hardware-ros1-gateway.env
   if [ ! -f "$PROFILE" ]; then
     echo "missing_profile=$PROFILE"
     echo "Stop and report. Do not invent ROS addresses."
     exit 0
   fi
   PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
     --profile "$PROFILE" \
     --platform-id ugv_0 \
     --rosservice-list-file /tmp/changxin-rosservice-list.txt \
     --service-type-file /tmp/changxin-rosservice-types.txt \
     --service-args-file /tmp/changxin-rosservice-args.txt \
     --require-rosservice-audit \
     --require-service-signatures \
     > /tmp/changxin-phase3a-read-only-ros1-signature-retry.json

9. Report:
   - git log -2
   - git status --short
   - ROS env summary
   - parsed host/port and TCP result
   - rosservice list rc and captured file path if run
   - gateway services found
   - verifier JSON path and key fields if run
   - boundary confirmation:
     dry_run_called=false
     dispatch_called=false
     controlled_motion_authorized=false
     rostopic_publish=false
     repo_architecture_changed=false
     non_convex_alpha_docs_touched=false
```

## Task 3: Mac-Side Receipt Recording After 4060 Sends Output

**Files:**
- Create: `docs/superpowers/evidence/2026-06-03-ugv-phase-3a-4060-read-only-ros1-signature-receipt.md`
- Create: `docs/superpowers/evidence/2026-06-03-ugv-phase-3a-4060-read-only-ros1-signature-receipt.json`
- Modify: `docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md`
- Modify: `docs/superpowers/specs/2026-06-02-distributed-fleet-phase-2-to-langgraph-roadmap.md`

- [ ] **Step 1: Record user-pasted 4060 output**

The MD receipt must include:

```text
source=user_pasted_4060_codex_reply
evidence_classification=reported_by_unit_4060_codex_not_reverified_by_mac
commands=rosservice list/type/args only
dry_run_called=false
dispatch_called=false
controlled_motion_authorized=false
```

- [ ] **Step 2: Record machine-readable receipt**

The JSON receipt must include:

```json
{
  "schema": "UgvPhase3AReadOnlyRos1SignatureReceipt.v1",
  "source": "user_pasted_4060_codex_reply",
  "evidence_classification": "reported_by_unit_4060_codex_not_reverified_by_mac",
  "boundary_confirmed_by_4060": {
    "rosservice_list_run": true,
    "rosservice_type_run": true,
    "rosservice_args_run": true,
    "gateway_dry_run_called": false,
    "gateway_dispatch_called": false,
    "controlled_motion_authorized": false
  }
}
```

- [ ] **Step 3: Verify JSON formatting**

Run:

```bash
python3 -m json.tool docs/superpowers/evidence/2026-06-03-ugv-phase-3a-4060-read-only-ros1-signature-receipt.json >/tmp/phase3a-receipt.pretty.json
```

Expected: command exits `0`.

- [ ] **Step 4: Commit the receipt only**

Run:

```bash
git status --short
git add \
  docs/superpowers/evidence/2026-06-03-ugv-phase-3a-4060-read-only-ros1-signature-receipt.md \
  docs/superpowers/evidence/2026-06-03-ugv-phase-3a-4060-read-only-ros1-signature-receipt.json \
  docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md \
  docs/superpowers/specs/2026-06-02-distributed-fleet-phase-2-to-langgraph-roadmap.md
git commit -m "docs: record ugv phase3a read-only ros1 receipt"
git push
```

Expected: no non-convex alpha documents, local ROS profiles, generated `/tmp`
files, or binary files are staged.

## Exit Gate

Phase 3A is accepted only when the Mac repo records a 4060 receipt proving:

- Phase 2B branch still matches the expected head or a documented successor
- 4060 ran read-only ROS1 service list/type/args capture
- service signature validation report exists
- gateway `dry_run` was not called
- gateway `dispatch` was not called
- controlled motion was not authorized
- non-convex alpha documents were not touched

The next phase after Phase 3A is gateway lifecycle/dry-run planning. It still
requires explicit user authorization and must not dispatch or authorize motion.
