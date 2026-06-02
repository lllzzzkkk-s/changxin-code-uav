#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import import_external_evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import real external fleet evidence into the standard evidence directory.",
    )
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--model-lab-evaluation", type=Path)
    parser.add_argument("--migration-verification-report", type=Path)
    parser.add_argument("--handoff-package-verification-report", type=Path)
    parser.add_argument("--artifact-package-verification-report", type=Path)
    parser.add_argument("--site-acceptance-ros1-report", type=Path)
    parser.add_argument("--artifact-package", action="append", default=[], type=Path)
    parser.add_argument("--hardware-run-artifact", action="append", default=[], type=Path)
    args = parser.parse_args()

    report = import_external_evidence(
        evidence_dir=args.evidence_dir,
        model_lab_evaluation=args.model_lab_evaluation,
        migration_verification_report=args.migration_verification_report,
        handoff_package_verification_report=args.handoff_package_verification_report,
        artifact_package_verification_report=args.artifact_package_verification_report,
        site_acceptance_ros1_report=args.site_acceptance_ros1_report,
        artifact_packages=args.artifact_package,
        hardware_run_artifacts=args.hardware_run_artifact,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
