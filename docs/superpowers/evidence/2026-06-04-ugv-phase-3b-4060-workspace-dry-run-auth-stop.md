# UGV Phase 3B 4060 Workspace Dry-Run Authorization Stop

Date: 2026-06-04

Source: user-pasted 4060 Codex reply.

Evidence classification:
`reported_by_unit_4060_codex_not_reverified_by_mac`.

## Summary

The unit 4060 Codex continued Phase 3B and stopped at the Stage 2 authorization
point. It did not enter Stage 3 `apply/build` and did not start the gateway
wrapper.

Result:

```text
CATKIN_WS=/home/uavdev/catkin_ws
CATKIN_SRC=/home/uavdev/catkin_ws/src
workspace created: yes
devel/setup.bash exists: yes
platform_gateway_msgs installed: no
dry-run ok: true
Stage 3 apply/build authorization: still required
```

## Git And Repo State

4060 reported:

```text
git fetch/pull --ff-only: up to date

git log -2 --oneline
afb1712 docs: record phase3a gateway missing retry
49f5fb2 docs: plan phase3a master retry

git status --short
<empty>
```

## Catkin Workspace State

4060 reported:

```text
CATKIN_WS=/home/uavdev/catkin_ws
CATKIN_SRC=/home/uavdev/catkin_ws/src
/home/uavdev/catkin_ws/devel/setup.bash exists
/home/uavdev/catkin_ws/src contains only the catkin top-level CMakeLists.txt symlink
platform_gateway_msgs not installed yet
```

Workspace creation log:

```text
/tmp/changxin-phase3b-catkin-ws-create.log
sha256=5336378d6ea1f16334ac3d99cf2108ff4e99b4ea7dfdf015b087535a298372a3
```

## Gateway Workspace Dry-Run

4060 reported:

```text
/tmp/changxin-phase3b-gateway-workspace-dry-run.json
schema='Ros1GatewayWorkspacePlan.v1'
ok=True
dry_run=True
installed=False
mode='copy'
catkin_src='/home/uavdev/catkin_ws/src'
validation_errors=[]
warnings=[]
sha256=948c362139e7b5337d5f16b6d8006c512b395b5969bfe695026156bb111a4f62
```

Interpretation:

- The intended catkin workspace now exists on the 4060 side.
- The repository gateway message package source can be planned into
  `/home/uavdev/catkin_ws/src`.
- `platform_gateway_msgs` has not been installed or built yet.
- Phase 3B Stage 3 is ready to request explicit authorization.

## Local Proxy Note

4060 reported that a machine-local proxy file exists at `D:/changxin/.env` with
localhost proxy values for that Codex workdir.

This is recorded only as a reported local machine configuration. It must not be
committed as a repo profile and is not Mac-verified.

## Boundary

4060 reported:

```text
/fleet/ugv_0/gateway/dry_run called: false
/fleet/ugv_0/gateway/dispatch called: false
controlled_motion_authorized=false
rostopic_pub=false
repo_architecture_changed=false
non_convex_alpha_docs_touched=false
machine_specific_ros_ip_env_committed=false
gateway_wrapper_started=false
apply_build_run=false
```

This Mac-side receipt did not re-run the 4060 checks, did not connect to ROS,
did not inspect the unit `D:\changxin` archive, and did not touch non-convex
alpha documents.

## Next Authorization Point

The next action is Phase 3B Stage 3 only:

```text
Authorize installing platform_gateway_msgs into /home/uavdev/catkin_ws/src and
running catkin_make. Do not start the gateway wrapper yet.
```

Stage 4 gateway wrapper startup remains a separate authorization point after
Stage 3 apply/build succeeds.
