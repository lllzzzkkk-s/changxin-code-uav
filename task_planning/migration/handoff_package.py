from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple

from task_planning.migration.bundle import build_migration_bundle
from task_planning.migration.evidence_collection import collect_distributed_fleet_evidence
from task_planning.migration.machine_identity import (
    current_machine_id,
    hashed_machine_id_errors,
    resolve_hashed_machine_id,
)
from task_planning.migration.verify import (
    ALLOWED_MIGRATION_VERIFICATION_CONTEXTS,
    MigrationVerification,
    verify_migration_archive,
)


HANDOFF_PACKAGE_SCHEMA = "DistributedFleetHandoffPackage.v1"
HANDOFF_PACKAGE_MANIFEST_SCHEMA = "DistributedFleetHandoffPackageManifest.v1"
HANDOFF_PACKAGE_VERIFICATION_SCHEMA = "DistributedFleetHandoffPackageVerification.v1"
PHASE_GATE_SCHEMA = "DistributedFleetPhaseGate.v1"
REQUIRED_EXTERNAL_EVIDENCE_SLOTS = [
    "migration_bundle_verified_after_transfer",
    "home_5090_model_lab_evaluated",
    "artifact_package_verified_after_transfer",
    "unit_ros1_gateway_signatures_observed",
    "unit_hardware_execution_artifact_verified",
]
REQUIRED_EXTERNAL_EVIDENCE_SLOT_SNIPPETS = {
    "migration_bundle_verified_after_transfer": [
        "reports/migration_verification.json",
        "reports/handoff_package_verification.json",
        "verify_task_planning_migration_bundle.py",
        "verify_distributed_fleet_handoff_package.py",
        "--verification-context receiving_machine",
    ],
    "home_5090_model_lab_evaluated": [
        "reports/model_lab_evaluation.json",
        "artifact_packages/*.tar.gz",
        "MODEL_LAB_EVIDENCE_KIND=home_5090_live",
        "RTX 5090",
        "evaluate_model_lab_case.py",
        "package_task_planning_artifacts.py",
    ],
    "artifact_package_verified_after_transfer": [
        "artifact_packages/*.tar.gz",
        "reports/artifact_package_verification.json",
        "verify_task_planning_artifacts.py",
        "--artifact-package-verification-report",
        "--verification-context unit_workplace_receiving",
        "source_machine_id",
        "verifier_machine_id",
    ],
    "unit_ros1_gateway_signatures_observed": [
        "reports/site_acceptance_work_hardware_ros1.json",
        "check_task_planning_site_acceptance.py",
        "--run-rosservice-list",
        "--run-service-signatures",
        "TaskCommandJson",
        "task_command_json",
    ],
    "unit_hardware_execution_artifact_verified": [
        "hardware_artifacts/<run_id>/",
        "record_unit_hardware_dispatch_artifact.py",
        "/gateway/dispatch",
        "operator_approved=true",
        "execution_context=unit_workplace_hardware",
    ],
}


@dataclass(frozen=True)
class DistributedFleetHandoffPackage:
    root: Path
    archive: Path
    manifest: Path
    migration_bundle_archive: Path
    evidence_dir: Path
    file_count: int
    schema: str = HANDOFF_PACKAGE_SCHEMA

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "root": str(self.root),
            "archive": str(self.archive),
            "manifest": str(self.manifest),
            "migration_bundle_archive": str(self.migration_bundle_archive),
            "evidence_dir": str(self.evidence_dir),
            "file_count": self.file_count,
        }


@dataclass(frozen=True)
class DistributedFleetHandoffPackageVerification:
    archive: Path
    extract_dir: Path
    package_root: Path
    checked_files: int
    manifest_errors: List[str] = field(default_factory=list)
    component_errors: List[str] = field(default_factory=list)
    migration_verification: Optional[MigrationVerification] = None
    verification_context: str = "unspecified"
    source_machine_id: str = ""
    verifier_machine_id: str = ""
    schema: str = HANDOFF_PACKAGE_VERIFICATION_SCHEMA

    @property
    def ok(self) -> bool:
        return (
            not self.manifest_errors
            and not self.component_errors
            and self.migration_verification is not None
            and self.migration_verification.ok
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "archive": str(self.archive),
            "extract_dir": str(self.extract_dir),
            "package_root": str(self.package_root),
            "checked_files": self.checked_files,
            "manifest_errors": list(self.manifest_errors),
            "component_errors": list(self.component_errors),
            "migration_verification": (
                self.migration_verification.as_dict()
                if self.migration_verification is not None
                else None
            ),
            "verification_context": self.verification_context,
            "source_machine_id": self.source_machine_id,
            "verifier_machine_id": self.verifier_machine_id,
        }


