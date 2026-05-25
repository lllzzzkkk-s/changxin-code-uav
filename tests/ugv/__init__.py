from pathlib import Path


_REPO_UGV_PACKAGE = Path(__file__).resolve().parents[2] / "ugv"
if _REPO_UGV_PACKAGE.is_dir():
    __path__.append(str(_REPO_UGV_PACKAGE))
