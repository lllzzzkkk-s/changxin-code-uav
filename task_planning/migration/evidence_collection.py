from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from task_planning.migration.goal_evidence import build_distributed_fleet_goal_evidence
from task_planning.migration.external_handoff import build_external_evidence_handoff
from task_planning.migration.golden_suite import run_dev_mock_golden_suite
from task_planning.migration.lane_matrix import run_lane_matrix
from task_planning.migration.readiness import check_task_planning_readiness
from task_planning.migration.site_acceptance import check_task_planning_site_acceptance


@dataclass(frozen=True)
class DistributedFleetEvidenceCollection:
    root: Path
    manifest: Path
    reports: Dict[str, Path]
    artifact_roots: Dict[str, Path]
    schema: str = "DistributedFleetEvidenceCollection.v1"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "root": str(self.root),
            "manifest": str(self.manifest),
            "reports": {name: str(path) for name, path in self.reports.items()},
            "artifact_roots": {name: str(path) for name, path in self.artifact_roots.items()},
        }


def collect_distributed_fleet_evidence(
    *,
    repo_root: Path,
    output_dir: Path,
    case_id: str = "uav_ugv_coordination",
) -> DistributedFleetEvidenceCollection:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    reports_dir = output_dir / "reports"
    artifacts_dir = output_dir / "artifacts"
    reports_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    reports: Dict[str, Path] = {}
    artifact_roots: Dict[str, Path] = {}

    for profile_name in ("dev_mock", "home_model_lab", "server_sim", "work_hardware"):
        report = check_task_planning_readiness(
            repo_root / "profiles" / f"{profile_name}.env",
            repo_root=repo_root,
        )
        reports[f"readiness_{profile_name}"] = _write_json(
            reports_dir / f"readiness_{profile_name}.json",
            report.as_dict(),
        )

    lane_artifact_root = artifacts_dir / "lane_matrix"
    lane_matrix = run_lane_matrix(
        repo_root=repo_root,
        artifact_root=lane_artifact_root,
        case_id=case_id,
    )
    artifact_roots["lane_matrix"] = lane_artifact_root
    reports["lane_matrix"] = _write_json(reports_dir / "lane_matrix.json", lane_matrix.as_dict())

    golden_suite_artifact_root = artifacts_dir / "dev_mock_golden_suite"
    golden_suite = run_dev_mock_golden_suite(
        repo_root=repo_root,
        artifact_root=golden_suite_artifact_root,
    )
    artifact_roots["dev_mock_golden_suite"] = golden_suite_artifact_root
    reports["dev_mock_golden_suite"] = _write_json(
        reports_dir / "dev_mock_golden_suite.json",
        golden_suite.as_dict(),
    )

    site_acceptance = check_task_planning_site_acceptance(
        profile_path=repo_root / "profiles/work_hardware.env",
        repo_root=repo_root,
    )
    reports["site_acceptance_work_hardware"] = _write_json(
        reports_dir / "site_acceptance_work_hardware.json",
        site_acceptance.as_dict(),
    )

    goal_evidence = build_distributed_fleet_goal_evidence(
        repo_root=repo_root,
        site_acceptance_reports=[reports["site_acceptance_work_hardware"]],
        lane_matrix_reports=[reports["lane_matrix"]],
        dev_mock_golden_suite_reports=[reports["dev_mock_golden_suite"]],
    )
    reports["goal_evidence"] = _write_json(
        reports_dir / "goal_evidence.json",
        goal_evidence.as_dict(),
    )
    reports["phase_gate_report"] = _write_json(
        reports_dir / "phase_gate.json",
        goal_evidence.phase_gate,
    )
    external_handoff = build_external_evidence_handoff(
        repo_root=repo_root,
        evidence_dir=output_dir,
        case_id=case_id,
        missing_required=[item.name for item in goal_evidence.missing_required],
    )
    reports["external_evidence_requirements"] = external_handoff.requirements_path
    reports["next_external_evidence"] = external_handoff.next_steps_path

    manifest_path = _write_json(
        output_dir / "manifest.json",
        {
            "schema": "DistributedFleetEvidenceCollectionManifest.v1",
            "case_id": case_id,
            "repo_root": str(repo_root),
            "phase_gate": goal_evidence.phase_gate,
            "reports": {name: str(path.relative_to(output_dir)) for name, path in reports.items()},
            "artifact_roots": {name: str(path.relative_to(output_dir)) for name, path in artifact_roots.items()},
            "missing_required": [item.name for item in goal_evidence.missing_required],
        },
    )
    (output_dir / "EVIDENCE.md").write_text(
        _evidence_doc(case_id=case_id, missing=[item.name for item in goal_evidence.missing_required]),
        encoding="utf-8",
    )
    reports["evidence_readme"] = output_dir / "EVIDENCE.md"
    (output_dir / "PHASE_GATE.md").write_text(
        _phase_gate_doc(phase_gate=goal_evidence.phase_gate),
        encoding="utf-8",
    )
    reports["phase_gate"] = output_dir / "PHASE_GATE.md"

    return DistributedFleetEvidenceCollection(
        root=output_dir,
        manifest=manifest_path,
        reports=reports,
        artifact_roots=artifact_roots,
    )


