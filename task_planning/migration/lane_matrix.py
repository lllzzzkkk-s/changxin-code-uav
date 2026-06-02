from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.config import EnvironmentProfile, load_profile
from task_planning.mission_ops.golden_cases import golden_case_by_id
from task_planning.mission_ops.replay import ArtifactComparison, compare_artifact_bundles, load_artifact_bundle
from task_planning.mission_ops.runner import MissionManagerRunner
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore


DEFAULT_LANES = ("dev_mock", "server_sim", "work_hardware")


@dataclass(frozen=True)
class LaneRun:
    lane: str
    profile_path: Path
    status: str
    current_state: str
    artifact_bundle_path: Path
    validation_errors: List[str]

    @property
    def ok(self) -> bool:
        return not self.validation_errors

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["profile_path"] = str(self.profile_path)
        data["artifact_bundle_path"] = str(self.artifact_bundle_path)
        data["ok"] = self.ok
        return data


@dataclass(frozen=True)
class LaneMatrixComparison:
    name: str
    mode: str
    left_lane: str
    right_lane: str
    equivalent: bool
    validation_errors: List[str]
    diffs: List[Dict[str, Any]]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LaneMatrixReport:
    case_id: str
    artifact_root: Path
    runs: List[LaneRun]
    comparisons: List[LaneMatrixComparison]
    schema: str = "TaskPlanningLaneMatrix.v1"

    @property
    def ok(self) -> bool:
        return all(run.ok for run in self.runs) and all(comparison.equivalent for comparison in self.comparisons)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "case_id": self.case_id,
            "artifact_root": str(self.artifact_root),
            "runs": [run.as_dict() for run in self.runs],
            "comparisons": [comparison.as_dict() for comparison in self.comparisons],
        }


def run_lane_matrix(
    *,
    repo_root: Path,
    artifact_root: Path,
    case_id: str = "uav_ugv_coordination",
    lanes: Optional[List[str]] = None,
) -> LaneMatrixReport:
    repo_root = repo_root.resolve()
    artifact_root = artifact_root.resolve()
    selected_lanes = lanes or list(DEFAULT_LANES)
    runs = [
        _run_lane(
            lane=lane,
            profile_path=repo_root / "profiles" / f"{lane}.env",
            artifact_root=artifact_root / lane,
            case_id=case_id,
        )
        for lane in selected_lanes
    ]
    comparisons = _build_comparisons(runs)
    return LaneMatrixReport(
        case_id=case_id,
        artifact_root=artifact_root,
        runs=runs,
        comparisons=comparisons,
    )


def _run_lane(
    *,
    lane: str,
    profile_path: Path,
    artifact_root: Path,
    case_id: str,
) -> LaneRun:
    profile = _profile_with_artifact_root(load_profile(profile_path), artifact_root)
    mission_case = golden_case_by_id(case_id)
    state_store = JsonMissionOpsStateStore(artifact_root / "_state")
    gateway = None if profile.platform_backend == "ros1_gateway" else MockPlatformGateway()
    runner = MissionManagerRunner(state_store=state_store, gateway=gateway)

    result = runner.run(mission_case.run_input(), profile.as_env_dict())
    if mission_case.resume_failure_report is not None:
        result = runner.resume(result.run_id, {"failure_report": mission_case.resume_failure_report.as_dict()})

    artifact_bundle_path = Path(result.artifact_bundle_path or "")
    bundle = load_artifact_bundle(artifact_bundle_path)
    validation_errors = list(bundle.validation_errors)
    validation_errors.extend(_lane_result_errors(profile, result.status, result.state.current_state))
    return LaneRun(
        lane=lane,
        profile_path=profile_path,
        status=result.status,
        current_state=result.state.current_state,
        artifact_bundle_path=artifact_bundle_path,
        validation_errors=validation_errors,
    )


def _build_comparisons(runs: List[LaneRun]) -> List[LaneMatrixComparison]:
    by_lane = {run.lane: run for run in runs}
    comparisons: List[LaneMatrixComparison] = []
    if "dev_mock" in by_lane and "server_sim" in by_lane:
        comparisons.append(_exact_comparison(
            name="dev_mock_vs_server_sim",
            left=by_lane["dev_mock"],
            right=by_lane["server_sim"],
        ))
    if "dev_mock" in by_lane and "work_hardware" in by_lane:
        comparisons.append(_work_hardware_pre_dispatch_comparison(
            left=by_lane["dev_mock"],
            right=by_lane["work_hardware"],
        ))
    return comparisons


