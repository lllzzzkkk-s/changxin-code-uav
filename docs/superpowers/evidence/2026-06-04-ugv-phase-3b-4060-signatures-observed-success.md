# UGV Phase 3B 4060 Signatures Observed Success

Date: 2026-06-04

Source: user-pasted 4060 Codex reply.

Evidence classification:
`reported_by_unit_4060_codex_not_reverified_by_mac`.

## Summary

The unit 4060 Codex retried Phase 3B Stage 4 after the UGV ROS master was
restored. The gateway wrapper started, registered the expected services,
read-only service-signature verification passed, and the wrapper was stopped
after capture.

Result:

```text
tcp_connect=OK
gateway_wrapper_started=true
wrapper_alive_for_capture=true
stopped_after_capture=true
TaskPlanningSiteAcceptance.v1 ok=true
acceptance_level=work_hardware_ros1_signatures_observed
```

This closes the Phase 3B read-only signature objective. It does not prove
gateway `dry_run`, gateway `dispatch`, controlled motion, or hardware execution.

## Git And Repo State

4060 reported:

```text
git log -2 --oneline
e2b3e1c docs: record phase3b master preflight block
48d9544 docs: record phase3b gateway build

git status --short
<empty>
```

## ROS Preflight

4060 reported:

```text
ROS_MASTER_URI=http://192.168.0.201:11311
ROS_IP=172.20.26.179
ROS_HOSTNAME=
parsed_ros_master_host=192.168.0.201
parsed_ros_master_port=11311
tcp_connect=OK
```

## Wrapper Lifecycle

4060 reported:

```text
pid=2151
pid_file=/tmp/changxin-phase3b-gateway-wrapper.pid
log=/tmp/changxin-phase3b-gateway-wrapper.log
state=/tmp/changxin-phase3b-gateway-wrapper-state.json
wrapper_alive_for_capture=true
stopped_after_capture=true
final_wrapper_returncode=0
state_sha256=4ed3138ba8b0cd1a0a3620c3a849b99c5c9663fc5b8ebfeec1b501220ac96f90
log_sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
pid_sha256=f75bc0fa00798d5d2b0f1f2f6e58a968c0e0e0c207c4afc1b0ff8af366f13ac4
```

## Verifier Result

4060 reported:

```text
json=/tmp/changxin-phase3b-site-acceptance-ros1-gateway.json
json_sha256=f3b2e5e621cc719707c266fe2da3419257b95576944fd22e401ec01ab20cb967
rc=0
schema=TaskPlanningSiteAcceptance.v1
ok=true
acceptance_level=work_hardware_ros1_signatures_observed
platform_backend=ros1_gateway
observed_service_count=69
matched_services=[
  /fleet/ugv_0/gateway/dispatch,
  /fleet/ugv_0/gateway/dry_run
]
missing_services=[]
validation_errors=[]
```

## Raw Read-Only Captures

4060 reported:

```text
/tmp/changxin-phase3b-rosservice-list.txt
lines=69
sha256=0a28eedc69c460ecc245f1dc575e42e8dacdbc69cbe80cc3e30629cae989c4a4

/tmp/changxin-phase3b-rosservice-types.txt
sha256=9cbd36b81f559d1f396014fec73af18b05bf37480d38d9a93d869e9ee701be8d
/fleet/ugv_0/gateway/dry_run platform_gateway_msgs/TaskCommandJson
/fleet/ugv_0/gateway/dispatch platform_gateway_msgs/TaskCommandJson

/tmp/changxin-phase3b-rosservice-args.txt
sha256=687fd385dd1e70e8ffba2a3f5da3cd1d8724acb38fa58e1afa3608ac6296f326
/fleet/ugv_0/gateway/dry_run task_command_json
/fleet/ugv_0/gateway/dispatch task_command_json

/tmp/changxin-phase3b-raw-rosservice.rc.json
sha256=7f2db39651f732caf8c6a161ed7656a3cc4808fb215fa1b707b63465b8217572
list/type/args rc all 0
```

## Boundary

4060 reported:

```text
dry_run_called=false
dispatch_called=false
controlled_motion_authorized=false
rostopic_pub=false
repo_architecture_changed=false
non_convex_alpha_docs_touched=false
machine_specific_ros_ip_env_committed=false
```

This Mac-side receipt did not re-run the 4060 checks, did not connect to ROS,
did not inspect the unit `D:\changxin` archive, and did not touch non-convex
alpha documents.

## Interpretation

This receipt proves, as reported by the 4060 side:

- the UGV ROS master was reachable
- the gateway wrapper could start and register services
- `/fleet/ugv_0/gateway/dry_run` was visible
- `/fleet/ugv_0/gateway/dispatch` was visible
- both services used `platform_gateway_msgs/TaskCommandJson`
- both services accepted the `task_command_json` request arg
- the read-only site-acceptance verifier passed
- the wrapper was stopped after evidence capture

This receipt does not prove:

- gateway `dry_run`
- gateway `dispatch`
- controlled motion
- task progress
- final hardware execution proof

## Next Step

The next gate is Phase 3C no-motion gateway `dry_run`. It requires explicit
authorization because it will call `/fleet/ugv_0/gateway/dry_run`, although it
must still be a no-motion service call and must not call dispatch.

Phase 3C should use a validated `TaskCommand.v1` extracted from a prior
artifact and an operator-confirmed `UnitUgvTargetMap.v1` with
`action=manual_confirm`.
