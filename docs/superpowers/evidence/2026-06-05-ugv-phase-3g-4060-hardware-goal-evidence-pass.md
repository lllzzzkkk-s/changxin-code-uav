# UGV Phase 3G 4060 Hardware Goal Evidence Pass

Date: 2026-06-05

This receipt records the Phase 3G same-case/same-machine goal-evidence
alignment result from the 4060 WSL2 unit lane.

The key Phase 3G target passed:

```text
unit_hardware_execution_artifact_verified=pass
```

Overall goal evidence still returned `rc=1 / ok=false`, but the remaining gaps
are unrelated to the UGV Phase 3 hardware artifact:

```text
dev_mock_golden_suite_recorded=missing
migration_bundle_verified_after_transfer=missing
artifact_package_verified_after_transfer=missing
home_5090_model_lab_evaluated=missing
```

## Repo State

```text
git log -2 --oneline
8c42238 docs: plan phase3g evidence alignment
6a54f39 docs: fix phase3f source artifact gate

git status --short
<empty>
```

## Phase 3F Hardware Artifact

```text
root=/tmp/changxin-phase3f/hardware_artifacts/phase3f-ugv0-manual-confirm-dispatch
precheck=/tmp/changxin-phase3f/generated_hardware_artifact_precheck.json
precheck_sha256=4c10c28d12a911cc8504aae60e800d518e0c0a04848dbba69f7a5e04c9a5c555
```

## Same-Case Lane Matrix

```text
path=/tmp/changxin-phase3g/lane_matrix_single_ugv_inspection.json
sha256=3df3245f1f9b499a641ed41e985018473f23cb6ee922d89a299c2a14893bb772
ok=true
case_id=single_ugv_inspection
work_hardware=OPERATOR_APPROVAL
```

## Same-Machine ROS1 Signature

```text
path=/tmp/changxin-phase3g/site_acceptance_ros1_signature_same_machine.json
sha256=70b9d7e45d1132924d7c79d20d796080eb8ba929a05086cd3fb06d4cf57eb5bb
ok=true
acceptance_level=work_hardware_ros1_signatures_observed
machine_id=bbe13c5ea196bdb8dcf4798975edaaa2e949fae1ef414638b263f94e5880537d
matched_services=/fleet/ugv_0/gateway/dry_run, /fleet/ugv_0/gateway/dispatch
type=platform_gateway_msgs/TaskCommandJson
args=task_command_json
wrapper_stopped_after_capture=true
```

## Goal Evidence

```text
summary=/tmp/changxin-phase3g/goal_evidence_same_case_same_machine_summary.json
summary_sha256=e28e11d6ced17f9af547cc58d3a9a948220d04f62abd1db0d3f99bf55a40492b

full=/tmp/changxin-phase3g/goal_evidence_same_case_same_machine_full.json
full_sha256=841b349860b78bcddb66b1f8f6cc7f2adc9a026ae5f7aed0a4c3bb898036bce4

unit_hardware_execution_artifact_verified=pass
```

Interpretation:

- Phase 3F recorder success now counts in the goal-evidence checker.
- Same-case lane matrix evidence for `single_ugv_inspection` is accepted.
- Same-machine ROS1 signature evidence is accepted.
- The hardware artifact dispatch service matches the signed
  `/fleet/ugv_0/gateway/dispatch` service for the same machine id.
- The remaining `ok=false` gaps are global proof-chain inputs outside this UGV
  Phase 3G hardware gate.

## Boundary Confirmation

```text
gateway_dry_run_called=false
gateway_dispatch_called=false
controlled_motion_authorized=false
move_base_used=false
rostopic_pub=false
repo_architecture_changed=false
non_convex_alpha_docs_touched=false
committed_machine_specific_ros_env=false
```
