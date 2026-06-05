from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from task_planning.config import EnvironmentProfile, ProfileValidationError, load_profile


Status = str
CommandResolver = Callable[[str], Optional[str]]
ImportSpecFinder = Callable[[str], object]


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    status: Status
    message: str
    evidence: Dict[str, object]

    @property
    def ok(self) -> bool:
        return self.status in {"pass", "warn", "skip"}

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EnvironmentReadinessReport:
    profile_path: Path
    repo_root: Path
    mission_profile: str
    checks: List[ReadinessCheck]
    next_commands: List[str]
    schema: str = "TaskPlanningReadiness.v1"

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def failures(self) -> List[ReadinessCheck]:
        return [check for check in self.checks if check.status == "fail"]

    @property
    def warnings(self) -> List[ReadinessCheck]:
        return [check for check in self.checks if check.status == "warn"]

    def as_dict(self) -> Dict[str, object]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "profile_path": str(self.profile_path),
            "repo_root": str(self.repo_root),
            "mission_profile": self.mission_profile,
            "checks": [check.as_dict() for check in self.checks],
            "failures": [check.as_dict() for check in self.failures],
            "warnings": [check.as_dict() for check in self.warnings],
            "next_commands": list(self.next_commands),
        }


def check_task_planning_readiness(
    profile_path: Path,
    *,
    repo_root: Optional[Path] = None,
    command_resolver: CommandResolver = shutil.which,
    import_spec_finder: ImportSpecFinder = importlib.util.find_spec,
) -> EnvironmentReadinessReport:
    repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    profile_path = profile_path.resolve()
    checks: List[ReadinessCheck] = [
        _python_check(),
        _repo_files_check(repo_root),
    ]

    try:
        profile = load_profile(profile_path)
    except (OSError, ProfileValidationError) as exc:
        checks.append(ReadinessCheck(
            name="profile_contract",
            status="fail",
            message=f"profile cannot be loaded: {exc}",
            evidence={"profile_path": str(profile_path)},
        ))
        return EnvironmentReadinessReport(
            profile_path=profile_path,
            repo_root=repo_root,
            mission_profile="unknown",
            checks=checks,
            next_commands=[],
        )

    checks.append(ReadinessCheck(
        name="profile_contract",
        status="pass",
        message="profile loaded and lane constraints passed",
        evidence=profile.as_dict(),
    ))
    checks.extend(_lane_boundary_checks(profile))
    checks.append(_artifact_root_check(profile, repo_root))
    checks.append(_catkin_package_check(repo_root))
    checks.extend(_ros_runtime_checks(profile, command_resolver, import_spec_finder))

    return EnvironmentReadinessReport(
        profile_path=profile_path,
        repo_root=repo_root,
        mission_profile=profile.mission_profile,
        checks=checks,
        next_commands=_next_commands(profile),
    )


def _python_check() -> ReadinessCheck:
    version = sys.version_info
    status = "pass" if version >= (3, 8) else "fail"
    return ReadinessCheck(
        name="python_runtime",
        status=status,
        message="Python runtime is supported" if status == "pass" else "Python 3.8 or newer is required",
        evidence={
            "executable": sys.executable,
            "version": platform.python_version(),
            "platform": platform.platform(),
        },
    )


def _repo_files_check(repo_root: Path) -> ReadinessCheck:
    required = [
        "AGENTS.md",
        "profiles/dev_mock.env",
        "profiles/home_model_lab.env",
        "profiles/home_model_lab_mock_endpoint.env",
        "profiles/server_sim.env",
        "profiles/work_hardware.env",
        "profiles/work_hardware_ros1_gateway.env.template",
        "task_planning/mission_ops/runner.py",
        "task_planning/mission_ops/mock_llm_client.py",
        "platform_gateway/mock_gateway.py",
        "platform_gateway/ros/catkin_pkg/platform_gateway_msgs/srv/TaskCommandJson.srv",
        "tools/run_task_planning_golden.py",
        "tools/run_task_planning_intent.py",
        "tools/run_dev_mock_golden_suite.py",
        "tools/replay_task_planning_artifact.py",
        "tools/extract_task_command_from_artifact.py",
        "tools/check_unit_ugv_target_map.py",
        "tools/check_unit_ugv_artifact_target_map.py",
        "tools/plan_work_hardware_gate.py",
        "tools/audit_ros1_gateway_services.py",
        "tools/prepare_ros1_gateway_workspace.py",
        "tools/check_model_lab_endpoint.py",
        "tools/evaluate_model_lab_case.py",
        "tools/package_task_planning_artifacts.py",
        "tools/verify_task_planning_artifacts.py",
        "tools/check_task_planning_site_acceptance.py",
        "tools/check_distributed_fleet_phase_gate.py",
        "tools/check_distributed_fleet_goal_evidence.py",
        "tools/collect_distributed_fleet_evidence.py",
        "tools/init_external_evidence_handoff.py",
        "tools/import_distributed_fleet_external_evidence.py",
        "tools/package_distributed_fleet_handoff.py",
        "tools/verify_distributed_fleet_handoff_package.py",
        "tools/record_unit_hardware_dispatch_artifact.py",
        "tools/run_mock_model_lab_endpoint.py",
        "tools/run_prevalidated_task_schema.py",
        "tools/check_task_planning_readiness.py",
        "tools/run_task_planning_lane_matrix.py",
    ]
    missing = [path for path in required if not (repo_root / path).exists()]
    return ReadinessCheck(
        name="required_files",
        status="pass" if not missing else "fail",
        message="required task-planning files are present" if not missing else "required task-planning files are missing",
        evidence={"missing": missing, "checked": required},
    )


