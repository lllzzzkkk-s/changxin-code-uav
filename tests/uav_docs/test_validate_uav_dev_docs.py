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


if __name__ == "__main__":
    unittest.main()
