# UGV Phase 3E 4060 Approved Manual-Confirm Dispatch Success

Date: 2026-06-04

Source: user-pasted 4060 Codex reply.

Evidence classification:
`reported_by_unit_4060_codex_not_reverified_by_mac`.

## Summary

The unit 4060 Codex completed Phase 3E by running one locally approved
`/fleet/ugv_0/gateway/dispatch` call through the ROS1 gateway wrapper with the
UGV target map still set to `manual_confirm`. The gateway accepted the command,
reported `manual_confirm_completed`, wrote `TaskProgressSet.v1`, and preserved
the no-motion boundary.

Result:

```text
dispatch_rc=0
dispatch_called_once=true
dispatch_accepted=true
operator_approved=true
enable_move_base=false
target_action=manual_confirm
progress_file_exists=true
wrapper_stopped_after_capture=true
motion_attempted=false
raw_ros_publish_attempted=false
```

This closes the Phase 3E approved no-motion dispatch/progress objective. It does
not prove `move_base_goal`, controlled motion, or physical navigation.

## Git And Repo State

4060 reported:

```text
git log -2 --oneline
56e354a docs: record phase3d dispatch rejection
3a712da docs: record phase3c dry run success

git status --short
<empty>
```

## Runtime

4060 reported:

```text
ROS_MASTER_URI=http://192.168.0.201:11311
ROS_IP=172.20.26.179
tcp_connect=OK
gateway_wrapper_pid=2932
dispatch_rc=0
dispatch_called_once=true
dispatch_accepted=true
operator_approved=true
enable_move_base=false
target_action=manual_confirm
progress_file_exists=true
wrapper_stopped_after_capture=true
```

## Artifacts

4060 reported:

```text
/tmp/changxin-phase3c/unit_ugv_targets.manual_confirm.json
sha256=62aac9e2a391793b01ed434eb02b7d52aebcbb4f1eb7e331e74c414a8298740e

/tmp/changxin-phase3c/extracted_task_command.report.json
sha256=bd5b762fe057ed8c12d4c4b354fab6f8f924d288cb43d1b5f6e81eefc59c0d80

/tmp/changxin-phase3c/task_command.rosservice.json
sha256=8c04ce46c3d2f5fde6b57d0335b09d64ebd5f3854bb253f9617f128fe6faf3e5

/tmp/changxin-phase3e/gateway-wrapper.log
sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

/tmp/changxin-phase3e/gateway-wrapper-state.json
sha256=4473f63d3837dfc075e90ee7ab31a7f622c19b0e4db11838cb95d3de34a566ee

/tmp/changxin-phase3e/gateway-dispatch-response.txt
sha256=0b65969c2ff4a1e1f432f4e33dd3bbeab8117684d148540563461a16554f82a2

/tmp/changxin-phase3e/gateway-dispatch-response.parsed.json
sha256=e2e848e8d867e45b0090253eb6703df96c246750ed725386b542cbe2d3aae7b4

/tmp/changxin-phase3e/task_progress_after_dispatch.json
sha256=95d38d4e8876e4592bd0ab6d6f58b1c48d359bdad6b42cd625e96287b0ba436f

/tmp/changxin-phase3e/task_progress_after_dispatch.summary.json
sha256=9fda37a26166339b2aee3303227a1868370d1db1bb72006e8751743195783dd1
```

## Parsed Dispatch Response

4060 reported:

```json
{
  "schema": "GatewayServiceResponse.v1",
  "mode": "dispatch",
  "platform_id": "ugv_0",
  "ack_schema": "CommandAck.v1",
  "ack_accepted": true,
  "ack_reason": "manual_confirm_completed",
  "motion_attempted": false,
  "raw_ros_publish_attempted": false,
  "local_check_dispatch_action": "manual_confirm"
}
```

## Progress Summary

4060 reported:

```json
{
  "schema": "TaskProgressSet.v1",
  "item_count": 1,
  "item_schema": "TaskProgress.v1",
  "task_id": "task_002",
  "platform_id": "ugv_0",
  "status": "completed",
  "progress_ratio": 1.0,
  "message": "manual_confirm_completed",
  "observations_target_id": "target_01",
  "observations_unit_ugv_action": "manual_confirm",
  "observations_motion_attempted": false
}
```

## Boundary

4060 reported:

```text
dispatch_called_once=true
dispatch_accepted=true
operator_approved=true
enable_move_base=false
target_action=manual_confirm
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

- the real ROS1 gateway accepted one locally approved UGV dispatch
- the dispatch used an operator-confirmed `manual_confirm` target map
- `--unit-ugv-enable-move-base` was not used
- `GatewayServiceResponse.v1` and `CommandAck.v1` matched the expected accepted
  no-motion response
- `TaskProgressSet.v1` was written for `ugv_0`, `task_002`, `target_01`
- no motion or raw ROS publish was attempted
- the wrapper was stopped after evidence capture

This receipt does not prove:

- `move_base_goal`
- controlled motion
- physical navigation
- a standardized imported goal-evidence artifact

## Next Step

The next gate is Phase 3F no-motion hardware evidence closure. It should not
call ROS again. Instead, the 4060 side should use already captured Phase 3E
response/progress files with `tools/record_unit_hardware_dispatch_artifact.py`
and then run goal-evidence checks against the generated hardware artifact.
