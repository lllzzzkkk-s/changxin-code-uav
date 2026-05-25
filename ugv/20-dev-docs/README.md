# UGV Developer Docs

This folder tracks the OS-mate UGV interface inventory. The initial manual
inventory has now been upgraded with one UGV-1 source snapshot and C0/C1 live
runtime evidence from the vehicle at `192.168.0.201`.

Use this script for offline OS/source inventory:

```bash
bash ugv/01-scripts/probe_ugv_readonly.sh --workspace-dir ~/catkin_ws --pack-source
```

Use this script for live read-only runtime graph checks after the nav stack is already running:

```bash
bash ugv/01-scripts/probe_ugv_runtime_readonly.sh --workspace-dir ~/catkin_ws
```

Keep raw vehicle evidence outside git unless explicitly reviewed.

The Mac-side first state adapter is implemented in `ugv/llm_control/state_adapter.py`.
It converts read-only runtime snapshots into `PlatformState.v1` and keeps the
phase-1 motion gate conservative: the gateway reports lock state but never
unlocks the chassis.

The first dry-run task command adapter is implemented in
`ugv/llm_control/command_adapter.py`. It maps `report_state`,
`cancel_navigation`, and gated `navigate_to_pose` requests into structured
reports and ROS instruction descriptions without publishing.
