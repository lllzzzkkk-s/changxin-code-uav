from __future__ import annotations

import ast
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from task_planning.config import load_profile
from task_planning.migration.ros1_service_audit import make_rosservice_command_runner


UNIT_UGV_ROS_GATEWAY_DRY_RUN_SCHEMA = "UnitUgvRosGatewayDryRun.v1"
CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess]


@dataclass(frozen=True)
class UnitUgvRosGatewayDryRunReport:
    ok: bool
    handoff_report_path: str
    output_dir: str
    handoff_schema: str
    service_name: str
    payload_file: str
    profile_path: str
    platform_id: str
    command: List[str]
    returncode: Optional[int]
    response_schema: str
    response_mode: str
    ack_accepted: Optional[bool]
    ack_reason: str
    motion_attempted: Optional[bool]
    raw_ros_publish_attempted: Optional[bool]
    files: Dict[str, str]
    validation_errors: List[str]
    dry_run_called: bool = False
    dispatch_called: bool = False
    rostopic_pub: bool = False
    controlled_motion_authorized: bool = False
    schema: str = UNIT_UGV_ROS_GATEWAY_DRY_RUN_SCHEMA

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "handoff_report_path": self.handoff_report_path,
            "output_dir": self.output_dir,
            "handoff_schema": self.handoff_schema,
            "service_name": self.service_name,
            "payload_file": self.payload_file,
            "profile_path": self.profile_path,
            "platform_id": self.platform_id,
            "command": list(self.command),
            "returncode": self.returncode,
            "response_schema": self.response_schema,
            "response_mode": self.response_mode,
            "ack_accepted": self.ack_accepted,
            "ack_reason": self.ack_reason,
            "motion_attempted": self.motion_attempted,
            "raw_ros_publish_attempted": self.raw_ros_publish_attempted,
            "files": dict(self.files),
            "validation_errors": list(self.validation_errors),
            "dry_run_called": self.dry_run_called,
            "dispatch_called": self.dispatch_called,
            "rostopic_pub": self.rostopic_pub,
            "controlled_motion_authorized": self.controlled_motion_authorized,
        }


