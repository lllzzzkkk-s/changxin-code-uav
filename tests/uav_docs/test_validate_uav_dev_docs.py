import csv
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC_ROOT = ROOT / "uav" / "20-dev-docs"

REQUIRED_FILES = [
    DOC_ROOT / "README.md",
    DOC_ROOT / "01-developer-guide.md",
    DOC_ROOT / "02-interface-table.csv",
    DOC_ROOT / "03-feature-deployment-matrix.csv",
    DOC_ROOT / "04-screenshot-state-appendix.md",
    DOC_ROOT / "05-developer-navigation.md",
    DOC_ROOT / "06-evidence-index.csv",
    DOC_ROOT / "07-material-gaps.csv",
    ROOT / "uav" / "01-scripts" / "validate_uav_dev_docs.py",
]

REQUIRED_INTERFACE_COLUMNS = [
    "id",
    "category",
    "name",
    "type",
    "direction",
    "message_or_format",
    "key_fields",
    "upstream",
    "downstream",
    "preconditions",
    "typical_use",
    "example",
    "machine_status",
    "risks",
    "evidence_id",
    "source_path",
]


class TestUavDocScaffold(unittest.TestCase):
    def test_required_files_exist(self):
        missing = [str(path.relative_to(ROOT)) for path in REQUIRED_FILES if not path.exists()]
        self.assertEqual([], missing)

    def test_interface_table_has_expected_columns(self):
        path = DOC_ROOT / "02-interface-table.csv"
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            self.assertEqual(REQUIRED_INTERFACE_COLUMNS, reader.fieldnames)

    def test_feature_matrix_contains_required_features(self):
        path = DOC_ROOT / "03-feature-deployment-matrix.csv"
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        names = {row["feature_name"] for row in rows}
        required = {
            "单机 LIO",
            "单机 VIO",
            "单机规划",
            "多点任务",
            "自动起降",
            "状态观测",
            "Elastic / 目标跟踪",
            "FUEL / 自主探索",
            "Formation / 集群",
            "YOLO 检测",
        }
        self.assertTrue(required.issubset(names))

    def test_evidence_index_contains_core_machine_claims(self):
        path = DOC_ROOT / "06-evidence-index.csv"
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        evidence_ids = {row["evidence_id"] for row in rows}
        required = {
            "E001_machine_orin_nx",
            "E002_ros_noetic",
            "E003_diff_planner_only_workspace",
            "E004_d435_present",
            "E005_livox_present",
            "E006_run_single_lio_script",
            "E007_run_single_vio_script",
            "E008_takeoff_topic",
            "E009_rc_mapping",
            "E010_elastic_not_onboard",
        }
        self.assertTrue(required.issubset(evidence_ids))

    def test_interface_table_contains_required_entries(self):
        path = DOC_ROOT / "02-interface-table.csv"
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        names = {row["name"] for row in rows}
        required = {
            "run_single_lio.sh",
            "run_single_vio.sh",
            "/px4ctrl/takeoff_land",
            "/move_base_simple/goal",
            "/back_trigger",
            "/mavros/state",
            "/mavros/battery",
            "/mavros/rc/in",
            "/ekf/ekf_odom",
            "/vins/imu_propagate",
            "points.yaml",
            "ctrl_param_fpv.yaml",
            "RC Channel 8",
        }
        self.assertTrue(required.issubset(names))

    def test_developer_guide_contains_required_headings(self):
        text = (DOC_ROOT / "01-developer-guide.md").read_text(encoding="utf-8")
        for heading in [
            "# 非凸α开发者文档",
            "## 1. 机器现状总览",
            "## 2. 当前已部署功能清单",
            "## 3. 启动链与运行链",
            "## 4. 接口说明",
            "## 5. 关键参数入口",
            "## 6. 状态观测与排障路径",
            "## 7. 二开建议与扩展边界",
        ]:
            self.assertIn(heading, text)

    def test_developer_guide_mentions_real_machine_boundaries(self):
        text = (DOC_ROOT / "01-developer-guide.md").read_text(encoding="utf-8")
        required_phrases = [
            "当前主链是单机 LIO / VIO + Diff-planner + px4ctrl + mavros + multipoint",
            "Elastic 不属于当前实机默认部署链路",
            "D435 + VINS 是当前视觉定位主链假设",
        ]
        for phrase in required_phrases:
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
