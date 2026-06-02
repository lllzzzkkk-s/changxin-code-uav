from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Sequence

from task_planning.migration.bundle import _sha256
from task_planning.migration.machine_identity import current_machine_id, hashed_machine_id_errors


MANIFEST_SCHEMA = "TaskPlanningMigrationManifest.v1"
MIGRATION_VERIFICATION_SCHEMA = "MigrationVerification.v1"
ALLOWED_MIGRATION_VERIFICATION_CONTEXTS = {
    "unspecified",
    "source_machine",
    "receiving_machine",
    "unit_workplace_receiving",
}


@dataclass(frozen=True)
class ManifestVerification:
    bundle_root: Path
    bundle_name: str
    checked_files: int
    source_machine_id: str = ""
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok,
            "bundle_root": str(self.bundle_root),
            "bundle_name": self.bundle_name,
            "checked_files": self.checked_files,
            "source_machine_id": self.source_machine_id,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class FirstCheck:
    name: str
    command: List[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def as_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok,
            "name": self.name,
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True)
class MigrationVerification:
    archive: Path
    extract_dir: Path
    bundle_root: Path
    manifest: ManifestVerification
    checks: List[FirstCheck] = field(default_factory=list)
    verification_context: str = "unspecified"
    verifier_machine_id: str = ""
    schema: str = MIGRATION_VERIFICATION_SCHEMA

    @property
    def ok(self) -> bool:
        return self.manifest.ok and all(check.ok for check in self.checks)

    def as_dict(self) -> Dict[str, object]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "archive": str(self.archive),
            "extract_dir": str(self.extract_dir),
            "bundle_root": str(self.bundle_root),
            "manifest": self.manifest.as_dict(),
            "checks": [check.as_dict() for check in self.checks],
            "verification_context": self.verification_context,
            "source_machine_id": self.manifest.source_machine_id,
            "verifier_machine_id": self.verifier_machine_id,
        }


def verify_manifest(bundle_root: Path) -> ManifestVerification:
    bundle_root = bundle_root.resolve()
    manifest_path = bundle_root / "manifest.json"
    errors: List[str] = []

    if not manifest_path.exists():
        return ManifestVerification(
            bundle_root=bundle_root,
            bundle_name=bundle_root.name,
            checked_files=0,
            source_machine_id="",
            errors=["missing manifest.json"],
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ManifestVerification(
            bundle_root=bundle_root,
            bundle_name=bundle_root.name,
            checked_files=0,
            source_machine_id="",
            errors=[f"invalid manifest.json: {exc}"],
        )

    bundle_name = str(manifest.get("bundle_name") or bundle_root.name)
    source_machine_id = str(manifest.get("source_machine_id") or "")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        errors.append(f"unexpected manifest schema: {manifest.get('schema')!r}")
    errors.extend(hashed_machine_id_errors(source_machine_id, "manifest source_machine_id"))

    files = manifest.get("files")
    if not isinstance(files, list):
        errors.append("manifest files must be a list")
        files = []

    checked_files = 0
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

        path = bundle_root / Path(rel_path)
        if not _is_within(path, bundle_root):
            errors.append(f"manifest path escapes bundle root: {rel_path!r}")
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

    return ManifestVerification(
        bundle_root=bundle_root,
        bundle_name=bundle_name,
        checked_files=checked_files,
        source_machine_id=source_machine_id,
        errors=errors,
    )


def extract_bundle(archive_path: Path, extract_dir: Path) -> Path:
    archive_path = archive_path.resolve()
    extract_dir = extract_dir.resolve()
    extract_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "r:gz") as tar:
        members = tar.getmembers()
        if not members:
            raise ValueError("migration archive is empty")
        top_levels = set()
        for member in members:
            _validate_tar_member(member, extract_dir)
            path = PurePosixPath(member.name)
            if path.parts:
                top_levels.add(path.parts[0])
        if len(top_levels) != 1:
            raise ValueError(f"migration archive must contain one top-level directory, got {sorted(top_levels)}")
        tar.extractall(extract_dir)

    return extract_dir / sorted(top_levels)[0]


