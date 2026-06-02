import tempfile
import unittest
from pathlib import Path

from task_planning.migration.lane_matrix import run_lane_matrix


class LaneMatrixTest(unittest.TestCase):
    def test_lane_matrix_runs_same_case_across_mock_server_and_work_pre_dispatch(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            report = run_lane_matrix(
                repo_root=repo_root,
                artifact_root=Path(tmp) / "lane-matrix",
                case_id="uav_ugv_coordination",
            )

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual({"dev_mock", "server_sim", "work_hardware"}, {run.lane for run in report.runs})
        by_lane = {run.lane: run for run in report.runs}
        self.assertEqual("dry_run_complete", by_lane["dev_mock"].status)
        self.assertEqual("dry_run_complete", by_lane["server_sim"].status)
        self.assertEqual("approval_required", by_lane["work_hardware"].status)
        comparisons = {comparison.name: comparison for comparison in report.comparisons}
        self.assertTrue(comparisons["dev_mock_vs_server_sim"].equivalent)
        self.assertEqual("exact", comparisons["dev_mock_vs_server_sim"].mode)
        self.assertTrue(comparisons["dev_mock_vs_work_hardware_pre_dispatch"].equivalent)
        self.assertEqual("pre_dispatch_compatible", comparisons["dev_mock_vs_work_hardware_pre_dispatch"].mode)

    def test_lane_matrix_subset_only_compares_available_lanes(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            report = run_lane_matrix(
                repo_root=repo_root,
                artifact_root=Path(tmp) / "lane-matrix",
                case_id="uav_ugv_coordination",
                lanes=["dev_mock"],
            )

        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual(["dev_mock"], [run.lane for run in report.runs])
        self.assertEqual([], report.comparisons)


if __name__ == "__main__":
    unittest.main()
