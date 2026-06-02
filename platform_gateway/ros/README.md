# ROS1 Platform Gateway Service Contract

This directory defines the minimal ROS1 service contract expected by the ground-station `Ros1ServiceGateway`.

## Service

`srv/TaskCommandJson.srv`

```text
string task_command_json
---
string response_json
```

`task_command_json` must contain `TaskCommand.v1` JSON.

`response_json` must contain `GatewayServiceResponse.v1` JSON produced by `platform_gateway/service_core.py`.

## Suggested Service Names

Per platform:

```text
/fleet/<platform_id>/gateway/dry_run
/fleet/<platform_id>/gateway/dispatch
```

These names match the default profile templates:

```text
ROS_GATEWAY_DRY_RUN_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dry_run
ROS_GATEWAY_DISPATCH_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dispatch
```

## Wrapper Rule

The ROS wrapper should do as little as possible:

1. receive `task_command_json`
2. call `PlatformGatewayServiceCore.dry_run_json(...)` or `dispatch_json(...)`
3. return `response_json`

The wrapper must not accept raw ROS topic names from the center, arbitrary shell commands, or platform-local mission replanning requests.

## Run Node

Use the included minimal catkin package if the target workspace does not already define an equivalent service:

```bash
python3 /path/to/changxin-code/tools/prepare_ros1_gateway_workspace.py --catkin-src ~/catkin_ws/src
python3 /path/to/changxin-code/tools/prepare_ros1_gateway_workspace.py --catkin-src ~/catkin_ws/src --apply
cd ~/catkin_ws
catkin_make
source devel/setup.bash
```

Expected generated symbol:

```text
platform_gateway_msgs.srv:TaskCommandJson
```

Before any `rosservice call`, audit the expected service names with read-only commands:

```bash
rosservice list | tee /tmp/changxin-rosservice-list.txt
PYTHONDONTWRITEBYTECODE=1 python3 /path/to/changxin-code/tools/audit_ros1_gateway_services.py \
  --profile /path/to/changxin-code/profiles/work_hardware.env \
  --platform-id uav_0 \
  --service-list-file /tmp/changxin-rosservice-list.txt
rosservice type /fleet/uav_0/gateway/dry_run
rosservice args /fleet/uav_0/gateway/dry_run
```

For machine-verifiable evidence, capture every expected service type and request arg before dispatch:

```bash
for s in /fleet/uav_0/gateway/dry_run /fleet/uav_0/gateway/dispatch; do printf "%s " "$s"; rosservice type "$s"; done | tee /tmp/changxin-rosservice-types.txt
for s in /fleet/uav_0/gateway/dry_run /fleet/uav_0/gateway/dispatch; do printf "%s " "$s"; rosservice args "$s"; done | tee /tmp/changxin-rosservice-args.txt
PYTHONDONTWRITEBYTECODE=1 python3 /path/to/changxin-code/tools/audit_ros1_gateway_services.py \
  --profile /path/to/changxin-code/profiles/work_hardware.env \
  --platform-id uav_0 \
  --service-list-file /tmp/changxin-rosservice-list.txt \
  --service-type-file /tmp/changxin-rosservice-types.txt \
  --service-args-file /tmp/changxin-rosservice-args.txt \
  --require-service-signatures
```

The expected signature is a `TaskCommandJson` service with request arg `task_command_json`.

After the generated service package is available in the sourced catkin workspace:

```bash
source ~/catkin_ws/devel/setup.bash
PYTHONPATH=/path/to/changxin-code:$PYTHONPATH \
python3 /path/to/changxin-code/tools/run_ros1_platform_gateway_node.py \
  --platform-id uav_0 \
  --platform-type uav \
  --capability inspect_area \
  --capability relay_or_overwatch \
  --service-symbol platform_gateway_msgs.srv:TaskCommandJson
```

Replace `platform_gateway_msgs.srv:TaskCommandJson` with the actual generated service module if the package name differs.