def _exact_comparison(*, name: str, left: LaneRun, right: LaneRun) -> LaneMatrixComparison:
    comparison = compare_artifact_bundles(left.artifact_bundle_path, right.artifact_bundle_path)
    return _from_artifact_comparison(
        name=name,
        mode="exact",
        left_lane=left.lane,
        right_lane=right.lane,
        comparison=comparison,
        equivalent=comparison.equivalent,
    )


def _work_hardware_pre_dispatch_comparison(*, left: LaneRun, right: LaneRun) -> LaneMatrixComparison:
    comparison = compare_artifact_bundles(left.artifact_bundle_path, right.artifact_bundle_path)
    right_bundle = load_artifact_bundle(right.artifact_bundle_path)
    validation_errors = list(comparison.validation_errors)
    validation_errors.extend(_work_hardware_pre_dispatch_errors(right, right_bundle.data))
    allowed_diff_paths = {"gateway_trace.records", "execution_events.event_types"}
    unexpected_diffs = [diff.as_dict() for diff in comparison.diffs if diff.path not in allowed_diff_paths]
    equivalent = not validation_errors and not unexpected_diffs
    return LaneMatrixComparison(
        name="dev_mock_vs_work_hardware_pre_dispatch",
        mode="pre_dispatch_compatible",
        left_lane=left.lane,
        right_lane=right.lane,
        equivalent=equivalent,
        validation_errors=validation_errors,
        diffs=unexpected_diffs,
    )


def _from_artifact_comparison(
    *,
    name: str,
    mode: str,
    left_lane: str,
    right_lane: str,
    comparison: ArtifactComparison,
    equivalent: bool,
) -> LaneMatrixComparison:
    return LaneMatrixComparison(
        name=name,
        mode=mode,
        left_lane=left_lane,
        right_lane=right_lane,
        equivalent=equivalent,
        validation_errors=list(comparison.validation_errors),
        diffs=[diff.as_dict() for diff in comparison.diffs],
    )


def _work_hardware_pre_dispatch_errors(run: LaneRun, data: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    profile = data.get("environment_profile.json") or {}
    validation = data.get("validation_report.json") or {}
    gateway = data.get("gateway_trace.json") or {}
    if profile.get("mission_profile") != "work_hardware":
        errors.append("right lane must use MISSION_PROFILE=work_hardware")
    if profile.get("model_provider") != "mock":
        errors.append("work_hardware pre-dispatch matrix must not require a model endpoint")
    if profile.get("platform_backend") != "mock":
        errors.append("work_hardware pre-dispatch matrix must use PLATFORM_BACKEND=mock")
    if validation.get("current_state") != "OPERATOR_APPROVAL":
        errors.append("work_hardware pre-dispatch run must stop at OPERATOR_APPROVAL")
    if run.status != "approval_required":
        errors.append("work_hardware pre-dispatch run must return status=approval_required")
    if gateway.get("records") not in ([], None):
        errors.append("work_hardware pre-dispatch run must not dispatch gateway records")
    return errors


def _lane_result_errors(profile: EnvironmentProfile, status: str, current_state: str) -> List[str]:
    errors: List[str] = []
    if profile.mission_profile in {"dev_mock", "server_sim"}:
        if status != "dry_run_complete":
            errors.append(f"{profile.mission_profile} expected dry_run_complete, got {status}")
        if current_state != "DISPATCH_OR_HOLD":
            errors.append(f"{profile.mission_profile} expected DISPATCH_OR_HOLD, got {current_state}")
    if profile.mission_profile == "work_hardware":
        if status != "approval_required":
            errors.append(f"work_hardware expected approval_required, got {status}")
        if current_state != "OPERATOR_APPROVAL":
            errors.append(f"work_hardware expected OPERATOR_APPROVAL, got {current_state}")
    return errors


def _profile_with_artifact_root(profile: EnvironmentProfile, artifact_root: Path) -> EnvironmentProfile:
    data = profile.as_env_dict()
    data["MISSION_ARTIFACT_ROOT"] = str(artifact_root)
    return EnvironmentProfile.from_mapping(data)
