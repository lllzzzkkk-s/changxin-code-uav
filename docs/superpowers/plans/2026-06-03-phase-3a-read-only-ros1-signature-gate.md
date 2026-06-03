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
f506515 feat: add phase2b no-motion reporting
5652c93 docs: record ugv phase2a 4060 receipt
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
