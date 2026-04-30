# UAV Action Safety Gate Design

Date: 2026-04-30

## Goal

Define the first publish-capable boundary for UAV LLM control without adding a publisher. The gate must decide whether an already compiled dry-run command is eligible for a later publish step, return audit-ready reasons, remain side-effect free, and expose stage profiles that can be tightened from A-stage sim evidence to B/C real-aircraft preparation.

## Non-Goals

- No ROS topic publish.
- No MAVROS service call.
- No arming, set_mode, setpoint, takeoff, land, return-home, or movement execution.
- No bypass of the existing A-stage confirmation gate.
- No real-aircraft authorization.

## Safety Model

The system has three layers:

1. **Dry-run compiler:** `process_command` and `build_dry_run_report` convert intent plus state into a ROS payload candidate and stop at `needs_confirmation`.
2. **Action safety gate:** `evaluate_action_gate` checks whether that dry-run candidate is publish-eligible under strict operator, state, topic, timeout, and rollback requirements. It never publishes.
3. **Publisher adapter:** not implemented in this stage. Any future publisher must consume an `allowed=True` gate decision and still perform a final ROS graph check before publish.

The important migration rule is that A-stage is not a terminal design. A-stage may use sim localization and broader high-level topics to prove the contract, but the same gate API must run with stricter B/C profiles before any bench or real-aircraft action work.

## Stage Profiles

| Profile | Purpose | Localization | Topics | Max relative goal | Timeout |
| --- | --- | --- | --- | --- | --- |
| `a-stage-sim-dry-run` | WSL/headless sim proof and dry-run audit | `sim`, `lio`, `vio` | `/goal`, `/move_base_simple/goal`, `/back_trigger`, `/px4ctrl/takeoff_land` | 1.0 m | 3.0 s |
| `b-stage-bench` | Hardware/bench rehearsal without broad command surface | `lio`, `vio` | `/goal`, `/back_trigger` | 0.5 m | 2.0 s |
| `c-stage-real` | Real-aircraft pre-publish gate | `lio`, `vio` | `/goal` only | 0.3 m | 1.0 s |

Profiles are normal `ActionGateConfig` values. A later publisher must not hard-code policy; it should receive the active profile and preserve the audit fields in the gate decision.

## Topic Classification

| Class | Topics | Policy |
| --- | --- | --- |
| Read-only state | `/mavros/state`, `/mavros/battery`, `/mavros/rc/in`, odometry topics | Query only, no action gate needed |
| High-level action candidate | `/goal`, `/move_base_simple/goal`, `/back_trigger`, `/px4ctrl/takeoff_land` | Eligible only through action gate |
| Low-level command | `/setpoints_cmd` | Deny at action gate |
| MAVROS control | `/mavros/set_mode`, `/mavros/cmd/arming`, `/mavros/setpoint_raw/attitude`, `/mavros/*` control endpoints | Deny at action gate |

## Gate Contract

### Inputs

- `CommandResult` or equivalent mapping from the dry-run compiler.
- `StateSnapshot` with fresh FCU, battery, RC, and localization data.
- `ActionApproval` with:
  - `operator_id`
  - exact `confirmation_phrase`
  - `approved_at`
  - `expires_at`
  - `sim_evidence_id`
  - `rollback_plan_id`
  - `action_summary`
- `requested_timeout_s`
- optional `ActionGateConfig`

### Required Conditions

The gate allows a candidate only when every condition is true:

- Dry-run command status is `needs_confirmation`.
- Dry-run command has not already attempted publish.
- Intent is allowlisted.
- ROS payload exists.
- Topic is allowlisted.
- Topic is not `/setpoints_cmd`.
- Topic is not a `/mavros/*` endpoint.
- FCU, battery, RC, and localization snapshots are fresh.
- FCU is connected.
- FCU mode is `OFFBOARD`.
- Localization source is allowed by the active stage profile. A-stage accepts `sim`, `lio`, or `vio`; B/C reject `sim`.
- Operator confirmation exists.
- Operator confirmation is not expired and not from the future.
- Confirmation phrase exactly matches `CONFIRM {request_id} {intent} {topic}`.
- Operator ID is present.
- Sim evidence ID is present.
- Rollback plan ID is present.
- Action summary is present.
- Requested timeout is positive and within the configured bound.
- Pose payload target Z is within `[0.5, 3.0]` meters.
- Relative goal distance is within the configured bound.

