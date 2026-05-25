# UGV Network Bridge Plan

Date: 2026-05-25

Source: `ugv/02-pdf-source/OS-mate-网络配置.pdf`.

## Stable Assumptions

- UGV router starts at `192.168.1.1`, password `12345678`.
- Router is bridged to the main Wi-Fi.
- After bridge, the router receives a management IP under `192.168.0.xxx`.
- Main gateway is `192.168.0.1`.
- 3D lidar setup UI starts at `192.168.1.200`.
- Lidar `Device IP Address` must be moved to `192.168.0.xxx`.
- Lidar `Device IP Gateway` should be `192.168.0.1`.
- Lidar `Destination IP Address` is the UGV IPC address.
- IPC wired IPv4 address must be set to the same value as lidar `Destination IP Address`.

## Fleet Convention

Use one subnet for ground station to vehicle connectivity, while keeping one ROS master per platform.

Suggested address blocks:

| Platform | Router | IPC | Lidar |
|---|---:|---:|---:|
| UGV-1 | `192.168.0.111` | `192.168.0.121` | `192.168.0.131` |
| UGV-2 | `192.168.0.112` | `192.168.0.122` | `192.168.0.132` |
| UGV-3 | `192.168.0.113` | `192.168.0.123` | `192.168.0.133` |

These are conventions, not confirmed live addresses. The live fleet inventory must record actual DHCP reservations and static IPs.

## System Design Impact

- Platform gateway endpoints should target IPC IPs.
- Lidar IPs are sensor configuration endpoints, not control endpoints.
- Router IPs are management endpoints, not ROS endpoints.
- Cross-platform task control remains center PDDL -> task-level BT -> platform gateway -> local ROS1 master.

