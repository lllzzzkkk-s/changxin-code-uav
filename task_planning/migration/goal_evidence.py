from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from task_planning.migration.artifact_package import (
    ARTIFACT_PACKAGE_VERIFICATION_SCHEMA,
    ARTIFACT_PACKAGE_VERIFICATION_SET_SCHEMA,
    ArtifactPackageVerification,
    verify_artifact_package,
)
from task_planning.migration.golden_suite import REQUIRED_GOLDEN_CASE_IDS
from task_planning.migration.hardware_evidence import inspect_hardware_execution_artifact
from task_planning.migration.machine_identity import hashed_machine_id_errors
from task_planning.migration.model_lab import model_lab_home_5090_live_errors
from task_planning.migration.readiness import check_task_planning_readiness
from task_planning.migration.verify import MIGRATION_VERIFICATION_SCHEMA


PASS = "pass"
FAIL = "fail"
MISSING = "missing"
WARN = "warn"
HANDOFF_PACKAGE_VERIFICATION_SCHEMA = "DistributedFleetHandoffPackageVerification.v1"
PHASE_GATE_SCHEMA = "DistributedFleetPhaseGate.v1"
EXTERNAL_PROOF_ITEM_NAMES = (
    "migration_bundle_verified_after_transfer",
    "artifact_package_verified_after_transfer",
    "home_5090_model_lab_evaluated",
    "unit_ros1_gateway_signatures_observed",
    "unit_hardware_execution_artifact_verified",
)


@dataclass(frozen=True)
class GoalEvidenceItem:
    name: str
    status: str
    message: str
    required: bool
    evidence: Dict[str, Any] = field(default_factory=dict)
    next_commands: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == PASS or (not self.required and self.status in {PASS, WARN, MISSING})

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DistributedFleetGoalEvidenceReport:
    repo_root: Path
    items: List[GoalEvidenceItem]
    schema: str = "DistributedFleetGoalEvidence.v1"

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.items)

    @property
    def missing_required(self) -> List[GoalEvidenceItem]:
        return [item for item in self.items if item.required and item.status == MISSING]

    @property
    def failed_required(self) -> List[GoalEvidenceItem]:
        return [item for item in self.items if item.required and item.status == FAIL]

    @property
    def phase_gate(self) -> Dict[str, Any]:
        return _goal_phase_gate(self.items)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "repo_root": str(self.repo_root),
            "phase_gate": self.phase_gate,
            "items": [item.as_dict() for item in self.items],
            "missing_required": [item.as_dict() for item in self.missing_required],
            "failed_required": [item.as_dict() for item in self.failed_required],
        }


def summarize_goal_evidence_report(
    report: DistributedFleetGoalEvidenceReport,
    *,
    missing_only: bool = False,
) -> Dict[str, Any]:
    relevant_items = [
        item
        for item in report.items
        if not missing_only or (item.required and item.status in {MISSING, FAIL})
    ]
    return {
        "schema": "DistributedFleetGoalEvidenceSummary.v1",
        "ok": report.ok,
        "repo_root": str(report.repo_root),
        "phase_gate": report.phase_gate,
        "counts": {
            "total": len(report.items),
            "passed_required": len([item for item in report.items if item.required and item.status == PASS]),
            "missing_required": len(report.missing_required),
            "failed_required": len(report.failed_required),
            "warnings": len([item for item in report.items if item.status == WARN]),
        },
        "items": [
            {
                "name": item.name,
                "status": item.status,
                "required": item.required,
                "message": item.message,
                "next_commands": item.next_commands,
            }
            for item in relevant_items
        ],
    }


def _goal_phase_gate(items: Sequence[GoalEvidenceItem]) -> Dict[str, Any]:
    required_by_name = {item.name: item for item in items if item.required}
    unresolved_required = [
        item
        for item in required_by_name.values()
        if item.status in {MISSING, FAIL}
    ]
    external_names = set(EXTERNAL_PROOF_ITEM_NAMES)
    local_unresolved = sorted(
        item.name for item in unresolved_required
        if item.name not in external_names
    )
    missing_external = sorted(
        name for name in EXTERNAL_PROOF_ITEM_NAMES
        if required_by_name.get(name) is None or required_by_name[name].status == MISSING
    )
    failed_external = sorted(
        name for name in EXTERNAL_PROOF_ITEM_NAMES
        if required_by_name.get(name) is not None and required_by_name[name].status == FAIL
    )
    passed_external = sorted(
        name for name in EXTERNAL_PROOF_ITEM_NAMES
        if required_by_name.get(name) is not None and required_by_name[name].status == PASS
    )

    if local_unresolved:
        status = "local_implementation_required"
        message = "local implementation evidence is still missing or failing before external proof collection"
    elif failed_external:
        status = "external_evidence_rejected"
        message = "local v1 is frozen, but one or more supplied external proofs were rejected"
    elif missing_external:
        status = "waiting_for_external_proofs"
        message = "local v1 is frozen; collect the required external proofs before starting the next phase"
    else:
        status = "next_phase_ready"
        message = "all local and external proof gates passed; the next phase can start"

    return {
        "schema": PHASE_GATE_SCHEMA,
        "status": status,
        "message": message,
        "local_v1_freeze": not local_unresolved,
        "next_phase_ready": status == "next_phase_ready",
        "required_external_proofs": list(EXTERNAL_PROOF_ITEM_NAMES),
        "missing_external_proofs": missing_external,
        "failed_external_proofs": failed_external,
        "passed_external_proofs": passed_external,
        "local_unresolved_required": local_unresolved,
        "policy": (
            "Do not keep iterating local implementation solely because these external proofs are missing; "
            "only resume local changes if a verifier accepts weak proof or a real import exposes a code defect."
        ),
    }


def build_distributed_fleet_goal_evidence(
    *,
    repo_root: Path,
    artifact_packages: Sequence[Path] = (),
    artifact_package_verification_reports: Sequence[Path] = (),
    artifact_work_dir: Optional[Path] = None,
    site_acceptance_reports: Sequence[Path] = (),
    lane_matrix_reports: Sequence[Path] = (),
    dev_mock_golden_suite_reports: Sequence[Path] = (),
    model_lab_evaluations: Sequence[Path] = (),
    migration_verification_reports: Sequence[Path] = (),
    handoff_package_verification_reports: Sequence[Path] = (),
    hardware_run_artifacts: Sequence[Path] = (),
) -> DistributedFleetGoalEvidenceReport:
    repo_root = repo_root.resolve()
    site_reports = [_load_json_report(path) for path in site_acceptance_reports]
    lane_reports = [_load_json_report(path) for path in lane_matrix_reports]
    golden_suite_reports = [_load_json_report(path) for path in dev_mock_golden_suite_reports]
    model_reports = [_load_model_lab_evaluation(path) for path in model_lab_evaluations]
    migration_reports = [_load_json_report(path) for path in migration_verification_reports]
    handoff_reports = [_load_json_report(path) for path in handoff_package_verification_reports]
    artifact_verification_reports = [_load_json_report(path) for path in artifact_package_verification_reports]
    artifact_verifications = _verify_artifact_packages(artifact_packages, artifact_work_dir=artifact_work_dir)
    hardware_artifact_reports = [_inspect_hardware_artifact(path) for path in hardware_run_artifacts]

    items = [
        _repo_contract_item(repo_root),
        _profile_readiness_item(repo_root, "profiles/dev_mock.env", "dev_mock_profile_ready"),
        _profile_readiness_item(repo_root, "profiles/home_model_lab.env", "home_model_lab_profile_isolated"),
        _profile_readiness_item(repo_root, "profiles/work_hardware.env", "work_hardware_profile_no_large_model"),
        _mock_first_boundary_item(repo_root),
        _lane_matrix_item(lane_reports),
        _dev_mock_golden_suite_item(golden_suite_reports),
        _migration_bundle_item(migration_reports, handoff_reports),
        _artifact_package_item(artifact_verifications, artifact_verification_reports, site_reports, lane_reports),
        _home_model_lab_item(model_reports, lane_reports, artifact_verifications, artifact_verification_reports, site_reports),
        _work_site_acceptance_item(site_reports),
        _ros1_signature_item(site_reports),
        _hardware_execution_item(hardware_artifact_reports, lane_reports, site_reports),
    ]
    return DistributedFleetGoalEvidenceReport(repo_root=repo_root, items=items)


