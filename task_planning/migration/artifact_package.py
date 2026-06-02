from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from task_planning.migration.machine_identity import (
    current_machine_id,
    hashed_machine_id_errors,
    resolve_hashed_machine_id,
)
from task_planning.mission_ops.artifacts import ARTIFACT_FILENAMES
from task_planning.mission_ops.replay import load_artifact_bundle


ARTIFACT_PACKAGE_MANIFEST_SCHEMA = "TaskPlanningArtifactPackageManifest.v1"
ARTIFACT_PACKAGE_VERIFICATION_SCHEMA = "TaskPlanningArtifactPackageVerification.v1"
ARTIFACT_PACKAGE_VERIFICATION_SET_SCHEMA = "TaskPlanningArtifactPackageVerificationSet.v1"
ALLOWED_VERIFICATION_CONTEXTS = {"unspecified", "source_machine", "receiving_machine", "unit_workplace_receiving"}


@dataclass(frozen=True)
class ArtifactPackage:
    root: Path
    archive: Path
    manifest: Path
    artifact_count: int
    file_count: int
    source_machine_id: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "schema": "TaskPlanningArtifactPackage.v1",
            "root": str(self.root),
            "archive": str(self.archive),
            "manifest": str(self.manifest),
            "artifact_count": self.artifact_count,
            "file_count": self.file_count,
            "source_machine_id": self.source_machine_id,
        }


@dataclass(frozen=True)
class ArtifactValidation:
    name: str
    kind: str
    path: Path
    case_id: str = ""
    metadata: Dict[str, object] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok,
            "name": self.name,
            "kind": self.kind,
            "path": str(self.path),
            "case_id": self.case_id,
            "metadata": dict(self.metadata),
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class ArtifactPackageVerification:
    archive: Path
    extract_dir: Path
    package_root: Path
    checked_files: int
    manifest_errors: List[str] = field(default_factory=list)
    artifact_validations: List[ArtifactValidation] = field(default_factory=list)
    verification_context: str = "unspecified"
    source_machine_id: str = ""
    verifier_machine_id: str = ""
    schema: str = ARTIFACT_PACKAGE_VERIFICATION_SCHEMA

    @property
    def ok(self) -> bool:
        return not self.manifest_errors and all(item.ok for item in self.artifact_validations)

    def as_dict(self) -> Dict[str, object]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "archive": str(self.archive),
            "extract_dir": str(self.extract_dir),
            "package_root": str(self.package_root),
            "checked_files": self.checked_files,
            "manifest_errors": list(self.manifest_errors),
            "artifact_validations": [item.as_dict() for item in self.artifact_validations],
            "verification_context": self.verification_context,
            "source_machine_id": self.source_machine_id,
            "verifier_machine_id": self.verifier_machine_id,
        }


