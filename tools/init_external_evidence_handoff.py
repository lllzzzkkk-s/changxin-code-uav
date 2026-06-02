#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import build_external_evidence_handoff


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create the standard external evidence handoff scaffold without fabricating proof.",
    )
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--case", default="uav_ugv_coordination")
    parser.add_argument("--missing-required", action="append", default=[])
    args = parser.parse_args()

    missing = args.missing_required or _missing_from_goal_report(args.evidence_dir / "reports" / "goal_evidence.json")
    handoff = build_external_evidence_handoff(
        repo_root=REPO_ROOT,
        evidence_dir=args.evidence_dir,
        case_id=args.case,
        missing_required=missing,
    )
    print(json.dumps(handoff.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def _missing_from_goal_report(path: Path) -> List[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    missing = data.get("missing_required", [])
    if not isinstance(missing, list):
        return []
    result: List[str] = []
    for item in missing:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            result.append(item["name"])
    return result


if __name__ == "__main__":
    raise SystemExit(main())
