#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import (
    build_distributed_fleet_goal_evidence,
    discover_goal_evidence_inputs,
    merge_goal_evidence_inputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print only the distributed fleet phase gate so a receiving agent can decide whether to keep local work frozen or start the next phase.",
    )
    parser.add_argument("--evidence-dir", action="append", default=[], type=Path)
    parser.add_argument("--artifact-package", action="append", default=[], type=Path)
    parser.add_argument("--artifact-package-verification-report", action="append", default=[], type=Path)
    parser.add_argument("--artifact-work-dir", type=Path)
    parser.add_argument("--site-acceptance-report", action="append", default=[], type=Path)
    parser.add_argument("--lane-matrix-report", action="append", default=[], type=Path)
    parser.add_argument("--dev-mock-golden-suite-report", action="append", default=[], type=Path)
    parser.add_argument("--model-lab-evaluation", action="append", default=[], type=Path)
    parser.add_argument("--migration-verification-report", action="append", default=[], type=Path)
    parser.add_argument("--handoff-package-verification-report", action="append", default=[], type=Path)
    parser.add_argument("--hardware-run-artifact", action="append", default=[], type=Path)
    parser.add_argument(
        "--require-next-phase-ready",
        action="store_true",
        help="Exit nonzero unless every local and external proof gate has passed.",
    )
    parser.add_argument("--print-discovered-inputs", action="store_true")
    args = parser.parse_args()

    discovered = discover_goal_evidence_inputs(args.evidence_dir)
    inputs = merge_goal_evidence_inputs(
        discovered=discovered,
        artifact_packages=args.artifact_package,
        artifact_package_verification_reports=args.artifact_package_verification_report,
        artifact_work_dir=args.artifact_work_dir,
        site_acceptance_reports=args.site_acceptance_report,
        lane_matrix_reports=args.lane_matrix_report,
        dev_mock_golden_suite_reports=args.dev_mock_golden_suite_report,
        model_lab_evaluations=args.model_lab_evaluation,
        migration_verification_reports=args.migration_verification_report,
        handoff_package_verification_reports=args.handoff_package_verification_report,
        hardware_run_artifacts=args.hardware_run_artifact,
    )
    report = build_distributed_fleet_goal_evidence(
        repo_root=REPO_ROOT,
        artifact_packages=inputs.artifact_packages,
        artifact_package_verification_reports=inputs.artifact_package_verification_reports,
        artifact_work_dir=inputs.artifact_work_dir,
        site_acceptance_reports=inputs.site_acceptance_reports,
        lane_matrix_reports=inputs.lane_matrix_reports,
        dev_mock_golden_suite_reports=inputs.dev_mock_golden_suite_reports,
        model_lab_evaluations=inputs.model_lab_evaluations,
        migration_verification_reports=inputs.migration_verification_reports,
        handoff_package_verification_reports=inputs.handoff_package_verification_reports,
        hardware_run_artifacts=inputs.hardware_run_artifacts,
    )
    phase_gate = report.phase_gate
    output = {
        "schema": "DistributedFleetPhaseGateCheck.v1",
        "ok": phase_gate["next_phase_ready"] or phase_gate["status"] == "waiting_for_external_proofs",
        "repo_root": str(REPO_ROOT),
        "phase_gate": phase_gate,
        "counts": {
            "total": len(report.items),
            "passed_required": len([item for item in report.items if item.required and item.status == "pass"]),
            "missing_required": len(report.missing_required),
            "failed_required": len(report.failed_required),
        },
        "missing_required_names": [item.name for item in report.missing_required],
        "failed_required_names": [item.name for item in report.failed_required],
    }
    if args.print_discovered_inputs:
        output["discovered_inputs"] = discovered.as_dict()
        output["merged_inputs"] = inputs.as_dict()
    print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))

    if args.require_next_phase_ready:
        return 0 if phase_gate["next_phase_ready"] else 1
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