def run_unit_ugv_ros_gateway_dry_run(
    *,
    handoff_report_path: Path,
    output_dir: Path,
    command_runner: Optional[CommandRunner] = None,
) -> UnitUgvRosGatewayDryRunReport:
    expanded_handoff_path = handoff_report_path.expanduser().resolve()
    expanded_output_dir = output_dir.expanduser().resolve()
    expanded_output_dir.mkdir(parents=True, exist_ok=True)
    files: Dict[str, str] = {}
    validation_errors: List[str] = []

    handoff = _read_json(expanded_handoff_path, validation_errors, "handoff report")
    handoff_schema = str(handoff.get("schema") or "")
    platform_id = str(handoff.get("platform_id") or "")
    gateway_plan = handoff.get("gateway_dry_run_plan") if isinstance(handoff.get("gateway_dry_run_plan"), dict) else {}
    service_name = str(gateway_plan.get("service_name") or handoff.get("service_name") or "")
    payload_file = str(gateway_plan.get("payload_file") or "")
    profile_path = str(gateway_plan.get("profile_path") or "")

    _validate_handoff(handoff, handoff_schema, service_name, payload_file, validation_errors)
    payload_path = _resolve_payload_path(payload_file, expanded_handoff_path.parent)
    payload_text = ""
    if payload_file:
        try:
            payload_text = payload_path.read_text(encoding="utf-8").strip()
        except Exception as exc:
            validation_errors.append(f"payload file read failed: {exc}")

    command: List[str] = []
    completed: Optional[subprocess.CompletedProcess] = None
    dry_run_called = False
    response_data: Dict[str, Any] = {}
    if not validation_errors:
        command = ["rosservice", "call", service_name, payload_text]
        runner = command_runner or _profile_command_runner(profile_path, expanded_handoff_path.parent, validation_errors)
        if not validation_errors:
            completed = runner(command)
            dry_run_called = True
            files["dry_run_response_stdout"] = str(_write_text(expanded_output_dir / "dry_run_response.txt", completed.stdout or ""))
            files["dry_run_response_stderr"] = str(_write_text(expanded_output_dir / "dry_run_response.stderr.txt", completed.stderr or ""))
            if completed.returncode != 0:
                validation_errors.append(f"rosservice dry_run call failed with rc={completed.returncode}")
            response_data = _parse_gateway_response(completed.stdout or "", validation_errors)
            if response_data:
                files["dry_run_response_parsed"] = str(_write_json(
                    expanded_output_dir / "dry_run_response.parsed.json",
                    response_data,
                ))
                validation_errors.extend(_response_errors(response_data, expected_platform_id=platform_id or "ugv_0"))

    response_schema = str(response_data.get("schema") or "")
    response_mode = str(response_data.get("mode") or "")
    ack = _ack(response_data)
    report = UnitUgvRosGatewayDryRunReport(
        ok=not validation_errors,
        handoff_report_path=str(expanded_handoff_path),
        output_dir=str(expanded_output_dir),
        handoff_schema=handoff_schema,
        service_name=service_name,
        payload_file=str(payload_path) if payload_file else "",
        profile_path=str(_resolve_optional_path(profile_path, expanded_handoff_path.parent)) if profile_path else "",
        platform_id=platform_id,
        command=command,
        returncode=completed.returncode if completed is not None else None,
        response_schema=response_schema,
        response_mode=response_mode,
        ack_accepted=_ack_accepted(ack),
        ack_reason=str(ack.get("reason") or ""),
        motion_attempted=_optional_bool(response_data.get("motion_attempted")),
        raw_ros_publish_attempted=_optional_bool(response_data.get("raw_ros_publish_attempted")),
        files=files,
        validation_errors=_dedupe(validation_errors),
        dry_run_called=dry_run_called,
    )
    report_path = expanded_output_dir / "dry_run_report.json"
    files["dry_run_report"] = str(report_path)
    report = UnitUgvRosGatewayDryRunReport(
        ok=report.ok,
        handoff_report_path=report.handoff_report_path,
        output_dir=report.output_dir,
        handoff_schema=report.handoff_schema,
        service_name=report.service_name,
        payload_file=report.payload_file,
        profile_path=report.profile_path,
        platform_id=report.platform_id,
        command=report.command,
        returncode=report.returncode,
        response_schema=report.response_schema,
        response_mode=report.response_mode,
        ack_accepted=report.ack_accepted,
        ack_reason=report.ack_reason,
        motion_attempted=report.motion_attempted,
        raw_ros_publish_attempted=report.raw_ros_publish_attempted,
        files=files,
        validation_errors=report.validation_errors,
        dry_run_called=report.dry_run_called,
    )
    _write_json(report_path, report.as_dict())
    return report