def build_artifact_package(
    *,
    artifact_paths: Sequence[Path],
    output_dir: Path,
    package_name: str = "task-planning-artifacts",
    source_machine_id: Optional[str] = None,
) -> ArtifactPackage:
    if not artifact_paths:
        raise ValueError("at least one artifact path is required")

    resolved_source_machine_id = resolve_hashed_machine_id(source_machine_id, "source_machine_id")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    package_root = output_dir / package_name
    if package_root.exists():
        shutil.rmtree(package_root)
    package_root.mkdir(parents=True)
    artifacts_root = package_root / "artifacts"
    artifacts_root.mkdir()

    artifact_entries: List[Dict[str, object]] = []
    packaged_files: List[str] = []
    used_names: Set[str] = set()
    for source in artifact_paths:
        source = source.expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"artifact path does not exist: {source}")
        if not source.is_dir():
            raise ValueError(f"artifact path must be a directory: {source}")
        kind = classify_artifact_dir(source)
        name = _unique_name(_slug(source.name), used_names)
        target_rel = Path("artifacts") / name
        target = package_root / target_rel
        copied = _copy_regular_tree(source, target, package_root)
        packaged_files.extend(copied)
        artifact_entries.append({
            "name": name,
            "kind": kind,
            "source_path": str(source),
            "packaged_path": target_rel.as_posix(),
            "files": copied,
        })

    readme_path = package_root / "ARTIFACT_PACKAGE.md"
    readme_path.write_text(_package_doc(artifact_entries), encoding="utf-8")
    packaged_files = ["ARTIFACT_PACKAGE.md"] + sorted(packaged_files)

    manifest_data = _manifest(
        package_name=package_name,
        package_root=package_root,
        artifact_entries=artifact_entries,
        rel_files=packaged_files,
        source_machine_id=resolved_source_machine_id,
    )
    manifest_path = package_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2, sort_keys=True), encoding="utf-8")

    archive_path = output_dir / f"{package_name}.tar.gz"
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(package_root, arcname=package_name)

    return ArtifactPackage(
        root=package_root,
        archive=archive_path,
        manifest=manifest_path,
        artifact_count=len(artifact_entries),
        file_count=len(packaged_files),
        source_machine_id=str(manifest_data["source_machine_id"]),
    )


def classify_artifact_dir(path: Path) -> str:
    filenames = {item.name for item in path.iterdir() if item.is_file()}
    required_mission_files = set(ARTIFACT_FILENAMES)
    legacy_mission_files = required_mission_files - {"execution_events.json"}
    if required_mission_files.issubset(filenames) or legacy_mission_files.issubset(filenames):
        return "mission_run"
    if {
        "environment_profile.json",
        "mission_input.json",
        "baseline_task_schema.json",
        "model_lab_evaluation.json",
    }.issubset(filenames):
        return "model_lab_evaluation"
    raise ValueError(f"unsupported artifact directory shape: {path}")


def verify_artifact_package(
    *,
    archive_path: Path,
    work_dir: Optional[Path] = None,
    verification_context: str = "unspecified",
) -> ArtifactPackageVerification:
    if verification_context not in ALLOWED_VERIFICATION_CONTEXTS:
        raise ValueError(f"unsupported artifact verification context: {verification_context}")
    archive_path = archive_path.resolve()
    if work_dir is None:
        extract_dir = Path(tempfile.mkdtemp(prefix="task-planning-artifacts-verify-")).resolve()
    else:
        work_dir = work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        extract_dir = Path(tempfile.mkdtemp(prefix="extract-", dir=str(work_dir))).resolve()

    package_root = extract_artifact_package(archive_path, extract_dir)
    manifest, manifest_errors = _load_manifest(package_root)
    source_machine_id = str(manifest.get("source_machine_id") or "") if isinstance(manifest, Mapping) else ""
    verifier_machine_id = current_machine_id()
    manifest_errors.extend(_machine_transfer_errors(
        verification_context=verification_context,
        source_machine_id=source_machine_id,
        verifier_machine_id=verifier_machine_id,
    ))
    checked_files = 0
    artifact_validations: List[ArtifactValidation] = []

    if not manifest_errors:
        checked_files, file_errors = _verify_manifest_files(package_root, manifest)
        manifest_errors.extend(file_errors)
        artifact_validations = _validate_manifest_artifacts(package_root, manifest)

    return ArtifactPackageVerification(
        archive=archive_path,
        extract_dir=extract_dir,
        package_root=package_root,
        checked_files=checked_files,
        manifest_errors=manifest_errors,
        artifact_validations=artifact_validations,
        verification_context=verification_context,
        source_machine_id=source_machine_id,
        verifier_machine_id=verifier_machine_id,
    )


