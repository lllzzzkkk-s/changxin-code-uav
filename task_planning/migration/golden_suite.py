from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.config import EnvironmentProfile, load_profile
from task_planning.mission_ops.golden_cases import GoldenMissionCase, golden_mission_cases
from task_planning.mission_ops.replay import load_artifact_bundle
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore


REQUIRED_GOLDEN_CASE_IDS: Tuple[str, ...] = (
    "single_ugv_inspection",
    "uav_reconnaissance",
    "uav_ugv_coordination",
    "failure_and_replan",
    "disconnect_continue_authorized_subtree",
)


@dataclass(frozen=True)
class GoldenSuiteCaseResult:
    case_id: str
    run_id: str
    status: str
    expected_status: str
    current_state: str
    expected_current_state: str
    artifact_bundle_path: Path
    validation_errors: List[str]

    @property
    def ok(self) -> bool:
        return not self.validation_errors

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["artifact_bundle_path"] = str(self.artifact_bundle_path)
        data["ok"] = self.ok
        return data


@dataclass(frozen=True)
class GoldenSuiteReport:
    profile_path: Path
    artifact_root: Path
    case_results: List[GoldenSuiteCaseResult]
    required_case_ids: Tuple[str, ...] = REQUIRED_GOLDEN_CASE_IDS
    schema: str = "DevMockGoldenSuite.v1"

    @property
    def ok(self) -> bool:
        return not self.validation_errors and all(result.ok for result in self.case_results)

    @property
    def validation_errors(self) -> List[str]:
        observed = [result.case_id for result in self.case_results]
        errors: List[str] = []
        if tuple(observed) != self.required_case_ids:
            errors.append(f"golden case order/coverage mismatch: {observed}")
        return errors

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "profile_path": str(self.profile_path),
            "artifact_root": str(self.artifact_root),
            "required_case_ids": list(self.required_case_ids),
            "case_results": [result.as_dict() for result in self.case_results],
            "validation_errors": self.validation_errors,
        }


def run_dev_mock_golden_suite(
    *,
    repo_root: Path,
    artifact_root: Path,
    profile_path: Optional[Path] = None,
) -> GoldenSuiteReport:
    repo_root = repo_root.resolve()
    artifact_root = artifact_root.resolve()
    profile_path = profile_path or repo_root / "profiles/dev_mock.env"
    profile = _profile_with_artifact_root(load_profile(profile_path), artifact_root)
    state_store = JsonMissionOpsStateStore(artifact_root / "_state")
    runner = MissionManagerRunner(
        state_store=state_store,
        gateway=MockPlatformGateway(),
    )

    case_results = [
        _run_case(runner=runner, mission_case=mission_case, profile=profile)
        for mission_case in golden_mission_cases()
    ]
    return GoldenSuiteReport(
        profile_path=profile_path,
        artifact_root=artifact_root,
        case_results=case_results,
    )


def _run_case(
    *,
    runner: MissionManagerRunner,
    mission_case: GoldenMissionCase,
    profile: EnvironmentProfile,
) -> GoldenSuiteCaseResult:
    result = runner.run(mission_case.run_input(), profile.as_env_dict())
    if mission_case.resume_failure_report is not None:
        result = runner.resume(result.run_id, {"failure_report": mission_case.resume_failure_report.as_dict()})

    artifact_bundle_path = Path(result.artifact_bundle_path or "")
    bundle = load_artifact_bundle(artifact_bundle_path)
    expected_status, expected_current_state = _expected_outcome(mission_case)
    validation_errors = list(bundle.validation_errors)
    validation_errors.extend(_result_errors(
        mission_case=mission_case,
        profile=profile,
        bundle_data=bundle.data,
        status=result.status,
        current_state=result.state.current_state,
        expected_status=expected_status,
        expected_current_state=expected_current_state,
    ))

    return GoldenSuiteCaseResult(
        case_id=mission_case.case_id,
        run_id=result.run_id,
        status=result.status,
        expected_status=expected_status,
        current_state=result.state.current_state,
        expected_current_state=expected_current_state,
        artifact_bundle_path=artifact_bundle_path,
        validation_errors=validation_errors,
    )


def _expected_outcome(mission_case: GoldenMissionCase) -> Tuple[str, str]:
    if mission_case.resume_failure_report is not None:
        return "replan_requested", "REQUEST_REPLAN"
    return "dry_run_complete", "DISPATCH_OR_HOLD"


def _result_errors(
    *,
    mission_case: GoldenMissionCase,
    profile: EnvironmentProfile,
    bundle_data: Dict[str, Any],
    status: str,
    current_state: str,
    expected_status: str,
    expected_current_state: str,
) -> List[str]:
    errors: List[str] = []
    if profile.mission_profile != "dev_mock":
        errors.append(f"golden suite requires MISSION_PROFILE=dev_mock, got {profile.mission_profile}")
    if profile.model_provider != "mock":
        errors.append(f"golden suite requires MODEL_PROVIDER=mock, got {profile.model_provider}")
    if profile.platform_backend != "mock":
        errors.append(f"golden suite requires PLATFORM_BACKEND=mock, got {profile.platform_backend}")
    if status != expected_status:
        errors.append(f"{mission_case.case_id} expected status={expected_status}, got {status}")
    if current_state != expected_current_state:
        errors.append(f"{mission_case.case_id} expected current_state={expected_current_state}, got {current_state}")

    profile_artifact = bundle_data.get("environment_profile.json") or {}
    mission_input = bundle_data.get("mission_input.json") or {}
    execution_events = bundle_data.get("execution_events.json") or {}
    event_types = [
        event.get("event_type")
        for event in execution_events.get("items") or []
        if isinstance(event, dict)
    ]
    if profile_artifact.get("mission_profile") != "dev_mock":
        errors.append(f"{mission_case.case_id} artifact must use mission_profile=dev_mock")
    if profile_artifact.get("platform_backend") != "mock":
        errors.append(f"{mission_case.case_id} artifact must use platform_backend=mock")
    if mission_input.get("run_input", {}).get("case_id") != mission_case.case_id:
        errors.append(f"{mission_case.case_id} artifact mission_input case_id mismatch")
    if execution_events.get("schema") != "ExecutionEventLog.v1":
        errors.append(f"{mission_case.case_id} artifact must include ExecutionEventLog.v1")
    if "bt_runtime_completed" not in event_types:
        errors.append(f"{mission_case.case_id} artifact must include bt_runtime_completed event")
    if mission_case.resume_failure_report is not None and "central_replan_requested" not in event_types:
        errors.append(f"{mission_case.case_id} artifact must include central_replan_requested event")
    return errors


def _profile_with_artifact_root(profile: EnvironmentProfile, artifact_root: Path) -> EnvironmentProfile:
    data = profile.as_env_dict()
    data["MISSION_ARTIFACT_ROOT"] = str(artifact_root)
    return EnvironmentProfile.from_mapping(data)
