from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC_ROOT = ROOT / "uav" / "20-dev-docs"
OUT_ROOT = ROOT / "docs"
SCRIPT_ROOT = Path(__file__).resolve().parent

RUNTIME_ROOT = Path("/Users/apple/.cache/codex-runtimes/codex-primary-runtime/dependencies")
NODE_EXEC = RUNTIME_ROOT / "node" / "bin" / "node"
NODE_MODULES = RUNTIME_ROOT / "node" / "node_modules"
PYTHON_BUNDLE = RUNTIME_ROOT / "python"


def ensure_docx_import() -> None:
    try:
        import docx  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    site_packages = sorted(PYTHON_BUNDLE.glob("lib/python*/site-packages"))
    for path in site_packages:
        sys.path.append(str(path))

    import docx  # noqa: F401


def ensure_node_modules_link() -> tuple[Path, bool]:
    link_path = SCRIPT_ROOT / "node_modules"
    if link_path.is_symlink():
        if link_path.resolve() == NODE_MODULES.resolve():
            return link_path, False
        link_path.unlink()
    elif link_path.exists():
        raise RuntimeError(f"unexpected node_modules path exists: {link_path}")

    os.symlink(NODE_MODULES, link_path, target_is_directory=True)
    return link_path, True


def markdown_bundle_to_docx(markdown_paths: list[Path], out_path: Path) -> None:
    ensure_docx_import()
    from docx import Document

    document = Document()
    for markdown_path in markdown_paths:
        for raw_line in markdown_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                document.add_paragraph("")
                continue
            if line.startswith("# "):
                document.add_heading(line[2:], level=1)
            elif line.startswith("## "):
                document.add_heading(line[3:], level=2)
            elif line.startswith("### "):
                document.add_heading(line[4:], level=3)
            elif line.startswith("- "):
                document.add_paragraph(line[2:], style="List Bullet")
            else:
                document.add_paragraph(line)
    document.save(out_path)


def export_xlsx_bundle() -> None:
    link_path, created = ensure_node_modules_link()
    try:
        subprocess.run(
            [str(NODE_EXEC), str(SCRIPT_ROOT / "export_uav_dev_docs_xlsx.mjs")],
            cwd=ROOT,
            check=True,
        )
    finally:
        if created and link_path.exists():
            link_path.unlink()


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    export_xlsx_bundle()
    docx_path = OUT_ROOT / "非凸α-开发者文档包.docx"
    markdown_bundle_to_docx(
        [
            DOC_ROOT / "01-developer-guide.md",
            DOC_ROOT / "04-screenshot-state-appendix.md",
            DOC_ROOT / "05-developer-navigation.md",
        ],
        docx_path,
    )
    print("WROTE", docx_path)


if __name__ == "__main__":
    main()