def _lane_boundary_checks(profile: EnvironmentProfile) -> List[ReadinessCheck]:
    checks: List[ReadinessCheck] = []
    if profile.mission_profile in {"dev_mock", "work_hardware"} and profile.model_provider == "mock":
        checks.append(ReadinessCheck(
            name="large_model_dependency",
            status="pass",
            message="this lane can run without local large-model inference",
            evidence={"model_provider": profile.model_provider, "mission_profile": profile.mission_profile},
        ))
    elif profile.mission_profile == "home_model_lab":
        checks.append(ReadinessCheck(
            name="hardware_boundary",
            status="pass",
            message="home model-lab profile is hardware-isolated through PLATFORM_BACKEND=mock",
            evidence={"platform_backend": profile.platform_backend},
        ))
        checks.append(ReadinessCheck(
            name="model_endpoint_probe",
            status="warn",
            message="model endpoint is configured but not probed by readiness; use check_model_lab_endpoint.py for a live smoke test",
            evidence={"model_base_url": profile.model_base_url, "model_name": profile.model_name},
        ))
    elif profile.model_provider == "remote_http":
        checks.append(ReadinessCheck(
            name="model_endpoint_boundary",
            status="warn",
            message="remote model endpoint is optional and must remain validator-gated before planning or gateway dispatch",
            evidence={"model_base_url": profile.model_base_url, "mission_profile": profile.mission_profile},
        ))

    if profile.mission_profile == "work_hardware":
        checks.append(ReadinessCheck(
            name="unit_execution_boundary",
            status="pass",
            message="work_hardware is the unit/workplace execution lane and does not depend on the home 5090 server",
            evidence={
                "platform_backend": profile.platform_backend,
                "hardware_approval_required": profile.hardware_approval_required,
            },
        ))
    return checks


def _artifact_root_check(profile: EnvironmentProfile, repo_root: Path) -> ReadinessCheck:
    artifact_root = Path(profile.mission_artifact_root).expanduser()
    if not artifact_root.is_absolute():
        artifact_root = repo_root / artifact_root
    parent = artifact_root.parent
    status = "pass" if parent.exists() else "warn"
    return ReadinessCheck(
        name="artifact_root",
        status=status,
        message="artifact root parent exists" if status == "pass" else "artifact root parent does not exist yet",
        evidence={"artifact_root": str(artifact_root), "parent": str(parent)},
    )


def _catkin_package_check(repo_root: Path) -> ReadinessCheck:
    required = [
        "platform_gateway/ros/catkin_pkg/platform_gateway_msgs/package.xml",
        "platform_gateway/ros/catkin_pkg/platform_gateway_msgs/CMakeLists.txt",
        "platform_gateway/ros/catkin_pkg/platform_gateway_msgs/srv/TaskCommandJson.srv",
    ]
    missing = [path for path in required if not (repo_root / path).exists()]
    return ReadinessCheck(
        name="ros1_gateway_catkin_package",
        status="pass" if not missing else "fail",
        message="ROS1 gateway message package template is present" if not missing else "ROS1 gateway message package template is incomplete",
        evidence={"missing": missing, "checked": required},
    )


