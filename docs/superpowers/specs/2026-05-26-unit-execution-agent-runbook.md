# Unit Execution Agent Runbook

Date: 2026-05-26

## Purpose

This runbook is the short entry point for an agent working on the unit/workplace execution machine.

The unit/workplace machine is the only lane that can touch the physical UAV/UGV execution platform. The home RTX 5090 server is a model-capability lab only. Its outputs may be transferred as verified artifacts, but the unit/workplace lane must remain runnable when the home server is offline.

Keep this control chain:

```text
center PDDL -> task-level BT/state machine -> platform gateway -> local ROS1
```

## Hard Boundaries

- Use ROS1.
- Keep one ROS master per platform.
- Keep platform execution behind `PLATFORM_BACKEND=mock` until read-only ROS1 gateway evidence passes.
- Do not call a local or home LLM as part of unit hardware execution.
- Do not publish raw ROS topics or call low-level `/mavros/*`, `/cmd_vel`, `/setpoints_cmd`, or equivalent controls from the center.
- Do not edit and commit machine-specific `ROS_MASTER_URI`, `ROS_IP`, IP addresses, credentials, or tokens.
- Do not dispatch to hardware unless the operator has explicitly approved that run and `HARDWARE_APPROVAL_REQUIRED=true` is still present.

## Inputs From Other Machines

Allowed incoming files:

- A distributed fleet handoff package created by `tools/package_distributed_fleet_handoff.py`.
- A migration bundle created by `tools/package_task_planning_migration.py`.
- A model-lab or replay artifact package created by `tools/package_task_planning_artifacts.py`.
- A standard evidence directory created by `tools/collect_distributed_fleet_evidence.py`.

Reject live dependencies on the home 5090 server. Treat home model output as a file artifact that must pass checksum and schema verification before use.

Reject `MODEL_LAB_EVIDENCE_KIND=mock_endpoint` as proof that the home 5090 model was evaluated. Mock endpoint artifacts are useful for HTTP plumbing tests only. A real model-lab report must also show `mission_profile=home_model_lab`, `model_provider=local_http`, `platform_backend=mock`, `baseline_equivalent`, `diffs`, and empty `validation_errors`.

## First Commands

Run these from the repository root on the unit/workplace machine.

If the active agent is on the unit RTX 4060 Windows host, start with the Windows-safe receiving entry and let it hand off verification to WSL2. Native PowerShell only receives files, checks SHA256, validates paths, and starts WSL2:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\tools\windows_unit_receiving_entry.ps1 `
  -HandoffPackage C:\incoming\distributed-fleet-handoff-package.tar.gz `
  -HandoffSha256 <64-char-sha256> `
  -ArtifactPackage C:\incoming\task-planning-artifacts.tar.gz `
  -ArtifactSha256 <64-char-sha256>
```

Expected output is documented in `docs/superpowers/specs/2026-05-29-windows-safe-unit-receiving-kit.md`. The script writes Windows logs to `C:\changxin-evidence\logs` and WSL2 evidence to `/tmp/changxin-distributed-fleet-evidence`. Omit `-ArtifactPackage` and `-ArtifactSha256` when no artifact package has arrived; the artifact proof then remains explicitly missing.

If you received one handoff package, unpack it first and use its bundled migration checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 /path/to/changxin-code/tools/verify_distributed_fleet_handoff_package.py \
  distributed-fleet-handoff-package.tar.gz \
  --work-dir /tmp/changxin-handoff-verify \
  --verification-context receiving_machine > /tmp/changxin-handoff-package-verification.json
tar -xzf distributed-fleet-handoff-package.tar.gz
cd distributed-fleet-handoff-package/migration/task-planning-migration-bundle
```

Verify a transferred migration bundle before using it:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_migration_bundle.py \
  /path/to/task-planning-migration-bundle.tar.gz \
  --work-dir /tmp/changxin-migration-verify \
  --verification-context unit_workplace_receiving
```

Create or refresh a local evidence folder:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/collect_distributed_fleet_evidence.py \
  --output-dir /tmp/changxin-distributed-fleet-evidence
PYTHONDONTWRITEBYTECODE=1 python3 tools/init_external_evidence_handoff.py \
  --evidence-dir /tmp/changxin-distributed-fleet-evidence
```

Check the unit lane without sending ROS control commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_readiness.py \
  --profile profiles/work_hardware.env
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
  --profile profiles/work_hardware.env
PYTHONDONTWRITEBYTECODE=1 python3 tools/plan_work_hardware_gate.py \
  --profile profiles/work_hardware.env \
  --through-stage mock_gateway_dispatch
```

Run the mock-gated hardware lane without a model call:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py \
  --profile profiles/work_hardware.env \
  --case uav_ugv_coordination
```

## Artifact Intake

