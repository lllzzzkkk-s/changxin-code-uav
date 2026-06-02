from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from task_planning.config import EnvironmentProfile, load_profile
from task_planning.contracts import CapabilityRegistry, TaskSchema, validate_mission_request
from task_planning.migration.machine_identity import current_machine_id, hashed_machine_id_errors
from task_planning.mission_ops.golden_cases import golden_case_by_id
from task_planning.mission_ops.http_model_client import OpenAICompatibleModelClient
from task_planning.mission_ops.mock_llm_client import MockLLMClient
from task_planning.mission_ops.model_client import NeedsClarification


TARGET_HOME_GPU_MARKER = "5090"


@dataclass(frozen=True)
class ModelLabDiff:
    path: str
    baseline: Any
    model: Any

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelLabEvaluation:
    case_id: str
    output_dir: Path
    profile_path: Path
    ok: bool
    baseline_equivalent: bool
    validation_errors: List[str]
    diffs: List[ModelLabDiff]
    mission_profile: str
    model_provider: str
    model_name: str
    model_base_url: str
    model_lab_evidence_kind: str
    platform_backend: str
    machine_id: str
    accelerator_probe: Mapping[str, Any]
    schema: str = "ModelLabEvaluation.v1"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "case_id": self.case_id,
            "output_dir": str(self.output_dir),
            "profile_path": str(self.profile_path),
            "baseline_equivalent": self.baseline_equivalent,
            "validation_errors": list(self.validation_errors),
            "diffs": [diff.as_dict() for diff in self.diffs],
            "mission_profile": self.mission_profile,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "model_base_url": self.model_base_url,
            "model_lab_evidence_kind": self.model_lab_evidence_kind,
            "platform_backend": self.platform_backend,
            "machine_id": self.machine_id,
            "accelerator_probe": dict(self.accelerator_probe),
        }


def evaluate_model_lab_case(
    *,
    profile_path: Path,
    case_id: str,
    output_dir: Path,
    require_baseline_equivalence: bool = False,
    accelerator_probe: Optional[Mapping[str, Any]] = None,
) -> ModelLabEvaluation:
    profile = load_profile(profile_path)
    mission_case = golden_case_by_id(case_id)
    output_dir = output_dir.resolve() / case_id
    output_dir.mkdir(parents=True, exist_ok=True)
    validation_errors = _profile_boundary_errors(profile)
    accelerator_probe = dict(accelerator_probe or probe_accelerators())
    if profile.model_lab_evidence_kind == "home_5090_live":
        validation_errors.extend(_home_5090_accelerator_errors(accelerator_probe))

    baseline_schema = MockLLMClient().compile_task_schema(mission_case.intent, mission_case.context_snapshot)
    _write_json(output_dir / "environment_profile.json", profile.as_dict())
    _write_json(output_dir / "mission_input.json", {
        "schema": "ModelLabMissionInput.v1",
        "case_id": mission_case.case_id,
        "intent": mission_case.intent,
        "context_snapshot": dict(mission_case.context_snapshot),
    })
    _write_json(output_dir / "baseline_task_schema.json", baseline_schema.as_dict())

    model_schema: Optional[TaskSchema] = None
    if not validation_errors:
        try:
            result = OpenAICompatibleModelClient.from_profile(profile).compile_task_schema(
                mission_case.intent,
                mission_case.context_snapshot,
            )
        except Exception as exc:  # pragma: no cover - exact urllib exception depends on runtime
            validation_errors.append(f"model endpoint call failed: {exc}")
        else:
            if isinstance(result, NeedsClarification):
                validation_errors.append("model returned NeedsClarification")
                _write_json(output_dir / "model_needs_clarification.json", result.as_dict())
            else:
                model_schema = result
                _write_json(output_dir / "model_task_schema.json", model_schema.as_dict())
                validation_errors.extend(validate_mission_request(
                    model_schema.mission_request,
                    CapabilityRegistry.scout_and_confirm_default(),
                ))

    diffs = _mission_request_diffs(baseline_schema, model_schema) if model_schema else []
    baseline_equivalent = model_schema is not None and not diffs
    if require_baseline_equivalence and not baseline_equivalent:
        validation_errors.append("model task schema differs from mock baseline")

    evaluation = ModelLabEvaluation(
        case_id=case_id,
        output_dir=output_dir,
        profile_path=profile_path,
        ok=not validation_errors,
        baseline_equivalent=baseline_equivalent,
        validation_errors=validation_errors,
        diffs=diffs,
        mission_profile=profile.mission_profile,
        model_provider=profile.model_provider,
        model_name=profile.model_name,
        model_base_url=profile.model_base_url,
        model_lab_evidence_kind=profile.model_lab_evidence_kind,
        platform_backend=profile.platform_backend,
        machine_id=current_machine_id(),
        accelerator_probe=accelerator_probe,
    )
    _write_json(output_dir / "model_lab_evaluation.json", evaluation.as_dict())
    return evaluation


def probe_accelerators() -> Dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except FileNotFoundError:
        return _accelerator_probe_result(
            ok=False,
            command=command,
            gpus=[],
            errors=["nvidia-smi is not available"],
        )
    except subprocess.TimeoutExpired:
        return _accelerator_probe_result(
            ok=False,
            command=command,
            gpus=[],
            errors=["nvidia-smi timed out"],
        )

    gpus = _parse_nvidia_smi_csv(completed.stdout.splitlines()) if completed.returncode == 0 else []
    errors = [] if completed.returncode == 0 else [
        f"nvidia-smi exited with {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}"
    ]
    if completed.returncode == 0 and not gpus:
        errors.append("nvidia-smi returned no GPUs")
    return _accelerator_probe_result(
        ok=completed.returncode == 0 and bool(gpus),
        command=command,
        gpus=gpus,
        errors=errors,
    )


