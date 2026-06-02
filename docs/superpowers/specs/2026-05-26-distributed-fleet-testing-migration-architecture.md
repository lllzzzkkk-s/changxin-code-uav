# Distributed Fleet Testing And Migration Architecture

Date: 2026-05-26

## Source Goal

This spec implements the first migration slice from:

- `/Users/apple/Documents/Obsidian Vault/知识系统/docs/goal-distributed-fleet-testing-and-migration.md`
- `/Users/apple/Documents/Obsidian Vault/知识系统/docs/agent-handoff-task-planning-architecture.md`
- `/Users/apple/Documents/Obsidian Vault/知识系统/docs/task-planning-implementation-roadmap.md`

## Fixed Constraints

- The physical UAV/UGV execution platforms are at the unit/workplace.
- The home RTX 5090 server is only a model-capability lab. It is not required for robot execution.
- The work RTX 4060 laptop must remain useful without large-model inference.
- Migration must prove the unit/workplace lane can pass mock and read-only gates before any real ROS1 gateway dispatch; home model-lab results are only compared as artifacts.
- Home/server outputs must enter the unit/workplace lane as verified artifact packages with `verification_context=unit_workplace_receiving`, never as a live execution dependency.
- Artifact-package receiving proof must also include hashed `source_machine_id` and `verifier_machine_id`; unit/workplace receiving proof is rejected when those ids match.
- Phase 1 stays mock-first and command-driven.
- Keep the control chain:

```text
center PDDL -> task-level BT/state machine -> platform gateway -> local ROS1
```

- Keep one ROS1 master per platform.
- Do not put LLMs on UAV/UGV platforms.
- Do not let any model directly publish ROS topics, ROS services, shell commands, `/mavros/*`, `/cmd_vel`, or `/setpoints_cmd`.

## Test Lanes

Profiles live under `profiles/`:

| Profile | Purpose | Model | Platform backend | Required now |
| --- | --- | --- | --- | --- |
| `dev_mock` | everyday development on work 4060 or any dev host | `mock` | `mock` | yes |
| `home_model_lab` | test 5090 model schema quality only | `local_http` | `mock` | optional |
| `home_model_lab_mock_endpoint` | test OpenAI-compatible HTTP plumbing only | `local_http` mock endpoint | `mock` | optional, not proof |
| `server_sim` | replay/simulation/CI lane | `mock` or future remote | `sim` | optional |
| `work_hardware` | unit/workplace execution lane | `mock` or optional remote | `mock` now, `ros1_gateway` later | yes, gated |

The default `work_hardware.env` deliberately uses `PLATFORM_BACKEND=mock`. A real `ros1_gateway` profile requires `ROS_MASTER_URI`, `ROS_IP`, and `HARDWARE_APPROVAL_REQUIRED=true`, plus a real gateway implementation.

## Implemented In This Slice

- `task_planning/config/profiles.py`
  - parses `.env` profiles
  - validates lane-specific safety rules
  - fails early on unsafe local/remote model or ROS1 gateway settings
- `profiles/*.env`
  - four lane profiles
- `task_planning/mission_ops/artifacts.py`
  - writes portable run artifacts under `MISSION_ARTIFACT_ROOT/<run_id>/`
- `task_planning/mission_ops/golden_cases.py`
  - representative cases for UGV inspection, UAV reconnaissance, UAV+UGV coordination, failure/replan, and disconnect continuation
- `task_planning/migration/golden_suite.py` and `tools/run_dev_mock_golden_suite.py`
  - run and verify every required dev_mock golden case as one machine-readable `DevMockGoldenSuite.v1` report
  - prove the phase-1 deterministic path writes complete portable artifacts before model-lab or hardware evidence is added
- `task_planning/mission_ops/http_model_client.py`
  - optional OpenAI-compatible HTTP model adapter for the home model lab or future remote endpoint
  - not the phase-1 default
- `MissionManagerRunner`
  - accepts profile dictionaries
  - writes artifact bundles for profiled runs
  - auto-installs `Ros1ServiceGateway` for `work_hardware` + `PLATFORM_BACKEND=ros1_gateway` when no explicit gateway is provided
  - blocks accidental `ros1_gateway` use if a mock gateway was explicitly injected
  - forces manual approval state for `work_hardware` when `HARDWARE_APPROVAL_REQUIRED=true`
