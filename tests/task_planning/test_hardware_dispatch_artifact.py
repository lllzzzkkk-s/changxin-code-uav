import json
import tempfile
import unittest
from pathlib import Path

from task_planning.contracts import TaskSchema
from task_planning.migration import (
    import_external_evidence,
    inspect_hardware_execution_artifact,
    record_unit_hardware_dispatch_artifact,
    run_prevalidated_task_schema,
)


class HardwareDispatchArtifactTest(unittest.TestCase):
    def test_records_unit_dispatch_artifact_from_captured_ack_and_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source_artifact(root / "prevalidated-run")
            profile = _write_ros1_profile(root / "work_hardware_ros1.env")
            progress = [_task_progress()]

            record = record_unit_hardware_dispatch_artifact(
                source_artifact=source,
                profile_path=profile,
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                dispatch_stdout=_dispatch_stdout(),
                task_progress=progress,
                operator_approved=True,
                run_id="unit-run-001",
            )

            self.assertTrue(record.ok, record.as_dict())
            artifact = record.artifact_root
            self.assertTrue(artifact.is_dir())
            inspection = inspect_hardware_execution_artifact(artifact)
            self.assertTrue(inspection["ok"], inspection)
            profile_data = json.loads((artifact / "environment_profile.json").read_text(encoding="utf-8"))
            self.assertEqual("work_hardware", profile_data["mission_profile"])
            self.assertEqual("ros1_gateway", profile_data["platform_backend"])
            self.assertTrue(profile_data["hardware_approval_required"])
            self.assertTrue(profile_data["operator_approved"])
            self.assertEqual("local_unit_operator", profile_data["operator_approval_source"])
            self.assertTrue(profile_data["machine_id"])
            self.assertEqual("unit_workplace_hardware", profile_data["execution_context"])

            _write_lane_matrix_report(root / "evidence" / "reports" / "lane_matrix.json")
            _write_site_ros1_report(
                root / "evidence" / "reports" / "site_acceptance_work_hardware_ros1.json",
                machine_id=profile_data["machine_id"],
            )
            import_report = import_external_evidence(
                evidence_dir=root / "evidence",
                hardware_run_artifacts=[artifact],
            )
            self.assertTrue(import_report.ok, import_report.as_dict())
            self.assertTrue((root / "evidence" / "hardware_artifacts" / "unit-run-001").is_dir())

    def test_records_unit_dispatch_artifact_from_real_prevalidated_run(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema_path = root / "model_task_schema.json"
            schema_path.write_text(json.dumps(_schema().as_dict()), encoding="utf-8")
            prevalidated = run_prevalidated_task_schema(
                profile_path=repo_root / "profiles/work_hardware.env",
                task_schema_path=schema_path,
                artifact_root=root / "prevalidated",
                case_id="uav_ugv_coordination",
            )
            self.assertTrue(prevalidated.ok, prevalidated.as_dict())

            ack = _accepted_ack()
            ack["mission_id"] = "golden_uav_ugv_coordination"
            progress = _task_progress()
            progress["mission_id"] = "golden_uav_ugv_coordination"

            record = record_unit_hardware_dispatch_artifact(
                source_artifact=prevalidated.artifact_bundle_path,
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=ack,
                task_progress=[progress],
                operator_approved=True,
                run_id="unit-run-from-prevalidated",
            )

            self.assertTrue(record.ok, record.as_dict())
            inspection = inspect_hardware_execution_artifact(record.artifact_root)
            self.assertTrue(inspection["ok"], inspection)
            self.assertEqual("uav_ugv_coordination", inspection["evidence"]["case_id"])

    def test_hardware_evidence_summary_counts_only_strict_successful_dispatch_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = record_unit_hardware_dispatch_artifact(
                source_artifact=_write_source_artifact(root / "prevalidated-run"),
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=_accepted_ack(),
                task_progress=[_task_progress()],
                operator_approved=True,
                run_id="unit-run-with-extra-trace",
            )
            self.assertTrue(record.ok, record.as_dict())

            gateway_trace_path = record.artifact_root / "gateway_trace.json"
            gateway_trace = json.loads(gateway_trace_path.read_text(encoding="utf-8"))
            invalid_dispatch = dict(gateway_trace["records"][0])
            invalid_dispatch["service"] = "/fleet/ugv_0/gateway/dispatch"
            invalid_dispatch["platform_id"] = "uav_0"
            gateway_trace["records"].append(invalid_dispatch)
            gateway_trace_path.write_text(json.dumps(gateway_trace, indent=2, sort_keys=True), encoding="utf-8")

            inspection = inspect_hardware_execution_artifact(record.artifact_root)

            self.assertFalse(inspection["ok"], inspection)
            self.assertIn("successful /gateway/dispatch service must match platform_id", "\n".join(inspection["validation_errors"]))
            self.assertEqual(1, inspection["evidence"]["ros1_dispatch_call_count"])
            self.assertEqual(["/fleet/uav_0/gateway/dispatch"], inspection["evidence"]["ros1_dispatch_services"])

    def test_hardware_evidence_summary_reports_common_ack_dispatch_progress_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = record_unit_hardware_dispatch_artifact(
                source_artifact=_write_source_artifact(root / "prevalidated-run"),
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=_accepted_ack(),
                task_progress=[_task_progress()],
                operator_approved=True,
                run_id="unit-run-with-extra-ack-progress",
            )
            self.assertTrue(record.ok, record.as_dict())

            command_acks_path = record.artifact_root / "command_acks.json"
            command_acks = json.loads(command_acks_path.read_text(encoding="utf-8"))
            extra_ack = _accepted_ack()
            extra_ack["task_id"] = "other_task"
            command_acks["items"].append(extra_ack)
            command_acks_path.write_text(json.dumps(command_acks, indent=2, sort_keys=True), encoding="utf-8")

            progress_path = record.artifact_root / "task_progress.json"
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            extra_progress = _task_progress()
            extra_progress["task_id"] = "other_task"
            progress["items"].append(extra_progress)
            progress_path.write_text(json.dumps(progress, indent=2, sort_keys=True), encoding="utf-8")

            inspection = inspect_hardware_execution_artifact(record.artifact_root)

            self.assertFalse(inspection["ok"], inspection)
            errors = "\n".join(inspection["validation_errors"])
            self.assertIn("all accepted CommandAck entries must correspond", errors)
            self.assertIn("all TaskProgress entries must correspond", errors)
            self.assertEqual(2, inspection["evidence"]["accepted_command_ack_count"])
            self.assertEqual(2, inspection["evidence"]["task_progress_count"])
            self.assertEqual(1, inspection["evidence"]["strict_accepted_ack_matches_dispatch_count"])
            self.assertEqual(1, inspection["evidence"]["strict_task_progress_matches_dispatch_count"])
            self.assertEqual(1, inspection["evidence"]["strict_common_ack_dispatch_progress_key_count"])
            self.assertEqual(
                [{"mission_id": "mission_001", "task_id": "task_001", "platform_id": "uav_0"}],
                inspection["evidence"]["strict_common_ack_dispatch_progress_keys"],
            )

    def test_rejects_recording_without_operator_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = record_unit_hardware_dispatch_artifact(
                source_artifact=_write_source_artifact(root / "prevalidated-run"),
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=_accepted_ack(),
                task_progress=[_task_progress()],
                operator_approved=False,
            )

            self.assertFalse(record.ok)
            self.assertIn("operator_approved=true", "\n".join(record.validation_errors))
            self.assertFalse(record.artifact_root.exists())

    def test_rejects_dry_run_service_as_final_dispatch_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = record_unit_hardware_dispatch_artifact(
                source_artifact=_write_source_artifact(root / "prevalidated-run"),
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dry_run",
                command_ack=_accepted_ack(),
                task_progress=[_task_progress()],
                operator_approved=True,
            )

            self.assertFalse(record.ok)
            self.assertIn("/gateway/dispatch", "\n".join(record.validation_errors))

    def test_rejects_non_gateway_dispatch_service_as_final_dispatch_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = record_unit_hardware_dispatch_artifact(
                source_artifact=_write_source_artifact(root / "prevalidated-run"),
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/custom/dispatch",
                command_ack=_accepted_ack(),
                task_progress=[_task_progress()],
                operator_approved=True,
            )

            self.assertFalse(record.ok)
            self.assertIn("/gateway/dispatch", "\n".join(record.validation_errors))

    def test_rejects_progress_for_different_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = _task_progress()
            progress["task_id"] = "other_task"

            record = record_unit_hardware_dispatch_artifact(
                source_artifact=_write_source_artifact(root / "prevalidated-run"),
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=_accepted_ack(),
                task_progress=[progress],
                operator_approved=True,
            )

            self.assertFalse(record.ok)
            self.assertIn("TaskProgress item must match", "\n".join(record.validation_errors))

    def test_rejects_progress_for_different_mission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = _task_progress()
            progress["mission_id"] = "other_mission"

            record = record_unit_hardware_dispatch_artifact(
                source_artifact=_write_source_artifact(root / "prevalidated-run"),
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=_accepted_ack(),
                task_progress=[progress],
                operator_approved=True,
            )

            self.assertFalse(record.ok)
            self.assertIn("TaskProgress item must match", "\n".join(record.validation_errors))

    def test_rejects_failed_prevalidated_source_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source_artifact(root / "prevalidated-run")
            (source / "validation_report.json").write_text(json.dumps({
                "schema": "ValidationReport.v1",
                "status": "failed",
                "errors": ["schema drift"],
                "current_state": "NEEDS_CLARIFICATION",
            }, indent=2, sort_keys=True), encoding="utf-8")

            record = record_unit_hardware_dispatch_artifact(
                source_artifact=source,
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=_accepted_ack(),
                task_progress=[_task_progress()],
                operator_approved=True,
            )

            self.assertFalse(record.ok)
            errors = "\n".join(record.validation_errors)
            self.assertIn("source_artifact validation_report.status must be passed", errors)
            self.assertIn("source_artifact validation_report.errors must be empty", errors)
            self.assertFalse(record.artifact_root.exists())

    def test_rejects_non_work_hardware_source_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source_artifact(root / "dev-run")
            profile = json.loads((source / "environment_profile.json").read_text(encoding="utf-8"))
            profile["mission_profile"] = "dev_mock"
            profile["hardware_approval_required"] = False
            (source / "environment_profile.json").write_text(json.dumps(profile, indent=2, sort_keys=True), encoding="utf-8")

            record = record_unit_hardware_dispatch_artifact(
                source_artifact=source,
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=_accepted_ack(),
                task_progress=[_task_progress()],
                operator_approved=True,
            )

            self.assertFalse(record.ok)
            errors = "\n".join(record.validation_errors)
            self.assertIn("source_artifact must use mission_profile=work_hardware", errors)
            self.assertIn("source_artifact must preserve hardware_approval_required=true", errors)
            self.assertFalse(record.artifact_root.exists())

    def test_rejects_source_artifact_that_already_targets_ros1_gateway(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source_artifact(root / "ros1-source-run")
            profile = json.loads((source / "environment_profile.json").read_text(encoding="utf-8"))
            profile["platform_backend"] = "ros1_gateway"
            (source / "environment_profile.json").write_text(json.dumps(profile, indent=2, sort_keys=True), encoding="utf-8")

            record = record_unit_hardware_dispatch_artifact(
                source_artifact=source,
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=_accepted_ack(),
                task_progress=[_task_progress()],
                operator_approved=True,
            )

            self.assertFalse(record.ok)
            self.assertIn("source_artifact must be a mock/sim pre-dispatch artifact", "\n".join(record.validation_errors))
            self.assertFalse(record.artifact_root.exists())

    def test_rejects_source_artifact_not_waiting_at_operator_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source_artifact(root / "complete-source-run")
            validation = json.loads((source / "validation_report.json").read_text(encoding="utf-8"))
            validation["current_state"] = "COMPLETE"
            (source / "validation_report.json").write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")

            record = record_unit_hardware_dispatch_artifact(
                source_artifact=source,
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=_accepted_ack(),
                task_progress=[_task_progress()],
                operator_approved=True,
            )

            self.assertFalse(record.ok)
            self.assertIn("current_state must be OPERATOR_APPROVAL", "\n".join(record.validation_errors))
            self.assertFalse(record.artifact_root.exists())

    def test_rejects_string_false_command_ack_as_malformed_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ack = _accepted_ack()
            ack["accepted"] = "false"

            record = record_unit_hardware_dispatch_artifact(
                source_artifact=_write_source_artifact(root / "prevalidated-run"),
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=ack,
                task_progress=[_task_progress()],
                operator_approved=True,
            )

            self.assertFalse(record.ok)
            errors = "\n".join(record.validation_errors)
            self.assertIn("CommandAck accepted must be a JSON boolean", errors)
            self.assertIn("CommandAck must be accepted=true", errors)
            self.assertFalse(record.artifact_root.exists())

    def test_rejects_explicit_command_ack_with_wrong_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ack = _accepted_ack()
            ack["schema"] = "NotCommandAck.v1"

            record = record_unit_hardware_dispatch_artifact(
                source_artifact=_write_source_artifact(root / "prevalidated-run"),
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=ack,
                task_progress=[_task_progress()],
                operator_approved=True,
            )

            self.assertFalse(record.ok)
            self.assertIn("CommandAck schema must be CommandAck.v1", "\n".join(record.validation_errors))
            self.assertFalse(record.artifact_root.exists())

    def test_rejects_parsed_command_ack_with_wrong_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ack = _accepted_ack()
            ack["schema"] = "NotCommandAck.v1"

            record = record_unit_hardware_dispatch_artifact(
                source_artifact=_write_source_artifact(root / "prevalidated-run"),
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                dispatch_stdout=_dispatch_stdout(ack),
                task_progress=[_task_progress()],
                operator_approved=True,
            )

            self.assertFalse(record.ok)
            self.assertIn("CommandAck schema must be CommandAck.v1", "\n".join(record.validation_errors))
            self.assertFalse(record.artifact_root.exists())

    def test_rejects_malformed_task_progress_item_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            record = record_unit_hardware_dispatch_artifact(
                source_artifact=_write_source_artifact(root / "prevalidated-run"),
                profile_path=_write_ros1_profile(root / "work_hardware_ros1.env"),
                output_dir=root / "hardware",
                platform_id="uav_0",
                task_id="task_001",
                dispatch_service="/fleet/uav_0/gateway/dispatch",
                command_ack=_accepted_ack(),
                task_progress=["not-a-progress-object"],
                operator_approved=True,
            )

            self.assertFalse(record.ok)
            errors = "\n".join(record.validation_errors)
            self.assertIn("task_progress[0] must be an object", errors)
            self.assertIn("at least one TaskProgress item must match", errors)
            self.assertFalse(record.artifact_root.exists())


def _write_source_artifact(root: Path) -> Path:
    root.mkdir(parents=True)
    task_command = {
        "schema": "TaskCommand.v1",
        "mission_id": "mission_001",
        "task_id": "task_001",
        "platform_id": "uav_0",
        "capability": "inspect_area",
        "parameters": {"area_id": "area_alpha"},
        "preconditions": {"localization_ok": True, "min_battery_percentage": 0.3},
        "abort_policy": "hold_position",
        "disconnect_policy": "continue_current_task",
        "timeout_s": 180,
        "requires_operator_confirm": False,
    }
    json_files = {
        "environment_profile.json": {
            "schema": "EnvironmentProfile.v1",
            "mission_profile": "work_hardware",
            "model_provider": "mock",
            "platform_backend": "mock",
            "hardware_approval_required": True,
        },
        "mission_input.json": {"schema": "MissionInput.v1", "run_input": {"case_id": "uav_ugv_coordination"}},
        "model_output.json": {"schema": "ModelOutput.v1", "output": {}},
        "task_schema.json": {"schema": "TaskSchema.v1", "mission_request": {"mission_id": "mission_001"}},
        "validation_report.json": {"schema": "ValidationReport.v1", "status": "passed", "errors": [], "current_state": "OPERATOR_APPROVAL"},
        "blackboard_snapshot.json": {"schema": "MissionBlackboard.v1"},
        "planner_output.json": {"schema": "PddlPlan.v1", "steps": []},
        "bt_artifact.json": {"schema": "BehaviorTree.v1", "task_commands": [task_command]},
        "gateway_trace.json": {"schema": "GatewayTrace.v1", "records": []},
        "command_acks.json": {"schema": "CommandAckSet.v1", "items": []},
        "task_progress.json": {"schema": "TaskProgressSet.v1", "items": []},
        "failure_report.json": {"schema": "FailureReport.v1", "status": "not_reported"},
        "replan_decision.json": {"schema": "ReplanRequest.v1", "status": "not_requested"},
    }
    for filename, data in json_files.items():
        (root / filename).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    (root / "pddl_problem.pddl").write_text("(define (problem test))\n", encoding="utf-8")
    (root / "run_summary.md").write_text("# Mission Run\n", encoding="utf-8")
    return root


def _schema():
    return TaskSchema.from_intent(
        mission_id="golden_uav_ugv_coordination",
        intent="搜索 A 区，发现目标后派无人车接近确认，无人机继续中继或观察",
        area_id="area_A",
        target_id="target_01",
        context_snapshot={"mission_id": "golden_uav_ugv_coordination"},
    )


def _write_lane_matrix_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": "TaskPlanningLaneMatrix.v1",
        "ok": True,
        "case_id": "uav_ugv_coordination",
        "runs": [
            {"lane": "dev_mock", "ok": True},
            {"lane": "server_sim", "ok": True},
            {"lane": "work_hardware", "ok": True},
        ],
        "comparisons": [
            {"name": "dev_mock_vs_server_sim", "equivalent": True},
            {"name": "dev_mock_vs_work_hardware_pre_dispatch", "equivalent": True},
        ],
    }, indent=2, sort_keys=True), encoding="utf-8")