def parse_unit_ugv_ros_gateway_dry_run_response_stdout(
    *,
    response_stdout_path: Path,
    output_dir: Path,
    expected_platform_id: str = "ugv_0",
    service_name: str = "/fleet/ugv_0/gateway/dry_run",
) -> UnitUgvRosGatewayDryRunReport:
    expanded_stdout_path = response_stdout_path.expanduser().resolve()
    expanded_output_dir = output_dir.expanduser().resolve()
    expanded_output_dir.mkdir(parents=True, exist_ok=True)
    files: Dict[str, str] = {
        "dry_run_response_stdout": str(expanded_stdout_path),
    }
    validation_errors: List[str] = []
    try:
        stdout = expanded_stdout_path.read_text(encoding="utf-8")
    except Exception as exc:
        stdout = ""
        validation_errors.append(f"dry_run response stdout read failed: {exc}")
    response_data = _parse_gateway_response(stdout, validation_errors) if not validation_errors else {}
    if response_data:
        files["dry_run_response_parsed"] = str(_write_json(
            expanded_output_dir / "dry_run_response.parsed.json",
            response_data,
        ))
        validation_errors.extend(_response_errors(response_data, expected_platform_id=expected_platform_id))
    ack = _ack(response_data)
    report_path = expanded_output_dir / "dry_run_report.from_stdout.json"
    files["dry_run_report"] = str(report_path)
    report = UnitUgvRosGatewayDryRunReport(
        ok=not validation_errors,
        handoff_report_path="",
        output_dir=str(expanded_output_dir),
        handoff_schema="",
        service_name=service_name,
        payload_file="",
        profile_path="",
        platform_id=expected_platform_id,
        command=[],
        returncode=None,
        response_schema=str(response_data.get("schema") or ""),
        response_mode=str(response_data.get("mode") or ""),
        ack_accepted=_ack_accepted(ack),
        ack_reason=str(ack.get("reason") or ""),
        motion_attempted=_optional_bool(response_data.get("motion_attempted")),
        raw_ros_publish_attempted=_optional_bool(response_data.get("raw_ros_publish_attempted")),
        files=files,
        validation_errors=_dedupe(validation_errors),
        dry_run_called=False,
    )
    _write_json(report_path, report.as_dict())
    return report


def _default_command_runner(args: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args),
        check=False,
        capture_output=True,
        text=True,
    )


def _profile_command_runner(
    profile_path: str,
    base_dir: Path,
    errors: List[str],
) -> CommandRunner:
    if not profile_path:
        return _default_command_runner
    resolved = _resolve_optional_path(profile_path, base_dir)
    try:
        profile = load_profile(resolved)
    except Exception as exc:
        errors.append(f"ros1 gateway profile parse failed: {exc}")
        return _default_command_runner
    return make_rosservice_command_runner(profile)


def _validate_handoff(
    handoff: Mapping[str, Any],
    handoff_schema: str,
    service_name: str,
    payload_file: str,
    errors: List[str],
) -> None:
    if handoff_schema != "UnitUgvObjectApproachRosReadyHandoff.v1":
        errors.append("handoff report schema must be UnitUgvObjectApproachRosReadyHandoff.v1")
    if not handoff.get("ok"):
        errors.append("handoff report must have ok=true")
    if not handoff.get("ros_ready"):
        errors.append("handoff report must have ros_ready=true")
    if handoff.get("next_runtime_stage") != "4060_ros1_gateway_dry_run":
        errors.append("handoff next_runtime_stage must be 4060_ros1_gateway_dry_run")
    if not service_name:
        errors.append("handoff gateway dry-run service_name is required")
    elif "/gateway/dry_run" not in service_name or "/gateway/dispatch" in service_name:
        errors.append("handoff service_name must target /gateway/dry_run and never /gateway/dispatch")
    if not payload_file:
        errors.append("handoff gateway dry-run payload_file is required")


def _parse_gateway_response(stdout: str, errors: List[str]) -> Dict[str, Any]:
    stripped = stdout.strip()
    if not stripped:
        errors.append("rosservice dry_run stdout is empty")
        return {}
    direct = _json_object(stripped)
    if direct is not None:
        return direct
    for value in _response_json_values(stripped):
        decoded = _decode_response_json_value(value)
        if decoded is not None:
            return decoded
    decoded = _decode_embedded_gateway_json(stripped)
    if decoded is not None:
        return decoded
    errors.append("rosservice dry_run stdout did not contain GatewayServiceResponse.v1 JSON")
    return {}


def _response_json_values(stdout: str) -> List[str]:
    lines = stdout.splitlines()
    values: List[str] = []
    for index, line in enumerate(lines):
        if "response_json:" not in line:
            continue
        raw_value = line.split("response_json:", 1)[1].strip()
        continuation: List[str] = []
        for next_line in lines[index + 1:]:
            if next_line.strip() and not next_line[:1].isspace():
                break
            continuation.append(next_line.strip())
        block_markers = {">", "|", ">-", "|-", ">+", "|+"}
        if raw_value in block_markers:
            values.extend(_value_variants(continuation))
        else:
            values.extend(_value_variants([raw_value] + continuation))
    return [value for value in values if value.strip()]


