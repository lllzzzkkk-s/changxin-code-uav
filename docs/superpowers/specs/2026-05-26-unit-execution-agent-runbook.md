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

For a site-specific single-UGV object approach rehearsal, run the operator intent through the same MissionManager/PDDL/BT chain with a non-ROS profile first:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_intent.py \
  --profile profiles/dev_mock.env \
  --intent "让小车识别附近的充电桩，然后走过去" \
  --mission-id unit_single_ugv_object_approach_001 \
  --primary-platform ugv_0 \
  --case-id unit_single_ugv_object_approach \
  --artifact-root /tmp/changxin-single-ugv-intent-runs \
  > /tmp/changxin-single-ugv-intent-run.json
```

Expected output: `MissionIntentRun.v1` with `ok=true`, `ros_connected=false`, `hardware_dispatch_performed=false`, and an `artifact_bundle_path`. Fail condition: the selected profile is `PLATFORM_BACKEND=ros1_gateway`, the intent is empty, or artifact generation fails. This command is only an artifact-generation step; it does not connect ROS and does not dispatch.

If an external Mission Ops shell such as OpenClaw, Hermes, or another agent framework is used, keep it outside the execution core. Let it write a `TaskSchema.v1` draft JSON, then pass that file through the same validator/PDDL/BT/gateway artifact path:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_intent.py \
  --profile profiles/dev_mock.env \
  --intent "让小车识别附近的灭火器，然后靠近" \
  --mission-id unit_single_ugv_agent_object_approach_001 \
  --primary-platform ugv_0 \
  --case-id unit_single_ugv_agent_object_approach \
  --agent-name openclaw \
  --agent-draft-file /tmp/changxin-agent-task-schema-draft.json \
  --artifact-root /tmp/changxin-agent-intent-runs \
  > /tmp/changxin-agent-intent-run.json
```

Expected output includes `semantic_compiler.kind=agent_adapter`. The adapter rejects raw ROS references such as `/cmd_vel`, `/mavros/*`, `/setpoints_cmd`, and `/move_base_simple/goal`; it only accepts a validated `TaskSchema.v1` draft and still does not connect ROS or dispatch.

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

The current single-UGV object approach path does not yet run YOLO or another perception backend. The natural-language "识别附近的显示器" intent is compiled into an `object_query`, then bound to a local `UnitUgvTargetMap.v1`. That target map is operator-confirmed site evidence for now; YOLO should be added later as another perception backend without bypassing the same validator/PDDL/BT/gateway chain.

Set the target-map path for the side that prepares or reviews the UGV target
binding. The 4060 may prepare and validate this file as the HMI/ground-station
side, but the controlled-motion gateway wrapper must run on the single UGV IPC
or another vehicle-local ROS1 environment that can import `move_base_msgs` and
reach the local `/move_base` action server:

```bash
export CHANGXIN_GATEWAY_RUNTIME="${CHANGXIN_GATEWAY_RUNTIME:-$HOME/changxin_gateway_runtime}"
export UNIT_UGV_TARGET_MAP="${UNIT_UGV_TARGET_MAP:-$CHANGXIN_GATEWAY_RUNTIME/unit_ugv_targets.json}"
export CHANGXIN_GATEWAY_WS="${CHANGXIN_GATEWAY_WS:-$HOME/catkin_ws}"
```

The vehicle does not need Codex. If the 4060 can SSH to the vehicle as
`yhs@192.168.0.201`, use the SSH lifecycle wrapper from the 4060 to operate the
vehicle-side gateway process. This keeps the process on the UGV IPC while letting
the 4060 handle orchestration and evidence collection:

```bash
# 4060/HMI side: verify SSH connectivity.
bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 \
  auth-check

# If the vehicle already has a Git checkout, fast-forward it.
bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 \
  --remote-repo /home/yhs/changxin-code \
  pull

# If Git/network is not reliable on the vehicle, copy only the gateway-relevant
# repo subset from the 4060 checkout.
bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 \
  --remote-repo /home/yhs/changxin-code \
  sync-lite

# Copy the current HMI/operator target map to the vehicle-side runtime path.
bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 \
  --local-target-map /home/uavdev/changxin_gateway_runtime/unit_ugv_targets.json \
  --remote-target-map /home/yhs/changxin_gateway_runtime/unit_ugv_targets.json \
  sync-target-map
```

Expected output: SSH commands complete without starting the gateway unless the
selected action is `start` or `start-motion`. Pass condition: the vehicle has the
latest wrapper scripts and the target map exists at the vehicle-side path. Fail
condition: SSH is unavailable, the vehicle repo cannot be updated or synced, or
the target map is not copied to the path the vehicle wrapper will read.