def extract_artifact_package(archive_path: Path, extract_dir: Path) -> Path:
    archive_path = archive_path.resolve()
    extract_dir = extract_dir.resolve()
    extract_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "r:gz") as tar:
        members = tar.getmembers()
        if not members:
            raise ValueError("artifact package is empty")
        top_levels = set()
        for member in members:
            _validate_tar_member(member, extract_dir)
            path = PurePosixPath(member.name)
            if path.parts:
                top_levels.add(path.parts[0])
        if len(top_levels) != 1:
            raise ValueError(f"artifact package must contain one top-level directory, got {sorted(top_levels)}")
        tar.extractall(extract_dir)
    return extract_dir / sorted(top_levels)[0]


def _manifest(
    *,
    package_name: str,
    package_root: Path,
    artifact_entries: Sequence[Mapping[str, object]],
    rel_files: Iterable[str],
    source_machine_id: str,
) -> Dict[str, object]:
    files = []
    for rel_path in rel_files:
        path = package_root / rel_path
        files.append({
            "path": rel_path,
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        })
    return {
        "schema": ARTIFACT_PACKAGE_MANIFEST_SCHEMA,
        "package_name": package_name,
        "source_machine_id": source_machine_id,
        "artifacts": list(artifact_entries),
        "files": files,
        "commands": {
            "verify_artifacts": "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py <artifact-package.tar.gz> --work-dir /tmp/changxin-artifact-verify --verification-context unit_workplace_receiving",
            "verify_artifacts_after_transfer": "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py <artifact-package.tar.gz> --work-dir /tmp/changxin-artifact-verify --verification-context unit_workplace_receiving",
            "verify_artifacts_on_source": "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py <artifact-package.tar.gz> --work-dir /tmp/changxin-artifact-verify --verification-context source_machine",
            "prevalidated_schema_replay": "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_prevalidated_task_schema.py --profile profiles/work_hardware.env --task-schema <verified_package>/artifacts/<model_lab>/model_task_schema.json --case <lane-matrix-case-id> --artifact-root /tmp/changxin-prevalidated-runs",
            "work_hardware_gate": "PYTHONDONTWRITEBYTECODE=1 python3 tools/plan_work_hardware_gate.py --profile profiles/work_hardware.env --through-stage mock_gateway_dispatch",
        },
    }


def _copy_regular_tree(source: Path, target: Path, package_root: Path) -> List[str]:
    target.mkdir(parents=True)
    rel_files: List[str] = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"artifact package does not accept symlinks: {path}")
        if not path.is_file():
            continue
        rel_source = path.relative_to(source)
        rel_target = target.relative_to(package_root) / rel_source
        destination = package_root / rel_target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        rel_files.append(rel_target.as_posix())
    return sorted(rel_files)


def _load_manifest(package_root: Path) -> Tuple[Dict[str, Any], List[str]]:
    manifest_path = package_root / "manifest.json"
    if not manifest_path.exists():
        return {}, ["missing manifest.json"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"invalid manifest.json: {exc}"]
    errors: List[str] = []
    if manifest.get("schema") != ARTIFACT_PACKAGE_MANIFEST_SCHEMA:
        errors.append(f"unexpected manifest schema: {manifest.get('schema')!r}")
    errors.extend(hashed_machine_id_errors(manifest.get("source_machine_id"), "manifest source_machine_id"))
    if not isinstance(manifest.get("files"), list):
        errors.append("manifest files must be a list")
    if not isinstance(manifest.get("artifacts"), list):
        errors.append("manifest artifacts must be a list")
    return manifest, errors


def _machine_transfer_errors(
    *,
    verification_context: str,
    source_machine_id: str,
    verifier_machine_id: str,
) -> List[str]:
    if verification_context not in {"receiving_machine", "unit_workplace_receiving"}:
        return []
    errors = [
        *hashed_machine_id_errors(source_machine_id, "source_machine_id"),
        *hashed_machine_id_errors(verifier_machine_id, "verifier_machine_id"),
    ]
    if source_machine_id and verifier_machine_id and source_machine_id == verifier_machine_id:
        errors.append(
            "receiving-machine artifact verification must run on a different machine than the source; "
            "use verification_context=source_machine for local sanity checks"
        )
    return errors


