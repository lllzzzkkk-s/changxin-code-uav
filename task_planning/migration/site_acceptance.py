from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from task_planning.config import ProfileValidationError, load_profile
from task_planning.hardware import HardwareGatePlan, build_hardware_gate_plan
from task_planning.migration.artifact_package import ArtifactPackageVerification, verify_artifact_package
from task_planning.migration.machine_identity import current_machine_id
from task_planning.migration.readiness import (
    CommandResolver,
    EnvironmentReadinessReport,
    ImportSpecFinder,
    check_task_planning_readiness,
)
from task_planning.migration.ros1_service_audit import (
    CommandRunner,
    Ros1GatewayServiceAudit,
    audit_ros1_gateway_services,
    make_rosservice_command_runner,
    parse_service_args_file,
    parse_service_signature_file,
)


@dataclass(frozen=True)
class SiteArtifactPackageEvidence:
    archive: Path
    verification: Optional[ArtifactPackageVerification] = None
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.verification is not None and self.verification.ok

    def as_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok,
            "archive": str(self.archive),
            "verification": self.verification.as_dict() if self.verification else None,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class SiteAcceptanceReport:
    profile_path: Path
    repo_root: Path
    machine_id: str
    mission_profile: str
    platform_backend: str
    acceptance_level: str
    case_id: str
    readiness: EnvironmentReadinessReport
    artifact_packages: List[SiteArtifactPackageEvidence]
    hardware_gate: Optional[HardwareGatePlan]
    rosservice_audit: Optional[Ros1GatewayServiceAudit]
    validation_errors: List[str]
    next_commands: List[str]
    schema: str = "TaskPlanningSiteAcceptance.v1"

    @property
    def ok(self) -> bool:
        return not self.validation_errors

    def as_dict(self) -> Dict[str, object]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "profile_path": str(self.profile_path),
            "repo_root": str(self.repo_root),
            "machine_id": self.machine_id,
            "mission_profile": self.mission_profile,
            "platform_backend": self.platform_backend,
            "acceptance_level": self.acceptance_level,
            "case_id": self.case_id,
            "readiness": self.readiness.as_dict(),
            "artifact_packages": [item.as_dict() for item in self.artifact_packages],
            "hardware_gate": self.hardware_gate.as_dict() if self.hardware_gate else None,
            "rosservice_audit": self.rosservice_audit.as_dict() if self.rosservice_audit else None,
            "validation_errors": list(self.validation_errors),
            "next_commands": list(self.next_commands),
        }