def _write_json(path: Path, data: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return path


def _evidence_doc(*, case_id: str, missing: List[str]) -> str:
    missing_lines = [f"- `{name}`" for name in missing] or ["- none"]
    return "\n".join([
        "# Distributed Fleet Evidence Collection",
        "",
        f"Case: `{case_id}`",
        "",
        "This directory is a local baseline evidence set. It does not prove live home 5090 model-lab execution, live unit ROS1 services, or real hardware movement unless those external reports are supplied separately.",
        "",
        "Key reports:",
        "",
        "- `reports/readiness_dev_mock.json`",
        "- `reports/readiness_home_model_lab.json`",
        "- `reports/readiness_server_sim.json`",
        "- `reports/readiness_work_hardware.json`",
        "- `reports/lane_matrix.json`",
        "- `reports/dev_mock_golden_suite.json`",
        "- `reports/site_acceptance_work_hardware.json`",
        "- `reports/goal_evidence.json`",
        "- `reports/phase_gate.json`",
        "- `reports/external_evidence_requirements.json`",
        "- `NEXT_EXTERNAL_EVIDENCE.md`",
        "",
        "Missing required external evidence:",
        "",
        *missing_lines,
        "",
        f"All external proof must use case `{case_id}` and match `reports/lane_matrix.json`.",
        "Artifact-package transfer proof must be generated on the unit/workplace receiving machine; the report records `source_machine_id` and `verifier_machine_id`, rejects same-machine proof, and carries artifact-level `case_id` evidence.",
        "Home 5090 model-lab proof must be generated on the model-lab machine, include a successful `nvidia-smi` accelerator probe showing RTX 5090, and keep the same `case_id` as the lane matrix.",
        "Home 5090 proof also requires a verified artifact package containing the full model-lab artifact directory; the packaged model_lab_evaluation artifact must match the report metadata.",
        "Final unit/work hardware proof must include `operator_approved=true`, `operator_approval_source=local_unit_operator`, execution endpoint `machine_id`, `validation_report.schema=ValidationReport.v1`, `validation_report.current_state=HARDWARE_DISPATCH_RECORDED`, `validation_report.errors=[]`, and `mission_input.run_input.case_id` matching the lane matrix.",
        "The final hardware proof must carry `validation_report.source_validation_report.schema=ValidationReport.v1`, `source_validation_report.current_state=OPERATOR_APPROVAL`, and `source_validation_report.errors=[]` so the real dispatch remains linked to a clean pre-dispatch approval artifact.",
        "",
        "Typical external evidence commands:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/evaluate_model_lab_case.py --profile profiles/home_model_lab.env --case uav_ugv_coordination --output-dir /tmp/changxin-model-lab",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_mock_model_lab_endpoint.py --port 8000  # plumbing only, not home_5090_live proof",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_artifacts.py --artifact /tmp/changxin-model-lab/uav_ugv_coordination --output-dir /tmp/changxin-artifact-packages",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py <artifact-package.tar.gz> --work-dir /tmp/changxin-artifact-verify --verification-context unit_workplace_receiving > <evidence-dir>/reports/artifact_package_verification.json",
        "cp profiles/work_hardware_ros1_gateway.env.template <local-work-hardware-ros1-gateway.env>  # fill real ROS_MASTER_URI and ROS_IP on the unit/workplace machine",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile <local-work-hardware-ros1-gateway.env> --platform-id <platform_id> --run-rosservice-list --run-service-signatures --require-rosservice-audit --require-service-signatures",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/init_external_evidence_handoff.py --evidence-dir <evidence-dir>",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_distributed_fleet_handoff_package.py <distributed-fleet-handoff-package.tar.gz> --work-dir /tmp/changxin-handoff-verify --verification-context receiving_machine > <evidence-dir>/reports/handoff_package_verification.json",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/record_unit_hardware_dispatch_artifact.py --source-artifact <prevalidated_artifact_root> --profile <local-work-hardware-ros1-gateway.env> --output-dir <evidence-dir>/hardware_artifacts --platform-id <platform_id> --task-id <task_id> --dispatch-service /fleet/<platform_id>/gateway/dispatch --dispatch-stdout-file /tmp/changxin-dispatch-response.txt --task-progress-file /tmp/changxin-task-progress.json --operator-approved",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/import_distributed_fleet_external_evidence.py --evidence-dir <evidence-dir> --model-lab-evaluation <model_lab_evaluation.json> --migration-verification-report <migration_verification.json> --handoff-package-verification-report <handoff_package_verification.json> --artifact-package-verification-report <artifact_package_verification.json> --site-acceptance-ros1-report <site_acceptance_work_hardware_ros1.json> --artifact-package <artifact-package.tar.gz> --hardware-run-artifact <hardware-run-artifact-root>",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_phase_gate.py --evidence-dir <evidence-dir> --print-discovered-inputs",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir <evidence-dir> --model-lab-evaluation <model_lab_evaluation.json> --artifact-package-verification-report <artifact_package_verification.json> --migration-verification-report <migration-report.json> --handoff-package-verification-report <handoff-package-report.json> --hardware-run-artifact <artifact-root>",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir <evidence-dir> --missing-only --print-discovered-inputs",
        "```",
        "",
    ])


def _phase_gate_doc(*, phase_gate: Dict[str, Any]) -> str:
    missing = phase_gate.get("missing_external_proofs")
    if not isinstance(missing, list):
        missing = []
    failed = phase_gate.get("failed_external_proofs")
    if not isinstance(failed, list):
        failed = []
    local = phase_gate.get("local_unresolved_required")
    if not isinstance(local, list):
        local = []
    missing_lines = [f"- `{name}`" for name in missing] or ["- none"]
    failed_lines = [f"- `{name}`" for name in failed] or ["- none"]
    local_lines = [f"- `{name}`" for name in local] or ["- none"]
    return "\n".join([
        "# Distributed Fleet Phase Gate",
        "",
        f"Status: `{phase_gate.get('status')}`",
        f"Local v1 freeze: `{phase_gate.get('local_v1_freeze')}`",
        f"Next phase ready: `{phase_gate.get('next_phase_ready')}`",
        "",
        str(phase_gate.get("message") or ""),
        "",
        "Policy:",
        "",
        str(phase_gate.get("policy") or ""),
        "",
        "Missing external proofs:",
        "",
        *missing_lines,
        "",
        "Failed external proofs:",
        "",
        *failed_lines,
        "",
        "Local unresolved requirements:",
        "",
        *local_lines,
        "",
        "If local v1 freeze is `True`, do not keep expanding local implementation just because external proofs are still missing.",
        "Import the real reports and packages, rerun `tools/check_distributed_fleet_goal_evidence.py`, and start the next phase only when `next_phase_ready` is `True`.",
        "",
    ])
