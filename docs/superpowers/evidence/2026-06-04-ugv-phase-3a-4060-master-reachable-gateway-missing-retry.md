# UGV Phase 3A 4060 Master Reachable Gateway Missing Retry

Date: 2026-06-04

Source: user-pasted 4060 Codex reply.

Evidence classification:
`reported_by_unit_4060_codex_not_reverified_by_mac`.

## Summary

The unit 4060 Codex completed the Phase 3A read-only retry after the local
operator started the UGV-side ROS master.

Result:

```text
ROS master TCP reachability: OK
ROS_MASTER_URI: http://192.168.0.201:11311
captured service count: 65
gateway dry_run service: not found
gateway dispatch service: not found
Phase 3A service-signature gate: failed correctly
```

This changes the blocker from "ROS master unreachable" to "gateway wrapper
services are not registered on the reachable UGV ROS master."

## Git And Repo State

4060 reported:

```text
git log -2 --oneline
49f5fb2 docs: plan phase3a master retry
d982994 docs: record ugv phase3a workspace inventory

git status --short
<empty>
```

## ROS Environment And Reachability

4060 reported:

```text
ROS_MASTER_URI=http://192.168.0.201:11311
ROS_IP=
ROS_HOSTNAME=

parsed_ros_master_scheme=http
parsed_ros_master_host=192.168.0.201
parsed_ros_master_port=11311
tcp_connect=192.168.0.201:11311:OK
```

## Read-Only Service Capture

4060 reported:

```text
/tmp/changxin-rosservice-list.txt
service_count=65
sha256=0424826f29ae186bad03c11f398dfe26cd946da16cddea6241ae2fc84a747468
```

Gateway services:

```text
/fleet/*/gateway/dry_run: not found
/fleet/*/gateway/dispatch: not found
/tmp/changxin-gateway-services.txt: 0 lines
```

Because no gateway services were discovered, no service-signature query targets
existed:

```text
/tmp/changxin-rosservice-types.txt: 0 lines
/tmp/changxin-rosservice-args.txt: 0 lines
TYPE_QUERY_COUNT=0
ARGS_QUERY_COUNT=0
```

## Verifier Result

4060 reported:

```text
/tmp/changxin-phase3a-read-only-ros1-signature-retry.json
schema=TaskPlanningSiteAcceptance.v1
ok=False
platform_backend=ros1_gateway
profile_path=/tmp/changxin-work-hardware-ros1-gateway-retry.env
rosservice_audit.observed_service_count=65
rosservice_audit.matched_services=[]
rosservice_audit.missing_services=[
  "/fleet/ugv_0/gateway/dispatch",
  "/fleet/ugv_0/gateway/dry_run"
]
```

Key validation errors:

```text
rosservice_audit:missing_service:/fleet/ugv_0/gateway/dispatch
rosservice_audit:missing_service:/fleet/ugv_0/gateway/dry_run
valid rosservice type/args evidence is required for ROS1 gateway acceptance
```

4060 also reported that `python3 -m json.tool` passed for the retry JSON and
that its final repo status stayed clean.

## Boundary

4060 reported:

```text
dry_run_called=false
dispatch_called=false
controlled_motion_authorized=false
rostopic_publish=false
repo_architecture_changed=false
non_convex_alpha_docs_touched=false
```

This Mac-side receipt did not re-run the 4060 checks, did not connect to ROS,
did not call ROS services, did not inspect the unit `D:\changxin` archive, and
did not touch non-convex alpha documents.

## Interpretation

This receipt proves:

- the intended UGV ROS master at `http://192.168.0.201:11311` is reachable
  from the 4060 WSL2 environment
- a read-only `rosservice list` observed `65` services
- the expected `/fleet/ugv_0/gateway/dry_run` and
  `/fleet/ugv_0/gateway/dispatch` services were absent
- the Phase 3A verifier rejected the gate for the correct reason

This receipt does not prove:

- Phase 3A acceptance
- gateway service signatures
- gateway wrapper startup readiness
- gateway `dry_run`
- gateway `dispatch`
- controlled motion
- hardware execution proof

## Next Step

The next step is Phase 3B gateway lifecycle preparation:

1. Confirm the intended catkin workspace path on the 4060/unit side.
2. Run `tools/prepare_ros1_gateway_workspace.py` dry-run against that path.
3. Apply and build the gateway message package only after explicit operator
   authorization.
4. Start the gateway wrapper only after explicit operator authorization.
5. Re-run Phase 3A read-only service-signature capture after the services are
   registered.

Do not call gateway `dry_run` or `dispatch` in this next step.
