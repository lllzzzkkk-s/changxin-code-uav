# Phase 2B Operator View Signals

Date: 2026-06-03

## Scope

This spec defines the Phase 2B data signals that an operator-facing view may
display from no-hardware task-planning artifacts.

It does not implement Qt, ROS, gateway lifecycle control, gateway `dry_run`,
gateway `dispatch`, or controlled motion. It only names the data that can be
shown after `Phase2NoMotionAcceptanceReport.v1` and
`ArtifactReplayDiagnosticSummary.v1` are generated.

## Allowed Data

The operator view may display these schema-backed records:

- `Phase2NoMotionAcceptanceReport.v1`
- `ArtifactReplayDiagnosticSummary.v1`
- `ExecutionEventLog.v1`
- `OperatorApprovalState.v1`
- `CommandAckSet.v1`
- `TaskProgressSet.v1`
- `ValidationReport.v1`
- `FailureReport.v1`
- `ReplanRequest.v1`

The view may display values from these artifact files:

- `environment_profile.json`
- `mission_input.json`
- `validation_report.json`
- `bt_artifact.json`
- `command_acks.json`
- `task_progress.json`
- `execution_events.json`
- `failure_report.json`
- `replan_decision.json`
- `run_summary.md`

## Forbidden Controls

The operator view may display `/cmd_vel`, `/move_base`, `/mavros/*`, or
`/setpoints_cmd` only as forbidden-token diagnostics. It must not publish, call,
construct, template, queue, or send those controls.

The view must not:

- publish ROS topics
- call ROS services
- call ROS actions
- source a ROS workspace
- instantiate `Ros1ServiceGateway`
- invoke `rosservice`, `rostopic`, or `rosnode`
- call `/fleet/{platform_id}/gateway/dry_run`
- call `/fleet/{platform_id}/gateway/dispatch`
- convert model output directly into ROS commands
- create platform-local missions or PDDL plans

## No-Motion Acceptance Fields

Display these fields from `Phase2NoMotionAcceptanceReport.v1`:

- `ok`
- `generated_at`
- `phase1_baseline.archive_path`
- `phase1_baseline.sha256`
- `phase1_baseline.verified_by_this_report`
- `phase2_run.artifact_roots`
- `phase2_run.current_states`
- `artifact_health.ok`
- `runtime_summary.event_counts`
- `runtime_summary.accepted_commands`
- `runtime_summary.rejected_commands`
- `runtime_summary.progress_count`
- `no_motion_boundary.platform_backend`
- `no_motion_boundary.ros_connected`
- `no_motion_boundary.dispatch_performed`
- `no_motion_boundary.hardware_proof`
- `no_motion_boundary.controlled_motion_authorized`
- `validation_errors`

The view should treat any `validation_errors` entry as a review-required state,
not as permission to proceed to hardware.

## Approval Fields

Display these fields from `OperatorApprovalState.v1` and the acceptance report:

- `approval_summary.required`
- `approval_summary.source`
- `approval_summary.event_count`
- `required`
- `approved`
- `source`
- `mission_id`
- `task_id`
- `platform_id`
- `target_id`
- `approved_at`
- `expires_at`
- `operator_note`

If approval is required but not approved, show the state as a hold. Do not
present a control that can approve hardware work from this Phase 2B view.

## Failure And Replan Fields

Display these fields from `ArtifactReplayDiagnosticSummary.v1`:

- `ok`
- `artifact_root`
- `current_state`
- `event_counts`
- `accepted_commands`
- `rejected_commands`
- `progress_count`
- `failure_report`
- `replan_requested`
- `approval_required`
- `validation_errors`

If `replan_requested` is true, the view may show the central-replan request and
the failure reason. It must not let a platform create a local replacement plan.

## Future Qt Integration Notes

A future Qt view can use the Phase 2B reports as a read-only data model.

Recommended widgets:

- run identity table for Phase 1 baseline and Phase 2 artifact roots
- event-count summary
- command ack list
- task progress list
- approval state panel
- validation error panel
- forbidden-token diagnostics panel

The first Qt implementation should load static JSON files from a selected
artifact or report directory. It should not start ROS processes, discover ROS
graphs, or expose motion buttons.