def model_lab_home_5090_live_errors(report: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    if report.get("schema") != "ModelLabEvaluation.v1":
        errors.append("schema must be ModelLabEvaluation.v1")
    if report.get("ok") is not True:
        errors.append("ok must be true")
    if report.get("mission_profile") != "home_model_lab":
        errors.append("mission_profile must be home_model_lab")
    if report.get("model_provider") != "local_http":
        errors.append("model_provider must be local_http")
    if report.get("platform_backend") != "mock":
        errors.append("platform_backend must be mock")
    if report.get("model_lab_evidence_kind") != "home_5090_live":
        errors.append("model_lab_evidence_kind must be home_5090_live")
    if not str(report.get("model_name") or "").strip():
        errors.append("model_name is required")
    if not str(report.get("model_base_url") or "").strip():
        errors.append("model_base_url is required")
    errors.extend(hashed_machine_id_errors(report.get("machine_id"), "machine_id"))
    if not str(report.get("case_id") or "").strip():
        errors.append("case_id is required")
    if not isinstance(report.get("baseline_equivalent"), bool):
        errors.append("baseline_equivalent must be a boolean")
    diffs = report.get("diffs")
    if not isinstance(diffs, list):
        errors.append("diffs must be a list")
    elif report.get("baseline_equivalent") is True and diffs:
        errors.append("diffs must be empty when baseline_equivalent=true")
    elif report.get("baseline_equivalent") is False and not diffs:
        errors.append("diffs must describe at least one difference when baseline_equivalent=false")
    validation_errors = report.get("validation_errors")
    if not isinstance(validation_errors, list):
        errors.append("validation_errors must be a list")
    elif validation_errors:
        errors.append("validation_errors must be empty when ok=true")
    errors.extend(_home_5090_accelerator_errors(report.get("accelerator_probe")))
    return errors


def accelerator_probe_has_home_5090(probe: Any) -> bool:
    if not isinstance(probe, Mapping):
        return False
    if probe.get("schema") != "AcceleratorProbe.v1" or probe.get("ok") is not True:
        return False
    gpus = probe.get("gpus")
    if not isinstance(gpus, Sequence) or isinstance(gpus, (str, bytes)):
        return False
    for gpu in gpus:
        if not isinstance(gpu, Mapping):
            continue
        name = str(gpu.get("name") or "").lower()
        if "rtx" in name and TARGET_HOME_GPU_MARKER in name:
            return True
    return False


def _home_5090_accelerator_errors(probe: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(probe, Mapping):
        return ["accelerator_probe is required for home_5090_live evidence"]
    if probe.get("schema") != "AcceleratorProbe.v1":
        errors.append("accelerator_probe.schema must be AcceleratorProbe.v1")
    if probe.get("ok") is not True:
        errors.append("accelerator_probe.ok must be true")
    if probe.get("source") != "nvidia-smi":
        errors.append("accelerator_probe.source must be nvidia-smi")
    command = probe.get("command")
    if not isinstance(command, Sequence) or isinstance(command, (str, bytes)) or not command:
        errors.append("accelerator_probe.command must be a non-empty list")
    elif str(command[0]) != "nvidia-smi":
        errors.append("accelerator_probe.command must run nvidia-smi")
    probe_errors = probe.get("errors")
    if not isinstance(probe_errors, list):
        errors.append("accelerator_probe.errors must be a list")
    elif probe_errors:
        errors.append("accelerator_probe.errors must be empty")
    if not accelerator_probe_has_home_5090(probe):
        errors.append("accelerator_probe must include an RTX 5090 GPU")
    return errors


def _accelerator_probe_result(
    *,
    ok: bool,
    command: Sequence[str],
    gpus: Sequence[Mapping[str, Any]],
    errors: Sequence[str],
) -> Dict[str, Any]:
    return {
        "schema": "AcceleratorProbe.v1",
        "ok": ok,
        "source": "nvidia-smi",
        "command": list(command),
        "gpus": [dict(gpu) for gpu in gpus],
        "errors": list(errors),
    }


def _parse_nvidia_smi_csv(lines: Sequence[str]) -> List[Dict[str, Any]]:
    gpus: List[Dict[str, Any]] = []
    for line in lines:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        gpus.append({
            "name": parts[0],
            "memory_total": parts[1],
            "driver_version": parts[2],
        })
    return gpus


def _profile_boundary_errors(profile: EnvironmentProfile) -> List[str]:
    errors: List[str] = []
    if profile.mission_profile != "home_model_lab":
        errors.append("model-lab evaluation requires MISSION_PROFILE=home_model_lab")
    if profile.platform_backend != "mock":
        errors.append("model-lab evaluation must keep PLATFORM_BACKEND=mock")
    return errors


def _mission_request_diffs(baseline: TaskSchema, model: Optional[TaskSchema]) -> List[ModelLabDiff]:
    if model is None:
        return []
    baseline_request = baseline.mission_request.as_dict()
    model_request = model.mission_request.as_dict()
    keys = sorted(set(baseline_request) | set(model_request))
    return [
        ModelLabDiff(path=f"mission_request.{key}", baseline=baseline_request.get(key), model=model_request.get(key))
        for key in keys
        if baseline_request.get(key) != model_request.get(key)
    ]


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
