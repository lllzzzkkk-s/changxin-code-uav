# UGV Phase 3C 4060 No-Motion Dry-Run Success

Date: 2026-06-04

Source: user-pasted 4060 Codex reply.

Evidence classification:
`reported_by_unit_4060_codex_not_reverified_by_mac`.

## Summary

The unit 4060 Codex completed Phase 3C by calling
`/fleet/ugv_0/gateway/dry_run` exactly once through the ROS1 gateway wrapper.
The call used an extracted validated `TaskCommand.v1` from an existing verified
artifact and an operator-confirmed `UnitUgvTargetMap.v1` with
`action=manual_confirm`.

Result:

```text
dry_run_rc=0
GatewayServiceResponse.v1
mode=dry_run
platform_id=ugv_0
CommandAck.v1 accepted=true
ack_reason=unit_ugv_dry_run_ok
motion_attempted=false
raw_ros_publish_attempted=false
wrapper_stopped_after_capture=true
```

This closes the Phase 3C no-motion gateway `dry_run` objective. It does not
prove gateway `dispatch`, controlled motion, task progress, or final hardware
execution.

## Git And Repo State

4060 reported:

```text
git log -2 --oneline
0db3a39 docs: record phase3b signature success
e2b3e1c docs: record phase3b master preflight block

git status --short
<empty>
```

## Runtime Inputs

4060 reported:

```text
artifact_root=/tmp/changxin-phase2b-dev-mock-single/8d783b73-f8f2-488c-9d53-6b3881806784
ROS_MASTER_URI=http://192.168.0.201:11311
ROS_IP=172.20.26.179
tcp_connect=OK
gateway_wrapper_pid=2502
dry_run_rc=0
progress_file_exists=false
wrapper_stopped_after_capture=true
```

## Artifacts

4060 reported:

```text
/tmp/changxin-phase3c/verified_artifact_gate.json
sha256=2a6dbef957f622aa0394d2bf535be74a67de60859956c4c01078ad81bea3d063

/tmp/changxin-phase3c/unit_ugv_targets.manual_confirm.json
sha256=62aac9e2a391793b01ed434eb02b7d52aebcbb4f1eb7e331e74c414a8298740e

/tmp/changxin-phase3c/extracted_task_command.report.json
sha256=bd5b762fe057ed8c12d4c4b354fab6f8f924d288cb43d1b5f6e81eefc59c0d80

/tmp/changxin-phase3c/task_command.rosservice.json
sha256=8c04ce46c3d2f5fde6b57d0335b09d64ebd5f3854bb253f9617f128fe6faf3e5

/tmp/changxin-phase3c/gateway-wrapper.log
sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

/tmp/changxin-phase3c/gateway-wrapper-state.json
sha256=59225e0daac31413e7e081c5d04e12bfcded068340517a435f77f91264aaf792

/tmp/changxin-phase3c/gateway-dry-run-response.txt
sha256=fd70e8320d65bca46ce9e57296a60b03c35f8ee78514b4927a6549aa3ac67b4a

/tmp/changxin-phase3c/gateway-dry-run-response.parsed.json
sha256=5b15d92108ad4f90663d0657be22f8cfde6deedd0c3e9edd6ab20cc33b15cb8d

/tmp/changxin-phase3c/gateway-dry-run-response.summary.json
sha256=148ce31236c013db682d930cce56962a78918119339132cbe2816d7dbffc492a
```

## Parsed Dry-Run Response

4060 reported:

```json
{
  "schema": "GatewayServiceResponse.v1",
  "mode": "dry_run",
  "platform_id": "ugv_0",
  "ack_schema": "CommandAck.v1",
  "ack_accepted": true,
  "ack_reason": "unit_ugv_dry_run_ok",
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
dry_run_called_once=true
dispatch_called=false
wrapper_started_without_unit_ugv_operator_approved=true
wrapper_started_without_unit_ugv_enable_move_base=true
wrapper_started_without_move_base_target_map=true
wrapper_started_without_progress_output=true
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

- the Phase 3B registered gateway `dry_run` service accepted a validated
  UGV `confirm_target(target_01)` TaskCommand
- the command mapped to an operator-confirmed `manual_confirm` target
- the gateway returned `GatewayServiceResponse.v1`
- the gateway returned `CommandAck.v1 accepted=true`
- the local UGV executor reported `unit_ugv_dry_run_ok`
- no motion or raw ROS publish was attempted
- no task-progress file was created
- the wrapper was stopped after evidence capture

This receipt does not prove:

- gateway `dispatch`
- dispatch rejection before approval
- operator-approved manual-confirm dispatch
- controlled motion
- final hardware execution proof

## Next Step

The next gate is Phase 3D pre-approval dispatch rejection. It requires explicit
authorization because it will call `/fleet/ugv_0/gateway/dispatch`, even though
the expected result is rejection before operator approval and no motion.
