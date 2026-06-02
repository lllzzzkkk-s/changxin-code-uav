import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from task_planning.mission_ops.run_ledger import (
    JsonMissionRunLedger,
    MissionRunEvent,
    MissionRunRecord,
    OperatorApprovalState,
    validate_operator_approval,
)


class RunLedgerTest(unittest.TestCase):
    def test_ledger_creates_record_and_appends_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = JsonMissionRunLedger(Path(tmp))
            record = MissionRunRecord(
                run_id="run_001",
                case_id="uav_ugv_coordination",
                mission_id="mission_001",
                profile="dev_mock",
                model_provider="mock",
                platform_backend="mock",
                phase_baseline="next_phase_ready",
                artifact_bundle_path="/tmp/changxin/run_001",
                current_state="DISPATCH_OR_HOLD",
            )

            ledger.save(record)
            ledger.append_event("run_001", MissionRunEvent(
                run_id="run_001",
                mission_id="mission_001",
                event_type="bt_runtime_started",
            ))
            restored = ledger.load("run_001")

        self.assertEqual("MissionRunRecord.v1", restored.schema)
        self.assertEqual("next_phase_ready", restored.phase_baseline)
        self.assertEqual("/tmp/changxin/run_001", restored.artifact_bundle_path)
        self.assertEqual(1, len(restored.events))
        self.assertEqual("bt_runtime_started", restored.events[0].event_type)

    def test_operator_approval_scope_and_expiration_are_validated(self):
        now = datetime(2026, 6, 2, 8, 0, tzinfo=timezone.utc)
        good = OperatorApprovalState(
            required=True,
            approved=True,
            source="local_unit_operator",
            mission_id="mission_001",
            task_id="task_002",
            platform_id="ugv_0",
            target_id="target_01",
            approved_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=10)).isoformat(),
            operator_note="manual confirm no-motion check",
        )
        wrong_task = OperatorApprovalState(
            required=True,
            approved=True,
            source="local_unit_operator",
            mission_id="mission_001",
            task_id="task_999",
            platform_id="ugv_0",
            target_id="target_01",
            approved_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=10)).isoformat(),
        )
        expired = OperatorApprovalState(
            required=True,
            approved=True,
            source="local_unit_operator",
            mission_id="mission_001",
            task_id="task_002",
            platform_id="ugv_0",
            target_id="target_01",
            approved_at=(now - timedelta(minutes=20)).isoformat(),
            expires_at=(now - timedelta(minutes=10)).isoformat(),
        )

        self.assertEqual([], validate_operator_approval(
            good,
            mission_id="mission_001",
            task_id="task_002",
            platform_id="ugv_0",
            target_id="target_01",
            now=now,
        ))
        self.assertIn("task scope mismatch", validate_operator_approval(
            wrong_task,
            mission_id="mission_001",
            task_id="task_002",
            platform_id="ugv_0",
            target_id="target_01",
            now=now,
        ))
        self.assertIn("operator approval is stale", validate_operator_approval(
            expired,
            mission_id="mission_001",
            task_id="task_002",
            platform_id="ugv_0",
            target_id="target_01",
            now=now,
        ))


if __name__ == "__main__":
    unittest.main()
