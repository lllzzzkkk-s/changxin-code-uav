# Platform Gateway ROS1 Catkin Package

This folder contains a minimal ROS1 package that can be copied or symlinked into a unit/workplace catkin workspace.

```bash
cp -R /path/to/changxin-code/platform_gateway/ros/catkin_pkg/platform_gateway_msgs ~/catkin_ws/src/
cd ~/catkin_ws
catkin_make
source devel/setup.bash
```

Expected generated Python symbol:

```text
platform_gateway_msgs.srv:TaskCommandJson
```

Start a platform gateway node after sourcing the workspace:

```bash
PYTHONPATH=/path/to/changxin-code:$PYTHONPATH \
python3 /path/to/changxin-code/tools/run_ros1_platform_gateway_node.py \
  --platform-id uav_0 \
  --platform-type uav \
  --capability inspect_area \
  --capability relay_or_overwatch \
  --service-symbol platform_gateway_msgs.srv:TaskCommandJson
```

This package only defines the JSON bridge service. Platform-specific local execution remains outside this package and must still pass through `platform_gateway/service_core.py`.
