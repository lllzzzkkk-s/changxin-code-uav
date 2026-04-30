import ast
from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON38_FILES = [
    REPO_ROOT / "uav/llm_control/core/pipeline.py",
    REPO_ROOT / "uav/llm_control/ros_adapters/action_gate_dry_run.py",
    REPO_ROOT / "uav/llm_control/ros_adapters/dry_run.py",
    REPO_ROOT / "uav/llm_control/safety/action_gate.py",
    REPO_ROOT / "uav/llm_control/safety/profiles.py",
    REPO_ROOT / "uav/llm_control/schemas/models.py",
    REPO_ROOT / "uav/llm_control/tools/catalog.py",
    REPO_ROOT / "uav/01-scripts/g3d_live_action_gate_check.py",
]


class TestPython38Compatibility(unittest.TestCase):
    def test_wsl_noetic_runtime_files_parse_as_python38(self):
        for path in PYTHON38_FILES:
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                ast.parse(path.read_text(), filename=str(path), feature_version=(3, 8))

    def test_wsl_noetic_runtime_files_avoid_python310_type_union_syntax(self):
        forbidden = re.compile(r"\|\s*(None|Mapping\[|Dict\[|str|CommandResult|ActionApproval|ActionGateConfig)")
        for path in PYTHON38_FILES:
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                self.assertIsNone(forbidden.search(path.read_text()))


if __name__ == "__main__":
    unittest.main()