def build_distributed_fleet_handoff_package(
    *,
    repo_root: Path,
    output_dir: Path,
    package_name: str = "distributed-fleet-handoff-package",
    case_id: str = "uav_ugv_coordination",
    evidence_dir: Optional[Path] = None,
    source_machine_id: Optional[str] = None,
) -> DistributedFleetHandoffPackage:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    resolved_source_machine_id = resolve_hashed_machine_id(source_machine_id, "source_machine_id")
    output_dir.mkdir(parents=True, exist_ok=True)
    package_root = output_dir / package_name
    if package_root.exists():
        shutil.rmtree(package_root)
    package_root.mkdir(parents=True)

    migration_dir = package_root / "migration"
    migration_bundle = build_migration_bundle(
        repo_root=repo_root,
        output_dir=migration_dir,
        bundle_name="task-planning-migration-bundle",
        source_machine_id=resolved_source_machine_id,
    )

    target_evidence_dir = package_root / "evidence"
    if evidence_dir is None:
        evidence = collect_distributed_fleet_evidence(
            repo_root=repo_root,
            output_dir=target_evidence_dir,
            case_id=case_id,
        )
        target_evidence_dir = evidence.root
    else:
        source_evidence_dir = evidence_dir.expanduser().resolve()
        if not source_evidence_dir.exists() or not source_evidence_dir.is_dir():
            raise FileNotFoundError(f"evidence_dir is missing or not a directory: {source_evidence_dir}")
        shutil.copytree(source_evidence_dir, target_evidence_dir)

    evidence_manifest = _load_json_object(target_evidence_dir / "manifest.json")
    missing_required = evidence_manifest.get("missing_required") or []
    if not isinstance(missing_required, list):
        missing_required = []

    handoff_doc = _handoff_doc(
        package_name=package_name,
        case_id=case_id,
        missing_required=[str(item) for item in missing_required],
    )
    (package_root / "HANDOFF.md").write_text(handoff_doc, encoding="utf-8")

    manifest_data = _manifest(
        package_name=package_name,
        package_root=package_root,
        case_id=case_id,
        repo_root=repo_root,
        migration_bundle_archive=migration_bundle.archive,
        evidence_dir=target_evidence_dir,
        missing_required=[str(item) for item in missing_required],
        source_machine_id=resolved_source_machine_id,
    )
    manifest_path = package_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2, sort_keys=True), encoding="utf-8")

    archive_path = output_dir / f"{package_name}.tar.gz"
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(package_root, arcname=package_name)

    return DistributedFleetHandoffPackage(
        root=package_root,
        archive=archive_path,
        manifest=manifest_path,
        migration_bundle_archive=migration_bundle.archive,
        evidence_dir=target_evidence_dir,
        file_count=len(manifest_data["files"]) + 1,
    )


