# UGV Phase 2A Mac To 4060 Handoff

Date: 2026-06-03

## Scope

This handoff is for the UGV task-planning lane only.

It is not part of the non-convex alpha UAV document lane. Do not edit or stage
the unrelated binary non-convex alpha files under `docs/` while doing this UGV
handoff.

The Mac side owns repo implementation, docs, unit tests, mock gateway runs, and
no-hardware artifacts. The unit RTX 4060 side owns transferred-package
verification, final archive verification, and any future unit ROS or hardware
checks.

The Mac side must not claim that it verified `D:\changxin` or live unit ROS.
The 4060 side must not rewrite repo architecture or dispatch unless the user
explicitly authorizes that specific action.

## Architecture Boundary

Preserve the current chain:

```text
operator intent
-> ModelClient / MockLLMClient
-> TaskSchema / MissionRequest validator
-> mission blackboard
-> PDDL problem and plan
-> plan validator
-> PDDL-to-BT runtime
-> platform gateway
-> local ROS1 gateway on each platform
```

Hard rules:

- ROS1 remains the runtime stack.
- The ground station remains the only global planner.
- PDDL remains the mission-level planning authority.
- Platform gateways receive capability-level `TaskCommand.v1` only.
- No edge LLM runs on the UGV.
- No raw `/cmd_vel`, `/move_base`, `/mavros/*`, or `/setpoints_cmd` path is
  allowed from the center.
- The current UGV proof semantics are `ugv_0 confirm_target(target_01)`,
  `manual_confirm`, no motion.

## Mac Output

The Mac-side Phase 2A implementation baseline is:

```text
branch: codex/phase2a-no-hardware-ops
commit: 9a062b2 feat: add distributed fleet task planning ops stack
```

Mac can produce a transfer directory containing:

```text
ugv-phase2a-mac-to-4060-handoff.tar.gz
ugv-phase2a-mac-to-4060-handoff.tar.gz.sha256
ugv-phase2a-4060-prompt.md
```

The handoff archive contains a migration bundle plus local no-hardware baseline
evidence. It does not contain or prove the unit final archive.

## 4060 Codex Prompt

Copy this prompt to the unit RTX 4060 Codex session:

```text
You are running on the unit RTX 4060 Windows/WSL2 machine, not on the Mac.

Task: receive and verify the UGV Phase 2A handoff from Mac. This is UGV
task-planning work only. It is unrelated to the non-convex alpha UAV document
lane.

Machine role:
- Windows durable root: D:\changxin
- WSL evidence root: /tmp/changxin-distributed-fleet-evidence
- Verify transferred packages and the final archive locally.
- Do not rewrite repo architecture.
- Do not edit or stage non-convex alpha UAV docs.
- Do not dispatch.
- Do not connect to real ROS unless the user explicitly asks for ROS read-only
  checks in this session.
- Do not treat Mac/source-machine verification as unit-side proof.

Expected Phase 1 final archive:
D:\changxin\final-archives\changxin-distributed-fleet-final-proof-20260602.tar.gz

Expected SHA256:
66465e2a1377e9f2dd11dc4136db9b92fa5d6e369f9f1c06c4a8a4c0ca850366

First, verify the final archive hash in Windows PowerShell:

Get-FileHash -Algorithm SHA256 D:\changxin\final-archives\changxin-distributed-fleet-final-proof-20260602.tar.gz

Then verify the Mac handoff package. Assume the user placed these files under:
D:\changxin\incoming\ugv-phase2a\

Use Windows PowerShell for hash intake only:

Get-FileHash -Algorithm SHA256 D:\changxin\incoming\ugv-phase2a\ugv-phase2a-mac-to-4060-handoff.tar.gz
Get-Content D:\changxin\incoming\ugv-phase2a\ugv-phase2a-mac-to-4060-handoff.tar.gz.sha256

Use WSL2 for repository Python checks:

mkdir -p /tmp/changxin-ugv-phase2a-transfer
mkdir -p /tmp/changxin-distributed-fleet-evidence/reports
tar -xzf /mnt/d/changxin/incoming/ugv-phase2a/ugv-phase2a-mac-to-4060-handoff.tar.gz -C /tmp/changxin-ugv-phase2a-transfer
cd /tmp/changxin-ugv-phase2a-transfer/ugv-phase2a-mac-to-4060-handoff/migration/task-planning-migration-bundle

PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_distributed_fleet_handoff_package.py \
  /mnt/d/changxin/incoming/ugv-phase2a/ugv-phase2a-mac-to-4060-handoff.tar.gz \
  --work-dir /tmp/changxin-ugv-phase2a-handoff-verify \
  --verification-context receiving_machine \
  > /tmp/changxin-distributed-fleet-evidence/reports/ugv_phase2a_handoff_package_verification.json

PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_migration_bundle.py \
  /tmp/changxin-ugv-phase2a-transfer/ugv-phase2a-mac-to-4060-handoff/migration/task-planning-migration-bundle.tar.gz \
  --work-dir /tmp/changxin-ugv-phase2a-migration-verify \
  --verification-context receiving_machine \
  > /tmp/changxin-distributed-fleet-evidence/reports/ugv_phase2a_migration_verification.json

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests/task_planning

PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_readiness.py \
  --profile profiles/work_hardware.env \
  > /tmp/changxin-distributed-fleet-evidence/reports/ugv_phase2a_work_hardware_readiness.json

PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
  --profile profiles/work_hardware.env \
  > /tmp/changxin-distributed-fleet-evidence/reports/ugv_phase2a_work_hardware_site_acceptance_no_dispatch.json

PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py \
  --evidence-dir /tmp/changxin-distributed-fleet-evidence \
  --missing-only \
  --print-discovered-inputs \
  > /tmp/changxin-distributed-fleet-evidence/reports/ugv_phase2a_goal_evidence_missing_only.json

Report back:
- final archive SHA256 result
- handoff package SHA256 result
- whether handoff verification ok=true
- whether migration verification ok=true
- unit test result
- readiness/site-acceptance report paths
- any remaining missing-only goal evidence

Stop there unless the user explicitly authorizes the next ROS read-only stage.
```

## Optional Windows Receiving Wrapper

If the updated repo checkout already exists on the 4060 at
`D:\changxin\changxin-code`, the 4060 Codex may use the Windows-safe receiving
wrapper instead of the manual WSL extraction path:

```powershell
cd D:\changxin\changxin-code
Set-ExecutionPolicy -Scope Process Bypass -Force
.\tools\windows_unit_receiving_entry.ps1 `
  -HandoffPackage D:\changxin\incoming\ugv-phase2a\ugv-phase2a-mac-to-4060-handoff.tar.gz `
  -HandoffSha256 <sha256-from-.sha256-file> `
  -EvidenceRoot D:\changxin\evidence `
  -WslEvidenceDir /tmp/changxin-distributed-fleet-evidence
```

PowerShell remains an intake wrapper only. WSL2 performs repository Python
verification.

## Stop Conditions

Stop and report instead of improvising if:

- the final archive hash does not match the expected SHA256;
- the handoff package hash does not match the `.sha256` file;
- `verification_context=receiving_machine` rejects the package;
- Python tests fail;
- readiness or site acceptance reports show unexpected dispatch, ROS publish,
  or raw movement command paths;
- the task drifts into non-convex alpha UAV documents.
