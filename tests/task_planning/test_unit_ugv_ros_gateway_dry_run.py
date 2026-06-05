import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from task_planning.migration.unit_ugv_ros_gateway_dry_run import (
    parse_unit_ugv_ros_gateway_dry_run_response_stdout,
    run_unit_ugv_ros_gateway_dry_run,
)


class UnitUgvRosGatewayDryRunTest(unittest.TestCase):
    def test_runner_calls_only_dry_run_service_from_ros_ready_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            handoff_path = _write_handoff(tmp_path)
            calls = []

            def fake_runner(command):
                calls.append(list(command))
                response = {
                    "schema": "GatewayServiceResponse.v1",
                    "mode": "dry_run",
                    "platform_id": "ugv_0",
                    "motion_attempted": False,
                    "raw_ros_publish_attempted": False,
                    "ack": {
                        "schema": "CommandAck.v1",
                        "mission_id": "mission_monitor",
                        "task_id": "task_002",
                        "platform_id": "ugv_0",
                        "accepted": True,
                        "reason": "unit_ugv_dry_run_ok",
                        "local_check": {"motion_attempted": False},
                    },
                }
                return subprocess.CompletedProcess(command, 0, json.dumps(response), "")

            report = run_unit_ugv_ros_gateway_dry_run(
                handoff_report_path=handoff_path,
                output_dir=tmp_path / "dry_run",
                command_runner=fake_runner,
            )
            self.assertTrue(Path(report.files["dry_run_response_stdout"]).exists())
            self.assertTrue(Path(report.files["dry_run_response_parsed"]).exists())
            self.assertTrue(Path(report.files["dry_run_report"]).exists())

        self.assertTrue(report.ok, report.validation_errors)
        self.assertEqual("UnitUgvRosGatewayDryRun.v1", report.schema)
        self.assertEqual("UnitUgvObjectApproachRosReadyHandoff.v1", report.handoff_schema)
        self.assertEqual("/fleet/ugv_0/gateway/dry_run", report.service_name)
        self.assertEqual("ugv_0", report.platform_id)
        self.assertTrue(report.dry_run_called)
        self.assertFalse(report.dispatch_called)
        self.assertFalse(report.rostopic_pub)
        self.assertFalse(report.controlled_motion_authorized)
        self.assertEqual(0, report.returncode)
        self.assertEqual("GatewayServiceResponse.v1", report.response_schema)
        self.assertEqual("dry_run", report.response_mode)
        self.assertTrue(report.ack_accepted)
        self.assertEqual("unit_ugv_dry_run_ok", report.ack_reason)
        self.assertFalse(report.motion_attempted)
        self.assertFalse(report.raw_ros_publish_attempted)
        self.assertEqual(1, len(calls))
        self.assertEqual("rosservice", calls[0][0])
        self.assertEqual("call", calls[0][1])
        self.assertEqual("/fleet/ugv_0/gateway/dry_run", calls[0][2])
        self.assertIn("task_command_json", calls[0][3])
        self.assertIn("task_002", calls[0][3])

    def test_runner_refuses_non_ros_ready_handoff_without_calling_rosservice(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            handoff_path = _write_handoff(tmp_path, ros_ready=False)
            calls = []

            report = run_unit_ugv_ros_gateway_dry_run(
                handoff_report_path=handoff_path,
                output_dir=tmp_path / "dry_run",
                command_runner=lambda command: calls.append(list(command)),
            )

        self.assertFalse(report.ok)
        self.assertIn("handoff report must have ros_ready=true", report.validation_errors)
        self.assertFalse(report.dry_run_called)
        self.assertFalse(report.dispatch_called)
        self.assertEqual([], calls)

    def test_runner_parses_rosservice_response_json_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            handoff_path = _write_handoff(tmp_path)

            def fake_runner(command):
                response = {
                    "schema": "GatewayServiceResponse.v1",
                    "mode": "dry_run",
                    "platform_id": "ugv_0",
                    "motion_attempted": False,
                    "raw_ros_publish_attempted": False,
                    "ack": {
                        "schema": "CommandAck.v1",
                        "mission_id": "mission_monitor",
                        "task_id": "task_002",
                        "platform_id": "ugv_0",
                        "accepted": True,
                        "reason": "unit_ugv_dry_run_ok",
                        "local_check": {},
                    },
                }
                stdout = f"response_json: {json.dumps(json.dumps(response), ensure_ascii=False)}\n"
                return subprocess.CompletedProcess(command, 0, stdout, "")

            report = run_unit_ugv_ros_gateway_dry_run(
                handoff_report_path=handoff_path,
                output_dir=tmp_path / "dry_run",
                command_runner=fake_runner,
            )

        self.assertTrue(report.ok, report.validation_errors)
        self.assertEqual("GatewayServiceResponse.v1", report.response_schema)
        self.assertTrue(report.ack_accepted)

    def test_response_stdout_parser_handles_yaml_folded_response_json_without_ros_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            stdout_path = tmp_path / "dry_run_response.txt"
            stdout_path.write_text("""response_json: >-
  {"schema": "GatewayServiceResponse.v1",
   "mode": "dry_run",
   "platform_id": "ugv_0",
   "motion_attempted": false,
   "raw_ros_publish_attempted": false,
   "ack": {"schema": "CommandAck.v1", "accepted": true, "reason": "unit_ugv_dry_run_ok"}}
""", encoding="utf-8")

            report = parse_unit_ugv_ros_gateway_dry_run_response_stdout(
                response_stdout_path=stdout_path,
                output_dir=tmp_path / "parsed",
                expected_platform_id="ugv_0",
            )

        self.assertTrue(report.ok, report.validation_errors)
        self.assertFalse(report.dry_run_called)
        self.assertEqual([], report.command)
        self.assertEqual("GatewayServiceResponse.v1", report.response_schema)
        self.assertEqual("dry_run", report.response_mode)
        self.assertTrue(report.ack_accepted)
        self.assertEqual("unit_ugv_dry_run_ok", report.ack_reason)
        self.assertFalse(report.motion_attempted)
        self.assertFalse(report.raw_ros_publish_attempted)

    def test_response_stdout_parser_handles_wrapped_escaped_response_json_without_ros_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            response = {
                "schema": "GatewayServiceResponse.v1",
                "mode": "dry_run",
                "platform_id": "ugv_0",
                "motion_attempted": False,
                "raw_ros_publish_attempted": False,
                "ack": {
                    "schema": "CommandAck.v1",
                    "accepted": True,
                    "reason": "unit_ugv_dry_run_ok",
                },
            }
            encoded = json.dumps(json.dumps(response), ensure_ascii=False)
            midpoint = len(encoded) // 2
            stdout_path = tmp_path / "dry_run_response.txt"
            stdout_path.write_text(
                "response_json: " + encoded[:midpoint] + "\n  " + encoded[midpoint:] + "\n",
                encoding="utf-8",
            )

            report = parse_unit_ugv_ros_gateway_dry_run_response_stdout(
                response_stdout_path=stdout_path,
                output_dir=tmp_path / "parsed",
                expected_platform_id="ugv_0",
            )

        self.assertTrue(report.ok, report.validation_errors)
        self.assertFalse(report.dry_run_called)
        self.assertEqual("GatewayServiceResponse.v1", report.response_schema)
        self.assertTrue(report.ack_accepted)


def _write_handoff(tmp: Path, *, ros_ready: bool = True) -> Path:
    payload_path = tmp / "task_command.rosservice.json"
    task_command = {
        "schema": "TaskCommand.v1",
        "mission_id": "mission_monitor",
        "task_id": "task_002",
        "platform_id": "ugv_0",
        "capability": "confirm_target",
        "parameters": {"target_id": "target_01"},
        "preconditions": {"localization_ok": True, "min_battery_percentage": 0.3},
        "abort_policy": "hold_position",
        "disconnect_policy": "continue_current_task",
        "timeout_s": 180,
        "requires_operator_confirm": False,
    }
    payload_path.write_text(json.dumps({
        "task_command_json": json.dumps(task_command, ensure_ascii=False, sort_keys=True),
    }, ensure_ascii=False), encoding="utf-8")
    handoff_path = tmp / "ros_ready_handoff_report.json"
    handoff_path.write_text(json.dumps({
        "schema": "UnitUgvObjectApproachRosReadyHandoff.v1",
        "ok": True,
        "ros_ready": ros_ready,
        "next_runtime_stage": "4060_ros1_gateway_dry_run",
        "platform_id": "ugv_0",
        "service_name": "/fleet/ugv_0/gateway/dry_run",
        "files": {
            "prep_bundle_report": str(tmp / "prep_bundle_report.json"),
        },
        "gateway_dry_run_plan": {
            "schema": "UnitUgvGatewayCallPlan.v1",
            "ok": True,
            "mode": "dry_run",
            "platform_id": "ugv_0",
            "service_name": "/fleet/ugv_0/gateway/dry_run",
            "payload_file": str(payload_path),
        },
    }, ensure_ascii=False), encoding="utf-8")
    return handoff_path


if __name__ == "__main__":
    unittest.main()