- `platform_gateway/ros1_service_gateway.py`
  - calls allowlisted `/fleet/{platform_id}/gateway/dry_run` or `/fleet/{platform_id}/gateway/dispatch` services with validated `TaskCommand.v1` JSON
  - never publishes raw ROS topics from the center
  - refuses dispatch before operator approval when the profile requires it
- `platform_gateway/service_core.py`
  - platform-side service core for future ROS1 service wrappers
  - validates incoming `TaskCommand.v1` JSON against platform state and capability registry
  - supports `dry_run` and `dispatch` modes while refusing raw ROS controls before any local executor is called
- `platform_gateway/ros/srv/TaskCommandJson.srv`
  - minimal ROS1 service contract: `string task_command_json -> string response_json`
- `platform_gateway/ros/catkin_pkg/platform_gateway_msgs`
  - minimal catkin package for generating `platform_gateway_msgs.srv:TaskCommandJson`
- `platform_gateway/ros1_service_node_template.py`
  - thin wrapper template for registering dry-run and dispatch services that delegate to `PlatformGatewayServiceCore`
- `platform_gateway/ros1_service_node.py` and `tools/run_ros1_platform_gateway_node.py`
  - runnable ROS1 node wrapper using a dynamically supplied generated service symbol such as `gateway_msgs.srv:TaskCommandJson`
  - keeps ROS imports runtime-only so non-ROS development machines can still run unit tests
- `task_planning/migration/bundle.py` and `tools/package_task_planning_migration.py`
  - produce a portable migration bundle with profiles, docs, core Python, ROS gateway package, tests, commands, manifest, checksums, and `MIGRATION.md`
- `task_planning/migration/verify.py` and `tools/verify_task_planning_migration_bundle.py`
  - extract a received migration archive into a clean verification directory
  - reject unsafe archive paths and symlinks
  - verify every manifest path, byte count, and sha256 checksum
  - record `verification_context=receiving_machine` or `unit_workplace_receiving`; source-machine checks do not satisfy transfer-completion evidence
  - record hashed `source_machine_id` and `verifier_machine_id`; receiving-machine proof is rejected when the ids match
  - optionally run the phase-1 `tests/task_planning` suite, one `dev_mock` golden case, the full dev_mock golden suite, the lane matrix, ROS1 service-audit plan, and work-hardware site acceptance from inside the extracted bundle
- `task_planning/migration/readiness.py` and `tools/check_task_planning_readiness.py`
  - classify whether the current machine/profile can run a lane without sending ROS commands
  - keep `work_hardware` mock gates runnable without ROS runtime or local large-model inference
  - warn on missing ROS CLI tools for mock gates, but fail real `ros1_gateway` readiness if ROS/catkin runtime is unavailable
  - emit the next lane-specific commands for a fresh agent or operator
- `task_planning/migration/lane_matrix.py` and `tools/run_task_planning_lane_matrix.py`
  - run the same mission case through `dev_mock`, `server_sim`, and `work_hardware` mock/pre-dispatch lanes
  - require exact artifact equivalence for `dev_mock` vs `server_sim`
  - require pre-dispatch compatibility for `dev_mock` vs `work_hardware`, allowing only the expected empty gateway trace caused by the manual approval gate
  - prove the migration chain can be exercised without the home 5090 server, local large-model inference, or real hardware dispatch