def _verify_manifest_files(package_root: Path, manifest: Mapping[str, Any]) -> Tuple[int, List[str]]:
    errors: List[str] = []
    checked_files = 0
    files = manifest.get("files") or []
    for index, item in enumerate(files):
        if not isinstance(item, Mapping):
            errors.append(f"files[{index}] must be an object")
            continue
        rel_path = item.get("path")
        if not isinstance(rel_path, str):
            errors.append(f"files[{index}].path must be a string")
            continue
        if not _is_safe_relative_posix_path(rel_path):
            errors.append(f"unsafe manifest path: {rel_path!r}")
            continue
        path = package_root / Path(rel_path)
        if not _is_within(path, package_root):
            errors.append(f"manifest path escapes package root: {rel_path!r}")
            continue
        if not path.exists():
            errors.append(f"missing file: {rel_path}")
            continue
        if not path.is_file():
            errors.append(f"not a regular file: {rel_path}")
            continue
        checked_files += 1
        expected_bytes = item.get("bytes")
        actual_bytes = path.stat().st_size
        if expected_bytes != actual_bytes:
            errors.append(f"bytes mismatch for {rel_path}: expected {expected_bytes}, got {actual_bytes}")
        expected_sha = item.get("sha256")
        actual_sha = _sha256(path)
        if expected_sha != actual_sha:
            errors.append(f"sha256 mismatch for {rel_path}: expected {expected_sha}, got {actual_sha}")
    return checked_files, errors


def _validate_manifest_artifacts(package_root: Path, manifest: Mapping[str, Any]) -> List[ArtifactValidation]:
    validations: List[ArtifactValidation] = []
    for index, item in enumerate(manifest.get("artifacts") or []):
        if not isinstance(item, Mapping):
            validations.append(ArtifactValidation(
                name=f"artifacts[{index}]",
                kind="unknown",
                path=package_root,
                errors=[f"artifacts[{index}] must be an object"],
            ))
            continue
        name = str(item.get("name") or f"artifacts[{index}]")
        kind = str(item.get("kind") or "unknown")
        packaged_path = item.get("packaged_path")
        if not isinstance(packaged_path, str) or not _is_safe_relative_posix_path(packaged_path):
            validations.append(ArtifactValidation(
                name=name,
                kind=kind,
                path=package_root,
                errors=[f"unsafe packaged_path: {packaged_path!r}"],
            ))
            continue
        root = package_root / Path(packaged_path)
        if not _is_within(root, package_root) or not root.exists() or not root.is_dir():
            validations.append(ArtifactValidation(
                name=name,
                kind=kind,
                path=root,
                errors=[f"artifact directory is missing or unsafe: {packaged_path!r}"],
            ))
            continue
        if kind == "mission_run":
            validation = load_artifact_bundle(root)
            case_id = _mission_run_case_id(validation.data)
            errors = list(validation.validation_errors)
            if not case_id:
                errors.append("mission_run artifact case_id is required")
            validations.append(ArtifactValidation(
                name=name,
                kind=kind,
                path=root,
                case_id=case_id,
                errors=errors,
            ))
        elif kind == "model_lab_evaluation":
            errors, case_id, metadata = _validate_model_lab_artifact(root)
            validations.append(ArtifactValidation(
                name=name,
                kind=kind,
                path=root,
                case_id=case_id,
                metadata=metadata,
                errors=errors,
            ))
        else:
            validations.append(ArtifactValidation(
                name=name,
                kind=kind,
                path=root,
                errors=[f"unsupported artifact kind: {kind}"],
            ))
    return validations