def verify_distributed_fleet_handoff_package(
    *,
    archive_path: Path,
    work_dir: Optional[Path] = None,
    verification_context: str = "unspecified",
    run_migration_checks: bool = False,
) -> DistributedFleetHandoffPackageVerification:
    if verification_context not in ALLOWED_MIGRATION_VERIFICATION_CONTEXTS:
        raise ValueError(f"unsupported handoff package verification context: {verification_context}")
    archive_path = archive_path.expanduser().resolve()
    if work_dir is None:
        extract_parent = Path(tempfile.mkdtemp(prefix="distributed-fleet-handoff-verify-")).resolve()
    else:
        work_dir = work_dir.expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        extract_parent = Path(tempfile.mkdtemp(prefix="extract-", dir=str(work_dir))).resolve()

    package_root = _extract_handoff_archive(archive_path, extract_parent)
    manifest_errors, checked_files, manifest = _verify_handoff_manifest(package_root)
    source_machine_id = str(manifest.get("source_machine_id") or "") if isinstance(manifest, dict) else ""
    verifier_machine_id = current_machine_id()
    manifest_errors.extend(_transfer_context_errors(
        source_machine_id=source_machine_id,
        verifier_machine_id=verifier_machine_id,
        verification_context=verification_context,
    ))
    component_errors = _verify_handoff_components(package_root, manifest)

    migration_verification: Optional[MigrationVerification] = None
    migration_archive_rel = _manifest_component(manifest, "migration_bundle_archive")
    if migration_archive_rel:
        migration_archive = package_root / migration_archive_rel
        if migration_archive.exists() and migration_archive.is_file():
            migration_verification = verify_migration_archive(
                archive_path=migration_archive,
                work_dir=extract_parent / "_migration_verify",
                run_checks=run_migration_checks,
                verification_context=verification_context,
            )
            component_errors.extend(_embedded_migration_identity_errors(
                source_machine_id=source_machine_id,
                verifier_machine_id=verifier_machine_id,
                migration_verification=migration_verification,
            ))

    return DistributedFleetHandoffPackageVerification(
        archive=archive_path,
        extract_dir=extract_parent,
        package_root=package_root,
        checked_files=checked_files,
        manifest_errors=manifest_errors,
        component_errors=component_errors,
        migration_verification=migration_verification,
        verification_context=verification_context,
        source_machine_id=source_machine_id,
        verifier_machine_id=verifier_machine_id,
    )


def _manifest(
    *,
    package_name: str,
    package_root: Path,
    case_id: str,
    repo_root: Path,
    migration_bundle_archive: Path,
    evidence_dir: Path,
    missing_required: List[str],
    source_machine_id: str,
) -> Dict[str, Any]:
    rel_files = [
        rel_path
        for rel_path in _iter_package_files(package_root)
        if rel_path != "manifest.json"
    ]
    return {
        "schema": HANDOFF_PACKAGE_MANIFEST_SCHEMA,
        "package_name": package_name,
        "case_id": case_id,
        "source_machine_id": source_machine_id,
        "source_repo_root": str(repo_root),
        "components": {
            "migration_bundle_archive": _rel(package_root, migration_bundle_archive),
            "migration_bundle_manifest": "migration/task-planning-migration-bundle/manifest.json",
            "evidence_dir": _rel(package_root, evidence_dir),
            "evidence_manifest": "evidence/manifest.json",
            "phase_gate": "evidence/PHASE_GATE.md",
            "phase_gate_report": "evidence/reports/phase_gate.json",
            "external_evidence_requirements": "evidence/reports/external_evidence_requirements.json",
            "next_external_evidence": "evidence/NEXT_EXTERNAL_EVIDENCE.md",
            "handoff_doc": "HANDOFF.md",
        },
        "missing_required": missing_required,
        "commands": {
            "verify_handoff_package": "PYTHONDONTWRITEBYTECODE=1 python3 <repo>/tools/verify_distributed_fleet_handoff_package.py <distributed-fleet-handoff-package.tar.gz> --work-dir /tmp/changxin-handoff-verify --verification-context receiving_machine",
            "verify_handoff_package_after_transfer": "PYTHONDONTWRITEBYTECODE=1 python3 <repo>/tools/verify_distributed_fleet_handoff_package.py <distributed-fleet-handoff-package.tar.gz> --work-dir /tmp/changxin-handoff-verify --verification-context receiving_machine",
            "verify_handoff_package_on_source": "PYTHONDONTWRITEBYTECODE=1 python3 <repo>/tools/verify_distributed_fleet_handoff_package.py <distributed-fleet-handoff-package.tar.gz> --work-dir /tmp/changxin-handoff-verify --verification-context source_machine",
            "verify_received_migration_bundle": "cd <package>/migration/task-planning-migration-bundle && PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_migration_bundle.py ../task-planning-migration-bundle.tar.gz --work-dir /tmp/changxin-migration-verify --verification-context receiving_machine",
            "inspect_phase_gate": "cd <package>/migration/task-planning-migration-bundle && PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_phase_gate.py --evidence-dir ../../evidence --print-discovered-inputs",
            "inspect_missing_evidence": "cd <package>/migration/task-planning-migration-bundle && PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir ../../evidence --missing-only --print-discovered-inputs",
            "unit_endpoint_runbook": "Open <package>/migration/task-planning-migration-bundle/docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md before ROS1 gateway preparation.",
            "import_external_evidence": "cd <package>/migration/task-planning-migration-bundle && PYTHONDONTWRITEBYTECODE=1 python3 tools/import_distributed_fleet_external_evidence.py --evidence-dir ../../evidence --model-lab-evaluation <model_lab_evaluation.json> --migration-verification-report <migration_verification.json> --handoff-package-verification-report <handoff_package_verification.json> --artifact-package-verification-report <artifact_package_verification.json> --site-acceptance-ros1-report <site_acceptance_work_hardware_ros1.json> --artifact-package <artifact-package.tar.gz> --hardware-run-artifact <hardware-run-artifact-root>",
            "record_unit_hardware_dispatch_artifact": "cd <package>/migration/task-planning-migration-bundle && PYTHONDONTWRITEBYTECODE=1 python3 tools/record_unit_hardware_dispatch_artifact.py --source-artifact <prevalidated_artifact_root> --profile <local-work-hardware-ros1-gateway.env> --output-dir ../../evidence/hardware_artifacts --platform-id <platform_id> --task-id <task_id> --dispatch-service /fleet/<platform_id>/gateway/dispatch --dispatch-stdout-file /tmp/changxin-dispatch-response.txt --task-progress-file /tmp/changxin-task-progress.json --operator-approved",
        },
        "files": [
            {
                "path": rel_path,
                "sha256": _sha256(package_root / rel_path),
                "bytes": (package_root / rel_path).stat().st_size,
            }
            for rel_path in rel_files
        ],
    }