- `task_planning/migration/model_lab.py` and `tools/evaluate_model_lab_case.py`
  - evaluate the home 5090 OpenAI-compatible endpoint against a golden mission case
  - keep `PLATFORM_BACKEND=mock` and never dispatch to hardware
  - write portable model-lab artifacts: profile, mission input, mock baseline schema, model schema, and evaluation report
  - record `MISSION_PROFILE=home_model_lab`, `MODEL_PROVIDER=local_http`, `PLATFORM_BACKEND=mock`, `MODEL_LAB_EVIDENCE_KIND`, hashed `machine_id`, and `nvidia-smi` accelerator probe output
  - only `MODEL_LAB_EVIDENCE_KIND=home_5090_live` plus the home-model-lab/local-http/mock-platform lane fields and a successful RTX 5090 probe can satisfy real home model-lab proof
  - require `baseline_equivalent`, `diffs`, and empty `validation_errors` in the live 5090 report so the mock/golden baseline comparison is explicit
  - require the live 5090 report `case_id` to match an OK lane-matrix `case_id`, so the model-lab proof is tied to the same mission case used across `dev_mock`, `server_sim`, and `work_hardware` pre-dispatch
  - report `MissionRequest` diffs against the mock baseline for review without letting those diffs bypass validators, PDDL, BT, or gateways
- `task_planning/mission_ops/mock_openai_endpoint.py` and `tools/run_mock_model_lab_endpoint.py`
  - provide an OpenAI-compatible local mock endpoint for development and CI plumbing tests before the real home 5090 endpoint exists
  - require `profiles/home_model_lab_mock_endpoint.env` with `MODEL_LAB_EVIDENCE_KIND=mock_endpoint`
  - never counts as `home_5090_model_lab_evaluated` in goal evidence or external evidence import
- `task_planning/migration/prevalidated_schema.py` and `tools/run_prevalidated_task_schema.py`
  - replay a saved `TaskSchema.v1` through validator, PDDL, BT, and mock/pre-dispatch gateway artifacts
  - require an explicit or inferable `case_id` and write it to `mission_input.run_input.case_id` so later unit hardware proof remains tied to the lane matrix
  - reject direct `PLATFORM_BACKEND=ros1_gateway` use so prevalidated schemas are checked before real gateway dispatch
  - allow model-lab schemas to be copied to the unit/workplace lane and run without a live model endpoint
  - stop at `OPERATOR_APPROVAL` under `work_hardware.env`
- `task_planning/migration/task_command_extraction.py` and `tools/extract_task_command_from_artifact.py`
  - extract a validated capability-level `TaskCommand.v1` from an artifact bundle without sending ROS commands
  - provide a `rosservice-yaml` output for the later ROS1 gateway dry-run service call
  - keeps real gateway dry-runs tied to previously validated PDDL/BT artifacts instead of hand-written ROS payloads
- `task_planning/migration/artifact_package.py`, `tools/package_task_planning_artifacts.py`, and `tools/verify_task_planning_artifacts.py`
  - package mission-run or model-lab artifact directories into a transfer archive with manifest, byte counts, and sha256 checksums
  - reject unsafe archive paths and symlinks
  - verify mission-run artifacts with the replay loader and model-lab artifacts with explicit schema checks
  - require a successful model-lab artifact to carry `model_task_schema.json`, and require model-lab profile fields to match the evaluation report while keeping `PLATFORM_BACKEND=mock`
  - record artifact-level `case_id` in verification output for mission-run and model-lab artifacts, and reject model-lab packages whose mission input and evaluation report disagree on `case_id`
  - expose model-lab artifact metadata in verification output so the goal checker can bind `reports/model_lab_evaluation.json` to the packaged artifact rather than accepting a loose JSON report
  - record hashed `source_machine_id` in the package manifest and `verifier_machine_id` in verification reports
  - record `verification_context=unit_workplace_receiving` when artifact packages are verified after transfer into the unit/workplace execution lane; reject that proof when source/verifier machine ids match
  - make the home/server to unit/workplace handoff file-based and auditable instead of network-dependent
- `task_planning/migration/site_acceptance.py` and `tools/check_task_planning_site_acceptance.py`
  - collect profile readiness, artifact-package verification, hardware gate planning, and optional ROS1 service audit evidence into one report
  - record hashed `machine_id` so unit/workplace ROS1 signature evidence is tied to the receiving machine that collected it
  - require ROS1 service/signature evidence to be recorded against a local `PLATFORM_BACKEND=ros1_gateway` profile, not the safe mock `work_hardware.env`
  - never send ROS control commands
  - make the unit/workplace receiving agent prove whether it is still at mock/pre-dispatch, artifact-replay, or observed ROS1-service readiness