The SSH lifecycle wrapper defaults to non-interactive mode with `BatchMode=yes`
and short connection timeouts so Codex does not hang at a password prompt. If
`auth-check` returns `Permission denied (publickey,password)`, stop the vehicle
gateway flow and fix credentials first. If the site temporarily uses password
authentication, pass the password through an environment variable and `sshpass`;
do not write it into repo files, profile files, shell history, or command-line
arguments:

```bash
# 4060/HMI side. Install sshpass first if needed.
if ! command -v sshpass >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y sshpass
fi

# Use the site-provided password only in this shell, then unset it after the run.
export UNIT_UGV_SSH_PASSWORD='<site-provided-password>'
bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 \
  auth-check
unset UNIT_UGV_SSH_PASSWORD
```

A more durable path is to install a dedicated 4060 key:

```bash
# 4060/HMI side: create a dedicated key if one does not already exist.
ssh-keygen -t ed25519 -f ~/.ssh/changxin_unit_ugv_ed25519 -C changxin-4060-to-unit-ugv
cat ~/.ssh/changxin_unit_ugv_ed25519.pub
```

Add the printed public key to `/home/yhs/.ssh/authorized_keys` on the vehicle
through a site-approved local terminal or another already-authorized admin path,
then verify from 4060:

```bash
bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 \
  --ssh-identity ~/.ssh/changxin_unit_ugv_ed25519 \
  auth-check
```

Expected output: `ssh_auth_ok`, vehicle hostname, `yhs`, and the remote working
directory. Do not run `pull`, `sync-lite`, `sync-target-map`, `precheck`,
`start`, or `start-motion` until `auth-check` passes.

Create or check the object-target readiness gate on the real UGV IPC or the machine that owns the UGV local ROS1 master. If the target map is missing, this command writes an unconfirmed template and exits nonzero; stop there until the local operator edits and confirms the mapping:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_unit_ugv_object_target_readiness.py \
  --target-map "$UNIT_UGV_TARGET_MAP" \
  --object-query 显示器 \
  --platform-id ugv_0 \
  --write-missing-template \
  --output /tmp/changxin-unit-ugv-object-target-readiness.json
```

Expected output when the target map is missing: `UnitUgvObjectTargetReadiness.v1` with `ok=false`, `target_map_template_written=true`, `target_binding_ready=false`, `perception_backend=operator_confirmed_target_map`, `yolo_connected=false`, `ros_connected=false`, and `next_runtime_stage=local_operator_confirm_target_map`. Pass condition after local editing: the same command returns `ok=true`, `target_binding_ready=true`, `selected_target_id=<target>`, and `next_runtime_stage=4060_ros1_gateway_handoff`.

If the current WSL user cannot create the selected `UNIT_UGV_TARGET_MAP`, the tool still writes the `/tmp/changxin-unit-ugv-object-target-readiness.json` report with `ok=false`, `target_map_template_written=false`, and a permission/write failure in `validation_errors`. Do not continue to ROS/gateway from that state. Use the correct site user or a site-approved writable runtime path, then rerun this readiness gate.

Future YOLO integration should write portable `ObjectDetectionSet.v1` JSON first. That detection evidence may prefill an unconfirmed target-map template, but it must not directly authorize ROS handoff, `/gateway/dry_run`, `/gateway/dispatch`, or motion:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/seed_unit_ugv_target_map_from_yolo_detection.py \
  --detections /tmp/changxin-yolo-detections.json \
  --target-map "$UNIT_UGV_TARGET_MAP" \
  --object-query 显示器 \
  --platform-id ugv_0 \
  --output /tmp/changxin-unit-ugv-yolo-target-seed.json
```

Expected output: `UnitUgvYoloTargetSeed.v1` with `ok=false`, `yolo_detection_observed=true`, `target_map_template_written=true`, `target_binding_ready=false`, `ros_connected=false`, `gateway_dry_run_called=false`, and `dispatch_called=false`. The local operator still has to confirm the map binding before the object-target readiness gate can pass.

Edit the target map with the site-specific object aliases and target pose, then set `operator_confirmed_mapping=true` only after the local operator has confirmed the mapping:

```bash
mkdir -p "$CHANGXIN_GATEWAY_RUNTIME"
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_unit_ugv_target_map.py \
  --write-template "$UNIT_UGV_TARGET_MAP" \
  --platform-id ugv_0 \
  --target-id target_01 \
  --object-query 显示器 \
  --object-query monitor \
  --output /tmp/changxin-unit-ugv-target-map-template.json

# Edit "$UNIT_UGV_TARGET_MAP" locally.
# For no-motion proof, keep action=manual_confirm.
# For bounded motion, use action=move_base_goal and fill frame_id/x/y/yaw/max_distance_m from the real local map.
# Set operator_confirmed_mapping=true only after local operator confirmation.

PYTHONDONTWRITEBYTECODE=1 python3 tools/check_unit_ugv_target_map.py \
  --target-map "$UNIT_UGV_TARGET_MAP" \
  --platform-id ugv_0 \
  --require-object-queries \
  --select-object-query 显示器 \
  --max-move-base-distance-m 1.0 \
  --output /tmp/changxin-unit-ugv-target-map-check.json
```