def _handoff_doc(*, package_name: str, case_id: str, missing_required: List[str]) -> str:
    missing_lines = [f"- `{name}`" for name in missing_required] or ["- none"]
    return "\n".join([
        "# Distributed Fleet Handoff Package",
        "",
        f"Package: `{package_name}`",
        f"Case: `{case_id}`",
        "",
        "This package is a transfer scaffold for another machine or agent. It contains a migration archive plus a local baseline evidence directory, but it does not prove that the home 5090, receiving machine, unit ROS1 gateway, or real hardware execution has happened.",
        "",
        "## Contents",
        "",
        "- `migration/task-planning-migration-bundle.tar.gz`: portable source bundle.",
        "- `migration/task-planning-migration-bundle/`: extracted source bundle for immediate inspection.",
        "- `evidence/`: local baseline evidence, goal report, and external-proof targets.",
        "- `evidence/PHASE_GATE.md`: local freeze and next-phase gate status.",
        "- `evidence/reports/phase_gate.json`: machine-readable local freeze and next-phase gate status.",
        "- `evidence/reports/external_evidence_requirements.json`: machine-readable external-proof slots.",
        "- `evidence/NEXT_EXTERNAL_EVIDENCE.md`: exact missing proof slots for the next machine.",
        "- `manifest.json`: checksums for this handoff package.",
        "",
        "## Phase Gate",
        "",
        "If `evidence/PHASE_GATE.md` says `Local v1 freeze: true` and `Next phase ready: false`, do not keep expanding local implementation solely because external proofs are missing. Import real reports and packages, then rerun `tools/check_distributed_fleet_goal_evidence.py`.",
        "",
        "## Missing External Proof",
        "",
        *missing_lines,
        "",
        "## First Commands On A Receiving Machine",
        "",
        "```bash",
        f"PYTHONDONTWRITEBYTECODE=1 python3 /path/to/changxin-code/tools/verify_distributed_fleet_handoff_package.py {package_name}.tar.gz --work-dir /tmp/changxin-handoff-verify --verification-context receiving_machine > /tmp/changxin-handoff-package-verification.json",
        f"tar -xzf {package_name}.tar.gz",
        f"cd {package_name}/migration/task-planning-migration-bundle",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_migration_bundle.py ../task-planning-migration-bundle.tar.gz --work-dir /tmp/changxin-migration-verify --verification-context receiving_machine",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_phase_gate.py --evidence-dir ../../evidence --print-discovered-inputs",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir ../../evidence --missing-only --print-discovered-inputs",
        "```",
        "",
        "## Unit/Workplace Execution Endpoint",
        "",
        "At the unit/workplace endpoint, read `docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md` first. Do not use the home 5090 endpoint as a live execution dependency. Read-only ROS1 signature evidence and `/gateway/dry_run` are gates, not final hardware execution proof.",
        "",
        "After a locally approved real `/gateway/dispatch`, use `tools/record_unit_hardware_dispatch_artifact.py` to assemble the captured dispatch response, accepted `CommandAck`, and `TaskProgress` into `evidence/hardware_artifacts/<run_id>/`; the tool itself does not send ROS commands.",
        "",
        "Final hardware proof must be imported as a real `work_hardware` + `ros1_gateway` dispatch artifact with `HARDWARE_APPROVAL_REQUIRED=true`, machine-readable `operator_approved=true`, `operator_approval_source=local_unit_operator`, `execution_context=unit_workplace_hardware`, a successful `/gateway/dispatch` trace, accepted `CommandAck`, and `TaskProgress` matching the same `mission_id` / `task_id` / `platform_id`.",
        "",
    ])