def check_task_planning_site_acceptance(
    *,
    profile_path: Path,
    repo_root: Optional[Path] = None,
    artifact_packages: Sequence[Path] = (),
    artifact_work_dir: Optional[Path] = None,
    require_artifact_package: bool = False,
    case_id: str = "",
    through_stage: str = "mock_gateway_dispatch",
    platform_ids: Sequence[str] = (),
    rosservice_list_file: Optional[Path] = None,
    require_rosservice_audit: bool = False,
    service_type_file: Optional[Path] = None,
    service_args_file: Optional[Path] = None,
    run_rosservice_list: bool = False,
    run_service_signatures: bool = False,
    require_service_signatures: bool = False,
    command_resolver: CommandResolver = shutil.which,
    import_spec_finder: ImportSpecFinder = importlib.util.find_spec,
    rosservice_command_runner: Optional[CommandRunner] = None,
) -> SiteAcceptanceReport:
    repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    profile_path = profile_path.resolve()
    readiness = check_task_planning_readiness(
        profile_path,
        repo_root=repo_root,
        command_resolver=command_resolver,
        import_spec_finder=import_spec_finder,
    )
    errors: List[str] = []

    if not readiness.ok:
        errors.extend(f"readiness:{check.name}:{check.message}" for check in readiness.failures)

    case_id = case_id.strip()
    mission_profile = readiness.mission_profile
    platform_backend = "unknown"
    profile = None
    try:
        profile = load_profile(profile_path)
        mission_profile = profile.mission_profile
        platform_backend = profile.platform_backend
    except (OSError, ProfileValidationError) as exc:
        errors.append(f"profile cannot be loaded for site acceptance: {exc}")

    package_evidence = _verify_artifact_packages(
        artifact_packages,
        artifact_work_dir=artifact_work_dir,
    )
    for package in package_evidence:
        if not package.ok:
            errors.extend(f"artifact_package:{package.archive}:{error}" for error in _package_errors(package))
        elif case_id:
            errors.extend(f"artifact_package:{package.archive}:{error}" for error in _package_case_errors(package, case_id))
    if require_artifact_package and not package_evidence:
        errors.append("at least one verified artifact package is required")

    hardware_gate = None
    if profile is not None and profile.mission_profile == "work_hardware":
        hardware_gate = build_hardware_gate_plan(profile, through_stage=through_stage)
        if not hardware_gate.ok:
            errors.extend(f"hardware_gate:{error}" for error in hardware_gate.validation_errors)

    rosservice_audit = None
    rosservice_requested = (
        platform_ids
        or rosservice_list_file is not None
        or service_type_file is not None
        or service_args_file is not None
        or run_rosservice_list
        or run_service_signatures
        or require_rosservice_audit
        or require_service_signatures
    )
    if rosservice_requested:
        if profile is not None and profile.platform_backend != "ros1_gateway":
            errors.append("ROS1 gateway service acceptance requires PLATFORM_BACKEND=ros1_gateway profile")
        observed_services = _read_rosservice_list(rosservice_list_file, errors) if rosservice_list_file else None
        observed_service_types = _read_service_signature_file(service_type_file, errors) if service_type_file else None
        observed_service_args = _read_service_args_file(service_args_file, errors) if service_args_file else None
        command_runner = rosservice_command_runner
        command_environment_source = "caller_supplied" if rosservice_command_runner is not None else None
        if command_runner is None and profile is not None and (run_rosservice_list or run_service_signatures):
            command_runner = make_rosservice_command_runner(profile)
            command_environment_source = "profile"
        try:
            rosservice_audit = audit_ros1_gateway_services(
                profile_path=profile_path,
                platform_ids=platform_ids,
                observed_services=observed_services,
                observed_service_types=observed_service_types,
                observed_service_args=observed_service_args,
                command_runner=command_runner,
                run_service_signature_checks=run_service_signatures,
                require_service_signatures=require_service_signatures,
                command_environment_source=command_environment_source,
            )
        except Exception as exc:
            errors.append(f"rosservice_audit failed: {exc}")
        else:
            if not rosservice_audit.ok:
                errors.extend(f"rosservice_audit:{error}" for error in rosservice_audit.validation_errors)
                errors.extend(f"rosservice_audit:missing_service:{service}" for service in rosservice_audit.missing_services)
            if require_rosservice_audit and rosservice_audit.observed_service_count == 0:
                errors.append("a captured rosservice list is required for ROS1 gateway acceptance")
            if require_service_signatures and not all(signature.ok for signature in rosservice_audit.service_signatures):
                errors.append("valid rosservice type/args evidence is required for ROS1 gateway acceptance")
    elif require_rosservice_audit:
        errors.append("platform ids are required for ROS1 gateway service acceptance")

    return SiteAcceptanceReport(
        profile_path=profile_path,
        repo_root=repo_root,
        machine_id=current_machine_id(),
        mission_profile=mission_profile,
        platform_backend=platform_backend,
        acceptance_level=_acceptance_level(mission_profile, platform_backend, hardware_gate, rosservice_audit),
        case_id=case_id,
        readiness=readiness,
        artifact_packages=package_evidence,
        hardware_gate=hardware_gate,
        rosservice_audit=rosservice_audit,
        validation_errors=errors,
        next_commands=_next_commands(
            mission_profile=mission_profile,
            readiness_commands=readiness.next_commands,
            require_artifact_package=require_artifact_package,
            require_rosservice_audit=require_rosservice_audit,
            require_service_signatures=require_service_signatures,
            platform_ids=platform_ids,
            case_id=case_id,
        ),
    )


def _verify_artifact_packages(
    artifact_packages: Sequence[Path],
    *,
    artifact_work_dir: Optional[Path],
) -> List[SiteArtifactPackageEvidence]:
    evidence: List[SiteArtifactPackageEvidence] = []
    for archive in artifact_packages:
        archive = archive.expanduser().resolve()
        try:
            verification = verify_artifact_package(
                archive_path=archive,
                work_dir=artifact_work_dir,
                verification_context="unit_workplace_receiving",
            )
        except Exception as exc:
            evidence.append(SiteArtifactPackageEvidence(
                archive=archive,
                verification=None,
                errors=[str(exc)],
            ))
        else:
            evidence.append(SiteArtifactPackageEvidence(
                archive=archive,
                verification=verification,
                errors=[],
            ))
    return evidence


def _package_errors(package: SiteArtifactPackageEvidence) -> List[str]:
    if package.errors:
        return list(package.errors)
    if package.verification is None:
        return ["missing artifact package verification"]
    errors = list(package.verification.manifest_errors)
    for artifact in package.verification.artifact_validations:
        errors.extend(f"{artifact.name}:{error}" for error in artifact.errors)
    return errors or ["artifact package verification failed"]