def run_bundle_first_checks(bundle_root: Path) -> List[FirstCheck]:
    bundle_root = bundle_root.resolve()
    artifact_root = bundle_root / "runs" / "verify-dev-mock"
    commands = [
        (
            "task_planning_tests",
            [sys.executable, "-m", "unittest", "discover", "tests/task_planning"],
        ),
        (
            "dev_mock_golden",
            [
                sys.executable,
                "tools/run_task_planning_golden.py",
                "--profile",
                "profiles/dev_mock.env",
                "--case",
                "uav_ugv_coordination",
                "--artifact-root",
                str(artifact_root),
            ],
        ),
        (
            "dev_mock_golden_suite",
            [
                sys.executable,
                "tools/run_dev_mock_golden_suite.py",
                "--artifact-root",
                str(bundle_root / "runs" / "verify-dev-mock-golden-suite"),
            ],
        ),
        (
            "lane_matrix",
            [
                sys.executable,
                "tools/run_task_planning_lane_matrix.py",
                "--artifact-root",
                str(bundle_root / "runs" / "verify-lane-matrix"),
                "--case",
                "uav_ugv_coordination",
            ],
        ),
        (
            "external_evidence_handoff",
            [
                sys.executable,
                "tools/init_external_evidence_handoff.py",
                "--evidence-dir",
                str(bundle_root / "runs" / "verify-external-evidence"),
                "--missing-required",
                "home_5090_model_lab_evaluated",
            ],
        ),
        (
            "external_evidence_import",
            [
                sys.executable,
                "tools/import_distributed_fleet_external_evidence.py",
                "--evidence-dir",
                str(bundle_root / "runs" / "verify-external-evidence"),
            ],
        ),
        (
            "ros1_service_audit_plan",
            [
                sys.executable,
                "tools/audit_ros1_gateway_services.py",
                "--profile",
                "profiles/work_hardware.env",
                "--platform-id",
                "uav_0",
                "--platform-id",
                "ugv_0",
            ],
        ),
        (
            "site_acceptance_work_hardware",
            [
                sys.executable,
                "tools/check_task_planning_site_acceptance.py",
                "--profile",
                "profiles/work_hardware.env",
            ],
        ),
    ]
    return [_run_check(name, command, bundle_root) for name, command in commands]


def verify_migration_archive(
    *,
    archive_path: Path,
    work_dir: Optional[Path] = None,
    run_checks: bool = True,
    verification_context: str = "unspecified",
) -> MigrationVerification:
    if verification_context not in ALLOWED_MIGRATION_VERIFICATION_CONTEXTS:
        raise ValueError(f"unsupported migration verification context: {verification_context}")
    archive_path = archive_path.resolve()
    if work_dir is None:
        extract_parent = Path(tempfile.mkdtemp(prefix="task-planning-migration-verify-")).resolve()
    else:
        work_dir = work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        extract_parent = Path(tempfile.mkdtemp(prefix="extract-", dir=str(work_dir))).resolve()

    bundle_root = extract_bundle(archive_path, extract_parent)
    manifest = verify_manifest(bundle_root)
    verifier_machine_id = current_machine_id()
    manifest = _apply_transfer_context_checks(
        manifest,
        verification_context=verification_context,
        verifier_machine_id=verifier_machine_id,
    )
    checks = run_bundle_first_checks(bundle_root) if run_checks and manifest.ok else []
    return MigrationVerification(
        archive=archive_path,
        extract_dir=extract_parent,
        bundle_root=bundle_root,
        manifest=manifest,
        checks=checks,
        verification_context=verification_context,
        verifier_machine_id=verifier_machine_id,
    )


def _apply_transfer_context_checks(
    manifest: ManifestVerification,
    *,
    verification_context: str,
    verifier_machine_id: str,
) -> ManifestVerification:
    if verification_context not in {"receiving_machine", "unit_workplace_receiving"}:
        return manifest
    errors = list(manifest.errors)
    errors.extend(hashed_machine_id_errors(manifest.source_machine_id, "source_machine_id"))
    errors.extend(hashed_machine_id_errors(verifier_machine_id, "verifier_machine_id"))
    if manifest.source_machine_id and verifier_machine_id and manifest.source_machine_id == verifier_machine_id:
        errors.append(
            "receiving-machine verification must run on a different machine than the source; "
            "use verification_context=source_machine for local sanity checks"
        )
    return ManifestVerification(
        bundle_root=manifest.bundle_root,
        bundle_name=manifest.bundle_name,
        checked_files=manifest.checked_files,
        source_machine_id=manifest.source_machine_id,
        errors=errors,
    )


def _run_check(name: str, command: Sequence[str], cwd: Path) -> FirstCheck:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["TASK_PLANNING_MIGRATION_VERIFY_SUBPROCESS"] = "1"
    env["PYTHONPATH"] = _prepend_path(str(cwd), env.get("PYTHONPATH", ""))
    completed = subprocess.run(
        list(command),
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return FirstCheck(
        name=name,
        command=list(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _validate_tar_member(member: tarfile.TarInfo, extract_dir: Path) -> None:
    if member.issym() or member.islnk():
        raise ValueError(f"migration archive must not contain links: {member.name!r}")
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


def _prepend_path(path: str, existing: str) -> str:
    return path if not existing else f"{path}{os.pathsep}{existing}"