def _value_variants(parts: List[str]) -> List[str]:
    compact_parts = [part for part in parts if part != ""]
    variants = [
        "\n".join(compact_parts).strip(),
        "".join(compact_parts).strip(),
        " ".join(compact_parts).strip(),
        _yaml_double_quoted_line_continuation_variant(compact_parts),
    ]
    if _looks_like_yaml_line_continuation(compact_parts):
        variants.insert(0, variants.pop())
    return _dedupe(variants)


def _yaml_double_quoted_line_continuation_variant(parts: List[str]) -> str:
    value = ""
    for part in parts:
        current = part.strip()
        if not current:
            continue
        if value.endswith("\\"):
            value = value[:-1] + current.lstrip()
        elif value:
            value = f"{value} {current.lstrip()}"
        else:
            value = current
    return value.replace("\\ ", " ").strip()


def _looks_like_yaml_line_continuation(parts: List[str]) -> bool:
    return any(part.rstrip().endswith("\\") for part in parts)


def _decode_response_json_value(value: str) -> Optional[Dict[str, Any]]:
    value = value.strip()
    if not value:
        return None
    parsed = _json_object(value)
    if parsed is not None:
        return parsed
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, str):
        parsed = _json_object(decoded)
        if parsed is not None:
            return parsed
    try:
        literal = ast.literal_eval(value)
    except Exception:
        return None
    if isinstance(literal, str):
        return _json_object(literal)
    return None


def _decode_embedded_gateway_json(text: str) -> Optional[Dict[str, Any]]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        for candidate in (text[index:], _unescaped_candidate(text[index:])):
            try:
                data, _ = decoder.raw_decode(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("schema") == "GatewayServiceResponse.v1":
                return data
    return None


def _unescaped_candidate(text: str) -> str:
    return text.replace('\\"', '"').replace("\\n", "")


def _json_object(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _response_errors(response: Mapping[str, Any], *, expected_platform_id: str) -> List[str]:
    errors: List[str] = []
    if response.get("schema") != "GatewayServiceResponse.v1":
        errors.append("dry_run response schema must be GatewayServiceResponse.v1")
    if response.get("mode") != "dry_run":
        errors.append("dry_run response mode must be dry_run")
    if response.get("platform_id") != expected_platform_id:
        errors.append("dry_run response platform_id must match handoff platform_id")
    if response.get("motion_attempted") is not False:
        errors.append("dry_run response must report motion_attempted=false")
    if response.get("raw_ros_publish_attempted") is not False:
        errors.append("dry_run response must report raw_ros_publish_attempted=false")
    ack = _ack(response)
    if ack.get("schema") not in {"", "CommandAck.v1"}:
        errors.append("dry_run response ack schema must be CommandAck.v1")
    if ack.get("accepted") is not True:
        errors.append("dry_run response ack.accepted must be true")
    return errors


def _ack(response: Mapping[str, Any]) -> Mapping[str, Any]:
    ack = response.get("ack")
    if isinstance(ack, Mapping):
        return ack
    return {
        "schema": response.get("ack_schema") or "",
        "accepted": response.get("ack_accepted"),
        "reason": response.get("ack_reason") or "",
    }


def _ack_accepted(ack: Mapping[str, Any]) -> Optional[bool]:
    accepted = ack.get("accepted")
    return accepted if isinstance(accepted, bool) else None


def _optional_bool(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _resolve_payload_path(payload_file: str, base_dir: Path) -> Path:
    path = Path(payload_file).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _resolve_optional_path(path_text: str, base_dir: Path) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _read_json(path: Path, errors: List[str], label: str) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{label} parse failed: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} must be a JSON object")
        return {}
    return data


def _write_json(path: Path, data: Dict[str, Any]) -> Path:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _dedupe(values: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
