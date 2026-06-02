import tempfile
import unittest
from pathlib import Path

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.mission_ops.mock_llm_client import MockLLMClient
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore


MISSION_OPS_CORE_FILES = [
    "task_planning/mission_ops/__init__.py",
    "task_planning/mission_ops/model_client.py",
    "task_planning/mission_ops/mock_llm_client.py",
    "task_planning/mission_ops/mission_manager.py",
    "task_planning/mission_ops/runner.py",
    "task_planning/mission_ops/tools.py",
]

AGENT_HANDOFF_DOCS = [
    "AGENTS.md",
    "docs/superpowers/specs/2026-05-25-local-llm-mission-ops-architecture.md",
    "docs/superpowers/specs/2026-05-26-distributed-fleet-testing-migration-architecture.md",
    "docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md",
]


class CapturingStateStore(JsonMissionOpsStateStore):
    def __init__(self, root):
        super().__init__(root)
        self.saved_states = []

    def save(self, state):
        self.saved_states.append(state)
        super().save(state)


class ModelClientBoundaryTest(unittest.TestCase):
    def test_phase1_core_does_not_depend_on_local_llm_client(self):
        repo_root = Path(__file__).resolve().parents[2]

        offenders = []
        for relative_path in MISSION_OPS_CORE_FILES:
            text = (repo_root / relative_path).read_text(encoding="utf-8")
            if "local_llm_client" in text or "LocalLLMClient" in text or "MockLocalLLMClient" in text:
                offenders.append(relative_path)

        self.assertEqual([], offenders)

    def test_mission_manager_uses_model_client_state_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CapturingStateStore(Path(tmp))
            runner = MissionManagerRunner(
                state_store=store,
                model_client=MockLLMClient(),
                gateway=MockPlatformGateway(),
            )

            result = runner.run({"intent": "搜索 A 区并派无人车确认目标"}, {"dry_run": True})

        state_names = [state.current_state for state in store.saved_states]
        self.assertEqual("dry_run_complete", result.status)
        self.assertIn("CALL_MODEL_CLIENT_FOR_TASK_SCHEMA", state_names)
        self.assertNotIn("CALL_LOCAL_LLM_FOR_TASK_SCHEMA", state_names)

    def test_agent_handoff_docs_do_not_reintroduce_local_llm_client(self):
        repo_root = Path(__file__).resolve().parents[2]

        offenders = []
        forbidden = "Local" + "LLMClient"
        for relative_path in AGENT_HANDOFF_DOCS:
            text = (repo_root / relative_path).read_text(encoding="utf-8")
            if forbidden in text or "CALL_LOCAL_LLM" in text:
                offenders.append(relative_path)

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
