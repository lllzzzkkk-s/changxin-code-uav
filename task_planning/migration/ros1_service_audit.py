from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
import json
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from task_planning.config import EnvironmentProfile, load_profile


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess]


@dataclass(frozen=True)
class ExpectedGatewayService:
    platform_id: str
    mode: str
    service_name: str

    def as_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class Ros1GatewayServiceSignature:
    service_name: str
    observed_type: str
    observed_args: List[str]
    type_ok: bool
    args_ok: bool
    errors: List[str]
    warnings: List[str]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Ros1GatewayServiceAudit:
    profile_path: Path
    mission_profile: str
    platform_ids: List[str]
    expected_services: List[ExpectedGatewayService]
    observed_service_count: int
    matched_services: List[str]
    missing_services: List[str]
    unexpected_gateway_like_services: List[str]
    service_signatures: List[Ros1GatewayServiceSignature]
    validation_errors: List[str]
    warnings: List[str]
    command_environment_source: str
    next_commands: List[str]
    schema: str = "Ros1GatewayServiceAudit.v1"

    @property
    def ok(self) -> bool:
        return not self.validation_errors and not self.missing_services and all(signature.ok for signature in self.service_signatures)

    def as_dict(self) -> Dict[str, object]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "profile_path": str(self.profile_path),
            "mission_profile": self.mission_profile,
            "platform_ids": list(self.platform_ids),
            "expected_services": [service.as_dict() for service in self.expected_services],
            "observed_service_count": self.observed_service_count,
            "matched_services": list(self.matched_services),
            "missing_services": list(self.missing_services),
            "unexpected_gateway_like_services": list(self.unexpected_gateway_like_services),
            "service_signatures": [signature.as_dict() for signature in self.service_signatures],
            "validation_errors": list(self.validation_errors),
            "warnings": list(self.warnings),
            "command_environment_source": self.command_environment_source,
            "next_commands": list(self.next_commands),
        }


def audit_ros1_gateway_services(
    *,
    profile_path: Path,
    platform_ids: Iterable[str],
    observed_services: Optional[Iterable[str]] = None,
    observed_service_types: Optional[Mapping[str, str]] = None,
    observed_service_args: Optional[Mapping[str, Iterable[str]]] = None,
    command_runner: Optional[CommandRunner] = None,
    run_service_signature_checks: bool = False,
    require_service_signatures: bool = False,
    command_environment_source: Optional[str] = None,
) -> Ros1GatewayServiceAudit:
    profile = load_profile(profile_path)
    platform_id_list = [item.strip() for item in platform_ids if item.strip()]
    proof_requested = (
        observed_services is not None
        or command_runner is not None
        or observed_service_types is not None
        or observed_service_args is not None
        or run_service_signature_checks
        or require_service_signatures
    )
    errors = _validate_inputs(profile, platform_id_list, proof_requested=proof_requested)
    observed = sorted(set(_normalize_service_name(item) for item in (observed_services or []) if item.strip()))
    warnings: List[str] = []
    if observed_services is None and command_runner is not None:
        completed = command_runner(["rosservice", "list"])
        if completed.returncode == 0:
            observed = _parse_rosservice_list(completed.stdout)
        else:
            errors.append(f"rosservice list failed: {completed.stderr or completed.stdout}")
    if observed_services is None and command_runner is None:
        warnings.append("no rosservice list was provided; audit is a plan only and does not prove services exist")

    expected = _expected_services(profile, platform_id_list)
    expected_names = [service.service_name for service in expected]
    if observed:
        matched = sorted(name for name in expected_names if name in observed)
        missing = sorted(name for name in expected_names if name not in observed)
        unexpected = sorted(name for name in observed if "/gateway/" in name and name not in expected_names)
    else:
        matched = []
        missing = []
        unexpected = []
        if require_service_signatures:
            errors.append("rosservice service-name evidence is required when service signatures are required")
    observed_types = _normalize_mapping(observed_service_types or {})
    observed_args = _normalize_args_mapping(observed_service_args or {})
    if run_service_signature_checks and command_runner is not None and expected_names:
        observed_types.update(_read_service_types(expected_names, command_runner, errors))
        observed_args.update(_read_service_args(expected_names, command_runner, errors))

    signatures = [
        _signature_for_service(
            service_name=name,
            observed_type=observed_types.get(name, ""),
            observed_args=observed_args.get(name, []),
            require_service_signatures=require_service_signatures,
        )
        for name in expected_names
    ]
    for signature in signatures:
        warnings.extend(signature.warnings)

    return Ros1GatewayServiceAudit(
        profile_path=profile_path,
        mission_profile=profile.mission_profile,
        platform_ids=platform_id_list,
        expected_services=expected,
        observed_service_count=len(observed),
        matched_services=matched,
        missing_services=missing,
        unexpected_gateway_like_services=unexpected,
        service_signatures=signatures,
        validation_errors=errors,
        warnings=warnings,
        command_environment_source=_command_environment_source(
            command_environment_source=command_environment_source,
            command_runner=command_runner,
            observed_services=observed_services,
            observed_service_types=observed_service_types,
            observed_service_args=observed_service_args,
        ),
        next_commands=_next_commands(profile_path, platform_id_list, expected_names),
    )


