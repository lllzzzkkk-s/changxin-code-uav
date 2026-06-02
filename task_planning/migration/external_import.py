from __future__ import annotations

import filecmp
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from task_planning.migration.artifact_package import (
    ARTIFACT_PACKAGE_VERIFICATION_SCHEMA,
    ARTIFACT_PACKAGE_VERIFICATION_SET_SCHEMA,
    verify_artifact_package,
)
from task_planning.migration.hardware_evidence import hardware_execution_artifact_errors
from task_planning.migration.machine_identity import hashed_machine_id_errors
from task_planning.migration.model_lab import model_lab_home_5090_live_errors
from task_planning.migration.verify import MIGRATION_VERIFICATION_SCHEMA
from task_planning.mission_ops.replay import load_artifact_bundle


HANDOFF_PACKAGE_VERIFICATION_SCHEMA = "DistributedFleetHandoffPackageVerification.v1"


@dataclass(frozen=True)
class ExternalEvidenceImportedItem:
    name: str
    source: Path
    target: Path
    kind: str

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["source"] = str(self.source)
        data["target"] = str(self.target)
        return data


@dataclass(frozen=True)
class ExternalEvidenceImportReport:
    evidence_dir: Path
    imported: List[ExternalEvidenceImportedItem] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)
    report_path: Optional[Path] = None
    schema: str = "DistributedFleetExternalEvidenceImport.v1"

    @property
    def ok(self) -> bool:
        return not self.validation_errors

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "evidence_dir": str(self.evidence_dir),
            "report_path": str(self.report_path) if self.report_path else "",
            "imported": [item.as_dict() for item in self.imported],
            "validation_errors": list(self.validation_errors),
        }


def import_external_evidence(
    *,
    evidence_dir: Path,
    model_lab_evaluation: Optional[Path] = None,
    migration_verification_report: Optional[Path] = None,
    handoff_package_verification_report: Optional[Path] = None,
    artifact_package_verification_report: Optional[Path] = None,
    site_acceptance_ros1_report: Optional[Path] = None,
    artifact_packages: Sequence[Path] = (),
    hardware_run_artifacts: Sequence[Path] = (),
) -> ExternalEvidenceImportReport:
    evidence_dir = evidence_dir.expanduser().resolve()
    reports_dir = evidence_dir / "reports"
    packages_dir = evidence_dir / "artifact_packages"
    hardware_dir = evidence_dir / "hardware_artifacts"
    for path in (reports_dir, packages_dir, hardware_dir):
        path.mkdir(parents=True, exist_ok=True)

    imported: List[ExternalEvidenceImportedItem] = []
    errors: List[str] = []
    artifact_verifications: List[Dict[str, Any]] = []

    model_lab_source = (
        _resolve_report_file(model_lab_evaluation, "model_lab_evaluation.json")
        if model_lab_evaluation is not None
        else None
    )

    if migration_verification_report is not None:
        _import_migration_verification_report(
            source=migration_verification_report,
            target=reports_dir / "migration_verification.json",
            imported=imported,
            errors=errors,
        )

    if handoff_package_verification_report is not None:
        _import_handoff_package_verification_report(
            source=handoff_package_verification_report,
            target=reports_dir / "handoff_package_verification.json",
            imported=imported,
            errors=errors,
        )

    if site_acceptance_ros1_report is not None:
        _import_site_acceptance_ros1_report(
            source=site_acceptance_ros1_report,
            target=reports_dir / "site_acceptance_work_hardware_ros1.json",
            imported=imported,
            errors=errors,
        )

    if artifact_package_verification_report is not None:
        artifact_verifications.extend(_import_artifact_package_verification_report(
            source=artifact_package_verification_report,
            target=reports_dir / "artifact_package_verification.json",
            artifact_packages=artifact_packages,
            packages_dir=packages_dir,
            reports_dir=reports_dir,
            imported=imported,
            errors=errors,
        ))
    else:
        for archive in artifact_packages:
            source = archive.expanduser().resolve()
            if not source.exists() or not source.is_file():
                errors.append(f"artifact package is missing or not a file: {source}")
                continue
            if not source.name.endswith(".tar.gz"):
                errors.append(f"artifact package must be a .tar.gz archive: {source}")
                continue
            try:
                verification = _verify_artifact_package_for_import(source)
            except Exception as exc:
                errors.append(f"artifact package verification failed: {source}: {exc}")
                continue
            verification_errors = _artifact_package_errors(verification)
            verification_errors.extend(_artifact_package_lane_case_errors(verification.as_dict(), reports_dir=reports_dir))
            if verification_errors:
                errors.append(f"artifact package verification failed: {source}: {'; '.join(verification_errors)}")
                continue
            target = packages_dir / source.name
            if _copy_file_if_safe(source, target, errors):
                verification_data = verification.as_dict()
                verification_data["archive"] = str(target)
                artifact_verifications.append(verification_data)
                imported.append(ExternalEvidenceImportedItem(
                    name="artifact_package_verified_after_transfer",
                    source=source,
                    target=target,
                    kind="artifact_package",
                ))

        if artifact_verifications:
            verification_set = {
                "schema": ARTIFACT_PACKAGE_VERIFICATION_SET_SCHEMA,
                "ok": True,
                "verification_context": "unit_workplace_receiving",
                "verifications": artifact_verifications,
            }
            (reports_dir / "artifact_package_verification.json").write_text(
                json.dumps(verification_set, indent=2, sort_keys=True, ensure_ascii=False),
                encoding="utf-8",
            )
            imported.append(ExternalEvidenceImportedItem(
                name="artifact_package_verified_after_transfer",
                source=reports_dir / "artifact_package_verification.json",
                target=reports_dir / "artifact_package_verification.json",
                kind="artifact_package_verification",
            ))

    if model_lab_source is not None:
        _import_model_lab_evaluation_report(
            source=model_lab_source,
            target=reports_dir / "model_lab_evaluation.json",
            reports_dir=reports_dir,
            artifact_verifications=artifact_verifications,
            imported=imported,
            errors=errors,
        )

    for artifact in hardware_run_artifacts:
        source = artifact.expanduser().resolve()
        if not source.exists() or not source.is_dir():
            errors.append(f"hardware run artifact is missing or not a directory: {source}")
            continue
        bundle = load_artifact_bundle(source)
        if not bundle.ok:
            errors.append(
                f"hardware run artifact is not a valid mission artifact bundle: "
                f"{source}: {'; '.join(bundle.validation_errors)}"
            )
            continue
        hardware_errors = _hardware_run_artifact_errors(bundle.data)
        hardware_errors.extend(_hardware_lane_case_errors(bundle.data, reports_dir=reports_dir))
        hardware_errors.extend(_hardware_ros1_gate_errors(bundle.data, reports_dir=reports_dir))
        if hardware_errors:
            errors.append(f"hardware run artifact verification failed: {source}: {'; '.join(hardware_errors)}")
            continue
        target = hardware_dir / source.name
        if _copy_dir_if_safe(source, target, errors):
            imported.append(ExternalEvidenceImportedItem(
                name="unit_hardware_execution_artifact_verified",
                source=source,
                target=target,
                kind="hardware_run_artifact",
            ))

    report = ExternalEvidenceImportReport(
        evidence_dir=evidence_dir,
        imported=imported,
        validation_errors=errors,
        report_path=reports_dir / "external_evidence_import.json",
    )
    report.report_path.write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def _import_json_report(
    *,
    source: Path,
    target: Path,
    name: str,
    kind: str,
    required_schema: Optional[str],
    required_ok: bool,
    imported: List[ExternalEvidenceImportedItem],
    errors: List[str],
    required_fields: Optional[Mapping[str, Any]] = None,
) -> None:
    source = source.expanduser().resolve()
    data = _load_json_object(source, errors)
    if data is None:
        return
    if required_schema is not None and data.get("schema") != required_schema:
        errors.append(f"{kind} must use schema {required_schema}, got {data.get('schema')!r}")
        return
    if required_ok and data.get("ok") is not True:
        errors.append(f"{kind} report must have ok=true")
        return
    for key, expected in (required_fields or {}).items():
        if data.get(key) != expected:
            errors.append(f"{kind} report must have {key}={expected!r}, got {data.get(key)!r}")
            return
    if _copy_file_if_safe(source, target, errors):
        imported.append(ExternalEvidenceImportedItem(name=name, source=source, target=target, kind=kind))


