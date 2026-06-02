import json
import tempfile
import unittest
from pathlib import Path

from task_planning.migration import REQUIRED_GOLDEN_CASE_IDS, run_dev_mock_golden_suite


class GoldenSuiteTest(unittest.TestCase):
    def test_dev_mock_golden_suite_runs_every_required_case_with_artifacts(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            report = run_dev_mock_golden_suite(
                repo_root=repo_root,
                artifact_root=Path(tmp) / "golden-suite",
            )

            self.assertTrue(report.ok, report.as_dict())
            self.assertEqual(list(REQUIRED_GOLDEN_CASE_IDS), [result.case_id for result in report.case_results])
            by_case = {result.case_id: result for result in report.case_results}
            self.assertEqual("replan_requested", by_case["failure_and_replan"].status)
            self.assertEqual("REQUEST_REPLAN", by_case["failure_and_replan"].current_state)
            for result in report.case_results:
                self.assertTrue(result.artifact_bundle_path.exists())
                environment = json.loads((result.artifact_bundle_path / "environment_profile.json").read_text(encoding="utf-8"))
                execution_events = json.loads((result.artifact_bundle_path / "execution_events.json").read_text(encoding="utf-8"))
                event_types = [event["event_type"] for event in execution_events["items"]]
                self.assertEqual("dev_mock", environment["mission_profile"])
                self.assertEqual("mock", environment["platform_backend"])
                self.assertEqual("ExecutionEventLog.v1", execution_events["schema"])
                self.assertIn("bt_runtime_completed", event_types)
                if result.case_id == "failure_and_replan":
                    self.assertIn("central_replan_requested", event_types)


if __name__ == "__main__":
    unittest.main()