def ros1_profile_environment(
    profile: EnvironmentProfile,
    *,
    base_env: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    if profile.ros_master_uri:
        env["ROS_MASTER_URI"] = profile.ros_master_uri
    if profile.ros_ip:
        env["ROS_IP"] = profile.ros_ip
    return env


def make_rosservice_command_runner(profile: EnvironmentProfile) -> CommandRunner:
    env = ros1_profile_environment(profile)

    def run(args: Sequence[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            list(args),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    return run


def _command_environment_source(
    *,
    command_environment_source: Optional[str],
    command_runner: Optional[CommandRunner],
    observed_services: Optional[Iterable[str]],
    observed_service_types: Optional[Mapping[str, str]],
    observed_service_args: Optional[Mapping[str, Iterable[str]]],
) -> str:
    if command_environment_source:
        return command_environment_source
    if command_runner is not None:
        return "caller_supplied"
    if observed_services is not None or observed_service_types is not None or observed_service_args is not None:
        return "captured_files"
    return "not_run"


def parse_service_signature_file(path: Path) -> Dict[str, str]:
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        data = json.loads(stripped)
        if not isinstance(data, dict):
            raise ValueError(f"service signature file must contain a JSON object: {path}")
        return {_normalize_service_name(str(key)): str(value).strip() for key, value in data.items()}

    result: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        service, _, value = line.partition(" ")
        if not value:
            service, _, value = line.partition(":")
        if not value:
            raise ValueError(f"service signature line must be '<service> <value>': {line!r}")
        result[_normalize_service_name(service)] = value.strip()
    return result


def parse_service_args_file(path: Path) -> Dict[str, List[str]]:
    raw = parse_service_signature_file(path)
    return {service: _split_args(value) for service, value in raw.items()}


def _validate_inputs(
    profile: EnvironmentProfile,
    platform_ids: List[str],
    *,
    proof_requested: bool,
) -> List[str]:
    errors: List[str] = []
    if profile.mission_profile != "work_hardware":
        errors.append("ROS1 gateway service audit requires MISSION_PROFILE=work_hardware")
    if proof_requested and profile.platform_backend != "ros1_gateway":
        errors.append("observed ROS1 gateway service proof requires PLATFORM_BACKEND=ros1_gateway profile")
    if not platform_ids:
        errors.append("at least one --platform-id is required")
    return errors


def _expected_services(profile: EnvironmentProfile, platform_ids: List[str]) -> List[ExpectedGatewayService]:
    services: List[ExpectedGatewayService] = []
    for platform_id in platform_ids:
        services.append(ExpectedGatewayService(
            platform_id=platform_id,
            mode="dry_run",
            service_name=profile.ros_gateway_dry_run_service_template.format(platform_id=platform_id),
        ))
        services.append(ExpectedGatewayService(
            platform_id=platform_id,
            mode="dispatch",
            service_name=profile.ros_gateway_dispatch_service_template.format(platform_id=platform_id),
        ))
    return services


def _read_service_types(
    service_names: Sequence[str],
    command_runner: CommandRunner,
    errors: List[str],
) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for service_name in service_names:
        completed = command_runner(["rosservice", "type", service_name])
        if completed.returncode == 0:
            result[service_name] = completed.stdout.strip().splitlines()[0].strip() if completed.stdout.strip() else ""
        else:
            errors.append(f"rosservice type {service_name} failed: {completed.stderr or completed.stdout}")
    return result


def _read_service_args(
    service_names: Sequence[str],
    command_runner: CommandRunner,
    errors: List[str],
) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for service_name in service_names:
        completed = command_runner(["rosservice", "args", service_name])
        if completed.returncode == 0:
            result[service_name] = _split_args(completed.stdout)
        else:
            errors.append(f"rosservice args {service_name} failed: {completed.stderr or completed.stdout}")
    return result


def _signature_for_service(
    *,
    service_name: str,
    observed_type: str,
    observed_args: Iterable[str],
    require_service_signatures: bool,
) -> Ros1GatewayServiceSignature:
    service_type = observed_type.strip()
    args = [item.strip() for item in observed_args if item and item.strip()]
    errors: List[str] = []
    warnings: List[str] = []

    if service_type:
        if not _is_task_command_json_type(service_type):
            errors.append(f"{service_name} type must end with TaskCommandJson, got {service_type!r}")
    elif require_service_signatures:
        errors.append(f"missing rosservice type evidence for {service_name}")
    else:
        warnings.append(f"missing rosservice type evidence for {service_name}")

    if args:
        if "task_command_json" not in args:
            errors.append(f"{service_name} args must include task_command_json, got {args!r}")
    elif require_service_signatures:
        errors.append(f"missing rosservice args evidence for {service_name}")
    else:
        warnings.append(f"missing rosservice args evidence for {service_name}")

    return Ros1GatewayServiceSignature(
        service_name=service_name,
        observed_type=service_type,
        observed_args=args,
        type_ok=bool(service_type) and _is_task_command_json_type(service_type),
        args_ok=bool(args) and "task_command_json" in args,
        errors=errors,
        warnings=warnings,
    )


def _is_task_command_json_type(service_type: str) -> bool:
    return service_type == "TaskCommandJson" or service_type.endswith("/TaskCommandJson")


def _normalize_mapping(values: Mapping[str, str]) -> Dict[str, str]:
    return {_normalize_service_name(str(key)): str(value).strip() for key, value in values.items()}


def _normalize_args_mapping(values: Mapping[str, Iterable[str]]) -> Dict[str, List[str]]:
    normalized: Dict[str, List[str]] = {}
    for key, value in values.items():
        if isinstance(value, str):
            normalized[_normalize_service_name(str(key))] = _split_args(value)
        else:
            normalized[_normalize_service_name(str(key))] = [str(item).strip() for item in value if str(item).strip()]
    return normalized


def _split_args(value: str) -> List[str]:
    return [item.strip() for item in value.replace(",", " ").split() if item.strip()]


def _parse_rosservice_list(text: str) -> List[str]:
    return sorted(set(_normalize_service_name(line) for line in text.splitlines() if line.strip()))


def _normalize_service_name(value: str) -> str:
    text = value.strip()
    if not text:
        return text
    return text if text.startswith("/") else f"/{text}"


def _next_commands(profile_path: Path, platform_ids: List[str], expected_names: List[str]) -> List[str]:
    platform_args = " ".join(f"--platform-id {platform_id}" for platform_id in platform_ids)
    commands = [
        f"PYTHONDONTWRITEBYTECODE=1 python3 tools/audit_ros1_gateway_services.py --profile {profile_path} {platform_args} --run-rosservice-list",
    ]
    if expected_names:
        commands.append(
            f"PYTHONDONTWRITEBYTECODE=1 python3 tools/audit_ros1_gateway_services.py --profile {profile_path} {platform_args} "
            "--run-rosservice-list --run-service-signatures "
            "--require-service-signatures"
        )
        commands.append(
            "Alternative archive form: rosservice list/type/args > /tmp/changxin-rosservice-*.txt, then rerun with --service-list-file/--service-type-file/--service-args-file"
        )
    return commands
