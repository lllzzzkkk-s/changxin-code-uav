import pathlib
import subprocess
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestExportUavDocs(unittest.TestCase):
    def test_export_script_creates_expected_outputs(self):
        subprocess.run(
            ["python", "uav/01-scripts/export_uav_dev_docs.py"],
            cwd=ROOT,
            check=True,
        )

        docx_path = ROOT / "docs" / "非凸α-开发者文档包.docx"
        interface_xlsx = ROOT / "docs" / "非凸α-接口总表.xlsx"
        feature_xlsx = ROOT / "docs" / "非凸α-功能部署矩阵.xlsx"
        gap_xlsx = ROOT / "docs" / "非凸α-素材缺口表.xlsx"

        for path in [docx_path, interface_xlsx, feature_xlsx, gap_xlsx]:
            self.assertTrue(path.exists(), path)

        with zipfile.ZipFile(interface_xlsx) as zf:
            content = zf.read("xl/workbook.xml").decode("utf-8")
        self.assertIn("接口总表", content)

        with zipfile.ZipFile(feature_xlsx) as zf:
            content = zf.read("xl/workbook.xml").decode("utf-8")
        self.assertIn("功能部署矩阵", content)

        with zipfile.ZipFile(gap_xlsx) as zf:
            content = zf.read("xl/workbook.xml").decode("utf-8")
        self.assertIn("素材缺口表", content)

        with zipfile.ZipFile(docx_path) as zf:
            content = zf.read("word/document.xml").decode("utf-8")
        self.assertIn("非凸α开发者文档", content)
        self.assertIn("状态与截图对照附录", content)


if __name__ == "__main__":
    unittest.main()
