# Windows Qt Sensor Streaming Runbook for OS-mate/YHS UGV

Date: 2026-05-26

This runbook describes how to let a Windows Qt application receive UGV point
cloud and camera data over the same LAN. It is based on the current UGV-1
evidence in this repo and the OS-mate runtime that has been verified on the
vehicle.

## Current UGV Facts

- Vehicle OS: Ubuntu 20.04, ROS1 Noetic.
- Keep one ROS master per vehicle. The Windows/WSL2 machine should connect to
  the vehicle IPC, not to the router management IP or the lidar IP.
- Current navigation entrypoint: `roslaunch yhs_nav yhs_nav.launch`.
- Current 3D lidar evidence:
  - NDT parameter uses `rslidar_points` as lidar topic.
  - Runtime node includes `/rslidar_sdk_node`.
  - Derived scan topics include `/scan`, `/scan1`, `/scan2`, `/scan3`.
- Current camera evidence:
  - Runtime nodes include `/ascamera_hp60c_ln_1` and `/ascamera_hp60c_ln_2`.
  - `/scan1` and `/scan2` are depth-camera-derived `LaserScan` inputs.
  - Raw image/depth topic names should be discovered live per vehicle.

## Recommendation

Do not use raw rosbridge JSON for full-rate point clouds or raw images.

Use this split:

```text
UGV ROS1 master
  -> local downsample/compress bridge
  -> Windows Qt binary/image stream

Small status/control topics:
  optional rosbridge or native ROS client

Large point cloud/camera streams:
  binary TCP/UDP/WebSocket, compressed image, or WSL2 ROS subscriber bridge
```

Rosbridge is useful for quick proof of concept and low-rate status, but it is
inefficient for multi-million-point `sensor_msgs/PointCloud2` because JSON and
base64 expansion create large CPU and bandwidth overhead.

## Network Setup

Use the IPC IP as the endpoint for SSH, ROS, and gateway traffic.

Example convention from the repo docs:

```text
UGV-1 IPC:    192.168.0.121
UGV-1 lidar:  192.168.0.131
UGV-1 router: 192.168.0.111
```

Verify from Windows/WSL2:

```bash
ping 192.168.0.121
ssh yhs@192.168.0.121
```

On the UGV:

```bash
ip addr
ip route
ping 192.168.0.1
ping <lidar-ip>
```

## UGV Side: Start and Discover Topics

Start the existing stack when you want the same sensor set as navigation:

```bash
source /opt/ros/noetic/setup.bash
source ~/catkin_ws/devel/setup.bash

roslaunch yhs_nav yhs_nav.launch
```

In another UGV terminal:

```bash
source /opt/ros/noetic/setup.bash
source ~/catkin_ws/devel/setup.bash

echo "===== point cloud / scan ====="
rostopic list | egrep 'rslidar_points|tmlidar_points|points|scan|cloud'

echo "===== camera ====="
rostopic list | egrep 'ascamera|camera|image|rgb|depth|compressed'

echo "===== known rates ====="
rostopic hz /rslidar_points
rostopic bw /rslidar_points
```

Check a point cloud message:

```bash
timeout 3s rostopic echo -n 1 /rslidar_points/header
timeout 3s rostopic echo -n 1 /rslidar_points/height
timeout 3s rostopic echo -n 1 /rslidar_points/width
timeout 3s rostopic echo -n 1 /rslidar_points/point_step
```

For camera topics, replace the topic after discovery:

```bash
rostopic info <image-topic>
rostopic hz <image-topic>
rostopic bw <image-topic>
```

## Option A: Fast Prototype with Rosbridge

Use this only for small topics or aggressively throttled/compressed streams.

On UGV:

```bash
source /opt/ros/noetic/setup.bash
source ~/catkin_ws/devel/setup.bash

rospack find rosbridge_server || sudo apt install ros-noetic-rosbridge-server
roslaunch rosbridge_server rosbridge_websocket.launch port:=9090
```

Windows Qt connects to:

```text
ws://<ugv-ip>:9090
```

Use rosbridge subscription throttling:

```json
{
  "op": "subscribe",
  "topic": "/scan",
  "type": "sensor_msgs/LaserScan",
  "throttle_rate": 100
}
```