Expected output: the checker exits `0` and writes `UnitUgvTargetMapCheckReport.v1` with `ok=true`, one selected target for the requested object query, no duplicate object aliases, and no unconfirmed target mappings. Fail condition: invalid JSON/schema, wrong `platform_id`, missing object aliases, duplicate aliases across targets, `operator_confirmed_mapping=false`, or a `move_base_goal` target without explicit pose and distance bounds.

Before any ROS1 gateway dry-run, the Mac/source side can prepare the full ROS-ready handoff from operator intent. This command is not a 4060 runtime step; it produces the artifact bundle and exact gateway dry-run plan that the 4060 ROS agent should execute next:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_unit_ugv_object_approach_pipeline.py \
  --profile profiles/dev_mock.env \
  --intent "让小车识别附近的显示器，然后走过去" \
  --mission-id unit_single_ugv_object_approach_001 \
  --case-id unit_single_ugv_object_approach \
  --target-map "$UNIT_UGV_TARGET_MAP" \
  --ros1-gateway-profile /tmp/work_hardware_ros1_gateway.env \
  --output-dir /tmp/changxin-unit-ugv-object-approach-handoff \
  --platform-id ugv_0 \
  --index 1 \
  --max-move-base-distance-m 1.0 \
  > /tmp/changxin-unit-ugv-object-approach-handoff.json
```

Expected output: `UnitUgvObjectApproachRosReadyHandoff.v1` with `ok=true`, `ros_ready=true`, `next_runtime_stage=4060_ros1_gateway_dry_run`, `service_name=/fleet/ugv_0/gateway/dry_run`, and Mac/source-side flags `mac_side_ros_connected=false`, `mac_side_service_called=false`, `mac_side_dispatch_performed=false`. The next 4060 step is HMI/ground-station-side ROS1 gateway signature verification and `/gateway/dry_run` against a gateway service hosted by the vehicle side, not another source-side-only check.

If an artifact was already produced separately, bind one validated artifact command to the local target map without connecting ROS:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_unit_ugv_artifact_target_map.py \
  /tmp/changxin-prevalidated-runs/<run_id> \
  --target-map "$UNIT_UGV_TARGET_MAP" \
  --platform-id ugv_0 \
  --index 0 \
  --max-move-base-distance-m 1.0 \
  > /tmp/changxin-unit-ugv-artifact-target-map-preflight.json
```

Expected output: `UnitUgvArtifactTargetMapPreflight.v1` with `ok=true`, the selected `TaskCommand.v1` mission/task/platform fields, a matching `selected_target_id`, and `ros_connected=false`, `dispatch_performed=false`. Fail condition: the artifact cannot be replayed, the selected UGV command is missing, `object_query` is not mapped, `target_id` disagrees with the object-query-selected target, the target map is unconfirmed, or a `move_base_goal` exceeds the site distance bound.

Package the validated command, rosservice payload, target-map copy, and preflight report into one source-side preparation directory before any gateway service call:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_unit_ugv_object_approach_bundle.py \
  /tmp/changxin-prevalidated-runs/<run_id> \
  --target-map "$UNIT_UGV_TARGET_MAP" \
  --output-dir /tmp/changxin-unit-ugv-object-approach-prep \
  --platform-id ugv_0 \
  --index 0 \
  --max-move-base-distance-m 1.0 \
  > /tmp/changxin-unit-ugv-object-approach-prep.json
```

Expected output: `UnitUgvObjectApproachPrepBundle.v1` with `ok=true`, `files.task_command_json`, `files.task_command_rosservice_json`, `files.artifact_target_map_preflight`, `ros_connected=false`, `dispatch_performed=false`, and `gateway_dry_run_called=false`. This is a handoff package for the next local gateway stage, not evidence that a gateway service was called.

Plan the exact gateway service call before executing any ROS command:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/plan_unit_ugv_gateway_call.py \
  --prep-report /tmp/changxin-unit-ugv-object-approach-prep/prep_bundle_report.json \
  --profile /tmp/work_hardware_ros1_gateway.env \
  --mode dry_run \
  > /tmp/changxin-unit-ugv-gateway-dry-run-plan.json
```

Expected output: `UnitUgvGatewayCallPlan.v1` with `ok=true`, `service_name=/fleet/ugv_0/gateway/dry_run`, `payload_file` pointing at `task_command.rosservice.json`, required service signature `platform_gateway_msgs/TaskCommandJson task_command_json`, and `ros_connected=false`, `service_called=false`, `dispatch_performed=false`. This checkpoint binds the validated mission artifact and target map to the local gateway contract before a human decides whether to run the service call.

