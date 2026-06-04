# UGV Phase 3B 4060 Apply Build Authorization Stop

Date: 2026-06-04

Source: user-pasted 4060 Codex reply.

Evidence classification:
`reported_by_unit_4060_codex_not_reverified_by_mac`.

## Summary

The unit 4060 Codex completed UGV Phase 3B Stage 3 apply/build and stopped at
the Stage 4 gateway-wrapper authorization point. It did not start the gateway
wrapper.

Result:

```text
platform_gateway_msgs applied: yes
catkin_make: passed
TaskCommandJson import: passed
gateway wrapper started: no
Stage 4 wrapper-start authorization: still required
```

## Git And Repo State

4060 reported:

```text
git log -2 --oneline
b0b9aa3 docs: record phase3b workspace dry-run
afb1712 docs: record phase3a gateway missing retry

git status --short
<empty>
```

## Apply Result

4060 reported:

```text
/tmp/changxin-phase3b-gateway-workspace-apply.json
schema='Ros1GatewayWorkspacePlan.v1'
ok=True
dry_run=False
installed=True
mode='copy'
repo_root='/mnt/d/changxin/changxin-code'
catkin_src='/home/uavdev/catkin_ws/src'
package_source='/mnt/d/changxin/changxin-code/platform_gateway/ros/catkin_pkg/platform_gateway_msgs'
package_target='/home/uavdev/catkin_ws/src/platform_gateway_msgs'
validation_errors=[]
warnings=[]
sha256=a5ed766d1100cedbaa99eedd840a6cdd05804ca3b217c0dc9780e76b3297eb56
```

## Build Result

4060 reported:

```text
catkin_make_rc=0
catkin_make_log=/tmp/changxin-phase3b-catkin-make.log
sha256=3a02c36a9512710f55651b03c97b6959ca708410f833beec6da6559b8135d0cd
```

## Generated Service Import

4060 reported:

```text
taskcommandjson_import_rc=0
output=<class 'platform_gateway_msgs.srv._TaskCommandJson.TaskCommandJson'>
log=/tmp/changxin-phase3b-taskcommandjson-import.log
log_sha256=85c230f42c84b4fa630f1ff6b9c8ca35eab0ffc32faabb860f930e639716e057
rc_sha256=9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
```

## Boundary

4060 reported:

```text
gateway_wrapper_started=false
/fleet/ugv_0/gateway/dry_run called=false
/fleet/ugv_0/gateway/dispatch called=false
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

- `platform_gateway_msgs` has been copied into the intended catkin workspace
- `catkin_make` completed successfully
- `platform_gateway_msgs.srv.TaskCommandJson` is importable after sourcing the
  built workspace
- Stage 3 apply/build is complete

This receipt does not prove:

- the gateway wrapper starts
- `/fleet/ugv_0/gateway/dry_run` exists
- `/fleet/ugv_0/gateway/dispatch` exists
- service signatures pass
- gateway `dry_run`
- gateway `dispatch`
- controlled motion
- hardware execution proof

## Next Authorization Point

The next action is Phase 3B Stage 4 plus read-only Stage 5 verification, only
after explicit authorization:

```text
Authorize starting the UGV gateway wrapper for service registration only, then
run read-only service-signature verification. Do not call dry_run or dispatch.
Stop or clean up the wrapper after the read-only evidence capture unless the
local operator explicitly keeps it running.
```