def _validate_model_lab_artifact(root: Path) -> Tuple[List[str], str, Dict[str, object]]:
    errors: List[str] = []
    required_schemas = {
        "environment_profile.json": "EnvironmentProfile.v1",
        "mission_input.json": "ModelLabMissionInput.v1",
        "baseline_task_schema.json": "TaskSchema.v1",
        "model_lab_evaluation.json": "ModelLabEvaluation.v1",
    }
    documents: Dict[str, Dict[str, Any]] = {}
    for filename, schema in required_schemas.items():
        data = _read_json(root / filename, errors)
        if data is None:
            continue
        documents[filename] = data
        if data.get("schema") != schema:
            errors.append(f"{filename} must be {schema}")

    profile = documents.get("environment_profile.json") or {}
    mission_input = documents.get("mission_input.json") or {}
    evaluation = documents.get("model_lab_evaluation.json") or {}
    metadata = _model_lab_artifact_metadata(evaluation)
    mission_input_case_id = str(mission_input.get("case_id") or "").strip()
    evaluation_case_id = str(evaluation.get("case_id") or "").strip()
    if not mission_input_case_id:
        errors.append("mission_input.json case_id is required")
    if not evaluation_case_id:
        errors.append("model_lab_evaluation.json case_id is required")
    if mission_input_case_id and evaluation_case_id and mission_input_case_id != evaluation_case_id:
        errors.append("model_lab_evaluation.json case_id must match mission_input.json")
    if profile and evaluation:
        for key in ("mission_profile", "model_provider", "platform_backend"):
            if profile.get(key) != evaluation.get(key):
                errors.append(f"model_lab_evaluation.json {key} must match environment_profile.json")
        if profile.get("platform_backend") != "mock":
            errors.append("model_lab artifact must keep PLATFORM_BACKEND=mock")
        if evaluation.get("ok") is True:
            if not isinstance(evaluation.get("baseline_equivalent"), bool):
                errors.append("model_lab_evaluation.json baseline_equivalent must be a boolean")
            if not isinstance(evaluation.get("diffs"), list):
                errors.append("model_lab_evaluation.json diffs must be a list")
            if evaluation.get("validation_errors") not in ([], None):
                errors.append("model_lab_evaluation.json validation_errors must be empty when ok=true")

    baseline_schema = documents.get("baseline_task_schema.json") or {}
    model_task_schema = root / "model_task_schema.json"
    model_schema: Dict[str, Any] = {}
    if model_task_schema.exists():
        data = _read_json(model_task_schema, errors)
        if data is not None:
            model_schema = data
            if data.get("schema") != "TaskSchema.v1":
                errors.append("model_task_schema.json must be TaskSchema.v1")
    elif evaluation.get("ok") is True:
        errors.append("model_task_schema.json is required when model_lab_evaluation ok=true")

    if evaluation.get("ok") is True and baseline_schema and model_schema:
        expected_diffs = _task_schema_diffs(baseline_schema, model_schema)
        baseline_equivalent = evaluation.get("baseline_equivalent")
        if baseline_equivalent != (not expected_diffs):
            errors.append("model_lab_evaluation.json baseline_equivalent must match baseline/model schema diff")
        if evaluation.get("diffs") != expected_diffs:
            errors.append("model_lab_evaluation.json diffs must match baseline/model schema diff")
    return errors, mission_input_case_id or evaluation_case_id, metadata


def _model_lab_artifact_metadata(evaluation: Mapping[str, Any]) -> Dict[str, object]:
    diffs = evaluation.get("diffs")
    validation_errors = evaluation.get("validation_errors")
    probe = evaluation.get("accelerator_probe")
    return {
        "mission_profile": str(evaluation.get("mission_profile") or ""),
        "model_provider": str(evaluation.get("model_provider") or ""),
        "model_name": str(evaluation.get("model_name") or ""),
        "model_lab_evidence_kind": str(evaluation.get("model_lab_evidence_kind") or ""),
        "platform_backend": str(evaluation.get("platform_backend") or ""),
        "machine_id": str(evaluation.get("machine_id") or ""),
        "baseline_equivalent": evaluation.get("baseline_equivalent"),
        "diff_count": len(diffs) if isinstance(diffs, list) else 0,
        "validation_error_count": len(validation_errors) if isinstance(validation_errors, list) else 0,
        "accelerator_probe_ok": bool(isinstance(probe, Mapping) and probe.get("ok") is True),
    }