- `task_planning/migration/goal_evidence.py` and `tools/check_distributed_fleet_goal_evidence.py`
  - aggregate repository contracts, profile readiness, lane-matrix comparability, dev_mock golden-suite coverage, artifact packages, model-lab evaluation, site acceptance, ROS1 signatures, migration verification, and hardware run artifacts
  - emit `phase_gate` in the full and summary reports so agents can distinguish local implementation work from the five real external proofs
  - mark `phase_gate.local_v1_freeze=true` when all remaining blockers are external proofs, and keep `phase_gate.next_phase_ready=false` until those proofs pass
  - expose `tools/check_distributed_fleet_phase_gate.py` as the short receiving-agent command when an agent only needs to know whether to keep local v1 frozen or start the next phase
  - require the local lane matrix report to prove the same mission case is comparable across `dev_mock`, `server_sim`, and `work_hardware` pre-dispatch lanes
  - require `home_5090_model_lab_evaluated` to use a `case_id` from an OK lane matrix, so a valid model-lab report for a different task cannot complete the same-case migration proof
  - require `home_5090_model_lab_evaluated` to see a verified model-lab artifact package for the same case, with packaged artifact metadata matching the evaluation report fields `mission_profile`, `model_provider`, `platform_backend`, `model_lab_evidence_kind`, and `machine_id`
  - require `artifact_package_verified_after_transfer` to include artifact-level `case_id` evidence matching an OK lane matrix, whether the verification report is standalone or embedded in site acceptance
  - count a `unit_workplace_receiving` artifact-package verification embedded in an OK `work_hardware` `TaskPlanningSiteAcceptance.v1` report with `machine_id` and a work-hardware acceptance level, so a unit agent can return one combined site acceptance report instead of duplicating files
  - keep the full goal honest by marking live home 5090, unit ROS1, migration transfer, or hardware execution evidence as `missing` until supplied
  - give a fresh agent one JSON report showing what is proved and what still requires a real machine
  - support `--summary` and `--missing-only --print-discovered-inputs` so a receiving agent can see unresolved external proof without parsing the full report
- `task_planning/migration/evidence_collection.py` and `tools/collect_distributed_fleet_evidence.py`
  - write a standard local evidence directory with readiness reports, full dev_mock golden-suite artifacts, lane matrix artifacts, site acceptance, and goal evidence
  - make first-run evidence collection reproducible on a fresh machine without sending ROS commands or calling the home model endpoint
  - write `reports/phase_gate.json` and `PHASE_GATE.md` so a receiving agent sees whether the local v1 implementation is frozen or still needs repo-side work
  - leave external proof gaps explicit in `EVIDENCE.md`
- `task_planning/migration/handoff_package.py` and `tools/package_distributed_fleet_handoff.py`
  - build one transfer archive containing the migration bundle, the local baseline evidence directory, `PHASE_GATE.md`, `reports/phase_gate.json`, `reports/external_evidence_requirements.json`, `NEXT_EXTERNAL_EVIDENCE.md`, and a short `HANDOFF.md`
  - let another machine or agent start from a single tarball without relying on this chat history
  - verify received handoff archives with `tools/verify_distributed_fleet_handoff_package.py`, including top-level checksums, the embedded migration bundle manifest, matching `case_id`, matching `missing_required` entries across the handoff manifest, evidence manifest, phase gate report, and external evidence requirements report, plus a readable `PHASE_GATE.md`
  - distinguish same-machine source sanity checks from receiving-machine proof with hashed source/verifier machine ids
  - keep the package honest by preserving missing external proof items instead of treating the package as home 5090 or unit hardware evidence
- `task_planning/migration/external_handoff.py` and `tools/init_external_evidence_handoff.py`
  - create `NEXT_EXTERNAL_EVIDENCE.md` and `reports/external_evidence_requirements.json` so another machine or agent can fill live home 5090, transfer, unit ROS1, and hardware-run evidence into standard paths without fabricating proof
  - tell the receiving agent that home 5090 proof needs both `reports/model_lab_evaluation.json` and the full packaged model-lab artifact directory, not a loose report alone