def _package_case_errors(package: SiteArtifactPackageEvidence, expected_case_id: str) -> List[str]:
    if package.verification is None:
        return []
    case_ids = sorted({
        str(artifact.case_id or "").strip()
        for artifact in package.verification.artifact_validations
        if artifact.ok and str(artifact.case_id or "").strip()
    })
    if not case_ids:
        return ["artifact package must include artifact case_id evidence for site acceptance"]
    mismatched = [case_id for case_id in case_ids if case_id != expected_case_id]
    if mismatched:
        return [
            "artifact package case_id must match site acceptance case_id "
            f"{expected_case_id}: {', '.join(mismatched)}"
        ]
    return []


def _read_rosservice_list(path: Optional[Path], errors: List[str]) -> Optional[List[str]]:
    if path is None:
        return None
    try:
        return path.expanduser().read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"cannot read rosservice list file: {exc}")
        return []


def _read_service_signature_file(path: Optional[Path], errors: List[str]) -> Optional[Dict[str, str]]:
    if path is None:
        return None
    try:
        return parse_service_signature_file(path.expanduser())
    except Exception as exc:
        errors.append(f"cannot read service type file: {exc}")
        return {}


def _read_service_args_file(path: Optional[Path], errors: List[str]) -> Optional[Dict[str, List[str]]]:
    if path is None:
        return None
    try:
        return parse_service_args_file(path.expanduser())
    except Exception as exc:
        errors.append(f"cannot read service args file: {exc}")
        return {}


def _acceptance_level(
    mission_profile: str,
    platform_backend: str,
    hardware_gate: Optional[HardwareGatePlan],
    rosservice_audit: Optional[Ros1GatewayServiceAudit],
) -> str:
    if mission_profile == "work_hardware":
        if (
            platform_backend == "ros1_gateway"
            and
            rosservice_audit is not None
            and rosservice_audit.ok
            and rosservice_audit.observed_service_count > 0
            and all(signature.type_ok and signature.args_ok for signature in rosservice_audit.service_signatures)
        ):
            return "work_hardware_ros1_signatures_observed"
        if (
            platform_backend == "ros1_gateway"
            and rosservice_audit is not None
            and rosservice_audit.ok
            and rosservice_audit.observed_service_count > 0
        ):
            return "work_hardware_ros1_services_observed"
        if hardware_gate is not None and hardware_gate.ok:
            return "work_hardware_pre_dispatch_ready"
        return "work_hardware_not_ready"
    if mission_profile == "home_model_lab":
        return "home_model_lab_ready_for_endpoint_probe"
    if mission_profile == "server_sim":
        return "server_sim_ready_for_replay"
    if mission_profile == "dev_mock":
        return "dev_mock_ready"
    return "unknown_profile"


def _next_commands(
    *,
    mission_profile: str,
    readiness_commands: Iterable[str],
    require_artifact_package: bool,
    require_rosservice_audit: bool,
    require_service_signatures: bool,
    platform_ids: Sequence[str],
    case_id: str,
) -> List[str]:
    commands = list(readiness_commands)
    if mission_profile in {"home_model_lab", "server_sim"}:
        commands.append("PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_artifacts.py --artifact <artifact_root> --output-dir /tmp/changxin-artifact-packages")
    if mission_profile == "work_hardware" or require_artifact_package:
        commands.append("PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py <artifact-package.tar.gz> --work-dir /tmp/changxin-artifact-verify --verification-context unit_workplace_receiving")
    if mission_profile == "work_hardware" and require_artifact_package:
        case_arg = f" --case {case_id}" if case_id else ""
        commands.append(
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py "
            f"--profile profiles/work_hardware.env --artifact-package <artifact-package.tar.gz> "
            f"--artifact-work-dir /tmp/changxin-artifact-verify --require-artifact-package{case_arg}"
        )
    if mission_profile == "work_hardware" and (require_rosservice_audit or require_service_signatures):
        platform_args = " ".join(f"--platform-id {platform_id}" for platform_id in platform_ids) or "--platform-id <platform_id>"
        commands.append(
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py "
            f"--profile <local-work-hardware-ros1-gateway.env> {platform_args} "
            "--run-rosservice-list --run-service-signatures "
            "--require-rosservice-audit --require-service-signatures"
        )
        commands.append("Alternative archive form: rosservice list/type/args > /tmp/changxin-rosservice-*.txt, then rerun with --rosservice-list-file/--service-type-file/--service-args-file")
    return _dedupe(commands)


def _dedupe(commands: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for command in commands:
        if command not in seen:
            seen.add(command)
            result.append(command)
    return result