def _write_site_ros1_report(path: Path, *, machine_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": "TaskPlanningSiteAcceptance.v1",
        "ok": True,
        "machine_id": machine_id,
        "mission_profile": "work_hardware",
        "platform_backend": "ros1_gateway",
        "acceptance_level": "work_hardware_ros1_signatures_observed",
        "readiness": {
            "schema": "EnvironmentReadinessReport.v1",
            "ok": True,
            "mission_profile": "work_hardware",
            "checks": [],
            "failures": [],
            "warnings": [],
            "next_commands": [],
        },
        "hardware_gate": {
            "schema": "HardwareGatePlan.v1",
            "ok": True,
            "requested_stage": "mock_gateway_dispatch",
            "steps": [],
            "validation_errors": [],
        },
        "rosservice_audit": {
            "schema": "Ros1GatewayServiceAudit.v1",
            "ok": True,
            "observed_service_count": 2,
            "matched_services": [
                "/fleet/uav_0/gateway/dry_run",
                "/fleet/uav_0/gateway/dispatch",
            ],
            "missing_services": [],
            "command_environment_source": "captured_files",
            "service_signatures": [
                {
                    "service_name": "/fleet/uav_0/gateway/dry_run",
                    "observed_type": "platform_gateway_msgs/TaskCommandJson",
                    "observed_args": ["task_command_json"],
                    "type_ok": True,
                    "args_ok": True,
                    "errors": [],
                    "warnings": [],
                },
                {
                    "service_name": "/fleet/uav_0/gateway/dispatch",
                    "observed_type": "platform_gateway_msgs/TaskCommandJson",
                    "observed_args": ["task_command_json"],
                    "type_ok": True,
                    "args_ok": True,
                    "errors": [],
                    "warnings": [],
                },
            ],
        },
        "validation_errors": [],
    }, indent=2, sort_keys=True), encoding="utf-8")