- `task_planning/migration/external_import.py` and `tools/import_distributed_fleet_external_evidence.py`
  - copy externally produced reports, artifact packages, and hardware artifact roots into the standard evidence directory only after source files exist and basic schemas match
  - reject home 5090 model-lab reports unless `reports/lane_matrix.json` already has an OK matching `case_id`, keeping imported model proof tied to the same mission case as the local lane matrix
  - import `reports/handoff_package_verification.json` as receiving-machine migration proof when it contains an OK embedded `MigrationVerification.v1`
  - verify artifact-package manifests, checksums, contained artifact schemas, and source-vs-verifier machine-id mismatch before copying them into `artifact_packages/`
  - reject artifact packages unless every verified artifact-level `case_id` matches the OK lane-matrix `case_id`
  - verify hardware artifact roots use `MISSION_PROFILE=work_hardware`, `PLATFORM_BACKEND=ros1_gateway`, `HARDWARE_APPROVAL_REQUIRED=true`, machine-readable `operator_approved=true`, `operator_approval_source=local_unit_operator`, hashed `machine_id`, `execution_context=unit_workplace_hardware`, passed validation, a successful `/gateway/dispatch` ROS1 service trace, accepted command acknowledgements, and task progress matching the same `mission_id` / `task_id` / `platform_id` before copying them into `hardware_artifacts/`
  - reject hardware artifact roots unless their `mission_input.run_input.case_id` matches an OK lane-matrix `case_id`, keeping final unit execution proof tied to the same cross-lane mission case
  - reject `/gateway/dry_run`-only or empty-trace artifacts as final unit/work hardware execution proof
  - avoid manual path/name drift for `reports/model_lab_evaluation.json`, `reports/migration_verification.json`, `reports/handoff_package_verification.json`, `reports/site_acceptance_work_hardware_ros1.json`, `artifact_packages/*.tar.gz`, and `hardware_artifacts/<run_id>/`
- `task_planning/migration/hardware_dispatch_artifact.py` and `tools/record_unit_hardware_dispatch_artifact.py`
  - assemble a final unit/workplace hardware proof artifact from an already validated source artifact, local `ros1_gateway` profile, captured `/gateway/dispatch` response, accepted `CommandAck`, and `TaskProgress`
  - require `--operator-approved`, `operator_approval_source=local_unit_operator`, hashed `machine_id`, `PLATFORM_BACKEND=ros1_gateway`, `execution_context=unit_workplace_hardware`, `/gateway/dispatch`, matching mission/task/platform ids, and task progress
  - do not send ROS commands; the real dispatch remains a separate local operator action
- `task_planning/migration/ros1_workspace.py` and `tools/prepare_ros1_gateway_workspace.py`
  - prepare `platform_gateway_msgs` for a unit/workplace ROS1 catkin workspace with dry-run first
  - install by copy or symlink only when `--apply` is explicit
  - emit the follow-up `catkin_make`, service import, and gateway node commands
  - keep real `ros1_gateway` profile values in a local copy of `profiles/work_hardware_ros1_gateway.env.template`
- `task_planning/migration/ros1_service_audit.py` and `tools/audit_ros1_gateway_services.py`
  - derive expected `/fleet/{platform_id}/gateway/dry_run` and `/fleet/{platform_id}/gateway/dispatch` service names from the work hardware profile
  - audit a captured `rosservice list` file or run read-only `rosservice list` on the unit/workplace ROS1 environment
  - emit and verify read-only `rosservice type` and `rosservice args` evidence before any `rosservice call`
  - require `TaskCommandJson` service type plus `task_command_json` request arg when `--require-service-signatures` is used
  - confirm the real service names and signatures with a local filled `PLATFORM_BACKEND=ros1_gateway` profile before any real dispatch

## Artifact Bundle Contract

Every profiled run writes:

```text
environment_profile.json
mission_input.json
model_output.json
task_schema.json
validation_report.json
blackboard_snapshot.json
pddl_problem.pddl
planner_output.json
bt_artifact.json
gateway_trace.json
command_acks.json
task_progress.json
failure_report.json
replan_decision.json
run_summary.md
```

These files are the migration bridge between:

- home model-lab output comparison
- server replay/simulation
- work hardware validation

## Current Commands