Before the dry-run, start or inspect the vehicle-side wrapper through SSH. For a
no-motion capability check, start the wrapper without `move_base` enablement:

```bash
bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 \
  --remote-repo /home/yhs/changxin-code \
  --remote-target-map /home/yhs/changxin_gateway_runtime/unit_ugv_targets.json \
  precheck -- --select-object-query 显示器

bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 \
  --remote-repo /home/yhs/changxin-code \
  --remote-target-map /home/yhs/changxin_gateway_runtime/unit_ugv_targets.json \
  start -- --select-object-query 显示器
```

For a bounded `move_base_goal` trial, require the vehicle-side imports, ROS
master, target map, and `/move_base` action server before starting the wrapper
with operator approval and move-base enablement:

```bash
bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 \
  --remote-repo /home/yhs/changxin-code \
  --remote-target-map /home/yhs/changxin_gateway_runtime/unit_ugv_targets.json \
  precheck -- \
    --select-object-query 显示器 \
    --enable-move-base \
    --require-move-base-server

bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 \
  --remote-repo /home/yhs/changxin-code \
  --remote-target-map /home/yhs/changxin_gateway_runtime/unit_ugv_targets.json \
  start-motion -- --select-object-query 显示器
```

Expected output: the wrapper process runs on the vehicle and registers
`/fleet/ugv_0/gateway/dry_run` and `/fleet/ugv_0/gateway/dispatch`. Pass
condition: the vehicle-side precheck validates `platform_gateway_msgs`, the target
map, ROS master, and, for motion trials, `move_base_msgs` plus the `/move_base`
action server. Fail condition: the wrapper starts on the 4060, the vehicle cannot
import `move_base_msgs`, the target map is missing/unconfirmed, ROS master is not
reachable from the vehicle, or `/move_base` is unavailable when motion is enabled.

After the vehicle-side ROS1 gateway services have passed service-name/type/args
signature verification from the 4060/HMI side, run the standard dry-run runner
as the HMI/ground-station client instead of hand-writing a raw `rosservice call`.
The runner reads the ROS-ready handoff, passes the prepared payload as one
subprocess argument to avoid shell quoting drift, records stdout/stderr, parses
`GatewayServiceResponse.v1`, and still never calls `/gateway/dispatch` or
publishes raw ROS topics:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_unit_ugv_ros_gateway_dry_run.py \
  --handoff-report /tmp/changxin-unit-ugv-object-approach-handoff/ros_ready_handoff_report.json \
  --output-dir /tmp/changxin-unit-ugv-gateway-dry-run \
  > /tmp/changxin-unit-ugv-gateway-dry-run.json
```

Expected output: `UnitUgvRosGatewayDryRun.v1` with `ok=true`, `dry_run_called=true`, `dispatch_called=false`, `rostopic_pub=false`, `controlled_motion_authorized=false`, `response_schema=GatewayServiceResponse.v1`, `response_mode=dry_run`, `ack_accepted=true`, `motion_attempted=false`, and `raw_ros_publish_attempted=false`. Fail condition: the handoff is not `ros_ready`, the service name is not `/fleet/ugv_0/gateway/dry_run`, `rosservice call` returns nonzero, the gateway response rejects the command, or the response reports motion/raw publish.

Use the SSH lifecycle wrapper to inspect status, collect service signatures, or
stop the vehicle-side gateway after a run:

```bash
bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 status

bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 signature

bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 logs

bash ugv/01-scripts/operate_unit_ugv_vehicle_gateway_ssh.sh \
  --remote yhs@192.168.0.201 stop
```

Expected output: `status` shows process and service-registration state,
`signature` writes vehicle-side service list/type/args files under the state
directory, `logs` prints recent wrapper output, and `stop` terminates only the
managed wrapper process. Pass condition: status/signature match the expected
`platform_gateway_msgs/TaskCommandJson task_command_json` contract. Fail
condition: services are missing, types/args differ, logs show wrapper exceptions,
or stop cannot terminate the managed pid.

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

For a real `move_base_goal` dispatch, the vehicle-side wrapper must already have
been started with `start-motion`. Pass condition: after a separately approved
`/fleet/ugv_0/gateway/dispatch` issued from the HMI/ground-station side,
`/tmp/changxin-task-progress.json` on the vehicle-side wrapper host contains
`TaskProgressSet.v1` for the same `mission_id/task_id/platform_id`. Fail
condition: the wrapper is accidentally hosted on the 4060 instead of the
vehicle-local ROS environment, no operator approval, `move_base` server
unavailable, target map invalid, dispatch response not accepted, or no matching
TaskProgress file.

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
