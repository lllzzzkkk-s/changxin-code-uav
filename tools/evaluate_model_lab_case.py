#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration.model_lab import evaluate_model_lab_case


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate a home model-lab endpoint against a golden mission case without hardware dispatch. "
            "home_5090_live proof records machine_id, baseline comparison fields, "
            "and requires an nvidia-smi RTX 5090 probe."
        ),
    )
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--case", default="uav_ugv_coordination")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--require-baseline-equivalence", action="store_true")
    args = parser.parse_args()

    evaluation = evaluate_model_lab_case(
        profile_path=args.profile,
        case_id=args.case,
        output_dir=args.output_dir,
        require_baseline_equivalence=args.require_baseline_equivalence,
    )
    print(json.dumps(evaluation.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if evaluation.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
