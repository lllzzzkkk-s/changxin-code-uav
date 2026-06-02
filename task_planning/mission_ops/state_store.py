from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from task_planning.mission_ops.state import MissionOpsState


class JsonMissionOpsStateStore:
    def __init__(self, root: Union[str, Path]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, state: MissionOpsState) -> None:
        path = self._path(state.run_id)
        path.write_text(json.dumps(state.as_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def load(self, run_id: str) -> MissionOpsState:
        path = self._path(run_id)
        return MissionOpsState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def _path(self, run_id: str) -> Path:
        return self.root / f"{run_id}.json"