def _task_schema_diffs(
    baseline_schema: Mapping[str, Any],
    model_schema: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    baseline_request = baseline_schema.get("mission_request")
    model_request = model_schema.get("mission_request")
    if not isinstance(baseline_request, Mapping):
        baseline_request = {}
    if not isinstance(model_request, Mapping):
        model_request = {}
    keys = sorted(set(baseline_request) | set(model_request))
    return [
        {
            "path": f"mission_request.{key}",
            "baseline": baseline_request.get(key),
            "model": model_request.get(key),
        }
        for key in keys
        if baseline_request.get(key) != model_request.get(key)
    ]


def _mission_run_case_id(data: Mapping[str, Any]) -> str:
    mission_input = data.get("mission_input.json")
    if not isinstance(mission_input, Mapping):
        return ""
    run_input = mission_input.get("run_input")
    if not isinstance(run_input, Mapping):
        return ""
    return str(run_input.get("case_id") or "").strip()


def _read_json(path: Path, errors: List[str]) -> Optional[Dict[str, Any]]:
    if not path.exists():
        errors.append(f"missing required file: {path.name}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON {path.name}: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{path.name} must contain a JSON object")
        return None
    return data


def _package_doc(artifact_entries: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "# Task Planning Artifact Package",
        "",
        "This package transfers model-lab, server, or mission-run artifacts between machines.",
        "",
        "Execution boundary:",
        "",
        "- The home 5090 lane can produce model capability evidence only.",
        "- The unit/workplace lane is the hardware execution endpoint.",
        "- Verify this package on the unit/workplace receiving machine before replaying any schema on the work_hardware lane.",
        "- A successful model-lab artifact must include `model_task_schema.json`; otherwise there is no validated schema to replay.",
        "- Model-lab profile fields must match the evaluation report and keep `PLATFORM_BACKEND=mock`.",
        "- Receiving-machine proof requires differing source_machine_id and verifier_machine_id; use source_machine only for local sanity checks before transfer.",
        "",
        "Artifacts:",
        "",
    ]
    for item in artifact_entries:
        lines.append(f"- `{item['name']}`: `{item['kind']}` at `{item['packaged_path']}`")
    lines.extend([
        "",
        "First receiving-side check:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py <artifact-package.tar.gz> --work-dir /tmp/changxin-artifact-verify --verification-context unit_workplace_receiving",
        "```",
        "",
    ])
    return "\n".join(lines)


def _validate_tar_member(member: tarfile.TarInfo, extract_dir: Path) -> None:
    if member.issym() or member.islnk():
        raise ValueError(f"artifact package must not contain links: {member.name!r}")
    if not _is_safe_relative_posix_path(member.name):
        raise ValueError(f"unsafe archive member path: {member.name!r}")
    target = extract_dir / Path(member.name)
    if not _is_within(target, extract_dir):
        raise ValueError(f"archive member escapes extract dir: {member.name!r}")


def _is_safe_relative_posix_path(value: str) -> bool:
    path = PurePosixPath(value)
    if not value or path.is_absolute():
        return False
    return all(part not in ("", ".", "..") for part in path.parts)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    cleaned = "".join(
        char if char.isascii() and (char.isalnum() or char in ("-", "_")) else "-"
        for char in value.strip().lower()
    )
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "artifact"


def _unique_name(base: str, used: Set[str]) -> str:
    candidate = base
    counter = 2
    while candidate in used:
        candidate = f"{base}-{counter}"
        counter += 1
    used.add(candidate)
    return candidate