### Output

`ActionGateDecision` returns:

- `allowed`
- `reasons`
- `topic`
- `message_type`
- `publish_attempted=False`
- `audit`

The gate always reports `publish_attempted=False` because it does not publish.

## Implemented Files

- `uav/llm_control/safety/action_gate.py`
- `uav/llm_control/safety/profiles.py`
- `uav/llm_control/safety/__init__.py`
- `uav/llm_control/schemas/models.py`
- `uav/llm_control/core/pipeline.py`
- `tests/uav_llm_control/test_action_safety_gate.py`
- `tests/uav_llm_control/test_pipeline.py`

## Acceptance Matrix

| Requirement | Test |
| --- | --- |
| Confirmed `/goal` dry-run can be marked publish-eligible without publishing | `test_confirmed_goal_payload_is_allowed_without_publish_side_effect` |
| Missing operator confirmation denies | `test_missing_confirmation_rejects_even_when_command_is_ready` |
| `/setpoints_cmd` denies explicitly | `test_rejects_disallowed_low_level_setpoint_topic` |
| Direct MAVROS endpoint denies explicitly | `test_rejects_direct_mavros_endpoint` |
| Stale state denies | `test_rejects_when_state_is_stale_or_not_offboard` |
| Non-OFFBOARD mode denies | `test_rejects_when_state_is_stale_or_not_offboard` |
| Expired approval denies | `test_rejects_expired_confirmation_timeout_and_out_of_bounds_goal` |
| Too-long timeout denies | `test_rejects_expired_confirmation_timeout_and_out_of_bounds_goal` |
| Out-of-bounds Z denies | `test_rejects_expired_confirmation_timeout_and_out_of_bounds_goal` |
| Missing sim evidence and rollback plan deny | `test_rejects_missing_sim_evidence_and_rollback_plan` |
| Too-large relative target denies | `test_rejects_goal_farther_than_action_gate_limit` |
| A/B/C profiles get progressively stricter | `test_stage_profiles_get_stricter_from_a_to_c` |
| A accepts sim localization while C rejects it | `test_real_profile_rejects_sim_source_even_when_a_stage_profile_would_allow_it` |
| B allows return-home candidate while C rejects that surface | `test_bench_profile_allows_return_home_candidate_but_real_profile_rejects_it` |
| C rejects takeoff/land command surface | `test_real_profile_rejects_takeoff_land_command_surface` |
| Dry-run compiler accepts sim localization for A-to-B/C transition testing | `test_move_relative_accepts_sim_localization_for_a_to_bc_transition_testing` |

## Verification Commands

Local:

```bash
python -m unittest tests.uav_llm_control.test_action_safety_gate
python -m unittest tests.uav_llm_control.test_pipeline tests.uav_llm_control.test_ros_adapter_dry_run tests.uav_llm_control.test_action_safety_gate
python -m unittest discover
git diff --check
```

WSL after syncing this module:

```bash
cd ~/changxin-code
source /opt/ros/noetic/setup.bash
source ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/devel/setup.bash
PYTHONPATH="$PWD:${PYTHONPATH:-}" python3 -m unittest \
  tests.uav_llm_control.test_pipeline \
  tests.uav_llm_control.test_ros_adapter_dry_run \
  tests.uav_llm_control.test_action_safety_gate
```

## Next Stage Boundary

The next stage may run the A-stage action gate under the live headless sim graph and record `allowed=True` decisions for dry-run candidates. It still must not publish. B/C work must switch to the stricter profiles before any bench or real-aircraft run. A publisher adapter requires a separate design, a profile selection rule, a final live ROS graph check, and a new sim-first rollback proof.