def _write_ros1_profile(path: Path) -> Path:
    path.write_text("\n".join([
        "MISSION_PROFILE=work_hardware",
        "MODEL_PROVIDER=mock",
        "MODEL_BASE_URL=",
        "MODEL_NAME=",
        "PLANNER_BACKEND=mock",
        "PLATFORM_BACKEND=ros1_gateway",
        "MISSION_STATE_STORE=json",
        "MISSION_ARTIFACT_ROOT=/tmp/changxin-work-hardware-runs",
        "ROS_MASTER_URI=http://127.0.0.1:11311",
        "ROS_IP=127.0.0.1",
        "HARDWARE_APPROVAL_REQUIRED=true",
        "ROS_GATEWAY_DISPATCH_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dispatch",
        "ROS_GATEWAY_DRY_RUN_SERVICE_TEMPLATE=/fleet/{platform_id}/gateway/dry_run",
    ]), encoding="utf-8")
    return path


def _dispatch_stdout(ack=None) -> str:
    return "response_json: " + json.dumps(json.dumps({
        "schema": "GatewayServiceResponse.v1",
        "mode": "dispatch",
        "platform_id": "uav_0",
        "motion_attempted": True,
        "raw_ros_publish_attempted": False,
        "ack": ack or _accepted_ack(),
    }))


def _accepted_ack():
    return {
        "schema": "CommandAck.v1",
        "mission_id": "mission_001",
        "task_id": "task_001",
        "platform_id": "uav_0",
        "accepted": True,
        "reason": "",
        "local_check": {
            "capability_known": True,
            "localization_ok": True,
            "battery_ok": True,
            "safety_ok": True,
            "motion_attempted": True,
        },
    }


def _task_progress():
    return {
        "schema": "TaskProgress.v1",
        "mission_id": "mission_001",
        "task_id": "task_001",
        "platform_id": "uav_0",
        "status": "completed",
        "progress_ratio": 1.0,
        "message": "unit dispatch completed",
        "observations": {"source": "unit_workplace"},
    }


if __name__ == "__main__":
    unittest.main()