Verify a transferred model-lab or replay artifact package before replaying anything:

This must run on the unit/workplace receiving machine. The verification report records hashed source and verifier machine ids and is rejected if those ids match; use `source_machine` only for a local package sanity check before transfer.
For model-lab artifacts, package verification also requires a successful report to include `model_task_schema.json`, and the artifact must keep model-lab profile fields consistent with the evaluation report while using `PLATFORM_BACKEND=mock`. Verification output records each artifact `case_id`; imported packages are rejected unless those case ids match the OK lane matrix.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py \
  /path/to/task-planning-artifacts.tar.gz \
  --work-dir /tmp/changxin-artifact-verify \
  --verification-context unit_workplace_receiving \
  > /tmp/changxin-artifact-package-verification.json
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
  --profile profiles/work_hardware.env \
  --artifact-package /path/to/task-planning-artifacts.tar.gz \
  --artifact-work-dir /tmp/changxin-artifact-verify \
  --require-artifact-package \
  --case uav_ugv_coordination
```

Replay a prevalidated schema only on the mock/approval lane:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_prevalidated_task_schema.py \
  --profile profiles/work_hardware.env \
  --task-schema /tmp/changxin-artifact-verify/artifacts/<artifact_name>/model_task_schema.json \
  --case uav_ugv_coordination \
  --artifact-root /tmp/changxin-prevalidated-runs
```

Extract one validated capability-level command from the resulting artifact before any real ROS1 dry-run call:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/extract_task_command_from_artifact.py \
  /tmp/changxin-prevalidated-runs/<run_id> \
  --platform-id uav_0 \
  --format rosservice-yaml > /tmp/changxin-task-command.yaml
```

## ROS1 Gateway Preparation

Prepare the gateway message package with a dry run first:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py \
  --catkin-src ~/catkin_ws/src
```

Apply only to the intended unit/workplace catkin workspace:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py \
  --catkin-src ~/catkin_ws/src \
  --apply