def _repo_contract_item(repo_root: Path) -> GoalEvidenceItem:
    required = [
        "AGENTS.md",
        "docs/superpowers/specs/2026-05-25-local-llm-mission-ops-architecture.md",
        "docs/superpowers/specs/2026-05-26-distributed-fleet-testing-migration-architecture.md",
        "docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md",
        "profiles/dev_mock.env",
        "profiles/home_model_lab.env",
        "profiles/server_sim.env",
        "profiles/work_hardware.env",
        "profiles/work_hardware_ros1_gateway.env.template",
        "task_planning/migration/external_handoff.py",
        "task_planning/migration/external_import.py",
        "task_planning/migration/handoff_package.py",
        "task_planning/migration/task_command_extraction.py",
        "tools/check_task_planning_site_acceptance.py",
        "tools/audit_ros1_gateway_services.py",
        "tools/init_external_evidence_handoff.py",
        "tools/import_distributed_fleet_external_evidence.py",
        "tools/package_distributed_fleet_handoff.py",
        "tools/verify_distributed_fleet_handoff_package.py",
        "tools/record_unit_hardware_dispatch_artifact.py",
        "tools/extract_task_command_from_artifact.py",
        "platform_gateway/ros/catkin_pkg/platform_gateway_msgs/srv/TaskCommandJson.srv",
    ]
    missing = [path for path in required if not (repo_root / path).exists()]
    return GoalEvidenceItem(
        name="repo_contract_files",
        status=PASS if not missing else FAIL,
        required=True,
        message="required distributed testing files are present" if not missing else "required distributed testing files are missing",
        evidence={"checked": required, "missing": missing},
    )


def _profile_readiness_item(repo_root: Path, profile_rel_path: str, name: str) -> GoalEvidenceItem:
    profile_path = repo_root / profile_rel_path
    try:
        report = check_task_planning_readiness(profile_path, repo_root=repo_root)
    except Exception as exc:
        return GoalEvidenceItem(
            name=name,
            status=FAIL,
            required=True,
            message=f"profile readiness failed: {exc}",
            evidence={"profile_path": str(profile_path)},
        )
    return GoalEvidenceItem(
        name=name,
        status=PASS if report.ok else FAIL,
        required=True,
        message="profile readiness contract passes" if report.ok else "profile readiness contract fails",
        evidence=report.as_dict(),
        next_commands=report.next_commands,
    )


def _mock_first_boundary_item(repo_root: Path) -> GoalEvidenceItem:
    core_files = [
        "task_planning/mission_ops/__init__.py",
        "task_planning/mission_ops/model_client.py",
        "task_planning/mission_ops/mock_llm_client.py",
        "task_planning/mission_ops/mission_manager.py",
        "task_planning/mission_ops/runner.py",
        "task_planning/mission_ops/tools.py",
    ]
    offenders = []
    for rel_path in core_files:
        path = repo_root / rel_path
        if not path.exists():
            offenders.append(f"{rel_path}:missing")
            continue
        text = path.read_text(encoding="utf-8")
        if "LocalLLMClient" in text or "local_llm_client" in text or "CALL_LOCAL_LLM" in text:
            offenders.append(rel_path)
    return GoalEvidenceItem(
        name="mock_first_model_boundary",
        status=PASS if not offenders else FAIL,
        required=True,
        message="phase-1 Mission Ops core remains mock-first" if not offenders else "phase-1 core references local LLM implementation",
        evidence={"checked": core_files, "offenders": offenders},
    )


def _dev_mock_golden_suite_item(reports: Sequence[Mapping[str, Any]]) -> GoalEvidenceItem:
    if not reports:
        return GoalEvidenceItem(
            name="dev_mock_golden_suite_recorded",
            status=MISSING,
            required=True,
            message="missing dev_mock golden-suite evidence report",
            evidence={"report_count": 0, "ok_count": 0},
            next_commands=[
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_dev_mock_golden_suite.py --artifact-root /tmp/changxin-dev-mock-golden-suite > /tmp/changxin-dev-mock-golden-suite.json",
            ],
        )

    validations = [_validate_dev_mock_golden_suite_report(report) for report in reports]
    ok_reports = [validation for validation in validations if not validation["errors"]]
    return GoalEvidenceItem(
        name="dev_mock_golden_suite_recorded",
        status=PASS if ok_reports else FAIL,
        required=True,
        message="dev_mock golden-suite report covers all required cases" if ok_reports else "dev_mock golden-suite report is invalid",
        evidence={
            "report_count": len(reports),
            "ok_count": len(ok_reports),
            "required_case_ids": list(REQUIRED_GOLDEN_CASE_IDS),
            "validations": validations,
        },
        next_commands=[
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_dev_mock_golden_suite.py --artifact-root /tmp/changxin-dev-mock-golden-suite > /tmp/changxin-dev-mock-golden-suite.json",
        ],
    )


def _lane_matrix_item(reports: Sequence[Mapping[str, Any]]) -> GoalEvidenceItem:
    if not reports:
        return GoalEvidenceItem(
            name="lane_matrix_comparable",
            status=MISSING,
            required=True,
            message="missing lane matrix evidence report",
            evidence={"report_count": 0, "ok_count": 0},
            next_commands=[
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_lane_matrix.py --artifact-root /tmp/changxin-lane-matrix > /tmp/changxin-lane-matrix.json",
            ],
        )

    validations = [_validate_lane_matrix_report(report) for report in reports]
    ok_reports = [validation for validation in validations if not validation["errors"]]
    return GoalEvidenceItem(
        name="lane_matrix_comparable",
        status=PASS if ok_reports else FAIL,
        required=True,
        message=(
            "dev_mock, server_sim, and work_hardware pre-dispatch lanes are comparable"
            if ok_reports else
            "lane matrix report is invalid"
        ),
        evidence={
            "report_count": len(reports),
            "ok_count": len(ok_reports),
            "validations": validations,
        },
        next_commands=[
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_lane_matrix.py --artifact-root /tmp/changxin-lane-matrix > /tmp/changxin-lane-matrix.json",
        ],
    )


