# changxin-code AGENTS

## Mission
This repository contains the ROS1 UAV/UGV code, docs, tests, and architecture notes for the heterogeneous fleet task-planning system.

When working on multi-robot task planning, preserve the current architecture:

```text
operator intent
-> command / CLI / agent-issued local call
-> ModelClient backed by MockLLMClient now, local_http/remote_http adapter later
-> TaskSchema / MissionRequest
-> schema validator
-> mission blackboard
-> PDDL problem generator
-> PDDL planner
-> plan validator
-> PDDL-to-BT/state-machine compiler
-> platform gateway
-> each platform local ROS1 master
```

## Required Read Order
Before changing task-planning architecture or implementation, read these first:

1. `docs/superpowers/specs/2026-05-25-local-llm-mission-ops-architecture.md`
2. `docs/superpowers/specs/2026-05-26-distributed-fleet-testing-migration-architecture.md`
3. `docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md`
4. `docs/superpowers/specs/2026-05-19-fleet-pddl-bt-architecture.md`
5. `docs/superpowers/specs/2026-05-19-pddl-bt-execution-model.md`
6. `docs/superpowers/specs/2026-05-19-platform-gateway-contract.md`
7. `/Users/apple/Documents/Obsidian Vault/知识系统/docs/agent-handoff-task-planning-architecture.md`
8. `/Users/apple/Documents/Obsidian Vault/知识系统/docs/goal-distributed-fleet-testing-and-migration.md`
9. `/Users/apple/Documents/Obsidian Vault/知识系统/wiki/analyses/Analysis - 任务规划系统 LangGraph vs MissionManager 决策.md`

## Stable Defaults
- Use ROS1.
- Keep one ROS master per platform.
- Keep the independent ground station as the only global planner.
- Keep PDDL as the mission-level planning authority.
- Compile PDDL plans into task-level BT/state-machine execution.
- Use platform gateways to deliver structured commands into each local ROS1 master.
- Phase 1 does not deploy small models on UGV/UAV platforms.
- Platforms may continue an already accepted BT subtree during disconnect, but must not create new missions or rebuild PDDL plans locally.

## Model Decision
Phase 1 does not require a real locally deployed LLM. Start with local commands / CLI / agent-issued calls plus `MockLLMClient`.

Allowed model roles:

- draft `MissionRequest` / `TaskSchema`
- ask clarification questions
- summarize relevant knowledge-system/project context
- explain validator or planner errors
- triage `FailureReport`
- draft experiment logs and review summaries

Forbidden model roles:

- direct ROS topic/service/action control
- direct `/mavros/*`, `/cmd_vel`, or `/setpoints_cmd` output
- replacing the PDDL planner
- replacing BT/state-machine execution
- replacing platform gateway safety checks
- running as a vehicle-side autonomy model in phase 1
- treating long chat history as the mission blackboard

When a real model endpoint is deployed, add it behind the same `ModelClient` interface as a local HTTP or remote HTTP adapter. The model still runs on the ground station or home model-lab side only and remains a semantic compiler / explanation assistant; the work/unit hardware lane must remain runnable with mock or prevalidated schemas.

## Distributed Test Lanes
Use profiles under `profiles/` to keep machine-specific settings out of code:

- `dev_mock`: baseline on the work 4060 laptop or any dev machine; uses `MockLLMClient` and mock gateway.
- `home_model_lab`: home 5090 model capability lane; may use an OpenAI-compatible local HTTP model endpoint, but must keep `PLATFORM_BACKEND=mock`.
- `server_sim`: optional replay/simulation/CI lane.
- `work_hardware`: unit/workplace execution lane. The physical platforms are at the unit/workplace, and hardware execution must not depend on the home 5090 server.

When an agent is running on the unit/workplace execution endpoint, use `docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md` as the short operational entry point.

Every profiled mission run should write portable artifacts under `MISSION_ARTIFACT_ROOT/<run_id>/` so model-lab, sim, and hardware behavior can be compared without sharing a single machine.

Home/server artifacts should move to the unit/workplace execution lane as verified artifact packages, not as live model dependencies. The receiving-side agent should verify package checksums, artifact schemas, and differing source/verifier machine ids before running any `work_hardware` prevalidated replay or ROS1 gateway preparation.

Operational entry points:

- Run golden cases: `PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile profiles/dev_mock.env`
- Run one operator intent through MissionManager/PDDL/BT without ROS: `PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_intent.py --profile profiles/dev_mock.env --intent "<operator-intent>" --mission-id <mission_id> --primary-platform ugv_0 --artifact-root /tmp/changxin-intent-runs`
- Run an external agent-drafted `TaskSchema.v1` through the same validator/PDDL/BT path without ROS: `PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_intent.py --profile profiles/dev_mock.env --intent "<operator-intent>" --mission-id <mission_id> --primary-platform ugv_0 --agent-name openclaw --agent-draft-file /tmp/task_schema_draft.json --artifact-root /tmp/changxin-agent-intent-runs`
- Run the required dev_mock golden suite with artifact verification: `PYTHONDONTWRITEBYTECODE=1 python3 tools/run_dev_mock_golden_suite.py --artifact-root /tmp/changxin-dev-mock-golden-suite`
- Check machine/profile readiness without sending ROS commands: `PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_readiness.py --profile profiles/work_hardware.env`
- Collect lane acceptance evidence without sending ROS control commands: `PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile profiles/work_hardware.env`
- Collect a local baseline evidence directory: `PYTHONDONTWRITEBYTECODE=1 python3 tools/collect_distributed_fleet_evidence.py --output-dir /tmp/changxin-distributed-fleet-evidence`
- Create or refresh the external evidence handoff scaffold for another machine/agent: `PYTHONDONTWRITEBYTECODE=1 python3 tools/init_external_evidence_handoff.py --evidence-dir /tmp/changxin-distributed-fleet-evidence`
- Import real external evidence into the standard evidence directory after home/server/unit runs: `PYTHONDONTWRITEBYTECODE=1 python3 tools/import_distributed_fleet_external_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence --model-lab-evaluation <model_lab_evaluation.json> --artifact-package <artifact-package.tar.gz> --artifact-package-verification-report <artifact_package_verification.json>`
- Check only the phase gate before deciding whether to keep local v1 frozen or start the next phase: `PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_phase_gate.py --evidence-dir /tmp/changxin-distributed-fleet-evidence --print-discovered-inputs`
- Aggregate goal-level evidence and remaining external gaps, including local lane-matrix comparability: `PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence`
- Print only unresolved goal gaps for handoff: `PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence --missing-only --print-discovered-inputs`
- Run the no-model/no-hardware cross-lane matrix: `PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_lane_matrix.py --artifact-root /tmp/changxin-lane-matrix --case uav_ugv_coordination`
- Validate or compare artifacts: `PYTHONDONTWRITEBYTECODE=1 python3 tools/replay_task_planning_artifact.py <artifact_root> [--compare-to <artifact_root>]`
- Print unit/work hardware gates without executing ROS commands: `PYTHONDONTWRITEBYTECODE=1 python3 tools/plan_work_hardware_gate.py --profile profiles/work_hardware.env --through-stage mock_gateway_dispatch`
- Audit ROS1 gateway service names and signatures with read-only ROS commands: `PYTHONDONTWRITEBYTECODE=1 python3 tools/audit_ros1_gateway_services.py --profile profiles/work_hardware.env --platform-id uav_0 --service-list-file /tmp/changxin-rosservice-list.txt --service-type-file /tmp/changxin-rosservice-types.txt --service-args-file /tmp/changxin-rosservice-args.txt --require-service-signatures`
- Prepare the ROS1 gateway catkin package with a dry-run first: `PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py --catkin-src ~/catkin_ws/src`
- Smoke-test the home model-lab endpoint without hardware dispatch: `PYTHONDONTWRITEBYTECODE=1 python3 tools/check_model_lab_endpoint.py --profile profiles/home_model_lab.env`
- Evaluate home model-lab output as portable artifacts only: `PYTHONDONTWRITEBYTECODE=1 python3 tools/evaluate_model_lab_case.py --profile profiles/home_model_lab.env --case uav_ugv_coordination --output-dir /tmp/changxin-model-lab` (final proof requires the report's `machine_id`, baseline comparison fields, and `accelerator_probe` to show an RTX 5090)
- Test OpenAI-compatible HTTP plumbing without a real 5090 model: run `PYTHONDONTWRITEBYTECODE=1 python3 tools/run_mock_model_lab_endpoint.py --port 8000`, then check `profiles/home_model_lab_mock_endpoint.env`. This uses `MODEL_LAB_EVIDENCE_KIND=mock_endpoint` and is not completion evidence for `home_5090_model_lab_evaluated`.
- Package model-lab or replay artifacts for transfer: `PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_artifacts.py --artifact /tmp/changxin-model-lab/uav_ugv_coordination --output-dir /tmp/changxin-artifact-packages`
- Verify transferred artifacts on the unit/workplace receiving machine: `PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py <artifact-package.tar.gz> --work-dir /tmp/changxin-artifact-verify --verification-context unit_workplace_receiving` (source/verifier machine ids must differ; use `source_machine` only for local sanity checks)
- Verify transferred artifacts as part of site acceptance: `PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile profiles/work_hardware.env --artifact-package <artifact-package.tar.gz> --artifact-work-dir /tmp/changxin-artifact-verify --require-artifact-package`
- Replay a prevalidated schema on the work hardware mock/approval lane without a model call: `PYTHONDONTWRITEBYTECODE=1 python3 tools/run_prevalidated_task_schema.py --profile profiles/work_hardware.env --task-schema /tmp/changxin-model-lab/uav_ugv_coordination/model_task_schema.json --artifact-root /tmp/changxin-prevalidated-runs`
- Extract a validated capability-level TaskCommand from an artifact before any ROS1 dry-run call: `PYTHONDONTWRITEBYTECODE=1 python3 tools/extract_task_command_from_artifact.py <artifact_bundle_path> --platform-id uav_0 --format rosservice-yaml`
- Validate a local unit UGV object/target map before any ROS1 gateway call: `PYTHONDONTWRITEBYTECODE=1 python3 tools/check_unit_ugv_target_map.py --target-map /tmp/unit_ugv_targets.json --platform-id ugv_0 --require-object-queries --select-object-query <object-name>`
- Preflight a validated UGV artifact against a local unit UGV target map before any ROS1 gateway call: `PYTHONDONTWRITEBYTECODE=1 python3 tools/check_unit_ugv_artifact_target_map.py <artifact_bundle_path> --target-map /tmp/unit_ugv_targets.json --platform-id ugv_0 --index 0`
- Prepare a self-contained no-ROS UGV object-approach handoff bundle before any gateway call: `PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_unit_ugv_object_approach_bundle.py <artifact_bundle_path> --target-map /tmp/unit_ugv_targets.json --output-dir /tmp/changxin-unit-ugv-object-approach-prep --platform-id ugv_0 --index 0`
- Build a portable migration bundle: `PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_migration.py --output-dir /tmp/changxin-migration`
- Verify a migration bundle after transfer: `PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_migration_bundle.py /tmp/changxin-migration/task-planning-migration-bundle.tar.gz --work-dir /tmp/changxin-migration-verify --verification-context receiving_machine`

`PLATFORM_BACKEND=ros1_gateway` uses `platform_gateway/ros1_service_gateway.py`. It sends validated `TaskCommand.v1` JSON only to `/fleet/{platform_id}/gateway/dry_run` or `/fleet/{platform_id}/gateway/dispatch` style services. It must not publish raw ROS topics from the center, and with `HARDWARE_APPROVAL_REQUIRED=true` it must stop before dispatch unless operator approval has been explicitly supplied. Final hardware proof artifacts must preserve that approval as `operator_approved=true`, `operator_approval_source=local_unit_operator`, and a hashed `machine_id`.

Platform-side gateway wrappers should delegate incoming TaskCommand JSON to `platform_gateway/service_core.py`. The service core validates capability-level commands, local safety state, battery, localization, and platform id before any local executor is called.

If no ROS1 service contract exists yet, use `platform_gateway/ros/catkin_pkg/platform_gateway_msgs` and keep the wrapper shaped like `platform_gateway/ros1_service_node_template.py`: receive JSON, call the service core, return JSON.

When a generated ROS service package is available, `tools/run_ros1_platform_gateway_node.py` can run the actual wrapper with `--service-symbol platform_gateway_msgs.srv:TaskCommandJson` or another generated service symbol. Do not import `rospy` in core modules; keep ROS imports runtime-only inside the wrapper.

## LangGraph Decision
Do not add LangGraph as a phase-1 production runtime dependency.

Phase 1 should use a deterministic `MissionManager` state machine under `task_planning/mission_ops/`.

However, do not paint the system into a corner. Phase 1 must be LangGraph-ready:

- expose a `MissionOpsRunner` interface
- persist `MissionOpsState` as JSON or SQLite
- implement each Mission Ops step as a typed tool/node
- keep model calls behind `model_client.py`
- keep core modules independent from Mission Ops runtime choices

LangGraph may be reconsidered later only if the Mission Ops layer needs durable checkpoint/resume, complex human-in-the-loop workflow, specialist subagents, background jobs, or execution trace replay. If added later, it remains a ground-station Mission Ops shell and must not bypass validator, PDDL, BT, platform gateway, or local ROS1.

## First Implementation Slice
Build the deterministic core first:

1. `task_planning/contracts/`
2. `task_planning/mission_ops/model_client.py`
3. `task_planning/mission_ops/mock_llm_client.py`
4. `task_planning/mission_ops/mission_manager.py`
5. `task_planning/mission_ops/runner.py`
6. `task_planning/mission_ops/state_store.py`
7. `task_planning/pddl/`
8. `task_planning/validation/`
9. `task_planning/execution/plan_to_bt.py`
10. mock `platform_gateway/`
11. tests for schema validation, mock model output, state persistence, mock planner output, plan-to-BT, gateway ack, and failure-to-replan

Do not start with hardware integration. Start with examples, dry-runs, and simulated gateway tests.

## Safety Boundary
- Center does not publish raw platform ROS topics.
- Center emits only capability-level `TaskCommand`.
- Gateway maps allowed task commands to local ROS interfaces.
- Gateway may reject commands and must return structured reasons.
- Blackboard is the planning state source of truth.
- All `ModelClient` outputs, including mock outputs, must pass schema validation before entering the deterministic core.