```

Then rebuild and source the ROS1 workspace using the unit's normal ROS procedure.

Create a local, uncommitted ROS1 profile from the template:

```bash
cp profiles/work_hardware_ros1_gateway.env.template /tmp/work_hardware_ros1_gateway.env
```

Fill real `ROS_MASTER_URI`, `ROS_IP`, and service template values only in that local file.

## Unit UGV Executor Wiring

If `/fleet/ugv_0/gateway/*` services are absent after the message workspace builds, do not start the default gateway node as final hardware proof. The default executor only proves service shape and rejects dispatch. A real UGV proof needs a local executor plus an operator-confirmed target map.

Create the target map on the real UGV IPC or the machine that owns the UGV local ROS1 master. This file is local site configuration, not center planner code. Start from a template, edit it with the site-specific object aliases and target pose, then set `operator_confirmed_mapping=true` only after the local operator has confirmed the mapping:

```bash
mkdir -p /home/yhs/changxin_gateway_runtime
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_unit_ugv_target_map.py \
  --write-template /home/yhs/changxin_gateway_runtime/unit_ugv_targets.json \
  --platform-id ugv_0 \
  --target-id target_01 \
  --object-query 充电桩 \
  --object-query charging_station

# Edit /home/yhs/changxin_gateway_runtime/unit_ugv_targets.json locally.
# For no-motion proof, keep action=manual_confirm.
# For bounded motion, use action=move_base_goal and fill frame_id/x/y/yaw/max_distance_m from the real local map.
# Set operator_confirmed_mapping=true only after local operator confirmation.

PYTHONDONTWRITEBYTECODE=1 python3 tools/check_unit_ugv_target_map.py \
  --target-map /home/yhs/changxin_gateway_runtime/unit_ugv_targets.json \
  --platform-id ugv_0 \
  --require-object-queries \
  --select-object-query 充电桩 \
  --max-move-base-distance-m 1.0 \
  > /tmp/changxin-unit-ugv-target-map-check.json
```

Expected output: the checker exits `0` and writes `UnitUgvTargetMapCheckReport.v1` with `ok=true`, one selected target for the requested object query, no duplicate object aliases, and no unconfirmed target mappings. Fail condition: invalid JSON/schema, wrong `platform_id`, missing object aliases, duplicate aliases across targets, `operator_confirmed_mapping=false`, or a `move_base_goal` target without explicit pose and distance bounds.

Before any ROS1 gateway dry-run, bind one validated artifact command to the local target map without connecting ROS:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_unit_ugv_artifact_target_map.py \
  /tmp/changxin-prevalidated-runs/<run_id> \
  --target-map /home/yhs/changxin_gateway_runtime/unit_ugv_targets.json \
  --platform-id ugv_0 \
  --index 0 \
  --max-move-base-distance-m 1.0 \
  > /tmp/changxin-unit-ugv-artifact-target-map-preflight.json
```

Expected output: `UnitUgvArtifactTargetMapPreflight.v1` with `ok=true`, the selected `TaskCommand.v1` mission/task/platform fields, a matching `selected_target_id`, and `ros_connected=false`, `dispatch_performed=false`. Fail condition: the artifact cannot be replayed, the selected UGV command is missing, `object_query` is not mapped, `target_id` disagrees with the object-query-selected target, the target map is unconfirmed, or a `move_base_goal` exceeds the site distance bound.

For a no-motion capability check, start the gateway without operator approval first:

```bash
cd /home/yhs/changxin_gateway_runtime
source /opt/ros/noetic/setup.bash
source /home/yhs/changxin_gateway_ws/devel/setup.bash
export ROS_MASTER_URI=http://192.168.0.201:11311  # replace with the real local UGV ROS master if different
export ROS_IP="$(hostname -I | awk '{print $1}')"

PYTHONDONTWRITEBYTECODE=1 python3 tools/run_ros1_platform_gateway_node.py \
  --platform-id ugv_0 \
  --platform-type ugv \
  --capability confirm_target \
  --service-symbol platform_gateway_msgs.srv:TaskCommandJson \
  --unit-ugv-target-map /home/yhs/changxin_gateway_runtime/unit_ugv_targets.json \
  --unit-ugv-progress-output /tmp/changxin-task-progress.json
```

Expected output: the node stays running and `rosservice list` shows `/fleet/ugv_0/gateway/dry_run` and `/fleet/ugv_0/gateway/dispatch`. Pass condition: `/gateway/dry_run` accepts the extracted `TaskCommand.v1` and `/gateway/dispatch` rejects with `operator approval required for unit UGV dispatch`. Fail condition: service registration fails, service type is not `platform_gateway_msgs/TaskCommandJson`, dry-run rejects the mapped `target_01`, or dispatch accepts before operator approval.

Only if the site decides `confirm_target(target_01)` is a bounded navigation action, replace `action=manual_confirm` with `action=move_base_goal` and add explicit pose fields:

```json
{
  "capability": "confirm_target",
  "action": "move_base_goal",
  "operator_confirmed_mapping": true,
  "frame_id": "map",
  "x": 0.0,
  "y": 0.0,
  "yaw": 0.0,
  "max_distance_m": 1.0,
  "description": "operator-confirmed bounded local move_base goal"
}
```

Expected output: JSON validation still exits `0`. Pass condition: the site operator confirms the pose, frame, and safety radius from the real UGV map. Fail condition: the target is guessed from chat, evidence history, or an unverified map.

For a real `move_base_goal` dispatch, the node must be started with both `--unit-ugv-operator-approved` and `--unit-ugv-enable-move-base` after local operator approval:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_ros1_platform_gateway_node.py \
  --platform-id ugv_0 \
  --platform-type ugv \
  --capability confirm_target \
  --service-symbol platform_gateway_msgs.srv:TaskCommandJson \
  --unit-ugv-target-map /home/yhs/changxin_gateway_runtime/unit_ugv_targets.json \
  --unit-ugv-operator-approved \
  --unit-ugv-enable-move-base \
  --unit-ugv-move-base-action /move_base \
  --unit-ugv-progress-output /tmp/changxin-task-progress.json
```

Expected output: the node stays running. Pass condition: after a separately approved `/fleet/ugv_0/gateway/dispatch`, `/tmp/changxin-task-progress.json` contains `TaskProgressSet.v1` for the same `mission_id/task_id/platform_id`. Fail condition: no operator approval, `move_base` server unavailable, target map invalid, dispatch response not accepted, or no matching TaskProgress file.

## Read-Only ROS1 Signature Audit

After sourcing the intended ROS1 workspace, collect service evidence without dispatch. The tool applies `ROS_MASTER_URI` and `ROS_IP` from the selected local profile when it runs `rosservice`, so the JSON report is tied to the profile being accepted rather than to whatever ROS address happens to be in the shell:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
  --profile /tmp/work_hardware_ros1_gateway.env \
  --platform-id uav_0 \
  --platform-id ugv_0 \
  --run-rosservice-list \
  --run-service-signatures \
  --require-rosservice-audit \
  --require-service-signatures > /tmp/changxin-site-acceptance-work-hardware-ros1.json
```

In the resulting report, `machine_id` should be populated. In the nested `rosservice_audit`, `command_environment_source` should be `profile` for direct collection. A file-based replay will show `captured_files`, and a test-injected runner will show `caller_supplied`.

If the operator wants raw command logs as well, capture them separately. These raw shell commands use the current shell environment, so they are supplemental logs; the site acceptance JSON above is the canonical signature proof:

```bash
rosservice list | tee /tmp/changxin-rosservice-list.txt
for s in /fleet/uav_0/gateway/dry_run /fleet/uav_0/gateway/dispatch /fleet/ugv_0/gateway/dry_run /fleet/ugv_0/gateway/dispatch; do printf "%s " "$s"; rosservice type "$s"; done | tee /tmp/changxin-rosservice-types.txt
for s in /fleet/uav_0/gateway/dry_run /fleet/uav_0/gateway/dispatch /fleet/ugv_0/gateway/dry_run /fleet/ugv_0/gateway/dispatch; do printf "%s " "$s"; rosservice args "$s"; done | tee /tmp/changxin-rosservice-args.txt
```

Only after the signature report passes and the local operator approves a no-motion bench check, use the extracted command file for the dry-run service:

```bash
rosservice call /fleet/uav_0/gateway/dry_run "$(cat /tmp/changxin-task-command.yaml)"
```

After all prior gates pass and the local operator explicitly approves one constrained real dispatch, capture the dispatch response and progress evidence. This command is intentionally separate from artifact recording:

```bash
rosservice call /fleet/uav_0/gateway/dispatch "$(cat /tmp/changxin-task-command.yaml)" | tee /tmp/changxin-dispatch-response.txt
```

Record the final hardware proof artifact from captured evidence; this tool does not send ROS commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/record_unit_hardware_dispatch_artifact.py \
  --source-artifact /tmp/changxin-prevalidated-runs/<run_id> \
  --profile /tmp/work_hardware_ros1_gateway.env \
  --output-dir /tmp/changxin-distributed-fleet-evidence/hardware_artifacts \
  --platform-id uav_0 \
  --task-id <task_id> \
  --dispatch-service /fleet/uav_0/gateway/dispatch \
  --dispatch-stdout-file /tmp/changxin-dispatch-response.txt \
  --task-progress-file /tmp/changxin-task-progress.json \
  --operator-approved
```

## Evidence To Return

Return these files to the main evidence directory or the coordinating agent:

- `reports/site_acceptance_work_hardware_ros1.json`
- `/tmp/changxin-site-acceptance-work-hardware-ros1.json`
- `/tmp/changxin-rosservice-list.txt`
- `/tmp/changxin-rosservice-types.txt`
- `/tmp/changxin-rosservice-args.txt`
- any hardware run artifact root created under the local `MISSION_ARTIFACT_ROOT` or by `tools/record_unit_hardware_dispatch_artifact.py`

A hardware run artifact only counts as real unit/work execution proof when it contains all of:

- `environment_profile.json` with `MISSION_PROFILE=work_hardware`, `PLATFORM_BACKEND=ros1_gateway`, `HARDWARE_APPROVAL_REQUIRED=true`, `operator_approved=true`, `operator_approval_source=local_unit_operator`, `machine_id`, and `execution_context=unit_workplace_hardware`
- `validation_report.json` with `status=passed`
- `gateway_trace.json` with a successful `/gateway/dispatch` `rosservice` call, `returncode=0`, and `publish_attempted=false`
- `command_acks.json` with at least one accepted `CommandAck`
- `task_progress.json` with at least one `TaskProgress`
- the successful `/gateway/dispatch` trace, accepted `CommandAck`, and `TaskProgress` must all match the same `mission_id` / `task_id` / `platform_id`

Read-only service signature reports and `/gateway/dry_run` calls are required gates, but they do not satisfy final live hardware execution proof.

Import returned evidence into the standard evidence folder:

The import command rejects a home 5090 `model_lab_evaluation.json`, transferred artifact package, or final hardware dispatch artifact unless the standard evidence folder already contains an OK `reports/lane_matrix.json` with the same `case_id`. Run the local baseline collection first so imported model, package, and hardware proof stay tied to the same mission case.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/import_distributed_fleet_external_evidence.py \
  --evidence-dir /tmp/changxin-distributed-fleet-evidence \
  --handoff-package-verification-report /tmp/changxin-handoff-package-verification.json \
  --artifact-package-verification-report /tmp/changxin-artifact-package-verification.json \
  --site-acceptance-ros1-report /tmp/changxin-site-acceptance-work-hardware-ros1.json \
  --artifact-package /path/to/task-planning-artifacts.tar.gz \
  --hardware-run-artifact /tmp/changxin-distributed-fleet-evidence/hardware_artifacts/<run_id>
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py \
  --evidence-dir /tmp/changxin-distributed-fleet-evidence
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py \
  --evidence-dir /tmp/changxin-distributed-fleet-evidence \
  --missing-only \
  --print-discovered-inputs
```

The goal evidence report should keep live hardware execution marked `missing` until a real unit/workplace `work_hardware` + `ros1_gateway` dispatch artifact with `execution_context=unit_workplace_hardware`, a `case_id` matching the OK lane matrix, passed validation, successful gateway trace, matching command acknowledgement, and matching task progress is imported.