def _load_json_object(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _extract_handoff_archive(archive_path: Path, extract_dir: Path) -> Path:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        members = tar.getmembers()
        if not members:
            raise ValueError("handoff package archive is empty")
        top_levels = set()
        for member in members:
            _validate_tar_member(member, extract_dir)
            path = PurePosixPath(member.name)
            if path.parts:
                top_levels.add(path.parts[0])
        if len(top_levels) != 1:
            raise ValueError(f"handoff package archive must contain one top-level directory, got {sorted(top_levels)}")
        tar.extractall(extract_dir)
    return extract_dir / sorted(top_levels)[0]


def _verify_handoff_manifest(package_root: Path) -> Tuple[List[str], int, Dict[str, Any]]:
    errors: List[str] = []
    checked_files = 0
    manifest_path = package_root / "manifest.json"
    if not manifest_path.exists():
        return ["missing manifest.json"], checked_files, {}
    try:
        manifest = _load_json_object(manifest_path)
    except Exception as exc:
        return [f"invalid manifest.json: {exc}"], checked_files, {}

    if manifest.get("schema") != HANDOFF_PACKAGE_MANIFEST_SCHEMA:
        errors.append(f"unexpected manifest schema: {manifest.get('schema')!r}")
    errors.extend(hashed_machine_id_errors(manifest.get("source_machine_id"), "source_machine_id"))
    if not str(manifest.get("case_id") or ""):
        errors.append("case_id is required")

    files = manifest.get("files")
    if not isinstance(files, list):
        errors.append("manifest files must be a list")
        files = []

    for index, item in enumerate(files):
        if not isinstance(item, dict):
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

    return errors, checked_files, manifest


def _verify_handoff_components(package_root: Path, manifest: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    manifest_case_id = str(manifest.get("case_id") or "")
    expected_components = [
        "migration_bundle_archive",
        "migration_bundle_manifest",
        "evidence_dir",
        "evidence_manifest",
        "phase_gate",
        "phase_gate_report",
        "external_evidence_requirements",
        "next_external_evidence",
        "handoff_doc",
    ]
    components = manifest.get("components")
    if not isinstance(components, dict):
        return ["manifest components must be an object"]

    for key in expected_components:
        rel_path = components.get(key)
        if not isinstance(rel_path, str):
            errors.append(f"components.{key} must be a string")
            continue
        if not _is_safe_relative_posix_path(rel_path):
            errors.append(f"components.{key} is unsafe: {rel_path!r}")
            continue
        path = package_root / Path(rel_path)
        if not _is_within(path, package_root):
            errors.append(f"components.{key} escapes package root: {rel_path!r}")
            continue
        if not path.exists():
            errors.append(f"components.{key} is missing: {rel_path}")
            continue
        if key != "evidence_dir" and not path.is_file():
            errors.append(f"components.{key} is not a regular file: {rel_path}")

    missing_required = manifest.get("missing_required")
    if not isinstance(missing_required, list):
        errors.append("missing_required must be a list")

    evidence_manifest_rel = _manifest_component(manifest, "evidence_manifest")
    evidence_missing_required: List[str] = []
    evidence_phase_gate: Any = None
    if evidence_manifest_rel:
        try:
            evidence_manifest = _load_json_object(package_root / evidence_manifest_rel)
        except Exception as exc:
            errors.append(f"evidence manifest is unreadable: {exc}")
        else:
            if evidence_manifest.get("schema") != "DistributedFleetEvidenceCollectionManifest.v1":
                errors.append(f"unexpected evidence manifest schema: {evidence_manifest.get('schema')!r}")
            evidence_case_id = str(evidence_manifest.get("case_id") or "")
            if not evidence_case_id:
                errors.append("evidence manifest case_id is required")
            elif manifest_case_id and manifest_case_id != evidence_case_id:
                errors.append("manifest case_id must match evidence manifest case_id")
            evidence_missing_required = _string_list(evidence_manifest.get("missing_required"))
            if evidence_missing_required is None:
                errors.append("evidence manifest missing_required must be a list")
            elif isinstance(missing_required, list) and missing_required != evidence_missing_required:
                errors.append("manifest missing_required must match evidence manifest missing_required")
            evidence_phase_gate = evidence_manifest.get("phase_gate")
            errors.extend(_phase_gate_manifest_errors(evidence_phase_gate, missing_required))

    phase_gate_rel = _manifest_component(manifest, "phase_gate")
    if phase_gate_rel:
        try:
            phase_gate_text = (package_root / phase_gate_rel).read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"PHASE_GATE.md is unreadable: {exc}")
        else:
            errors.extend(_phase_gate_doc_errors(phase_gate_text))

    phase_gate_report_rel = _manifest_component(manifest, "phase_gate_report")
    if phase_gate_report_rel:
        try:
            phase_gate_report = _load_json_object(package_root / phase_gate_report_rel)
        except Exception as exc:
            errors.append(f"phase gate report is unreadable: {exc}")
        else:
            errors.extend(_phase_gate_manifest_errors(phase_gate_report, missing_required))
            if isinstance(evidence_phase_gate, dict) and phase_gate_report != evidence_phase_gate:
                errors.append("phase gate report must match evidence manifest phase_gate")

    requirements_rel = _manifest_component(manifest, "external_evidence_requirements")
    if requirements_rel:
        try:
            requirements = _load_json_object(package_root / requirements_rel)
        except Exception as exc:
            errors.append(f"external evidence requirements report is unreadable: {exc}")
        else:
            if requirements.get("schema") != "DistributedFleetExternalEvidenceHandoff.v1":
                errors.append(f"unexpected external evidence requirements schema: {requirements.get('schema')!r}")
            requirements_case_id = str(requirements.get("case_id") or "")
            if not requirements_case_id:
                errors.append("external evidence requirements case_id is required")
            elif manifest_case_id and manifest_case_id != requirements_case_id:
                errors.append("manifest case_id must match external evidence requirements case_id")
            requirements_missing = _string_list(requirements.get("missing_required"))
            if requirements_missing is None:
                errors.append("external evidence requirements missing_required must be a list")
            elif isinstance(missing_required, list) and missing_required != requirements_missing:
                errors.append("manifest missing_required must match external evidence requirements missing_required")
            errors.extend(_external_evidence_slot_errors(requirements))

    next_external_rel = _manifest_component(manifest, "next_external_evidence")
    if next_external_rel:
        try:
            next_external_text = (package_root / next_external_rel).read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"NEXT_EXTERNAL_EVIDENCE.md is unreadable: {exc}")
        else:
            errors.extend(_next_external_evidence_doc_errors(next_external_text))

    handoff_doc_rel = _manifest_component(manifest, "handoff_doc")
    if handoff_doc_rel:
        try:
            handoff_text = (package_root / handoff_doc_rel).read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"HANDOFF.md is unreadable: {exc}")
        else:
            errors.extend(_handoff_doc_errors(handoff_text))
    return errors