### Operator Migration Path

Use this order when moving from this development checkout to another server or to the unit/workplace machine:

1. On any development machine, run `dev_mock` readiness, tests, and the full golden suite.
2. Build the migration bundle and package any mission/model-lab artifact folders with `tools/package_task_planning_artifacts.py`.
3. On the receiving machine, run `tools/verify_task_planning_migration_bundle.py --verification-context receiving_machine` before using the transferred copy.
4. On the unit/workplace receiving machine, run `tools/verify_task_planning_artifacts.py --verification-context unit_workplace_receiving > <artifact_package_verification.json>` on any transferred artifact package before replaying schemas.
5. On the unit/workplace receiving machine, run `tools/check_task_planning_site_acceptance.py` so another agent can see the current lane evidence in one JSON report.
6. Run `tools/collect_distributed_fleet_evidence.py --output-dir <evidence-dir>` to create a standard local baseline evidence folder for handoff.
7. Run `tools/package_distributed_fleet_handoff.py --output-dir <handoff-output-dir>` when you need a single tarball for another machine or agent interface.
8. On the receiving machine, run `tools/verify_distributed_fleet_handoff_package.py <handoff.tar.gz> --verification-context receiving_machine > <evidence-dir>/reports/handoff_package_verification.json` before trusting the handoff package contents; this report can satisfy migration transfer proof because it verifies the embedded migration bundle and rejects `case_id` drift across handoff, evidence, and external-requirements manifests.
9. Run `tools/init_external_evidence_handoff.py --evidence-dir <evidence-dir>` if you need to refresh the external-proof target paths and next commands for another agent.
10. Run `tools/import_distributed_fleet_external_evidence.py --evidence-dir <evidence-dir> ... --artifact-package <artifact-package.tar.gz> --artifact-package-verification-report <artifact_package_verification.json>` when real external reports/packages arrive from home/server/unit machines.
11. Run `tools/check_distributed_fleet_phase_gate.py --evidence-dir <evidence-dir> --print-discovered-inputs` when you only need the local-freeze / next-phase decision, then run `tools/check_distributed_fleet_goal_evidence.py --evidence-dir <evidence-dir>` for the full report. For handoff, add `--missing-only --print-discovered-inputs` to the full goal evidence command.
12. Run `tools/run_task_planning_lane_matrix.py` to prove `dev_mock`, `server_sim`, and `work_hardware` pre-dispatch artifacts remain comparable without model or hardware dependencies.
13. If the receiving machine is a server simulation lane, run `server_sim` golden and compare artifacts with `tools/replay_task_planning_artifact.py`.
14. If the receiving machine is the home 5090 model lab, run only `tools/check_model_lab_endpoint.py`, `tools/evaluate_model_lab_case.py`, artifact packaging, and artifact comparison; keep `PLATFORM_BACKEND=mock`.
15. If copying model-lab output to the unit/workplace lane, first verify the artifact package and site acceptance, then run `tools/run_prevalidated_task_schema.py --profile profiles/work_hardware.env --task-schema <verified_package>/artifacts/<model_lab>/model_task_schema.json --case <lane-matrix-case-id>` before any real gateway profile is used.
16. Extract any later bench-dry-run command with `tools/extract_task_command_from_artifact.py <artifact_bundle_path> --platform-id <platform_id> --format rosservice-yaml`; do not hand-write ROS service payloads.
17. If the receiving machine is the unit/workplace hardware lane, run `tools/check_task_planning_readiness.py --profile profiles/work_hardware.env`, then the staged hardware gate plan, then a mock-gateway golden run.
18. Run `tools/prepare_ros1_gateway_workspace.py --catkin-src <catkin_ws>/src` as a dry-run, then rerun with `--apply` only on the intended unit/workplace catkin workspace.
19. Only after the mock gates pass should the operator copy `profiles/work_hardware_ros1_gateway.env.template` to a local profile, fill real `ROS_MASTER_URI` and `ROS_IP`, and source the intended ROS1 workspace.
20. Run `tools/check_task_planning_site_acceptance.py --run-rosservice-list --run-service-signatures` for the intended platform ids to collect read-only ROS1 service and signature evidence. Real gateway dispatch remains behind `HARDWARE_APPROVAL_REQUIRED=true`.
21. Final hardware execution proof must be returned as a unit/workplace artifact root containing `execution_context=unit_workplace_hardware`, `mission_input.run_input.case_id` matching the OK lane matrix, a successful `/gateway/dispatch` `rosservice` trace, accepted `CommandAck`, and `TaskProgress` matching the same `mission_id` / `task_id` / `platform_id`; bench dry-run and service-signature evidence remain prerequisites, not completion proof.

