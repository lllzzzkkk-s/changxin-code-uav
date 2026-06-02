#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.config import EnvironmentProfile, load_profile
from task_planning.mission_ops.golden_cases import golden_case_by_id, golden_mission_cases
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore


def run_cases(
    *,
    profile_path: Path,
    case_ids: Optional[Iterable[str]] = None,
    artifact_root: Optional[Path] = None,
) -> List[Dict[str, str]]:
    profile = load_profile(profile_path)
    if artifact_root is not None:
        data = profile.as_env_dict()
        data["MISSION_ARTIFACT_ROOT"] = str(artifact_root)
        profile = EnvironmentProfile.from_mapping(data)
    else:
        profile = _normalize_artifact_root(profile)

    selected_cases = (
        [golden_case_by_id(case_id) for case_id in case_ids]
        if case_ids
        else golden_mission_cases()
    )
    state_root = Path(profile.mission_artifact_root) / "_state"
    gateway = None if profile.platform_backend == "ros1_gateway" else MockPlatformGateway()
    runner = MissionManagerRunner(
        state_store=JsonMissionOpsStateStore(state_root),
        gateway=gateway,
    )

    results: List[Dict[str, str]] = []
    for mission_case in selected_cases:
        result = runner.run(mission_case.run_input(), profile.as_env_dict())
        final_result = result
        if mission_case.resume_failure_report is not None:
            final_result = runner.resume(
                result.run_id,
                {"failure_report": mission_case.resume_failure_report.as_dict()},
            )
        results.append({
            "case_id": mission_case.case_id,
            "run_id": final_result.run_id,
            "status": final_result.status,
            "current_state": final_result.state.current_state,
            "artifact_bundle_path": final_result.artifact_bundle_path or "",
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run task-planning golden mission cases through a selected profile.")
    parser.add_argument("--profile", required=True, type=Path, help="Path to profiles/*.env")
    parser.add_argument("--case", action="append", dest="case_ids", help="Golden case id. Omit to run all cases.")
    parser.add_argument("--artifact-root", type=Path, help="Override MISSION_ARTIFACT_ROOT for this run.")
    args = parser.parse_args()

    results = run_cases(profile_path=args.profile, case_ids=args.case_ids, artifact_root=args.artifact_root)
    print(json.dumps({"schema": "GoldenMissionRunSet.v1", "results": results}, indent=2, sort_keys=True))
    return 0


def _normalize_artifact_root(profile: EnvironmentProfile) -> EnvironmentProfile:
    artifact_root = Path(profile.mission_artifact_root).expanduser()
    if artifact_root.is_absolute():
        return profile
    data = profile.as_env_dict()
    data["MISSION_ARTIFACT_ROOT"] = str(REPO_ROOT / artifact_root)
    return EnvironmentProfile.from_mapping(data)


if __name__ == "__main__":
    raise SystemExit(main())