def _phase_gate_manifest_errors(phase_gate: Any, missing_required: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(phase_gate, dict):
        return ["evidence manifest phase_gate must be an object"]
    if phase_gate.get("schema") != PHASE_GATE_SCHEMA:
        errors.append(f"evidence manifest phase_gate.schema must be {PHASE_GATE_SCHEMA}")
    status = str(phase_gate.get("status") or "")
    if status not in {
        "local_implementation_required",
        "external_evidence_rejected",
        "waiting_for_external_proofs",
        "next_phase_ready",
    }:
        errors.append("evidence manifest phase_gate.status is invalid")
    if not isinstance(phase_gate.get("local_v1_freeze"), bool):
        errors.append("evidence manifest phase_gate.local_v1_freeze must be boolean")
    if not isinstance(phase_gate.get("next_phase_ready"), bool):
        errors.append("evidence manifest phase_gate.next_phase_ready must be boolean")
    missing_external = _string_list(phase_gate.get("missing_external_proofs"))
    if missing_external is None:
        errors.append("evidence manifest phase_gate.missing_external_proofs must be a list")
        missing_external = []
    local_unresolved = _string_list(phase_gate.get("local_unresolved_required"))
    if local_unresolved is None:
        errors.append("evidence manifest phase_gate.local_unresolved_required must be a list")
        local_unresolved = []
    required_external = _string_list(phase_gate.get("required_external_proofs"))
    if required_external is None:
        errors.append("evidence manifest phase_gate.required_external_proofs must be a list")
    elif not set(REQUIRED_EXTERNAL_EVIDENCE_SLOTS).issubset(set(required_external)):
        errors.append("evidence manifest phase_gate.required_external_proofs must include every external proof slot")
    if (
        isinstance(missing_required, list)
        and phase_gate.get("local_v1_freeze") is True
        and sorted(str(item) for item in missing_required) != sorted(missing_external)
    ):
        errors.append("evidence manifest missing_required must match phase_gate.missing_external_proofs when local_v1_freeze is true")
    if phase_gate.get("next_phase_ready") is True and missing_required:
        errors.append("evidence manifest phase_gate.next_phase_ready cannot be true while missing_required is non-empty")
    if phase_gate.get("next_phase_ready") is True and local_unresolved:
        errors.append("evidence manifest phase_gate.next_phase_ready cannot be true while local_unresolved_required is non-empty")
    return errors


def _phase_gate_doc_errors(text: str) -> List[str]:
    if not text.strip():
        return ["PHASE_GATE.md must not be empty"]
    required_snippets = [
        "Status:",
        "Local v1 freeze:",
        "Next phase ready:",
        "Missing external proofs:",
        "Local unresolved requirements:",
        "do not keep expanding local implementation",
        "check_distributed_fleet_goal_evidence.py",
    ]
    return [
        f"PHASE_GATE.md must include {snippet}"
        for snippet in required_snippets
        if snippet not in text
    ]


def _external_evidence_slot_errors(requirements: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    slots = requirements.get("slots")
    if not isinstance(slots, list) or not slots:
        return ["external evidence requirements slots must be a non-empty list"]

    observed_names: List[str] = []
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict):
            errors.append(f"external evidence requirements slots[{index}] must be an object")
            continue
        name = str(slot.get("name") or "").strip()
        if not name:
            errors.append(f"external evidence requirements slots[{index}].name is required")
        else:
            observed_names.append(name)
        for key in ("target_paths", "constraints", "commands"):
            value = slot.get(key)
            if not isinstance(value, list) or not value:
                errors.append(f"external evidence requirements slots[{index}].{key} must be a non-empty list")
        slot_text = _slot_text(slot)
        for snippet in REQUIRED_EXTERNAL_EVIDENCE_SLOT_SNIPPETS.get(name, []):
            if snippet not in slot_text:
                errors.append(f"external evidence requirements slot {name} must mention {snippet}")

    missing_slots = [
        name for name in REQUIRED_EXTERNAL_EVIDENCE_SLOTS
        if name not in set(observed_names)
    ]
    if missing_slots:
        errors.append("external evidence requirements slots missing required names: " + ", ".join(missing_slots))
    return errors


def _next_external_evidence_doc_errors(text: str) -> List[str]:
    errors: List[str] = []
    if not text.strip():
        return ["NEXT_EXTERNAL_EVIDENCE.md must not be empty"]
    for name in REQUIRED_EXTERNAL_EVIDENCE_SLOTS:
        if name not in text:
            errors.append(f"NEXT_EXTERNAL_EVIDENCE.md must mention {name}")
    required_snippets = [
        "check_distributed_fleet_goal_evidence.py --evidence-dir",
        "--missing-only --print-discovered-inputs",
        "import_distributed_fleet_external_evidence.py",
        "--artifact-package-verification-report",
    ]
    for snippet in required_snippets:
        if snippet not in text:
            errors.append(f"NEXT_EXTERNAL_EVIDENCE.md must include {snippet}")
    return errors


def _handoff_doc_errors(text: str) -> List[str]:
    if not text.strip():
        return ["HANDOFF.md must not be empty"]
    required_snippets = [
        "docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md",
        "Do not use the home 5090 endpoint as a live execution dependency",
        "Read-only ROS1 signature evidence",
        "/gateway/dry_run",
        "tools/record_unit_hardware_dispatch_artifact.py",
        "work_hardware",
        "ros1_gateway",
        "HARDWARE_APPROVAL_REQUIRED=true",
        "operator_approved=true",
        "operator_approval_source=local_unit_operator",
        "execution_context=unit_workplace_hardware",
        "/gateway/dispatch",
        "CommandAck",
        "TaskProgress",
        "mission_id",
        "task_id",
        "platform_id",
        "verify_task_planning_migration_bundle.py",
        "verify_distributed_fleet_handoff_package.py",
        "--verification-context receiving_machine",
        "check_distributed_fleet_goal_evidence.py --evidence-dir",
    ]
    return [
        f"HANDOFF.md must include {snippet}"
        for snippet in required_snippets
        if snippet not in text
    ]


def _string_list(value: Any) -> Optional[List[str]]:
    if not isinstance(value, list):
        return None
    return [str(item) for item in value]


def _slot_text(slot: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("target_paths", "constraints", "commands"):
        value = slot.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return "\n".join(parts)


def _transfer_context_errors(
    *,
    source_machine_id: str,
    verifier_machine_id: str,
    verification_context: str,
) -> List[str]:
    if verification_context not in {"receiving_machine", "unit_workplace_receiving"}:
        return []
    errors = [
        *hashed_machine_id_errors(source_machine_id, "source_machine_id"),
        *hashed_machine_id_errors(verifier_machine_id, "verifier_machine_id"),
    ]
    if source_machine_id and verifier_machine_id and source_machine_id == verifier_machine_id:
        errors.append(
            "receiving-machine verification must run on a different machine than the source; "
            "use verification_context=source_machine for local sanity checks"
        )
    return errors


def _embedded_migration_identity_errors(
    *,
    source_machine_id: str,
    verifier_machine_id: str,
    migration_verification: MigrationVerification,
) -> List[str]:
    errors: List[str] = []
    migration_source = migration_verification.manifest.source_machine_id
    migration_verifier = migration_verification.verifier_machine_id
    if source_machine_id and migration_source and source_machine_id != migration_source:
        errors.append("handoff source_machine_id must match embedded migration source_machine_id")
    if verifier_machine_id and migration_verifier and verifier_machine_id != migration_verifier:
        errors.append("handoff verifier_machine_id must match embedded migration verifier_machine_id")
    return errors


def _manifest_component(manifest: Dict[str, Any], key: str) -> str:
    components = manifest.get("components")
    if not isinstance(components, dict):
        return ""
    value = components.get(key)
    if not isinstance(value, str) or not _is_safe_relative_posix_path(value):
        return ""
    return value


def _iter_package_files(root: Path) -> Iterable[str]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path.relative_to(root).as_posix()


def _rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _validate_tar_member(member: tarfile.TarInfo, extract_dir: Path) -> None:
    if member.issym() or member.islnk():
        raise ValueError(f"handoff package archive must not contain links: {member.name!r}")
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
