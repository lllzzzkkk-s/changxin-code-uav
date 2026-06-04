# UGV Phase 3D 4060 Pre-Approval Dispatch Rejection Success

Date: 2026-06-04

Source: user-pasted 4060 Codex reply.

Evidence classification:
`reported_by_unit_4060_codex_not_reverified_by_mac`.

## Summary

The unit 4060 Codex completed Phase 3D by calling
`/fleet/ugv_0/gateway/dispatch` exactly once with the gateway wrapper started
without local operator approval. The gateway rejected the dispatch request as
expected before motion or raw ROS publish.

Result:

```text
dispatch_rc=0
dispatch_called_once=true
dispatch_accepted=false
ack_reason=operator approval required for unit UGV dispatch
motion_attempted=false
raw_ros_publish_attempted=false
progress_file_exists=false
wrapper_stopped_after_capture=true
```

This closes the Phase 3D pre-approval dispatch rejection objective. It does not
prove operator-approved dispatch, task progress, controlled motion, or final
hardware execution.

## Git And Repo State

4060 reported:

```text
git log -2 --oneline
3a712da docs: record phase3c dry run success
0db3a39 docs: record phase3b signature success

git status --short
<empty>
```

## Runtime

4060 reported:

```text
ROS_MASTER_URI=http://192.168.0.201:11311
ROS_IP=172.20.26.179
tcp_connect=OK
gateway_wrapper_pid=2699
dispatch_rc=0
dispatch_called_once=true
dispatch_accepted=false
progress_file_exists=false
wrapper_stopped_after_capture=true
```

## Artifacts

4060 reported:

```text
/tmp/changxin-phase3d/input-hashes.json
sha256=f32be686a7b6443ef86a414f73a342262ef583d810a90022da09f312c327a8da

/tmp/changxin-phase3d/validated-input-gate.json
sha256=a03176a126256f8f0312d5b9142fc7936f733db8ff288c9c73aae200cbb5806e

/tmp/changxin-phase3d/gateway-wrapper.log
sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

/tmp/changxin-phase3d/gateway-wrapper-state.json
sha256=e2a72cecd0e656cb3d3885cebd7e0607192782068eff203514c18c51a86b036e

/tmp/changxin-phase3d/gateway-dispatch-reject-response.txt
sha256=435291e805e322be0cba41274fb3860c7228815fbe7c12b42b2f43a3d0d3c096

/tmp/changxin-phase3d/gateway-dispatch-reject-response.parsed.json
sha256=5e5724f9d752aa8afccc7df4b947ad0e8deda99a4352a21edcd9fa66229d79b4

/tmp/changxin-phase3d/gateway-dispatch-reject-response.summary.json
sha256=93300409fac155062421b8fb5a8ae51aa1b414b432e540fecff4860b07465e1f
```

## Parsed Dispatch Response

4060 reported:

```json
{
  "schema": "GatewayServiceResponse.v1",
  "mode": "dispatch",
  "platform_id": "ugv_0",
  "ack_schema": "CommandAck.v1",
  "ack_accepted": false,
  "ack_reason": "operator approval required for unit UGV dispatch",
  "motion_attempted": false,
  "raw_ros_publish_attempted": false,
  "local_check_target_mapped": true,
  "local_check_mapping_operator_confirmed": true,
  "local_check_motion_attempted": false,
  "local_check_raw_ros_publish_attempted": false
}
```

## Boundary

4060 reported:

```text
dispatch_called_once=true
dispatch_accepted=false
wrapper_command_only_used_unit_ugv_target_map=true
wrapper_started_without_unit_ugv_operator_approved=true
wrapper_started_without_unit_ugv_enable_move_base=true
wrapper_started_without_unit_ugv_progress_output=true
move_base_goal=false
controlled_motion_authorized=false
rostopic_pub=false
hand_written_task_command_json=false
repo_architecture_changed=false
non_convex_alpha_docs_touched=false
machine_specific_ros_ip_env_committed=false
```

This Mac-side receipt did not re-run the 4060 checks, did not connect to ROS,
did not inspect the unit `D:\changxin` archive, and did not touch non-convex
alpha documents.

## Interpretation

This receipt proves, as reported by the 4060 side:

- the real ROS1 gateway dispatch path was reachable
- one validated UGV `confirm_target(target_01)` TaskCommand was sent to
  `/fleet/ugv_0/gateway/dispatch`
- the gateway/local executor rejected dispatch before local operator approval
- the rejection reason matched the expected safety gate
- no motion or raw ROS publish was attempted
- no task-progress file was created
- the wrapper was stopped after evidence capture

This receipt does not prove:

- operator-approved dispatch
- manual-confirm dispatch progress
- controlled motion
- final hardware execution proof

## Next Step

The next gate is Phase 3E operator-approved `manual_confirm` dispatch. It
requires explicit authorization because it will call dispatch with
`--unit-ugv-operator-approved`, but it must still use `manual_confirm`, must not
enable `move_base`, and must prove `motion_attempted=false`.