For point clouds, subscribe only to a downsampled/throttled topic:

```json
{
  "op": "subscribe",
  "topic": "/qt/rslidar_points_2hz",
  "type": "sensor_msgs/PointCloud2",
  "throttle_rate": 500,
  "queue_length": 1
}
```

Do not subscribe to full-rate `/rslidar_points` via rosbridge unless the point
count is already very small.

## Option B: WSL2 ROS Subscriber Bridge

This is better than pure Windows ROS, but ROS1 networking must be handled
carefully because ROS nodes need bidirectional TCP connectivity.

In WSL2:

```bash
source /opt/ros/noetic/setup.bash

export ROS_MASTER_URI=http://<ugv-ip>:11311
export ROS_IP=<wsl2-or-lan-reachable-ip>

rostopic list
rostopic echo -n 1 /scan
```

If `rostopic list` works but `rostopic echo` hangs, the UGV cannot connect
back to the WSL2 subscriber. Fix by using Windows 11 WSL2 mirrored networking,
port forwarding, or run the bridge directly on the UGV instead.

Recommended WSL2 role:

```text
WSL2 bridge node:
  subscribes ROS topics
  crops/downsamples/compresses data
  serves Windows Qt over localhost TCP/UDP/WebSocket
```

Windows Qt should not parse huge ROS messages directly if the UI must stay
smooth.

## Option C: Recommended Production Shape

Run a small UGV-side or WSL2-side data gateway:

```text
UGV ROS topics
  /rslidar_points
  /scan
  /camera...
  /chassis_info_fb
        |
        v
sensor_stream_gateway
  - point cloud crop
  - voxel/random downsample
  - frame-rate throttle
  - JPEG/H264 image compression
  - binary frames over TCP/UDP/WebSocket
        |
        v
Windows Qt
```

Suggested ports:

```text
5001 point cloud binary stream
5002 camera 1 compressed stream
5003 camera 2 compressed stream
5004 low-rate status JSON
```

Keep vehicle control separate from sensor streaming. Do not expose arbitrary
`/cmd_vel` or `/smoother_cmd_vel` to the Windows UI.

## Point Cloud Load Control

A 4-million-point cloud is too large for a normal Windows GUI pipeline.

Approximate payload sizes:

```text
100k points  * 16 bytes = 1.6 MB/frame
400k points  * 16 bytes = 6.4 MB/frame
1M points    * 16 bytes = 16 MB/frame
4M points    * 16 bytes = 64 MB/frame before transport overhead
```

With JSON/base64/WebSocket overhead, 4M points can exceed 100 MB per frame.
At several Hz this will stall Windows Qt rendering unless the client is heavily
optimized with binary parsing, GPU buffers, and point-budget culling.

Recommended live UI budgets:

```text
Preview:       50k-150k points, 5-10 Hz
Good live view: 150k-400k points, 3-5 Hz
Heavy inspect: 400k-800k points, 1-2 Hz
Full cloud:    record or on-demand fetch, not continuous UI
```

### Rate Throttle

On UGV:

```bash
source /opt/ros/noetic/setup.bash
source ~/catkin_ws/devel/setup.bash

rosrun topic_tools throttle messages /rslidar_points 2.0 /qt/rslidar_points_2hz
rostopic hz /qt/rslidar_points_2hz
rostopic bw /qt/rslidar_points_2hz
```

This reduces frame rate but not points per frame.

### Prefer 2D Scan When Enough

If the UI only needs obstacle/range visualization, use `/scan` instead of the
raw 3D point cloud:

```bash
rostopic info /scan
rostopic hz /scan
rostopic bw /scan
```

`/scan` is much smaller and already used by `move_base`.

### Reduce Point Count

Use a bridge or PCL filter with these controls:

```text
voxel_leaf_size: 0.05-0.20 m
max_points: 100000-400000 for live UI
rate_hz: 2-5 Hz
range_max: 20-50 m depending on task
z_min/z_max: keep only useful height band
angle_sector: only front or ROI when full 360 is not needed
```

Also inspect lidar driver config for these fields if exposed by the current
driver:

```bash
rosparam list | grep -i rslidar
rosparam get /rslidar_sdk_node/config_path 2>/dev/null || true
find ~/catkin_ws/src -path '*rslidar*' -name '*.yaml' -o -name '*.json'
```

Typical driver-side controls include:

```text
min_distance
max_distance
start_angle
end_angle
dense_points
split_frame_mode / frame rate related settings
```

## Camera Load Control

First discover actual image topics:

```bash
rostopic list | egrep 'ascamera|camera|image|rgb|depth|compressed'
```

Check camera launch/runtime parameters:

```bash
rosparam list | grep ascamera
rosparam get /ascamera_hp60c_ln_1/fps 2>/dev/null || true
rosparam get /ascamera_hp60c_ln_1/rgb_width 2>/dev/null || true
rosparam get /ascamera_hp60c_ln_1/rgb_height 2>/dev/null || true
rosparam get /ascamera_hp60c_ln_1/depth_width 2>/dev/null || true
rosparam get /ascamera_hp60c_ln_1/depth_height 2>/dev/null || true
```

Known launch-like values seen on UGV-1:

```text
rgb_width/rgb_height: 640x480
depth_width/depth_height: 640x320
fps: 15
```

For Windows Qt live view, start with:

```text
RGB: 640x480 at 10-15 FPS, JPEG/H264
Depth: 320x240 or 640x320 at 5-10 FPS
```

If `image_transport` is available, republish compressed images on UGV:

```bash
rospack find image_transport

rosrun image_transport republish raw in:=<raw-image-topic> compressed out:=/qt/cam1/image
```

Then stream `/qt/cam1/image/compressed` or bridge its JPEG payload directly to
Windows Qt.

## Windows Qt Implementation Notes

For high-rate point clouds:

- Use binary transport, not JSON.
- Decode off the UI thread.
- Keep a fixed point budget.
- Store points in GPU buffers/VBOs.
- Drop old frames instead of queueing them.
- Render latest frame only.

Suggested binary point cloud frame:

```text
magic:       4 bytes
version:     uint16
flags:       uint16
stamp_ns:    uint64
frame_id_len:uint16
frame_id:    bytes
point_type:  uint16  # xyz, xyzi, xyzrgb
point_count: uint32
point_step:  uint16
payload_len: uint32
payload:     tightly packed float32 data
```

For camera:

- Prefer JPEG/H264 payloads.
- Decode to `QImage` or GPU texture off the UI thread.
- Keep queue length 1.

## Bring-up Checklist

1. Network:

```bash
ping <ugv-ip>
ssh yhs@<ugv-ip>
```

2. UGV ROS:

```bash
source /opt/ros/noetic/setup.bash
source ~/catkin_ws/devel/setup.bash
rosnode list
rostopic list | egrep 'rslidar|scan|camera|image|ascamera|chassis|imu'
```

3. Measure load:

```bash
rostopic hz /rslidar_points
rostopic bw /rslidar_points
```

4. Start reduced stream:

```bash
rosrun topic_tools throttle messages /rslidar_points 2.0 /qt/rslidar_points_2hz
```

5. Connect WSL2/Qt:

```text
Prototype: ws://<ugv-ip>:9090 via rosbridge, only reduced topics
Production: custom binary gateway, UGV or WSL2 side
```

6. UI safety:

```text
max point budget <= 400k for first live test
camera <= 640x480 at 10-15 FPS
drop stale frames
no direct /cmd_vel exposure
```

## Troubleshooting

`rostopic list` works in WSL2 but `rostopic echo` hangs:

```text
ROS master is reachable, but reverse TCP from UGV to WSL2 is not.
Use WSL2 mirrored networking, port forwarding, or run the data gateway on UGV.
```

Qt freezes:

```text
Lower point count first, then lower frame rate.
Do not let frames queue in Qt.
Use binary parsing and background decode.
```

Point cloud missing:

```bash
rostopic info /rslidar_points
rostopic hz /rslidar_points
rosnode list | grep rslidar
```

Camera missing:

```bash
rosnode list | grep ascamera
rostopic list | egrep 'ascamera|camera|image|depth|rgb'
```

Bandwidth too high:

```text
Use /scan for 2D preview.
Throttle /rslidar_points.
Add voxel/ROI downsample bridge before Windows.
Compress images.
```