The home 5090 lane is never part of the hardware execution chain. Its outputs can be copied as artifacts and compared, but the unit/workplace lane must remain runnable with mock/golden schemas when the home server is offline.

To test the local HTTP adapter without the real home model, run a mock endpoint and use the mock endpoint profile. These artifacts verify plumbing only and must not be imported as real home 5090 proof:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_mock_model_lab_endpoint.py --port 8000
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_model_lab_endpoint.py \
  --profile profiles/home_model_lab_mock_endpoint.env
PYTHONDONTWRITEBYTECODE=1 python3 tools/evaluate_model_lab_case.py \
  --profile profiles/home_model_lab_mock_endpoint.env \
  --case uav_ugv_coordination \
  --output-dir /tmp/changxin-model-lab-mock
```

Run all golden mission cases through the mock-first development lane:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_readiness.py \
  --profile profiles/dev_mock.env
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile profiles/dev_mock.env
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_dev_mock_golden_suite.py \
  --artifact-root /tmp/changxin-dev-mock-golden-suite
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_lane_matrix.py \
  --artifact-root /tmp/changxin-lane-matrix \
  --case uav_ugv_coordination
```

Run one case and send artifacts to a temporary or external location:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py \
  --profile profiles/dev_mock.env \
  --case uav_ugv_coordination \
  --artifact-root /tmp/changxin-task-planning-runs
```

Validate a generated artifact bundle:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/replay_task_planning_artifact.py \
  /tmp/changxin-task-planning-runs/<run_id>
```

Compare two artifact bundles, for example `dev_mock` vs `server_sim` or mock vs model-lab output:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/replay_task_planning_artifact.py \
  /tmp/changxin-task-planning-runs/<run_id_a> \
  --compare-to /tmp/changxin-task-planning-runs/<run_id_b>
```

Print the staged unit/work hardware gate plan without executing ROS commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_readiness.py \
  --profile profiles/work_hardware.env
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
  --profile profiles/work_hardware.env
PYTHONDONTWRITEBYTECODE=1 python3 tools/plan_work_hardware_gate.py \
  --profile profiles/work_hardware.env \
  --through-stage mock_gateway_dispatch
```

Prepare the ROS1 service package in the unit/workplace catkin workspace:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py \
  --catkin-src ~/catkin_ws/src
PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py \
  --catkin-src ~/catkin_ws/src \
  --apply
```

Audit ROS1 gateway service names and signatures with read-only commands. The site acceptance tool runs `rosservice` with `ROS_MASTER_URI` and `ROS_IP` from the selected local profile, which avoids accidentally auditing a different ROS master from the ambient shell:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py \
  --profile <local-work-hardware-ros1-gateway.env> \
  --platform-id uav_0 \
  --platform-id ugv_0 \
  --run-rosservice-list \
  --run-service-signatures \
  --require-rosservice-audit \
  --require-service-signatures
```

The generated `rosservice_audit.command_environment_source` records `profile` for this direct collection path without printing the real ROS address.
The generated site acceptance report also records a hashed `machine_id`; goal evidence and external import reject ROS1 signature reports without it.

Smoke-test the home model-lab OpenAI-compatible endpoint without hardware dispatch:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_model_lab_endpoint.py \
  --profile profiles/home_model_lab.env \
  --intent "搜索 A 区并派无人车确认目标"
PYTHONDONTWRITEBYTECODE=1 python3 tools/evaluate_model_lab_case.py \
  --profile profiles/home_model_lab.env \
  --case uav_ugv_coordination \
  --output-dir /tmp/changxin-model-lab
PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_artifacts.py \
  --artifact /tmp/changxin-model-lab/uav_ugv_coordination \
  --output-dir /tmp/changxin-artifact-packages
PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py \
  /path/to/task-planning-artifacts.tar.gz \
  --work-dir /tmp/changxin-artifact-verify \
  --verification-context unit_workplace_receiving \
  > /tmp/changxin-artifact-package-verification.json
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_prevalidated_task_schema.py \
  --profile profiles/work_hardware.env \
  --task-schema /tmp/changxin-model-lab/uav_ugv_coordination/model_task_schema.json \
  --case uav_ugv_coordination \
  --artifact-root /tmp/changxin-prevalidated-runs
PYTHONDONTWRITEBYTECODE=1 python3 tools/extract_task_command_from_artifact.py \
  /tmp/changxin-prevalidated-runs/<run_id> \
  --platform-id uav_0 \
  --format rosservice-yaml > /tmp/changxin-task-command.yaml
```

Exercise the platform-side gateway service core without ROS:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/platform_gateway_service_core.py \
  --mode dry_run \
  --platform-id uav_0 \
  --platform-type uav \
  --capability inspect_area \
  --capability relay_or_overwatch \
  --task-command-json '{"schema":"TaskCommand.v1","mission_id":"mission_001","task_id":"task_001","platform_id":"uav_0","capability":"inspect_area","parameters":{"area_id":"area_A"},"disconnect_policy":"continue_current_task"}'
```

Run the ROS1 platform gateway node inside a sourced catkin workspace:

```bash
PYTHONPATH=/path/to/changxin-code:$PYTHONPATH \
python3 tools/run_ros1_platform_gateway_node.py \
  --platform-id uav_0 \
  --platform-type uav \
  --capability inspect_area \
  --capability relay_or_overwatch \
  --service-symbol platform_gateway_msgs.srv:TaskCommandJson
```

Build a portable migration bundle:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_migration.py \
  --output-dir /tmp/changxin-migration
```

Build a single handoff package for another agent or machine:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/package_distributed_fleet_handoff.py \
  --output-dir /tmp/changxin-handoff-package
PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_distributed_fleet_handoff_package.py \
  /tmp/changxin-handoff-package/distributed-fleet-handoff-package.tar.gz \
  --work-dir /tmp/changxin-handoff-verify \
  --verification-context source_machine
```

Use `--verification-context receiving_machine` only after the handoff package has been transferred to another machine; the verifier rejects receiving-machine proof if the hashed source and verifier machine ids match.

Verify a transferred migration bundle before using it on another machine:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_migration_bundle.py \
  /tmp/changxin-migration/task-planning-migration-bundle.tar.gz \
  --work-dir /tmp/changxin-migration-verify \
  --verification-context receiving_machine
```

Run the phase-1 task-planning tests:

```bash
python3 -m unittest discover tests/task_planning
```

Run the full Python compile gate for this slice:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
roots = [Path('task_planning'), Path('platform_gateway'), Path('tests/task_planning'), Path('tools')]
for root in roots:
    for path in root.rglob('*.py'):
        compile(path.read_text(encoding='utf-8'), str(path), 'exec')
print('syntax_ok')
PY
```

## Remaining Work

- Copy or symlink `platform_gateway/ros/catkin_pkg/platform_gateway_msgs` into the actual unit/workplace catkin workspace, run `catkin_make`, and verify `tools/run_ros1_platform_gateway_node.py` can import `platform_gateway_msgs.srv:TaskCommandJson`.
- Confirm the actual ROS1 service names on the unit/workplace platform gateways, then align `ROS_GATEWAY_*_SERVICE_TEMPLATE` if the defaults differ.
- On the unit/workplace execution endpoint, import a real hardware dispatch artifact only after it contains successful `/gateway/dispatch` trace evidence, accepted ack, and task progress; do not count dry-run-only artifacts as completion.
- Run the model-lab endpoint smoke test against the real home 5090 Qwen endpoint once it exists, then compare its artifacts against `dev_mock` golden outputs.
- Move the generated migration bundle to another server or the unit/workplace laptop and run `tools/verify_task_planning_migration_bundle.py --verification-context receiving_machine` there.