def _validate_lane_matrix_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    if report.get("schema") != "TaskPlanningLaneMatrix.v1":
        errors.append("report schema must be TaskPlanningLaneMatrix.v1")
    if report.get("ok") is not True:
        errors.append("report ok must be true")
    if not str(report.get("case_id") or "").strip():
        errors.append("case_id is required")

    runs = report.get("runs")
    if not isinstance(runs, list):
        errors.append("runs must be a list")
        runs = []
    run_lanes = {
        str(run.get("lane") or ""): run
        for run in runs
        if isinstance(run, Mapping)
    }
    required_lanes = {"dev_mock", "server_sim", "work_hardware"}
    missing_lanes = sorted(required_lanes - set(run_lanes))
    if missing_lanes:
        errors.append(f"runs must include lanes: {', '.join(missing_lanes)}")
    for lane in sorted(required_lanes & set(run_lanes)):
        run = run_lanes[lane]
        if run.get("ok") is not True:
            errors.append(f"{lane} run ok must be true")
        if not str(run.get("artifact_bundle_path") or "").strip():
            errors.append(f"{lane} run must include artifact_bundle_path")
    work_run = run_lanes.get("work_hardware")
    if isinstance(work_run, Mapping):
        if work_run.get("status") != "approval_required":
            errors.append("work_hardware run must stop with status=approval_required")
        if work_run.get("current_state") != "OPERATOR_APPROVAL":
            errors.append("work_hardware run must stop at OPERATOR_APPROVAL")

    comparisons = report.get("comparisons")
    if not isinstance(comparisons, list):
        errors.append("comparisons must be a list")
        comparisons = []
    comparison_by_name = {
        str(comparison.get("name") or ""): comparison
        for comparison in comparisons
        if isinstance(comparison, Mapping)
    }
    required_comparisons = {
        "dev_mock_vs_server_sim": "exact",
        "dev_mock_vs_work_hardware_pre_dispatch": "pre_dispatch_compatible",
    }
    for name, mode in required_comparisons.items():
        comparison = comparison_by_name.get(name)
        if not isinstance(comparison, Mapping):
            errors.append(f"comparison {name} is required")
            continue
        if comparison.get("equivalent") is not True:
            errors.append(f"{name}.equivalent must be true")
        if comparison.get("mode") != mode:
            errors.append(f"{name}.mode must be {mode}")
        if comparison.get("diffs") not in ([], None):
            errors.append(f"{name}.diffs must be empty")
        if comparison.get("validation_errors") not in ([], None):
            errors.append(f"{name}.validation_errors must be empty")

    return {
        "schema": report.get("schema"),
        "ok": report.get("ok"),
        "case_id": str(report.get("case_id") or ""),
        "lanes": sorted(run_lanes),
        "comparisons": sorted(comparison_by_name),
        "errors": errors,
    }


def _migration_bundle_item(
    reports: Sequence[Mapping[str, Any]],
    handoff_reports: Sequence[Mapping[str, Any]],
) -> GoalEvidenceItem:
    validations = [_validate_migration_verification_report(report) for report in reports]
    handoff_validations = [_validate_handoff_package_verification_report(report) for report in handoff_reports]
    receiving_ok_count = len([validation for validation in validations if not validation["errors"]])
    receiving_ok_count += len([validation for validation in handoff_validations if not validation["errors"]])
    return GoalEvidenceItem(
        name="migration_bundle_verified_after_transfer",
        status=PASS if receiving_ok_count else MISSING,
        required=True,
        message=(
            "at least one transferred migration bundle or handoff package verification report is OK on a receiving machine"
            if receiving_ok_count else
            "missing receiving-machine migration bundle or handoff package verification report"
        ),
        evidence={
            "report_count": len(reports),
            "handoff_report_count": len(handoff_reports),
            "receiving_ok_count": receiving_ok_count,
            "validations": validations,
            "handoff_validations": handoff_validations,
        },
        next_commands=[
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_migration_bundle.py <bundle.tar.gz> --work-dir /tmp/changxin-migration-verify --verification-context receiving_machine > /tmp/changxin-migration-verify/report.json",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_distributed_fleet_handoff_package.py <distributed-fleet-handoff-package.tar.gz> --work-dir /tmp/changxin-handoff-verify --verification-context receiving_machine > <evidence-dir>/reports/handoff_package_verification.json",
        ],
    )


def _validate_migration_verification_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    if report.get("schema") != MIGRATION_VERIFICATION_SCHEMA:
        errors.append(f"report schema must be {MIGRATION_VERIFICATION_SCHEMA}")
    if report.get("ok") is not True:
        errors.append("report must have ok=true")
    if report.get("verification_context") not in {"receiving_machine", "unit_workplace_receiving"}:
        errors.append("verification_context must be receiving_machine or unit_workplace_receiving")
    errors.extend(_machine_transfer_errors(report))
    errors.extend(_migration_verifier_audit_errors(report))
    return {
        "schema": report.get("schema"),
        "ok": report.get("ok"),
        "verification_context": report.get("verification_context"),
        "source_machine_id": report.get("source_machine_id"),
        "verifier_machine_id": report.get("verifier_machine_id"),
        "archive": str(report.get("archive") or ""),
        "checked_files": _migration_manifest_checked_files(report),
        "errors": errors,
    }


def _validate_handoff_package_verification_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    if report.get("schema") != HANDOFF_PACKAGE_VERIFICATION_SCHEMA:
        errors.append(f"report schema must be {HANDOFF_PACKAGE_VERIFICATION_SCHEMA}")
    if report.get("ok") is not True:
        errors.append("report must have ok=true")
    if report.get("verification_context") not in {"receiving_machine", "unit_workplace_receiving"}:
        errors.append("verification_context must be receiving_machine or unit_workplace_receiving")
    errors.extend(_machine_transfer_errors(report))
    errors.extend(_handoff_verifier_audit_errors(report))

    migration = report.get("migration_verification")
    if not isinstance(migration, Mapping):
        errors.append("migration_verification must be an object")
        migration = {}
    migration_validation = _validate_migration_verification_report(migration)
    if migration_validation["errors"]:
        errors.extend(f"migration_verification: {error}" for error in migration_validation["errors"])
    errors.extend(_embedded_handoff_migration_identity_errors(report, migration))
    return {
        "schema": report.get("schema"),
        "ok": report.get("ok"),
        "verification_context": report.get("verification_context"),
        "source_machine_id": report.get("source_machine_id"),
        "verifier_machine_id": report.get("verifier_machine_id"),
        "archive": str(report.get("archive") or ""),
        "checked_files": _safe_int(report.get("checked_files")),
        "migration_schema": migration.get("schema"),
        "migration_ok": migration.get("ok"),
        "migration_verification_context": migration.get("verification_context"),
        "migration_source_machine_id": migration.get("source_machine_id"),
        "migration_verifier_machine_id": migration.get("verifier_machine_id"),
        "errors": errors,
    }


