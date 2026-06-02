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
    summarize_goal_evidence_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate distributed fleet testing evidence and show which goal requirements are still unproved.",
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
    parser.add_argument("--summary", action="store_true", help="Print a compact status summary instead of full evidence.")
    parser.add_argument("--missing-only", action="store_true", help="Print only missing or failed required items.")
    parser.add_argument("--print-discovered-inputs", action="store_true", help="Include auto-discovered evidence input paths.")
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
    if args.summary or args.missing_only:
        output = summarize_goal_evidence_report(report, missing_only=args.missing_only)
    else:
        output = report.as_dict()
    if args.print_discovered_inputs:
        output["discovered_inputs"] = discovered.as_dict()
        output["merged_inputs"] = inputs.as_dict()
    print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
