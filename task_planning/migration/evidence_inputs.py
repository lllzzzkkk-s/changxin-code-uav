from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class GoalEvidenceInputPaths:
    artifact_packages: List[Path] = field(default_factory=list)
    artifact_package_verification_reports: List[Path] = field(default_factory=list)
    artifact_work_dir: Optional[Path] = None
    site_acceptance_reports: List[Path] = field(default_factory=list)
    lane_matrix_reports: List[Path] = field(default_factory=list)
    dev_mock_golden_suite_reports: List[Path] = field(default_factory=list)
    model_lab_evaluations: List[Path] = field(default_factory=list)
    migration_verification_reports: List[Path] = field(default_factory=list)
    handoff_package_verification_reports: List[Path] = field(default_factory=list)
    hardware_run_artifacts: List[Path] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "artifact_packages": [str(path) for path in self.artifact_packages],
            "artifact_package_verification_reports": [str(path) for path in self.artifact_package_verification_reports],
            "artifact_work_dir": str(self.artifact_work_dir) if self.artifact_work_dir is not None else "",
            "site_acceptance_reports": [str(path) for path in self.site_acceptance_reports],
            "lane_matrix_reports": [str(path) for path in self.lane_matrix_reports],
            "dev_mock_golden_suite_reports": [str(path) for path in self.dev_mock_golden_suite_reports],
            "model_lab_evaluations": [str(path) for path in self.model_lab_evaluations],
            "migration_verification_reports": [str(path) for path in self.migration_verification_reports],
            "handoff_package_verification_reports": [str(path) for path in self.handoff_package_verification_reports],
            "hardware_run_artifacts": [str(path) for path in self.hardware_run_artifacts],
        }


def discover_goal_evidence_inputs(evidence_dirs: Sequence[Path]) -> GoalEvidenceInputPaths:
    artifact_packages: List[Path] = []
    artifact_package_verification_reports: List[Path] = []
    site_acceptance_reports: List[Path] = []
    lane_matrix_reports: List[Path] = []
    dev_mock_golden_suite_reports: List[Path] = []
    model_lab_evaluations: List[Path] = []
    migration_verification_reports: List[Path] = []
    handoff_package_verification_reports: List[Path] = []
    hardware_run_artifacts: List[Path] = []
    artifact_work_dir: Optional[Path] = None

    for evidence_dir in evidence_dirs:
        root = evidence_dir.expanduser().resolve()
        reports = root / "reports"
        _append_existing(lane_matrix_reports, reports / "lane_matrix.json")
        _append_existing(dev_mock_golden_suite_reports, reports / "dev_mock_golden_suite.json")
        _append_existing(site_acceptance_reports, reports / "site_acceptance_work_hardware.json")
        _append_existing(site_acceptance_reports, reports / "site_acceptance_work_hardware_ros1.json")
        _append_existing(model_lab_evaluations, reports / "model_lab_evaluation.json")
        _append_existing(model_lab_evaluations, reports / "home_model_lab_evaluation.json")
        _append_existing(migration_verification_reports, reports / "migration_verification.json")
        _append_existing(migration_verification_reports, reports / "task_planning_migration_verification.json")
        _append_existing(handoff_package_verification_reports, reports / "handoff_package_verification.json")
        _append_existing(handoff_package_verification_reports, reports / "distributed_fleet_handoff_verification.json")
        _append_existing(artifact_package_verification_reports, reports / "artifact_package_verification.json")
        _append_existing(artifact_package_verification_reports, reports / "artifact_package_verifications.json")

        for archive in sorted((root / "artifact_packages").glob("*.tar.gz")):
            _append_existing(artifact_packages, archive)
        for artifact in sorted((root / "hardware_artifacts").iterdir() if (root / "hardware_artifacts").exists() else []):
            if artifact.is_dir():
                _append_existing(hardware_run_artifacts, artifact)
        if artifact_work_dir is None and artifact_packages:
            artifact_work_dir = root / "_artifact_package_verify"

    return GoalEvidenceInputPaths(
        artifact_packages=_dedupe(artifact_packages),
        artifact_package_verification_reports=_dedupe(artifact_package_verification_reports),
        artifact_work_dir=artifact_work_dir,
        site_acceptance_reports=_dedupe(site_acceptance_reports),
        lane_matrix_reports=_dedupe(lane_matrix_reports),
        dev_mock_golden_suite_reports=_dedupe(dev_mock_golden_suite_reports),
        model_lab_evaluations=_dedupe(model_lab_evaluations),
        migration_verification_reports=_dedupe(migration_verification_reports),
        handoff_package_verification_reports=_dedupe(handoff_package_verification_reports),
        hardware_run_artifacts=_dedupe(hardware_run_artifacts),
    )


def merge_goal_evidence_inputs(
    *,
    discovered: GoalEvidenceInputPaths,
    artifact_packages: Iterable[Path] = (),
    artifact_package_verification_reports: Iterable[Path] = (),
    artifact_work_dir: Optional[Path] = None,
    site_acceptance_reports: Iterable[Path] = (),
    lane_matrix_reports: Iterable[Path] = (),
    dev_mock_golden_suite_reports: Iterable[Path] = (),
    model_lab_evaluations: Iterable[Path] = (),
    migration_verification_reports: Iterable[Path] = (),
    handoff_package_verification_reports: Iterable[Path] = (),
    hardware_run_artifacts: Iterable[Path] = (),
) -> GoalEvidenceInputPaths:
    return GoalEvidenceInputPaths(
        artifact_packages=_dedupe([*discovered.artifact_packages, *artifact_packages]),
        artifact_package_verification_reports=_dedupe([
            *discovered.artifact_package_verification_reports,
            *artifact_package_verification_reports,
        ]),
        artifact_work_dir=artifact_work_dir or discovered.artifact_work_dir,
        site_acceptance_reports=_dedupe([*discovered.site_acceptance_reports, *site_acceptance_reports]),
        lane_matrix_reports=_dedupe([*discovered.lane_matrix_reports, *lane_matrix_reports]),
        dev_mock_golden_suite_reports=_dedupe([
            *discovered.dev_mock_golden_suite_reports,
            *dev_mock_golden_suite_reports,
        ]),
        model_lab_evaluations=_dedupe([*discovered.model_lab_evaluations, *model_lab_evaluations]),
        migration_verification_reports=_dedupe([
            *discovered.migration_verification_reports,
            *migration_verification_reports,
        ]),
        handoff_package_verification_reports=_dedupe([
            *discovered.handoff_package_verification_reports,
            *handoff_package_verification_reports,
        ]),
        hardware_run_artifacts=_dedupe([*discovered.hardware_run_artifacts, *hardware_run_artifacts]),
    )


def _append_existing(paths: List[Path], path: Path) -> None:
    if path.exists():
        paths.append(path)


def _dedupe(paths: Iterable[Path]) -> List[Path]:
    seen = set()
    result: List[Path] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result
