import pathlib
import subprocess
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestExportUavDocs(unittest.TestCase):
    def test_export_script_does_not_hardcode_local_runtime_path(self):
        script = (ROOT / "uav" / "01-scripts" / "export_uav_dev_docs.py").read_text(encoding="utf-8")
        self.assertNotIn("/Users/apple/.cache/codex-runtimes", script)
        self.assertIn("UAV_DOCS_RUNTIME_ROOT", script)

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
        portal_html = ROOT / "docs" / "非凸α-二开速查台.html"

        for path in [docx_path, interface_xlsx, feature_xlsx, gap_xlsx, portal_html]:
            self.assertTrue(path.exists(), path)

        with zipfile.ZipFile(interface_xlsx) as zf:
            content = zf.read("xl/workbook.xml").decode("utf-8")
        for sheet_name in [
            "怎么用",
            "推荐接入",
            "场景速查",
            "状态接口",
            "动作接口",
            "脚本入口",
            "参数入口",
            "RC映射",
            "完整原表",
        ]:
            self.assertIn(sheet_name, content)

        with zipfile.ZipFile(feature_xlsx) as zf:
            content = zf.read("xl/workbook.xml").decode("utf-8")
        for sheet_name in ["怎么用", "当前已部署", "扩展能力", "二开建议", "完整矩阵"]:
            self.assertIn(sheet_name, content)

        with zipfile.ZipFile(gap_xlsx) as zf:
            content = zf.read("xl/workbook.xml").decode("utf-8")
        for sheet_name in ["怎么用", "缺口明细"]:
            self.assertIn(sheet_name, content)

        with zipfile.ZipFile(docx_path) as zf:
            content = zf.read("word/document.xml").decode("utf-8")
        self.assertIn("非凸α开发者文档", content)
        self.assertIn("状态与截图对照附录", content)

        html = portal_html.read_text(encoding="utf-8")
        self.assertIn("非凸α二开速查台", html)
        self.assertIn("当前主链是单机 LIO / VIO + Diff-planner + px4ctrl + mavros + multipoint", html)
        self.assertIn("场景入口", html)
        self.assertIn("点击任一场景卡片后，会自动把下方接口检索区切到对应关键词。", html)
        self.assertIn("启动链速览", html)
        self.assertIn("参数聚焦", html)
        self.assertIn("源码追踪", html)
        self.assertIn("建议改造层级", html)
        self.assertIn("data-scene-query=", html)
        self.assertIn("data-trace-title=", html)
        self.assertIn("data-trace-source=", html)
        self.assertIn("/mavros/battery", html)
        self.assertNotIn("Diff-Planner", html)
        self.assertIn("cd ~/Diff-planner &amp;&amp; ./sh_files/run_single_lio.sh", html)


if __name__ == "__main__":
    unittest.main()