def _ros_runtime_checks(
    profile: EnvironmentProfile,
    command_resolver: CommandResolver,
    import_spec_finder: ImportSpecFinder,
) -> List[ReadinessCheck]:
    needed_for_real_gateway = profile.mission_profile == "work_hardware" and profile.platform_backend == "ros1_gateway"
    status_if_missing = "fail" if needed_for_real_gateway else "warn"
    checks = [
        _command_check(
            name="ros_cli_rostopic",
            command="rostopic",
            resolver=command_resolver,
            status_if_missing=status_if_missing,
            missing_message="rostopic is needed for unit/workplace read-only ROS observations and real gateway checks",
        ),
        _command_check(
            name="ros_cli_rosservice",
            command="rosservice",
            resolver=command_resolver,
            status_if_missing=status_if_missing,
            missing_message="rosservice is needed for unit/workplace gateway dry-run and dispatch services",
        ),
        _command_check(
            name="catkin_make",
            command="catkin_make",
            resolver=command_resolver,
            status_if_missing=status_if_missing,
            missing_message="catkin_make is needed to build the ROS1 gateway service package in a catkin workspace",
        ),
    ]
    rospy_available = import_spec_finder("rospy") is not None
    checks.append(ReadinessCheck(
        name="python_rospy",
        status="pass" if rospy_available else status_if_missing,
        message="rospy can be imported" if rospy_available else "rospy is not importable in this Python environment",
        evidence={"available": rospy_available, "required_for_real_gateway": needed_for_real_gateway},
    ))
    if profile.mission_profile != "work_hardware":
        return [
            ReadinessCheck(
                name=check.name,
                status="skip" if check.status == "warn" else check.status,
                message=f"{check.message}; not required for {profile.mission_profile}",
                evidence=check.evidence,
            )
            for check in checks
        ]
    return checks


def _command_check(
    *,
    name: str,
    command: str,
    resolver: CommandResolver,
    status_if_missing: Status,
    missing_message: str,
) -> ReadinessCheck:
    resolved = resolver(command)
    return ReadinessCheck(
        name=name,
        status="pass" if resolved else status_if_missing,
        message=f"{command} found" if resolved else missing_message,
        evidence={"command": command, "path": resolved or "", "required_for_real_gateway": status_if_missing == "fail"},
    )


def _next_commands(profile: EnvironmentProfile) -> List[str]:
    commands = {
        "dev_mock": [
            "PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests/task_planning",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile profiles/dev_mock.env",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_dev_mock_golden_suite.py --artifact-root /tmp/changxin-dev-mock-golden-suite",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/collect_distributed_fleet_evidence.py --output-dir /tmp/changxin-distributed-fleet-evidence",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/init_external_evidence_handoff.py --evidence-dir /tmp/changxin-distributed-fleet-evidence",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/import_distributed_fleet_external_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence --model-lab-evaluation <model_lab_evaluation.json> --artifact-package <artifact-package.tar.gz> --artifact-package-verification-report <artifact_package_verification.json>",
        ],
        "home_model_lab": [
            "Optional plumbing-only mock: PYTHONDONTWRITEBYTECODE=1 python3 tools/run_mock_model_lab_endpoint.py --port 8000",
            "Optional plumbing-only check: PYTHONDONTWRITEBYTECODE=1 python3 tools/check_model_lab_endpoint.py --profile profiles/home_model_lab_mock_endpoint.env",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_model_lab_endpoint.py --profile profiles/home_model_lab.env",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/evaluate_model_lab_case.py --profile profiles/home_model_lab.env --case uav_ugv_coordination --output-dir /tmp/changxin-model-lab",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_artifacts.py --artifact /tmp/changxin-model-lab/uav_ugv_coordination --output-dir /tmp/changxin-artifact-packages",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_prevalidated_task_schema.py --profile profiles/work_hardware.env --task-schema /tmp/changxin-model-lab/uav_ugv_coordination/model_task_schema.json --case uav_ugv_coordination --artifact-root /tmp/changxin-prevalidated-runs",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile profiles/dev_mock.env --case uav_ugv_coordination --artifact-root /tmp/changxin-task-planning-dev",
        ],
        "server_sim": [
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile profiles/server_sim.env --case uav_ugv_coordination",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_artifacts.py --artifact <artifact_root> --output-dir /tmp/changxin-artifact-packages",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/replay_task_planning_artifact.py <artifact_root> [--compare-to <other_artifact_root>]",
        ],
        "work_hardware": [
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile profiles/work_hardware.env",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py <artifact-package.tar.gz> --work-dir /tmp/changxin-artifact-verify --verification-context unit_workplace_receiving",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/plan_work_hardware_gate.py --profile profiles/work_hardware.env --through-stage mock_gateway_dispatch",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile profiles/work_hardware.env --case uav_ugv_coordination",
            "Only after mock gates pass: source the unit/workplace ROS1 workspace and run read-only rostopic observations listed by the gate plan.",
        ],
    }
    return list(commands.get(profile.mission_profile, []))
