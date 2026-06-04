# UGV Phase 3A 4060 Workspace Startup Inventory

Date: 2026-06-04

## Evidence Status

This file records a user-pasted reply from the unit RTX 4060 Codex session. The
Mac session did not re-run the 4060 commands, did not access `D:\changxin`, did
not connect to ROS, and did not dispatch.

Machine-readable receipt:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-workspace-startup-inventory.json`

Related earlier Phase 3A evidence:

- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-ros-master-unreachable-receipt.md`
- `docs/superpowers/evidence/2026-06-04-ugv-phase-3a-4060-ros-master-reachability-diagnosis.md`

## 4060 Reported Result

The unit 4060 Codex reported that it completed a read-only workspace/startup
inventory. It did not start `roscore`, did not start a gateway, did not run
`rosservice list`, `rosservice type`, or `rosservice args`, did not run
`rostopic`, did not modify the repo, and did not touch non-convex alpha
documents.

Reported `git log -2 --oneline`:

```text
34cdfcb docs: record ugv phase3a reachability diagnosis
81b88ad docs: record ugv phase3a ros master failure
```

Reported `git status --short`:

```text
<empty>
```

Reported environment summary:

```text
HOME=/home/uavdev
USER=uavdev
pwd=/mnt/d/changxin/changxin-code
```

Generated inventory files:

```text
/tmp/changxin-phase3a-workspace-inventory.txt
101 lines

/tmp/changxin-phase3a-ros-startup-references.txt
5962 lines
```

Reported inventory key findings:

```text
No */devel/setup.bash found under /mnt/d/changxin or /home/uavdev scan roots.
No *.launch or *.service files found by the maxdepth inventory scan.
Found repo scripts:
  /mnt/d/changxin/changxin-code/tools/unit_receiving_wsl2.sh
  /mnt/d/changxin/changxin-code/ugv/01-scripts/probe_ugv_readonly.sh
  /mnt/d/changxin/changxin-code/ugv/01-scripts/probe_ugv_runtime_readonly.sh
  /mnt/d/changxin/changxin-code/uav/01-scripts/*.sh
Found duplicate/home copies:
  /home/uavdev/changxin-code-sync/...
  /home/uavdev/changxin-code/...
Found dependency tree CMake files under:
  /home/uavdev/uav-deps/...
```

Reported startup reference key findings:

```text
Repo references include:
  profiles/work_hardware_ros1_gateway.env.template
  tools/run_ros1_platform_gateway_node.py
  platform_gateway/ros1_service_gateway.py
  platform_gateway/ros1_service_node.py
  platform_gateway/ros1_service_node_template.py

Historical evidence references include prior roscore/roslaunch logs under:
  /home/uavdev/uav-g3*-evidence/...
```

The 4060 Codex noted that `rg` matches include historical logs and docs. Those
are text hits only, not running processes. It also noted that non-convex alpha
docs appear as text-search hits in `docs/非凸α-二开速查台.html`, but were not
modified.

## Boundary

The 4060 Codex reported:

- `ros_process_started=false`
- `service_signature_capture_retried=false`
- `rosservice_list_type_args_run=false`
- `gateway_dry_run_called=false`
- `gateway_dispatch_called=false`
- `controlled_motion_authorized=false`
- `rostopic_list_echo_pub_run=false`
- `repo_architecture_changed=false`
- `non_convex_alpha_docs_touched=false`
- final `git status --short` stayed empty
- WSL emitted the known localhost/NAT startup warning

## What This Proves

This receipt proves the current read-only startup inventory state:

```text
workspace inventory: completed
workspace inventory lines: 101
startup reference lines: 5962
devel/setup.bash under scan roots: not found
launch files under maxdepth scan: not found
service files under maxdepth scan: not found
repo read-only scripts: found
historical ROS logs: found
running ROS/gateway process: not proven
gateway dry_run: no
gateway dispatch: no
controlled motion: no
repo changes: none
```

## What This Does Not Prove

This receipt is not:

- a successful Phase 3A service-signature gate
- proof that gateway services exist
- proof that gateway services do not exist on another ROS master or workspace
- proof that gateway service types or args match the contract
- a gateway `dry_run`
- a gateway `dispatch`
- a hardware proof
- a controlled-motion authorization
- a Mac-side verification of the 4060 filesystem, ROS master, or `D:\changxin`

## Interpretation

Phase 3A remains open. The current blocker is now narrower:

- The 4060 WSL2 session does not expose a ready catkin workspace setup file
  under the scanned roots.
- The inventory did not find launch or service files at the requested depth.
- Repo-side scripts and gateway wrapper code exist, but they are not evidence
  that the unit ROS master/gateway is currently installed, built, sourced, or
  running.
- Historical `uav-g3*` evidence may contain clues, but it is evidence archive
  material, not a live runtime dependency.

The next step requires a local operator decision: either provide the actual unit
ROS workspace/startup path, or explicitly authorize starting/preparing the ROS1
master and gateway environment on the 4060 side.