def _import_artifact_package_verification_report(
    *,
    source: Path,
    target: Path,
    artifact_packages: Sequence[Path],
    packages_dir: Path,
    reports_dir: Path,
    imported: List[ExternalEvidenceImportedItem],
    errors: List[str],
) -> List[Dict[str, Any]]:
    source = source.expanduser().resolve()
    data = _load_json_object(source, errors)
    if data is None:
        return []

    candidate_errors: List[str] = []
    package_candidates = _artifact_package_candidates(
        artifact_packages=artifact_packages,
        packages_dir=packages_dir,
        errors=candidate_errors,
    )
    if candidate_errors:
        errors.extend(candidate_errors)
        return []

    verifications, report_errors = _artifact_package_report_verifications(data)
    if report_errors:
        errors.extend(f"artifact_package_verification report failed validation: {error}" for error in report_errors)
        return []

    normalized_verifications: List[Dict[str, Any]] = []
    packages_to_copy: Dict[Path, Path] = {}
    validation_errors: List[str] = []
    for index, verification in enumerate(verifications):
        normalized, source_package, target_package, item_errors = _normalize_artifact_package_verification(
            verification,
            index=index,
            package_candidates=package_candidates,
            reports_dir=reports_dir,
        )
        if item_errors:
            validation_errors.extend(item_errors)
            continue
        if normalized is not None and source_package is not None and target_package is not None:
            normalized_verifications.append(normalized)
            packages_to_copy[source_package] = target_package

    if validation_errors:
        errors.extend(f"artifact_package_verification report failed validation: {error}" for error in validation_errors)
        return []

    for source_package, target_package in sorted(packages_to_copy.items(), key=lambda item: str(item[1])):
        if _copy_file_if_safe(source_package, target_package, errors):
            imported.append(ExternalEvidenceImportedItem(
                name="artifact_package_verified_after_transfer",
                source=source_package,
                target=target_package,
                kind="artifact_package",
            ))
    if errors:
        return []

    normalized_report = {
        "schema": ARTIFACT_PACKAGE_VERIFICATION_SET_SCHEMA,
        "ok": True,
        "verification_context": "unit_workplace_receiving",
        "source_report": str(source),
        "verifications": normalized_verifications,
    }
    target.write_text(
        json.dumps(normalized_report, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    imported.append(ExternalEvidenceImportedItem(
        name="artifact_package_verified_after_transfer",
        source=source,
        target=target,
        kind="artifact_package_verification",
    ))
    return normalized_verifications


def _artifact_package_report_verifications(data: Mapping[str, Any]) -> Tuple[List[Mapping[str, Any]], List[str]]:
    errors: List[str] = []
    if data.get("schema") == ARTIFACT_PACKAGE_VERIFICATION_SCHEMA:
        if data.get("ok") is not True:
            errors.append("artifact package verification must have ok=true")
        return [data], errors
    if data.get("schema") == ARTIFACT_PACKAGE_VERIFICATION_SET_SCHEMA:
        if data.get("ok") is not True:
            errors.append("artifact package verification set must have ok=true")
        if data.get("verification_context") != "unit_workplace_receiving":
            errors.append("artifact package verification set must have verification_context=unit_workplace_receiving")
        verifications = data.get("verifications")
        if not isinstance(verifications, list) or not verifications:
            errors.append("artifact package verification set verifications must be a non-empty list")
            return [], errors
        entries = [item for item in verifications if isinstance(item, Mapping)]
        if len(entries) != len(verifications):
            errors.append("artifact package verification set verifications entries must be objects")
        return entries, errors
    return [], [
        f"artifact package verification report schema must be {ARTIFACT_PACKAGE_VERIFICATION_SCHEMA} "
        f"or {ARTIFACT_PACKAGE_VERIFICATION_SET_SCHEMA}"
    ]


def _artifact_package_candidates(
    *,
    artifact_packages: Sequence[Path],
    packages_dir: Path,
    errors: List[str],
) -> Dict[str, Tuple[Path, Path]]:
    candidates: Dict[str, Tuple[Path, Path]] = {}
    packages_dir.mkdir(parents=True, exist_ok=True)
    for existing in sorted(packages_dir.glob("*.tar.gz")):
        candidates[existing.name] = (existing.resolve(), existing.resolve())
    for archive in artifact_packages:
        source = archive.expanduser().resolve()
        if not source.exists() or not source.is_file():
            errors.append(f"artifact package is missing or not a file: {source}")
            continue
        if not source.name.endswith(".tar.gz"):
            errors.append(f"artifact package must be a .tar.gz archive: {source}")
            continue
        candidates[source.name] = (source, (packages_dir / source.name).resolve())
    return candidates


def _normalize_artifact_package_verification(
    verification: Mapping[str, Any],
    *,
    index: int,
    package_candidates: Mapping[str, Tuple[Path, Path]],
    reports_dir: Path,
) -> Tuple[Optional[Dict[str, Any]], Optional[Path], Optional[Path], List[str]]:
    prefix = f"verifications[{index}]"
    errors: List[str] = []
    if verification.get("schema") != ARTIFACT_PACKAGE_VERIFICATION_SCHEMA:
        errors.append(f"{prefix}: schema must be {ARTIFACT_PACKAGE_VERIFICATION_SCHEMA}")
    if verification.get("ok") is not True:
        errors.append(f"{prefix}: ok must be true")
    if verification.get("verification_context") != "unit_workplace_receiving":
        errors.append(f"{prefix}: verification_context must be unit_workplace_receiving")
    errors.extend(f"{prefix}: {error}" for error in _machine_transfer_errors(verification))
    if verification.get("manifest_errors") != []:
        errors.append(f"{prefix}: manifest_errors must be an empty list")
    if _safe_int(verification.get("checked_files")) <= 0:
        errors.append(f"{prefix}: checked_files must be greater than zero")
    if not isinstance(verification.get("artifact_validations"), list):
        errors.append(f"{prefix}: artifact_validations must be a list")

    archive = str(verification.get("archive") or "").strip()
    if not archive:
        errors.append(f"{prefix}: archive is required")
        return None, None, None, errors
    package_name = Path(archive).name
    candidate = package_candidates.get(package_name)
    if candidate is None:
        errors.append(f"{prefix}: matching artifact package archive is required for verification report: {package_name}")
        return None, None, None, errors
    source_package, target_package = candidate

    try:
        content_verification = _verify_artifact_package_content_for_import(source_package)
    except Exception as exc:
        errors.append(f"{prefix}: matching artifact package archive verification failed: {exc}")
        return None, None, None, errors
    content_errors = _artifact_package_errors(content_verification)
    if content_errors:
        errors.extend(f"{prefix}: matching artifact package archive verification failed: {error}" for error in content_errors)
    content_data = content_verification.as_dict()
    content_data["archive"] = str(target_package)
    content_data["verification_context"] = "unit_workplace_receiving"
    content_data["source_machine_id"] = verification.get("source_machine_id")
    content_data["verifier_machine_id"] = verification.get("verifier_machine_id")

    if str(content_verification.source_machine_id or "") != str(verification.get("source_machine_id") or ""):
        errors.append(f"{prefix}: source_machine_id must match matching artifact package manifest")
    errors.extend(f"{prefix}: {error}" for error in _artifact_package_lane_case_errors(content_data, reports_dir=reports_dir))
    if errors:
        return None, None, None, errors

    normalized = dict(verification)
    normalized["archive"] = str(target_package)
    normalized["checked_files"] = content_data["checked_files"]
    normalized["artifact_validations"] = content_data["artifact_validations"]
    normalized["original_archive"] = archive
    normalized["import_content_verification"] = {
        "checked_files": content_data["checked_files"],
        "source_machine_id": content_verification.source_machine_id,
    }
    return normalized, source_package, target_package, []


def _import_model_lab_evaluation_report(
    *,
    source: Path,
    target: Path,
    reports_dir: Path,
    artifact_verifications: Sequence[Mapping[str, Any]],
    imported: List[ExternalEvidenceImportedItem],
    errors: List[str],
) -> None:
    source = source.expanduser().resolve()
    data = _load_json_object(source, errors)
    if data is None:
        return
    validation_errors = _model_lab_evaluation_errors(
        data,
        reports_dir=reports_dir,
        artifact_verifications=artifact_verifications,
    )
    if validation_errors:
        errors.append(f"model_lab_evaluation report failed validation: {'; '.join(validation_errors)}")
        return
    if _copy_file_if_safe(source, target, errors):
        imported.append(ExternalEvidenceImportedItem(
            name="home_5090_model_lab_evaluated",
            source=source,
            target=target,
            kind="model_lab_evaluation",
        ))


def _model_lab_evaluation_errors(
    data: Mapping[str, Any],
    *,
    reports_dir: Path,
    artifact_verifications: Sequence[Mapping[str, Any]],
) -> List[str]:
    errors = model_lab_home_5090_live_errors(data)
    if errors:
        return errors
    lane_case_ids, lane_errors = _lane_matrix_case_ids_for_model_import(reports_dir / "lane_matrix.json")
    errors.extend(lane_errors)
    case_id = str(data.get("case_id") or "")
    if lane_case_ids and case_id not in lane_case_ids:
        errors.append("case_id must match an OK lane_matrix report before model_lab_evaluation import")
    if not errors:
        existing_errors: List[str] = []
        if artifact_verifications:
            model_lab_artifact_verifications = list(artifact_verifications)
        else:
            model_lab_artifact_verifications, existing_errors = _load_existing_artifact_verifications(reports_dir)
        errors.extend(existing_errors)
    if not errors:
        errors.extend(_model_lab_package_binding_errors(
            data,
            model_lab_artifact_verifications,
        ))
    return errors


def _load_existing_artifact_verifications(reports_dir: Path) -> Tuple[List[Mapping[str, Any]], List[str]]:
    path = reports_dir / "artifact_package_verification.json"
    if not path.exists() or not path.is_file():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], [f"existing artifact_package_verification report is unreadable: {exc}"]
    if not isinstance(data, Mapping):
        return [], ["existing artifact_package_verification report must contain a JSON object"]
    if data.get("schema") == ARTIFACT_PACKAGE_VERIFICATION_SET_SCHEMA:
        verifications = data.get("verifications")
        if isinstance(verifications, list):
            entries = [item for item in verifications if isinstance(item, Mapping)]
            if len(entries) != len(verifications):
                return [], ["existing artifact_package_verification verifications entries must be objects"]
            return _trusted_existing_artifact_verifications(entries, reports_dir=reports_dir)
        return [], ["existing artifact_package_verification verifications must be a list"]
    return _trusted_existing_artifact_verifications([data], reports_dir=reports_dir)


def _trusted_existing_artifact_verifications(
    entries: Sequence[Mapping[str, Any]],
    *,
    reports_dir: Path,
) -> Tuple[List[Mapping[str, Any]], List[str]]:
    evidence_dir = reports_dir.parent
    packages_dir = evidence_dir / "artifact_packages"
    trusted: List[Mapping[str, Any]] = []
    errors: List[str] = []
    for index, entry in enumerate(entries):
        item_errors: List[str] = []
        if entry.get("ok") is not True:
            item_errors.append("ok must be true")
        if entry.get("verification_context") != "unit_workplace_receiving":
            item_errors.append("verification_context must be unit_workplace_receiving")
        item_errors.extend(_machine_transfer_errors(entry))
        archive = str(entry.get("archive") or "").strip()
        archive_path = _resolve_existing_artifact_archive(archive, evidence_dir=evidence_dir)
        if not archive:
            item_errors.append("archive is required")
        elif not _path_is_within(archive_path, packages_dir):
            item_errors.append("archive must be inside the standard artifact_packages directory")
        elif not archive_path.exists() or not archive_path.is_file():
            item_errors.append("existing artifact package archive is missing")
        elif not archive_path.name.endswith(".tar.gz"):
            item_errors.append("existing artifact package archive must be a .tar.gz file")
        fresh_verification: Optional[Mapping[str, Any]] = None
        if not item_errors:
            fresh_verification, fresh_errors = _reverify_existing_artifact_archive(
                archive_path,
                claimed_source_machine_id=str(entry.get("source_machine_id") or ""),
            )
            item_errors.extend(fresh_errors)
        if not item_errors and fresh_verification is not None:
            item_errors.extend(_artifact_package_lane_case_errors(fresh_verification, reports_dir=reports_dir))
        if item_errors:
            errors.extend(f"existing artifact_package_verification[{index}]: {error}" for error in item_errors)
            continue
        trusted.append(fresh_verification or entry)
    if errors:
        return [], errors
    return trusted, []


def _reverify_existing_artifact_archive(
    archive_path: Path,
    *,
    claimed_source_machine_id: str,
) -> Tuple[Optional[Mapping[str, Any]], List[str]]:
    try:
        verification = _verify_artifact_package_for_import(archive_path)
    except Exception as exc:
        return None, [f"existing artifact package archive verification failed: {exc}"]
    errors = [
        f"existing artifact package archive verification failed: {error}"
        for error in _artifact_package_errors(verification)
    ]
    verification_data = verification.as_dict()
    verification_data["archive"] = str(archive_path)
    if claimed_source_machine_id and verification_data.get("source_machine_id") != claimed_source_machine_id:
        errors.append("existing artifact package archive source_machine_id must match verification report")
    if errors:
        return None, errors
    return verification_data, []


def _resolve_existing_artifact_archive(archive: str, *, evidence_dir: Path) -> Path:
    path = Path(archive).expanduser()
    if not path.is_absolute():
        path = evidence_dir / path
    return path.resolve()


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _model_lab_package_binding_errors(
    data: Mapping[str, Any],
    artifact_verifications: Sequence[Mapping[str, Any]],
) -> List[str]:
    proofs = _model_lab_artifact_proofs(artifact_verifications)
    if not proofs:
        return ["matching model-lab artifact package is required before model_lab_evaluation import"]
    case_id = str(data.get("case_id") or "")
    same_case = [proof for proof in proofs if proof.get("case_id") == case_id]
    if not same_case:
        return ["model-lab artifact package case_id must match model_lab_evaluation report before import"]

    required_metadata_keys = [
        "mission_profile",
        "model_provider",
        "platform_backend",
        "model_lab_evidence_kind",
        "machine_id",
    ]
    binding_errors: List[str] = []
    for proof in same_case:
        metadata = proof.get("metadata")
        if not isinstance(metadata, Mapping):
            metadata = {}
        proof_errors = []
        for key in required_metadata_keys:
            package_value = str(metadata.get(key) or "")
            report_value = str(data.get(key) or "")
            if not package_value:
                proof_errors.append(f"model-lab artifact package metadata.{key} is required before import")
            elif report_value and package_value != report_value:
                proof_errors.append(f"model-lab artifact package metadata.{key} must match model_lab_evaluation report before import")
        if not proof_errors:
            return []
        binding_errors.extend(proof_errors)
    return sorted(set(binding_errors))


def _model_lab_artifact_proofs(artifact_verifications: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    proofs: List[Mapping[str, Any]] = []
    for verification in artifact_verifications:
        validations = verification.get("artifact_validations")
        if not isinstance(validations, list):
            continue
        for validation in validations:
            if (
                isinstance(validation, Mapping)
                and validation.get("ok") is True
                and validation.get("kind") == "model_lab_evaluation"
                and str(validation.get("case_id") or "").strip()
            ):
                proofs.append(validation)
    return proofs


def _lane_matrix_case_ids_for_model_import(path: Path) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    if not path.exists() or not path.is_file():
        return [], ["lane_matrix report is required before model_lab_evaluation import"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], [f"lane_matrix report is unreadable: {exc}"]
    if not isinstance(data, Mapping):
        return [], ["lane_matrix report must contain a JSON object"]

    if data.get("schema") != "TaskPlanningLaneMatrix.v1":
        errors.append("lane_matrix report schema must be TaskPlanningLaneMatrix.v1")
    if data.get("ok") is not True:
        errors.append("lane_matrix report must have ok=true")
    case_id = str(data.get("case_id") or "").strip()
    if not case_id:
        errors.append("lane_matrix case_id is required")

    runs = data.get("runs")
    if not isinstance(runs, list):
        errors.append("lane_matrix runs must be a list")
        runs = []
    run_lanes = {
        str(run.get("lane") or ""): run
        for run in runs
        if isinstance(run, Mapping)
    }
    required_lanes = {"dev_mock", "server_sim", "work_hardware"}
    missing_lanes = sorted(required_lanes - set(run_lanes))
    if missing_lanes:
        errors.append(f"lane_matrix runs must include lanes: {', '.join(missing_lanes)}")
    for lane in sorted(required_lanes & set(run_lanes)):
        if run_lanes[lane].get("ok") is not True:
            errors.append(f"lane_matrix {lane} run must have ok=true")

    comparisons = data.get("comparisons")
    if not isinstance(comparisons, list):
        errors.append("lane_matrix comparisons must be a list")
        comparisons = []
    comparison_by_name = {
        str(comparison.get("name") or ""): comparison
        for comparison in comparisons
        if isinstance(comparison, Mapping)
    }
    for name in ("dev_mock_vs_server_sim", "dev_mock_vs_work_hardware_pre_dispatch"):
        comparison = comparison_by_name.get(name)
        if not isinstance(comparison, Mapping):
            errors.append(f"lane_matrix comparison {name} is required")
            continue
        if comparison.get("equivalent") is not True:
            errors.append(f"lane_matrix comparison {name} must have equivalent=true")

    return ([case_id] if case_id and not errors else []), errors


def _import_site_acceptance_ros1_report(
    *,
    source: Path,
    target: Path,
    imported: List[ExternalEvidenceImportedItem],
    errors: List[str],
) -> None:
    source = source.expanduser().resolve()
    data = _load_json_object(source, errors)
    if data is None:
        return
    validation_errors = _site_acceptance_ros1_errors(data)
    if validation_errors:
        errors.append(f"site_acceptance_ros1 report failed validation: {'; '.join(validation_errors)}")
        return
    if _copy_file_if_safe(source, target, errors):
        imported.append(ExternalEvidenceImportedItem(
            name="unit_ros1_gateway_signatures_observed",
            source=source,
            target=target,
            kind="site_acceptance_ros1",
        ))


def _site_acceptance_ros1_errors(data: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    if data.get("schema") != "TaskPlanningSiteAcceptance.v1":
        errors.append(f"schema must be TaskPlanningSiteAcceptance.v1, got {data.get('schema')!r}")
    if data.get("ok") is not True:
        errors.append("ok must be true")
    if data.get("mission_profile") != "work_hardware":
        errors.append(f"mission_profile must be 'work_hardware', got {data.get('mission_profile')!r}")
    if data.get("platform_backend") != "ros1_gateway":
        errors.append(f"platform_backend must be 'ros1_gateway', got {data.get('platform_backend')!r}")
    if data.get("acceptance_level") != "work_hardware_ros1_signatures_observed":
        errors.append(
            "acceptance_level must be 'work_hardware_ros1_signatures_observed', "
            f"got {data.get('acceptance_level')!r}"
        )
    for error in hashed_machine_id_errors(data.get("machine_id"), "machine_id"):
        errors.append(f"{error} for unit ROS1 signature evidence")
    if data.get("validation_errors") != []:
        errors.append("validation_errors must be an empty list")
    readiness = data.get("readiness")
    if not isinstance(readiness, Mapping):
        errors.append("readiness report is required")
    else:
        if readiness.get("ok") is not True:
            errors.append("readiness.ok must be true")
        if readiness.get("mission_profile") != "work_hardware":
            errors.append("readiness.mission_profile must be 'work_hardware'")
    hardware_gate = data.get("hardware_gate")
    if not isinstance(hardware_gate, Mapping):
        errors.append("hardware_gate report is required")
    elif hardware_gate.get("ok") is not True:
        errors.append("hardware_gate.ok must be true")
    audit = data.get("rosservice_audit")
    if not isinstance(audit, Mapping):
        errors.append("rosservice_audit is required")
        return errors
    if audit.get("ok") is not True:
        errors.append("rosservice_audit.ok must be true")
    if audit.get("command_environment_source") not in {"profile", "captured_files"}:
        errors.append("rosservice_audit.command_environment_source must be 'profile' or 'captured_files'")
    if _safe_int(audit.get("observed_service_count")) <= 0:
        errors.append("rosservice_audit.observed_service_count must be greater than zero")
    errors.extend(_ros1_audit_service_name_errors(audit))
    signatures = audit.get("service_signatures")
    if not isinstance(signatures, list) or not signatures:
        errors.append("rosservice_audit.service_signatures are required")
    else:
        signed_services: List[str] = []
        for index, signature in enumerate(signatures):
            if not isinstance(signature, Mapping):
                errors.append(f"rosservice_audit.service_signatures[{index}] must be an object")
                continue
            service_name = str(signature.get("service_name") or "").strip()
            if service_name:
                signed_services.append(service_name)
            if signature.get("type_ok") is not True:
                errors.append(f"rosservice_audit.service_signatures[{index}].type_ok must be true")
            if signature.get("args_ok") is not True:
                errors.append(f"rosservice_audit.service_signatures[{index}].args_ok must be true")
        errors.extend(_gateway_signature_pair_errors(signed_services))
    return errors


def _ros1_audit_service_name_errors(audit: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    matched = audit.get("matched_services")
    if not isinstance(matched, list) or not matched:
        errors.append("rosservice_audit.matched_services are required for unit ROS1 signature proof")
        matched_services = set()
    else:
        matched_services = {str(item).strip() for item in matched if str(item).strip()}
    missing = audit.get("missing_services")
    if not isinstance(missing, list):
        errors.append("rosservice_audit.missing_services must be a list")
    elif missing:
        errors.append("rosservice_audit.missing_services must be empty for unit ROS1 signature proof")
    signatures = audit.get("service_signatures")
    if isinstance(signatures, list):
        for index, signature in enumerate(signatures):
            if not isinstance(signature, Mapping):
                continue
            service_name = str(signature.get("service_name") or "").strip()
            if not service_name:
                errors.append(f"rosservice_audit.service_signatures[{index}].service_name is required")
            elif matched_services and service_name not in matched_services:
                errors.append(
                    f"rosservice_audit.service_signatures[{index}].service_name must be present in matched_services"
                )
    return errors


def _gateway_signature_pair_errors(signed_services: Sequence[str]) -> List[str]:
    prefixes: Dict[str, set] = {}
    for service in signed_services:
        service_name = str(service).strip()
        prefix, marker, mode = service_name.partition("/gateway/")
        if not marker:
            continue
        mode = mode.strip("/")
        if not prefix or mode not in {"dry_run", "dispatch"}:
            continue
        prefixes.setdefault(prefix, set()).add(mode)
    if any({"dry_run", "dispatch"}.issubset(modes) for modes in prefixes.values()):
        return []
    return ["rosservice_audit.service_signatures must include paired dry_run and dispatch services for one gateway prefix"]


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _import_migration_verification_report(
    *,
    source: Path,
    target: Path,
    imported: List[ExternalEvidenceImportedItem],
    errors: List[str],
) -> None:
    source = source.expanduser().resolve()
    data = _load_json_object(source, errors)
    if data is None:
        return
    if data.get("schema") != MIGRATION_VERIFICATION_SCHEMA:
        errors.append(f"migration_verification must use schema {MIGRATION_VERIFICATION_SCHEMA}, got {data.get('schema')!r}")
        return
    if data.get("ok") is not True:
        errors.append("migration_verification report must have ok=true")
        return
    if data.get("verification_context") not in {"receiving_machine", "unit_workplace_receiving"}:
        errors.append(
            "migration_verification report must have verification_context='receiving_machine' or 'unit_workplace_receiving'"
        )
        return
    transfer_errors = _machine_transfer_errors(data)
    if transfer_errors:
        errors.append(f"migration_verification report failed machine transfer validation: {'; '.join(transfer_errors)}")
        return
    audit_errors = _migration_verifier_audit_errors(data)
    if audit_errors:
        errors.append(f"migration_verification report failed verifier audit validation: {'; '.join(audit_errors)}")
        return
    if _copy_file_if_safe(source, target, errors):
        imported.append(ExternalEvidenceImportedItem(
            name="migration_bundle_verified_after_transfer",
            source=source,
            target=target,
            kind="migration_verification",
        ))


def _import_handoff_package_verification_report(
    *,
    source: Path,
    target: Path,
    imported: List[ExternalEvidenceImportedItem],
    errors: List[str],
) -> None:
    source = source.expanduser().resolve()
    data = _load_json_object(source, errors)
    if data is None:
        return
    validation_errors = _handoff_package_verification_errors(data)
    if validation_errors:
        errors.append(f"handoff_package_verification failed: {source}: {'; '.join(validation_errors)}")
        return
    if _copy_file_if_safe(source, target, errors):
        imported.append(ExternalEvidenceImportedItem(
            name="migration_bundle_verified_after_transfer",
            source=source,
            target=target,
            kind="handoff_package_verification",
        ))


def _handoff_package_verification_errors(data: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    if data.get("schema") != HANDOFF_PACKAGE_VERIFICATION_SCHEMA:
        errors.append(f"report schema must be {HANDOFF_PACKAGE_VERIFICATION_SCHEMA}")
    if data.get("ok") is not True:
        errors.append("report must have ok=true")
    if data.get("verification_context") not in {"receiving_machine", "unit_workplace_receiving"}:
        errors.append("verification_context must be receiving_machine or unit_workplace_receiving")
    errors.extend(_machine_transfer_errors(data))
    errors.extend(_handoff_verifier_audit_errors(data))
    migration = data.get("migration_verification")
    if not isinstance(migration, Mapping):
        errors.append("migration_verification must be an object")
        migration = {}
    if migration.get("schema") != MIGRATION_VERIFICATION_SCHEMA:
        errors.append(f"migration_verification schema must be {MIGRATION_VERIFICATION_SCHEMA}")
    if migration.get("ok") is not True:
        errors.append("migration_verification must have ok=true")
    if migration.get("verification_context") not in {"receiving_machine", "unit_workplace_receiving"}:
        errors.append("migration_verification context must be receiving_machine or unit_workplace_receiving")
    errors.extend(f"migration_verification: {error}" for error in _machine_transfer_errors(migration))
    errors.extend(f"migration_verification: {error}" for error in _migration_verifier_audit_errors(migration))
    errors.extend(_embedded_handoff_migration_identity_errors(data, migration))
    return errors


def _migration_verifier_audit_errors(data: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in ("archive", "extract_dir", "bundle_root"):
        if not str(data.get(field) or "").strip():
            errors.append(f"{field} is required from migration verifier output")
    manifest = data.get("manifest")
    if not isinstance(manifest, Mapping):
        errors.append("manifest verifier output is required")
    else:
        if manifest.get("ok") is not True:
            errors.append("manifest.ok must be true")
        if _safe_int(manifest.get("checked_files")) <= 0:
            errors.append("manifest.checked_files must be greater than zero")
        if manifest.get("errors") != []:
            errors.append("manifest.errors must be an empty list")
        manifest_source_machine_id = str(manifest.get("source_machine_id") or "")
        report_source_machine_id = str(data.get("source_machine_id") or "")
        if (
            manifest_source_machine_id
            and report_source_machine_id
            and manifest_source_machine_id != report_source_machine_id
        ):
            errors.append("manifest.source_machine_id must match report source_machine_id")
    checks = data.get("checks")
    if not isinstance(checks, list):
        errors.append("checks must be a list")
    else:
        for index, check in enumerate(checks):
            if not isinstance(check, Mapping):
                errors.append(f"checks[{index}] must be an object")
            elif check.get("ok") is not True:
                errors.append(f"checks[{index}].ok must be true")
    return errors


def _handoff_verifier_audit_errors(data: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in ("archive", "extract_dir", "package_root"):
        if not str(data.get(field) or "").strip():
            errors.append(f"{field} is required from handoff verifier output")
    if _safe_int(data.get("checked_files")) <= 0:
        errors.append("checked_files must be greater than zero")
    if data.get("manifest_errors") != []:
        errors.append("manifest_errors must be an empty list")
    if data.get("component_errors") != []:
        errors.append("component_errors must be an empty list")
    return errors


def _machine_transfer_errors(data: Mapping[str, Any]) -> List[str]:
    if data.get("verification_context") not in {"receiving_machine", "unit_workplace_receiving"}:
        return []
    source_machine_id = str(data.get("source_machine_id") or "")
    verifier_machine_id = str(data.get("verifier_machine_id") or "")
    errors: List[str] = []
    errors.extend(hashed_machine_id_errors(source_machine_id, "source_machine_id"))
    errors.extend(hashed_machine_id_errors(verifier_machine_id, "verifier_machine_id"))
    if source_machine_id and verifier_machine_id and source_machine_id == verifier_machine_id:
        errors.append("source_machine_id and verifier_machine_id must differ for receiving-machine proof")
    return errors


def _embedded_handoff_migration_identity_errors(
    handoff: Mapping[str, Any],
    migration: Mapping[str, Any],
) -> List[str]:
    errors: List[str] = []
    if (
        handoff.get("verification_context")
        and migration.get("verification_context")
        and handoff.get("verification_context") != migration.get("verification_context")
    ):
        errors.append("handoff verification_context must match embedded migration_verification context")
    for field in ("source_machine_id", "verifier_machine_id"):
        handoff_value = str(handoff.get(field) or "")
        migration_value = str(migration.get(field) or "")
        if handoff_value and migration_value and handoff_value != migration_value:
            errors.append(f"handoff {field} must match embedded migration_verification {field}")
    return errors


def _resolve_report_file(path: Path, filename: str) -> Path:
    expanded = path.expanduser()
    if expanded.is_dir():
        return expanded / filename
    return expanded


def _load_json_object(path: Path, errors: List[str]) -> Optional[Dict[str, Any]]:
    if not path.exists() or not path.is_file():
        errors.append(f"JSON report is missing or not a file: {path}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"JSON report is unreadable: {path}: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"JSON report must be an object: {path}")
        return None
    return data


def _verify_artifact_package_for_import(archive: Path):
    with tempfile.TemporaryDirectory(prefix="external-evidence-artifact-verify-") as tmp:
        return verify_artifact_package(
            archive_path=archive,
            work_dir=Path(tmp),
            verification_context="unit_workplace_receiving",
        )


def _verify_artifact_package_content_for_import(archive: Path):
    with tempfile.TemporaryDirectory(prefix="external-evidence-artifact-content-verify-") as tmp:
        return verify_artifact_package(
            archive_path=archive,
            work_dir=Path(tmp),
            verification_context="source_machine",
        )


def _artifact_package_errors(verification) -> List[str]:
    errors = list(verification.manifest_errors)
    for artifact in verification.artifact_validations:
        errors.extend(f"{artifact.name}: {error}" for error in artifact.errors)
    if not errors and not verification.ok:
        errors.append("artifact package verification returned ok=false")
    return errors


def _artifact_package_lane_case_errors(verification: Mapping[str, Any], *, reports_dir: Path) -> List[str]:
    lane_case_ids, lane_errors = _lane_matrix_case_ids_for_model_import(reports_dir / "lane_matrix.json")
    errors = list(lane_errors)
    case_ids = _artifact_validation_case_ids(verification)
    if case_ids and lane_case_ids:
        mismatched = sorted(case_id for case_id in case_ids if case_id not in lane_case_ids)
        if mismatched:
            errors.append(
                "artifact package case_id must match an OK lane_matrix report before import: "
                + ", ".join(mismatched)
            )
    elif not case_ids:
        errors.append("artifact package verification must include artifact case_id evidence before import")
    return errors


def _artifact_validation_case_ids(verification: Mapping[str, Any]) -> List[str]:
    validations = verification.get("artifact_validations")
    if not isinstance(validations, list):
        return []
    case_ids = {
        str(item.get("case_id") or "").strip()
        for item in validations
        if isinstance(item, Mapping) and item.get("ok") is True
    }
    return sorted(case_id for case_id in case_ids if case_id)


def _hardware_run_artifact_errors(bundle_data: Mapping[str, Any]) -> List[str]:
    return hardware_execution_artifact_errors(bundle_data)


def _hardware_lane_case_errors(bundle_data: Mapping[str, Any], *, reports_dir: Path) -> List[str]:
    lane_case_ids, lane_errors = _lane_matrix_case_ids_for_model_import(reports_dir / "lane_matrix.json")
    errors = list(lane_errors)
    case_id = _artifact_case_id(bundle_data)
    if case_id and lane_case_ids and case_id not in lane_case_ids:
        errors.append("hardware artifact case_id must match an OK lane_matrix report before import")
    return errors


def _hardware_ros1_gate_errors(bundle_data: Mapping[str, Any], *, reports_dir: Path) -> List[str]:
    gate_path = reports_dir / "site_acceptance_work_hardware_ros1.json"
    if not gate_path.exists():
        return ["site_acceptance_work_hardware_ros1 report is required before importing hardware artifact"]
    errors: List[str] = []
    gate = _load_json_object(gate_path, errors)
    if gate is None:
        return errors
    gate_errors = _site_acceptance_ros1_errors(gate)
    if gate_errors:
        return [f"site_acceptance_work_hardware_ros1 report failed validation: {'; '.join(gate_errors)}"]

    hardware_machine_id = _hardware_machine_id(bundle_data)
    gate_machine_id = str(gate.get("machine_id") or "")
    if hardware_machine_id != gate_machine_id:
        errors.append("hardware artifact machine_id must match site_acceptance_work_hardware_ros1 machine_id")

    signed_services = _site_acceptance_signed_services(gate)
    dispatch_services = _hardware_dispatch_services(bundle_data)
    if not dispatch_services:
        errors.append("hardware artifact dispatch service is required before import")
    else:
        unsigned = sorted(service for service in dispatch_services if service not in signed_services)
        if unsigned:
            errors.append(
                "hardware artifact dispatch service must match a signed site_acceptance_work_hardware_ros1 service: "
                + ", ".join(unsigned)
            )
    return errors


def _hardware_machine_id(bundle_data: Mapping[str, Any]) -> str:
    profile = bundle_data.get("environment_profile.json")
    if not isinstance(profile, Mapping):
        return ""
    return str(profile.get("machine_id") or "")


def _hardware_dispatch_services(bundle_data: Mapping[str, Any]) -> List[str]:
    gateway_trace = bundle_data.get("gateway_trace.json")
    records = gateway_trace.get("records") if isinstance(gateway_trace, Mapping) else []
    if not isinstance(records, list):
        return []
    return sorted({
        str(record.get("service") or "")
        for record in records
        if isinstance(record, Mapping)
        and record.get("rosservice_called") is True
        and _is_gateway_dispatch_service(record.get("service"))
        and record.get("returncode") == 0
        and str(record.get("service") or "")
    })


def _site_acceptance_signed_services(report: Mapping[str, Any]) -> List[str]:
    audit = report.get("rosservice_audit")
    signatures = audit.get("service_signatures") if isinstance(audit, Mapping) else []
    if not isinstance(signatures, list):
        return []
    return sorted({
        str(signature.get("service_name") or "").strip()
        for signature in signatures
        if isinstance(signature, Mapping) and str(signature.get("service_name") or "").strip()
    })


def _artifact_case_id(bundle_data: Mapping[str, Any]) -> str:
    mission_input = bundle_data.get("mission_input.json")
    if not isinstance(mission_input, Mapping):
        return ""
    run_input = mission_input.get("run_input")
    if not isinstance(run_input, Mapping):
        return ""
    return str(run_input.get("case_id") or "").strip()


def _is_gateway_dispatch_service(service: Any) -> bool:
    return isinstance(service, str) and service.strip().endswith("/gateway/dispatch")


def _copy_file_if_safe(source: Path, target: Path, errors: List[str]) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_file() and filecmp.cmp(source, target, shallow=False):
            return True
        errors.append(f"target already exists with different content: {target}")
        return False
    shutil.copy2(source, target)
    return True


def _copy_dir_if_safe(source: Path, target: Path, errors: List[str]) -> bool:
    if target.exists():
        errors.append(f"target directory already exists: {target}")
        return False
    shutil.copytree(source, target)
    return True