def _migration_verifier_audit_errors(report: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in ("archive", "extract_dir", "bundle_root"):
        if not str(report.get(field) or "").strip():
            errors.append(f"{field} is required from migration verifier output")
    manifest = report.get("manifest")
    if not isinstance(manifest, Mapping):
        errors.append("manifest verifier output is required")
    else:
        if manifest.get("ok") is not True:
            errors.append("manifest.ok must be true")
        checked_files = _safe_int(manifest.get("checked_files"))
        if checked_files <= 0:
            errors.append("manifest.checked_files must be greater than zero")
        if manifest.get("errors") != []:
            errors.append("manifest.errors must be an empty list")
        manifest_source_machine_id = str(manifest.get("source_machine_id") or "")
        report_source_machine_id = str(report.get("source_machine_id") or "")
        if (
            manifest_source_machine_id
            and report_source_machine_id
            and manifest_source_machine_id != report_source_machine_id
        ):
            errors.append("manifest.source_machine_id must match report source_machine_id")
    checks = report.get("checks")
    if not isinstance(checks, list):
        errors.append("checks must be a list")
    else:
        for index, check in enumerate(checks):
            if not isinstance(check, Mapping):
                errors.append(f"checks[{index}] must be an object")
            elif check.get("ok") is not True:
                errors.append(f"checks[{index}].ok must be true")
    return errors


def _handoff_verifier_audit_errors(report: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in ("archive", "extract_dir", "package_root"):
        if not str(report.get(field) or "").strip():
            errors.append(f"{field} is required from handoff verifier output")
    if _safe_int(report.get("checked_files")) <= 0:
        errors.append("checked_files must be greater than zero")
    if report.get("manifest_errors") != []:
        errors.append("manifest_errors must be an empty list")
    if report.get("component_errors") != []:
        errors.append("component_errors must be an empty list")
    return errors


def _migration_manifest_checked_files(report: Mapping[str, Any]) -> int:
    manifest = report.get("manifest")
    if isinstance(manifest, Mapping):
        return _safe_int(manifest.get("checked_files"))
    return 0


def _machine_transfer_errors(report: Mapping[str, Any]) -> List[str]:
    context = report.get("verification_context")
    if context not in {"receiving_machine", "unit_workplace_receiving"}:
        return []
    source_machine_id = str(report.get("source_machine_id") or "")
    verifier_machine_id = str(report.get("verifier_machine_id") or "")
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


def _artifact_package_item(
    verifications: Sequence[ArtifactPackageVerification],
    verification_reports: Sequence[Mapping[str, Any]],
    site_reports: Sequence[Mapping[str, Any]],
    lane_reports: Sequence[Mapping[str, Any]],
) -> GoalEvidenceItem:
    direct_ok_items = [item for item in verifications if item.ok]
    verified_package_archives = sorted({
        str(item.archive.resolve())
        for item in verifications
        if item.ok
    })
    embedded_reports = _artifact_package_verifications_from_site_reports(site_reports)
    all_reports = [*verification_reports, *embedded_reports]
    lane_case_ids = _ok_lane_matrix_case_ids(lane_reports)
    report_validations = [
        _validate_artifact_verification_report(
            report,
            lane_case_ids=lane_case_ids,
            verified_package_archives=verified_package_archives,
        )
        for report in all_reports
    ]
    receiving_ok_count = sum(validation["receiving_ok_count"] for validation in report_validations)
    return GoalEvidenceItem(
        name="artifact_package_verified_after_transfer",
        status=PASS if receiving_ok_count else MISSING,
        required=True,
        message=(
            "at least one artifact package was verified on the unit/workplace receiving machine"
            if receiving_ok_count else
            "missing unit/workplace receiving-machine artifact package verification evidence"
        ),
        evidence={
            "package_count": len(verifications),
            "direct_ok_count": len(direct_ok_items),
            "verified_package_archives": verified_package_archives,
            "verification_report_count": len(verification_reports),
            "site_embedded_verification_count": len(embedded_reports),
            "receiving_ok_count": receiving_ok_count,
            "required_context": "unit_workplace_receiving",
            "lane_matrix_case_ids": lane_case_ids,
            "report_validations": report_validations,
        },
        next_commands=[
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py <artifact-package.tar.gz> --work-dir /tmp/changxin-artifact-verify --verification-context unit_workplace_receiving > <evidence-dir>/reports/artifact_package_verification.json",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/import_distributed_fleet_external_evidence.py --evidence-dir <evidence-dir> --artifact-package <artifact-package.tar.gz> --artifact-package-verification-report <artifact_package_verification.json>",
        ],
    )


def _artifact_package_verifications_from_site_reports(
    site_reports: Sequence[Mapping[str, Any]],
) -> List[Mapping[str, Any]]:
    reports: List[Mapping[str, Any]] = []
    accepted_levels = {
        "work_hardware_pre_dispatch_ready",
        "work_hardware_ros1_services_observed",
        "work_hardware_ros1_signatures_observed",
    }
    for report in site_reports:
        if report.get("schema") != "TaskPlanningSiteAcceptance.v1":
            continue
        if report.get("ok") is not True:
            continue
        if report.get("mission_profile") != "work_hardware":
            continue
        if report.get("acceptance_level") not in accepted_levels:
            continue
        if _validate_work_site_acceptance_report(report)["errors"]:
            continue
        site_machine_id = str(report.get("machine_id") or "").strip()
        if not site_machine_id:
            continue
        packages = report.get("artifact_packages")
        if not isinstance(packages, list):
            continue
        for package in packages:
            if not isinstance(package, Mapping):
                continue
            if package.get("ok") is not True:
                continue
            verification = package.get("verification")
            if isinstance(verification, Mapping):
                verification_with_site = dict(verification)
                verification_with_site["_site_machine_id"] = site_machine_id
                verification_with_site["_site_artifact_archive"] = str(package.get("archive") or "")
                reports.append(verification_with_site)
    return reports


def _validate_artifact_verification_report(
    report: Mapping[str, Any],
    *,
    lane_case_ids: Sequence[str],
    verified_package_archives: Sequence[str],
) -> Dict[str, Any]:
    verifications: List[Mapping[str, Any]]
    errors: List[str] = []
    if report.get("ok") is not True:
        errors.append("ok must be true")
    if report.get("schema") == ARTIFACT_PACKAGE_VERIFICATION_SCHEMA:
        verifications = [report]
    elif report.get("schema") == ARTIFACT_PACKAGE_VERIFICATION_SET_SCHEMA:
        raw_verifications = report.get("verifications")
        if not isinstance(raw_verifications, list):
            errors.append("verifications must be a list")
            raw_verifications = []
        verifications = [item for item in raw_verifications if isinstance(item, Mapping)]
        if len(verifications) != len(raw_verifications):
            errors.append("all verifications entries must be objects")
    else:
        verifications = []
        errors.append(f"report schema must be {ARTIFACT_PACKAGE_VERIFICATION_SCHEMA} or {ARTIFACT_PACKAGE_VERIFICATION_SET_SCHEMA}")

    verification_validations = []
    report_site_machine_id = str(report.get("_site_machine_id") or "")
    report_site_artifact_archive = str(report.get("_site_artifact_archive") or "")
    for index, item in enumerate(verifications):
        item_errors: List[str] = []
        if item.get("ok") is not True:
            item_errors.append("ok must be true")
        if item.get("verification_context") != "unit_workplace_receiving":
            item_errors.append("verification_context must be unit_workplace_receiving")
        item_errors.extend(_machine_transfer_errors(item))
        item_errors.extend(_artifact_verifier_audit_errors(item))
        site_machine_id = str(item.get("_site_machine_id") or report_site_machine_id)
        if site_machine_id:
            item_errors.extend(hashed_machine_id_errors(site_machine_id, "site machine_id"))
            verifier_machine_id = str(item.get("verifier_machine_id") or "")
            if verifier_machine_id and site_machine_id != verifier_machine_id:
                item_errors.append("site machine_id must match artifact verification verifier_machine_id")
        site_artifact_archive = str(item.get("_site_artifact_archive") or report_site_artifact_archive)
        verification_archive = str(item.get("archive") or "")
        if site_artifact_archive:
            if verification_archive and site_artifact_archive != verification_archive:
                item_errors.append("site artifact archive must match artifact verification archive")
        elif not verified_package_archives:
            item_errors.append("artifact verification report must match a provided artifact package archive")
        elif verification_archive not in set(verified_package_archives):
            item_errors.append("artifact verification archive must match a provided artifact package archive")
        case_ids = _artifact_verification_case_ids(item)
        if not case_ids:
            item_errors.append("artifact_validations must include case_id evidence")
        elif not lane_case_ids:
            item_errors.append("no OK lane matrix case_id available for artifact package proof")
        else:
            mismatched = sorted(case_id for case_id in case_ids if case_id not in lane_case_ids)
            if mismatched:
                item_errors.append(
                    "artifact package case_id must match an OK lane matrix case_id: "
                    + ", ".join(mismatched)
                )
        verification_validations.append({
            "index": index,
            "ok": item.get("ok"),
            "verification_context": item.get("verification_context"),
            "source_machine_id": item.get("source_machine_id"),
            "verifier_machine_id": item.get("verifier_machine_id"),
            "archive": verification_archive,
            "checked_files": _safe_int(item.get("checked_files")),
            "site_machine_id": site_machine_id,
            "site_artifact_archive": site_artifact_archive,
            "case_ids": case_ids,
            "errors": item_errors,
        })
    for validation in verification_validations:
        errors.extend(
            f"verifications[{validation['index']}]: {error}"
            for error in validation["errors"]
        )

    receiving_ok = [
        validation for validation in verification_validations
        if not errors
        and not validation["errors"]
    ]
    return {
        "schema": report.get("schema"),
        "ok": report.get("ok"),
        "verification_count": len(verifications),
        "receiving_ok_count": len(receiving_ok),
        "required_context": "unit_workplace_receiving",
        "contexts": [str(item.get("verification_context") or "") for item in verifications],
        "source_machine_ids": [str(item.get("source_machine_id") or "") for item in verifications],
        "verifier_machine_ids": [str(item.get("verifier_machine_id") or "") for item in verifications],
        "archives": [str(item.get("archive") or "") for item in verifications],
        "verified_package_archives": list(verified_package_archives),
        "lane_matrix_case_ids": list(lane_case_ids),
        "verification_validations": verification_validations,
        "errors": errors,
    }


def _artifact_verifier_audit_errors(report: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in ("archive", "extract_dir", "package_root"):
        if not str(report.get(field) or "").strip():
            errors.append(f"{field} is required from artifact package verifier output")
    if _safe_int(report.get("checked_files")) <= 0:
        errors.append("checked_files must be greater than zero")
    if report.get("manifest_errors") != []:
        errors.append("manifest_errors must be an empty list")
    validations = report.get("artifact_validations")
    if not isinstance(validations, list) or not validations:
        errors.append("artifact_validations must be a non-empty list")
        return errors
    for index, validation in enumerate(validations):
        if not isinstance(validation, Mapping):
            errors.append(f"artifact_validations[{index}] must be an object")
            continue
        if validation.get("ok") is not True:
            errors.append(f"artifact_validations[{index}].ok must be true")
        if validation.get("errors") != []:
            errors.append(f"artifact_validations[{index}].errors must be an empty list")
    return errors


def _artifact_verification_case_ids(report: Mapping[str, Any]) -> List[str]:
    raw_validations = report.get("artifact_validations")
    if not isinstance(raw_validations, list):
        return []
    case_ids = {
        str(item.get("case_id") or "").strip()
        for item in raw_validations
        if isinstance(item, Mapping) and item.get("ok") is True
    }
    return sorted(case_id for case_id in case_ids if case_id)


def _home_model_lab_item(
    reports: Sequence[Mapping[str, Any]],
    lane_reports: Sequence[Mapping[str, Any]],
    artifact_verifications: Sequence[ArtifactPackageVerification],
    artifact_verification_reports: Sequence[Mapping[str, Any]],
    site_reports: Sequence[Mapping[str, Any]],
) -> GoalEvidenceItem:
    lane_case_ids = _ok_lane_matrix_case_ids(lane_reports)
    model_lab_artifact_package_proofs = _model_lab_artifact_package_proofs(
        artifact_verifications,
        artifact_verification_reports,
        site_reports,
        lane_case_ids=lane_case_ids,
    )
    model_lab_artifact_case_ids = sorted({
        proof["case_id"]
        for proof in model_lab_artifact_package_proofs
        if proof["case_id"]
    })
    validations = [
        _validate_model_lab_evaluation_report(
            report,
            lane_case_ids=lane_case_ids,
            model_lab_artifact_package_proofs=model_lab_artifact_package_proofs,
        )
        for report in reports
    ]
    ok_reports = [validation for validation in validations if not validation["errors"]]
    rejected_mock = [
        report for report in reports
        if report.get("schema") == "ModelLabEvaluation.v1"
        and report.get("model_lab_evidence_kind") == "mock_endpoint"
    ]
    case_hint = lane_case_ids[0] if lane_case_ids else "<lane-matrix-case-id>"
    return GoalEvidenceItem(
        name="home_5090_model_lab_evaluated",
        status=PASS if ok_reports else MISSING,
        required=True,
        message="home model-lab evaluation report is OK" if ok_reports else "missing live home model-lab evaluation evidence",
        evidence={
            "report_count": len(reports),
            "ok_count": len(ok_reports),
            "rejected_mock_endpoint_count": len(rejected_mock),
            "lane_matrix_case_ids": lane_case_ids,
            "model_lab_artifact_package_case_ids": model_lab_artifact_case_ids,
            "model_lab_artifact_package_proofs": model_lab_artifact_package_proofs,
            "report_validations": validations,
        },
        next_commands=[
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_lane_matrix.py --artifact-root /tmp/changxin-lane-matrix > /tmp/changxin-lane-matrix.json",
            f"PYTHONDONTWRITEBYTECODE=1 python3 tools/evaluate_model_lab_case.py --profile profiles/home_model_lab.env --case {case_hint} --output-dir /tmp/changxin-model-lab",
        ],
    )


def _ok_lane_matrix_case_ids(reports: Sequence[Mapping[str, Any]]) -> List[str]:
    case_ids = {
        validation["case_id"]
        for validation in (_validate_lane_matrix_report(report) for report in reports)
        if not validation["errors"] and validation["case_id"]
    }
    return sorted(case_ids)


def _validate_model_lab_evaluation_report(
    report: Mapping[str, Any],
    *,
    lane_case_ids: Sequence[str],
    model_lab_artifact_package_proofs: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    errors = model_lab_home_5090_live_errors(report)
    case_id = str(report.get("case_id") or "")
    if not errors:
        if not lane_case_ids:
            errors.append("no OK lane matrix case_id available for same-case model-lab proof")
        elif case_id not in lane_case_ids:
            errors.append("case_id must match an OK lane matrix case_id")
    if not errors:
        errors.extend(_model_lab_artifact_package_binding_errors(
            report,
            model_lab_artifact_package_proofs,
        ))
    probe = report.get("accelerator_probe")
    gpu_names = []
    if isinstance(probe, Mapping) and isinstance(probe.get("gpus"), list):
        gpu_names = [str(gpu.get("name") or "") for gpu in probe["gpus"] if isinstance(gpu, Mapping)]
    diffs = report.get("diffs")
    validation_errors = report.get("validation_errors")
    return {
        "errors": errors,
        "case_id": case_id,
        "lane_matrix_case_ids": list(lane_case_ids),
        "model_lab_artifact_package_case_ids": sorted({
            str(proof.get("case_id") or "")
            for proof in model_lab_artifact_package_proofs
            if str(proof.get("case_id") or "")
        }),
        "mission_profile": str(report.get("mission_profile") or ""),
        "model_provider": str(report.get("model_provider") or ""),
        "model_lab_evidence_kind": str(report.get("model_lab_evidence_kind") or ""),
        "platform_backend": str(report.get("platform_backend") or ""),
        "machine_id": str(report.get("machine_id") or ""),
        "baseline_equivalent": report.get("baseline_equivalent"),
        "diff_count": len(diffs) if isinstance(diffs, list) else 0,
        "validation_error_count": len(validation_errors) if isinstance(validation_errors, list) else 0,
        "accelerator_probe_ok": bool(isinstance(probe, Mapping) and probe.get("ok") is True),
        "gpu_names": gpu_names,
    }


def _model_lab_artifact_package_proofs(
    verifications: Sequence[ArtifactPackageVerification],
    verification_reports: Sequence[Mapping[str, Any]],
    site_reports: Sequence[Mapping[str, Any]],
    *,
    lane_case_ids: Sequence[str],
) -> List[Dict[str, Any]]:
    proofs: List[Dict[str, Any]] = []
    for verification in verifications:
        if not verification.ok:
            continue
        verification_data = verification.as_dict()
        if (
            verification_data.get("verification_context") != "unit_workplace_receiving"
            or _machine_transfer_errors(verification_data)
        ):
            continue
        for artifact in verification.artifact_validations:
            if not artifact.ok or artifact.kind != "model_lab_evaluation" or not artifact.case_id:
                continue
            proofs.append({
                "source": "artifact_package",
                "archive": str(verification.archive.resolve()),
                "verification_context": verification.verification_context,
                "source_machine_id": verification.source_machine_id,
                "verifier_machine_id": verification.verifier_machine_id,
                "case_id": artifact.case_id,
                "metadata": dict(artifact.metadata),
            })

    verified_package_archives = sorted({
        str(item.archive.resolve())
        for item in verifications
        if item.ok
    })
    embedded_reports = _artifact_package_verifications_from_site_reports(site_reports)
    for report in [*verification_reports, *embedded_reports]:
        report_validation = _validate_artifact_verification_report(
            report,
            lane_case_ids=lane_case_ids,
            verified_package_archives=verified_package_archives,
        )
        if report_validation["errors"]:
            continue
        entries = _artifact_verification_entries(report)
        for entry, entry_validation in zip(entries, report_validation["verification_validations"]):
            if entry_validation["errors"]:
                continue
            for artifact in _model_lab_artifact_validations(entry):
                proofs.append({
                    "source": "artifact_package_verification_report",
                    "archive": str(entry.get("archive") or ""),
                    "verification_context": str(entry.get("verification_context") or ""),
                    "source_machine_id": str(entry.get("source_machine_id") or ""),
                    "verifier_machine_id": str(entry.get("verifier_machine_id") or ""),
                    "case_id": str(artifact.get("case_id") or ""),
                    "metadata": dict(artifact.get("metadata") or {}),
                })
    return _dedupe_model_lab_artifact_proofs(proofs)


def _artifact_verification_entries(report: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    if report.get("schema") == ARTIFACT_PACKAGE_VERIFICATION_SCHEMA:
        return [report]
    if report.get("schema") != ARTIFACT_PACKAGE_VERIFICATION_SET_SCHEMA:
        return []
    raw_verifications = report.get("verifications")
    if not isinstance(raw_verifications, list):
        return []
    return [item for item in raw_verifications if isinstance(item, Mapping)]


def _model_lab_artifact_validations(report: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    raw_validations = report.get("artifact_validations")
    if not isinstance(raw_validations, list):
        return []
    return [
        item for item in raw_validations
        if isinstance(item, Mapping)
        and item.get("ok") is True
        and item.get("kind") == "model_lab_evaluation"
        and str(item.get("case_id") or "").strip()
    ]


def _dedupe_model_lab_artifact_proofs(proofs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for proof in proofs:
        key = "|".join([
            str(proof.get("source") or ""),
            str(proof.get("archive") or ""),
            str(proof.get("verification_context") or ""),
            str(proof.get("case_id") or ""),
        ])
        deduped[key] = {
            "source": str(proof.get("source") or ""),
            "archive": str(proof.get("archive") or ""),
            "verification_context": str(proof.get("verification_context") or ""),
            "source_machine_id": str(proof.get("source_machine_id") or ""),
            "verifier_machine_id": str(proof.get("verifier_machine_id") or ""),
            "case_id": str(proof.get("case_id") or ""),
            "metadata": dict(proof.get("metadata") or {}),
        }
    return [deduped[key] for key in sorted(deduped)]


def _model_lab_artifact_package_binding_errors(
    report: Mapping[str, Any],
    proofs: Sequence[Mapping[str, Any]],
) -> List[str]:
    case_id = str(report.get("case_id") or "")
    if not proofs:
        return ["model-lab artifact package evidence is required"]
    same_case = [proof for proof in proofs if proof.get("case_id") == case_id]
    if not same_case:
        return ["case_id must match a verified model-lab artifact package case_id"]

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
            report_value = str(report.get(key) or "")
            if not package_value:
                proof_errors.append(f"model-lab artifact package metadata.{key} is required")
            elif report_value and package_value != report_value:
                proof_errors.append(f"model-lab artifact package metadata.{key} must match evaluation report")
        if not proof_errors:
            return []
        binding_errors.extend(proof_errors)
    return sorted(set(binding_errors))


def _work_site_acceptance_item(reports: Sequence[Mapping[str, Any]]) -> GoalEvidenceItem:
    validations = [_validate_work_site_acceptance_report(report) for report in reports]
    accepted = [validation for validation in validations if not validation["errors"]]
    return GoalEvidenceItem(
        name="work_hardware_site_acceptance_recorded",
        status=PASS if accepted else MISSING,
        required=True,
        message="work_hardware site acceptance report is present" if accepted else "missing work_hardware site acceptance report",
        evidence={
            "report_count": len(reports),
            "accepted_count": len(accepted),
            "report_validations": validations,
        },
        next_commands=[
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile profiles/work_hardware.env > /tmp/changxin-site-acceptance.json",
        ],
    )


def _validate_work_site_acceptance_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    platform_backend = str(report.get("platform_backend") or "")
    acceptance_level = str(report.get("acceptance_level") or "")
    if report.get("schema") != "TaskPlanningSiteAcceptance.v1":
        errors.append("schema must be TaskPlanningSiteAcceptance.v1")
    if report.get("ok") is not True:
        errors.append("ok must be true")
    if report.get("mission_profile") != "work_hardware":
        errors.append("mission_profile must be work_hardware")
    for error in hashed_machine_id_errors(report.get("machine_id"), "machine_id"):
        errors.append(f"{error} for work_hardware site acceptance evidence")
    validation_errors = report.get("validation_errors")
    if validation_errors != []:
        errors.append("validation_errors must be an empty list")
    readiness = report.get("readiness")
    if not isinstance(readiness, Mapping):
        errors.append("readiness report is required")
        readiness_ok = False
    else:
        readiness_ok = readiness.get("ok") is True
        if not readiness_ok:
            errors.append("readiness.ok must be true")
        if readiness.get("mission_profile") != "work_hardware":
            errors.append("readiness.mission_profile must be work_hardware")
    hardware_gate = report.get("hardware_gate")
    if not isinstance(hardware_gate, Mapping):
        errors.append("hardware_gate report is required")
        hardware_gate_ok = False
    else:
        hardware_gate_ok = hardware_gate.get("ok") is True
        if not hardware_gate_ok:
            errors.append("hardware_gate.ok must be true")
    if acceptance_level == "work_hardware_pre_dispatch_ready":
        if platform_backend not in {"mock", "ros1_gateway"}:
            errors.append("platform_backend must be mock or ros1_gateway for work_hardware_pre_dispatch_ready")
    elif acceptance_level in {
        "work_hardware_ros1_services_observed",
        "work_hardware_ros1_signatures_observed",
    }:
        if platform_backend != "ros1_gateway":
            errors.append(f"platform_backend must be ros1_gateway for {acceptance_level}")
    else:
        errors.append("acceptance_level must be a work_hardware accepted level")
    return {
        "errors": errors,
        "schema": report.get("schema"),
        "ok": report.get("ok"),
        "mission_profile": report.get("mission_profile"),
        "platform_backend": platform_backend,
        "acceptance_level": acceptance_level,
        "machine_id": str(report.get("machine_id") or ""),
        "readiness_ok": readiness_ok,
        "hardware_gate_ok": hardware_gate_ok,
        "validation_error_count": len(validation_errors) if isinstance(validation_errors, list) else 0,
    }


def _ros1_signature_item(reports: Sequence[Mapping[str, Any]]) -> GoalEvidenceItem:
    validations = [_validate_ros1_signature_report(report) for report in reports]
    signed = [validation for validation in validations if not validation["errors"]]
    return GoalEvidenceItem(
        name="unit_ros1_gateway_signatures_observed",
        status=PASS if signed else MISSING,
        required=True,
        message="unit ROS1 gateway service names and signatures are verified" if signed else "missing unit ROS1 gateway signature evidence",
        evidence={
            "report_count": len(reports),
            "signature_report_count": len(signed),
            "report_validations": validations,
        },
        next_commands=[
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile <local-work-hardware-ros1-gateway.env> --platform-id <platform_id> --run-rosservice-list --run-service-signatures --require-rosservice-audit --require-service-signatures > /tmp/changxin-site-acceptance-ros1.json",
            "Alternative archive form: capture rosservice list/type/args to files and rerun check_task_planning_site_acceptance.py with --rosservice-list-file/--service-type-file/--service-args-file.",
        ],
    )


def _validate_ros1_signature_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    site_validation = _validate_work_site_acceptance_report(report)
    errors: List[str] = list(site_validation["errors"])
    if report.get("platform_backend") != "ros1_gateway":
        errors.append("platform_backend must be ros1_gateway")
    if report.get("acceptance_level") != "work_hardware_ros1_signatures_observed":
        errors.append("acceptance_level must be work_hardware_ros1_signatures_observed")
    audit = report.get("rosservice_audit")
    if not isinstance(audit, Mapping):
        errors.append("rosservice_audit is required")
        source = ""
        observed_service_count = 0
        signature_count = 0
        signed_services: List[str] = []
    else:
        source = str(audit.get("command_environment_source") or "")
        if audit.get("ok") is not True:
            errors.append("rosservice_audit.ok must be true")
        if source not in {"profile", "captured_files"}:
            errors.append("rosservice_audit.command_environment_source must be profile or captured_files")
        observed_service_count = _safe_int(audit.get("observed_service_count"))
        if observed_service_count <= 0:
            errors.append("rosservice_audit.observed_service_count must be greater than zero")
        errors.extend(_ros1_audit_service_name_errors(audit))
        signatures = audit.get("service_signatures")
        if not isinstance(signatures, list) or not signatures:
            errors.append("rosservice_audit.service_signatures are required")
            signature_count = 0
            signed_services = []
        else:
            signature_count = len(signatures)
            signed_services = []
            for index, signature in enumerate(signatures):
                if not isinstance(signature, Mapping):
                    errors.append(f"service_signatures[{index}] must be an object")
                    continue
                service_name = str(signature.get("service_name") or "").strip()
                if service_name:
                    signed_services.append(service_name)
                if signature.get("type_ok") is not True:
                    errors.append(f"service_signatures[{index}].type_ok must be true")
                if signature.get("args_ok") is not True:
                    errors.append(f"service_signatures[{index}].args_ok must be true")
            errors.extend(_gateway_signature_pair_errors(signed_services))
    return {
        "errors": errors,
        "command_environment_source": source,
        "machine_id": str(report.get("machine_id") or ""),
        "observed_service_count": observed_service_count,
        "signature_count": signature_count,
        "signed_services": sorted(set(signed_services)),
        "readiness_ok": site_validation["readiness_ok"],
        "hardware_gate_ok": site_validation["hardware_gate_ok"],
        "validation_error_count": site_validation["validation_error_count"],
    }


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
                errors.append(f"service_signatures[{index}].service_name is required")
            elif matched_services and service_name not in matched_services:
                errors.append(f"service_signatures[{index}].service_name must be present in matched_services")
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
    paired_prefixes = [
        prefix
        for prefix, modes in prefixes.items()
        if {"dry_run", "dispatch"}.issubset(modes)
    ]
    if paired_prefixes:
        return []
    return ["rosservice_audit.service_signatures must include paired dry_run and dispatch services for one gateway prefix"]


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _hardware_execution_item(
    reports: Sequence[Mapping[str, Any]],
    lane_reports: Sequence[Mapping[str, Any]],
    site_reports: Sequence[Mapping[str, Any]],
) -> GoalEvidenceItem:
    lane_case_ids = _ok_lane_matrix_case_ids(lane_reports)
    signature_validations = [_validate_ros1_signature_report(report) for report in site_reports]
    signature_machine_ids = sorted({
        validation["machine_id"]
        for validation in signature_validations
        if not validation["errors"] and validation["machine_id"]
    })
    signature_services_by_machine = _ros1_signature_services_by_machine(signature_validations)
    report_validations = [
        _validate_hardware_execution_report(
            report,
            lane_case_ids,
            signature_machine_ids=signature_machine_ids,
            signature_services_by_machine=signature_services_by_machine,
        )
        for report in reports
    ]
    ok_reports = [validation for validation in report_validations if not validation["errors"]]
    return GoalEvidenceItem(
        name="unit_hardware_execution_artifact_verified",
        status=PASS if ok_reports else MISSING,
        required=True,
        message="real unit/work hardware execution artifact is verified" if ok_reports else "missing real unit/work hardware execution artifact",
        evidence={
            "artifact_count": len(reports),
            "ok_count": len(ok_reports),
            "lane_matrix_case_ids": lane_case_ids,
            "valid_ros1_signature_machine_ids": signature_machine_ids,
            "valid_ros1_signature_services_by_machine": signature_services_by_machine,
            "report_validations": report_validations,
        },
        next_commands=[
            "After operator approval and real gateway dispatch, record the captured response/progress with: PYTHONDONTWRITEBYTECODE=1 python3 tools/record_unit_hardware_dispatch_artifact.py --source-artifact <prevalidated_artifact_root> --profile <local-work-hardware-ros1-gateway.env> --output-dir <evidence-dir>/hardware_artifacts --platform-id <platform_id> --task-id <task_id> --dispatch-service /fleet/<platform_id>/gateway/dispatch --dispatch-stdout-file /tmp/changxin-dispatch-response.txt --task-progress-file /tmp/changxin-task-progress.json --operator-approved",
            "Then rerun: PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir <evidence-dir>",
        ],
    )


def _validate_hardware_execution_report(
    report: Mapping[str, Any],
    lane_case_ids: Sequence[str],
    *,
    signature_machine_ids: Sequence[str],
    signature_services_by_machine: Mapping[str, Sequence[str]],
) -> Dict[str, Any]:
    errors = list(report.get("validation_errors") or [])
    if report.get("ok") is not True:
        errors.append("hardware execution report must have ok=true")
    evidence = report.get("evidence")
    case_id = ""
    machine_id = ""
    dispatch_services: List[str] = []
    if isinstance(evidence, Mapping):
        case_id = str(evidence.get("case_id") or "")
        machine_id = str(evidence.get("machine_id") or "")
        raw_services = evidence.get("ros1_dispatch_services")
        if isinstance(raw_services, list):
            dispatch_services = sorted({
                str(service).strip()
                for service in raw_services
                if str(service).strip()
            })
    if not case_id:
        errors.append("hardware execution artifact case_id is required")
    elif not lane_case_ids:
        errors.append("no OK lane matrix case_id available for hardware execution proof")
    elif case_id not in lane_case_ids:
        errors.append("hardware execution artifact case_id must match an OK lane matrix case_id")
    if not signature_machine_ids:
        errors.append("no OK unit ROS1 signature machine_id available for hardware execution proof")
    elif machine_id not in set(signature_machine_ids):
        errors.append("hardware execution machine_id must match an OK unit ROS1 signature report machine_id")
    else:
        signed_services = set(signature_services_by_machine.get(machine_id) or [])
        if not dispatch_services:
            errors.append("hardware execution artifact dispatch service is required")
        else:
            non_gateway = sorted(service for service in dispatch_services if not _is_gateway_dispatch_service(service))
            if non_gateway:
                errors.append(
                    "hardware dispatch service must be a /gateway/dispatch service: "
                    + ", ".join(non_gateway)
                )
            unsigned = sorted(service for service in dispatch_services if service not in signed_services)
            if unsigned:
                errors.append(
                    "hardware dispatch service must match an OK unit ROS1 signed service: "
                    + ", ".join(unsigned)
                )
    return {
        "ok": report.get("ok"),
        "path": str(report.get("path") or ""),
        "case_id": case_id,
        "machine_id": machine_id,
        "ros1_dispatch_services": dispatch_services,
        "lane_matrix_case_ids": list(lane_case_ids),
        "valid_ros1_signature_machine_ids": list(signature_machine_ids),
        "valid_ros1_signature_services": list(signature_services_by_machine.get(machine_id) or []),
        "errors": errors,
    }


def _ros1_signature_services_by_machine(
    validations: Sequence[Mapping[str, Any]],
) -> Dict[str, List[str]]:
    services_by_machine: Dict[str, List[str]] = {}
    for validation in validations:
        if validation.get("errors"):
            continue
        machine_id = str(validation.get("machine_id") or "")
        if not machine_id:
            continue
        services = [
            str(service).strip()
            for service in validation.get("signed_services", [])
            if str(service).strip()
        ]
        if not services:
            continue
        existing = set(services_by_machine.get(machine_id, []))
        existing.update(services)
        services_by_machine[machine_id] = sorted(existing)
    return services_by_machine


def _is_gateway_dispatch_service(service: Any) -> bool:
    return isinstance(service, str) and service.strip().endswith("/gateway/dispatch")


def _verify_artifact_packages(
    artifact_packages: Sequence[Path],
    *,
    artifact_work_dir: Optional[Path],
) -> List[ArtifactPackageVerification]:
    results: List[ArtifactPackageVerification] = []
    for archive in artifact_packages:
        try:
            results.append(verify_artifact_package(archive_path=archive, work_dir=artifact_work_dir))
        except Exception:
            continue
    return results


def _validate_dev_mock_golden_suite_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    if report.get("schema") != "DevMockGoldenSuite.v1":
        errors.append("report schema must be DevMockGoldenSuite.v1")
    if report.get("ok") is not True:
        errors.append("report ok must be true")

    required_case_ids = list(REQUIRED_GOLDEN_CASE_IDS)
    if report.get("required_case_ids") != required_case_ids:
        errors.append("required_case_ids must match the configured golden suite")

    case_results = report.get("case_results")
    if not isinstance(case_results, list):
        errors.append("case_results must be a list")
        case_results = []
    observed_case_ids = [
        result.get("case_id")
        for result in case_results
        if isinstance(result, Mapping)
    ]
    if observed_case_ids != required_case_ids:
        errors.append("case_results must cover every required case in order")
    for result in case_results:
        if not isinstance(result, Mapping):
            errors.append("case_results entries must be objects")
            continue
        case_id = result.get("case_id", "<unknown>")
        if result.get("ok") is not True:
            errors.append(f"{case_id} result ok must be true")
        if not result.get("artifact_bundle_path"):
            errors.append(f"{case_id} must include artifact_bundle_path")
        if not result.get("run_id"):
            errors.append(f"{case_id} must include run_id")
    return {
        "schema": report.get("schema"),
        "ok": report.get("ok"),
        "observed_case_ids": observed_case_ids,
        "errors": errors,
    }


def _load_json_report(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except Exception as exc:
        return {"schema": "UnreadableReport.v1", "ok": False, "error": str(exc), "path": str(path)}
    return data if isinstance(data, dict) else {"schema": "InvalidReport.v1", "ok": False, "path": str(path)}


def _load_model_lab_evaluation(path: Path) -> Dict[str, Any]:
    expanded = path.expanduser()
    if expanded.is_dir():
        expanded = expanded / "model_lab_evaluation.json"
    return _load_json_report(expanded)


def _inspect_hardware_artifact(path: Path) -> Dict[str, Any]:
    return inspect_hardware_execution_artifact(path)
