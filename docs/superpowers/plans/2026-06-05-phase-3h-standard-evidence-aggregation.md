# Phase 3H Standard Evidence Aggregation Plan

Date: 2026-06-05

Goal: aggregate the Phase 3G UGV hardware pass with the existing standard
evidence archive so the remaining goal-evidence gaps are separated into real
global proof-chain gaps versus missing command-line inputs.

This phase does not call ROS and does not rerun Phase 3F or Phase 3G hardware
steps.

## Starting Point

Phase 3G passed the UGV hardware goal-evidence item:

```text
unit_hardware_execution_artifact_verified=pass
```

Remaining gaps from the Phase 3G isolated checker run:

```text
dev_mock_golden_suite_recorded=missing
migration_bundle_verified_after_transfer=missing
artifact_package_verified_after_transfer=missing
home_5090_model_lab_evaluated=missing
```

These gaps are not UGV hardware failures. Phase 3H determines whether those
proofs are already present in the standard evidence directory and were simply
not passed into the Phase 3G checker invocation.

## Boundary

Allowed:

- inspect standard evidence files under `/tmp/changxin-distributed-fleet-evidence`
- run local no-ROS goal-evidence aggregation
- run local no-ROS `dev_mock` golden suite only if the standard evidence dir is
  missing it
- pass Phase 3G reports explicitly to the checker
- write temporary scripts under `/tmp/changxin-phase3h` for JSON inspection

Not allowed:

- gateway `dry_run`
- gateway `dispatch`
- controlled motion
- `move_base_goal`
- `--unit-ugv-enable-move-base`
- `rostopic pub`
- raw ROS control topics
- hand-written `TaskCommand` JSON
- repo architecture edits
- non-convex alpha document edits
- committed machine-specific ROS env/IP values

## Stage 0: Pull Latest Repo

Owner: 4060 Codex.

```bash
cd /mnt/d/changxin/changxin-code
git fetch origin
git checkout codex/phase2b-no-hardware-reporting
git pull --ff-only origin codex/phase2b-no-hardware-reporting
git log -2 --oneline
git status --short
mkdir -p /tmp/changxin-phase3h
```

For Windows/WSL2 quoting-sensitive work, prefer short temporary scripts under
`/tmp/changxin-phase3h` instead of brittle inline heredocs or long regex pipes.

Exit gate:

- head includes this Phase 3H plan
- worktree is clean

## Stage 0.5: Create Temporary JSON Status Script

Owner: 4060 Codex.

Use a temporary Python script for JSON extraction instead of long inline
heredocs, regex pipes, or fragile shell quoting. This is especially important
on Windows/WSL2 when command text may be copied through clients that introduce
CRLF, BOM, quote escaping, or pipe parsing issues.

Create the file using the editor or a short script writer that the local agent
trusts. Keep it under `/tmp/changxin-phase3h` and do not commit it.

Path:

```text
/tmp/changxin-phase3h/phase3h_extract_status.py
```

Content:

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def item_statuses(data):
    items = data.get("items") or []
    if isinstance(items, list):
        return {
            str(item.get("name") or ""): str(item.get("status") or "")
            for item in items
            if isinstance(item, dict)
        }
    return {}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: phase3h_extract_status.py <goal-evidence-json>", file=sys.stderr)
        return 2
    data = load(sys.argv[1])
    statuses = item_statuses(data)
    missing = [
        name for name, status in sorted(statuses.items())
        if status in {"missing", "fail"}
    ]
    output = {
        "schema": "Phase3HGoalEvidenceStatus.v1",
        "source": sys.argv[1],
        "ok": data.get("ok"),
        "phase_gate_status": (data.get("phase_gate") or {}).get("status"),
        "unit_hardware_execution_artifact_verified": statuses.get("unit_hardware_execution_artifact_verified"),
        "dev_mock_golden_suite_recorded": statuses.get("dev_mock_golden_suite_recorded"),
        "missing_or_failed": missing,
        "status_by_item": statuses,
    }
    print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

After creating it:

```bash
chmod +x /tmp/changxin-phase3h/phase3h_extract_status.py
python3 /tmp/changxin-phase3h/phase3h_extract_status.py --help 2>/dev/null || true
```

Exit gate:

- script exists under `/tmp/changxin-phase3h`
- script is not committed
- script can parse JSON files with UTF-8 or UTF-8 BOM

## Stage 1: Inventory Existing Evidence Inputs

Owner: 4060 Codex.

```bash
EVIDENCE_DIR=/tmp/changxin-distributed-fleet-evidence
test -d "$EVIDENCE_DIR"
find "$EVIDENCE_DIR/reports" -maxdepth 1 -type f -name '*.json' | sort \
  | tee /tmp/changxin-phase3h/standard-evidence-json-files.txt
find "$EVIDENCE_DIR/hardware_artifacts" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | sort \
  | tee /tmp/changxin-phase3h/standard-hardware-artifact-roots.txt
sha256sum /tmp/changxin-phase3h/standard-evidence-json-files.txt
sha256sum /tmp/changxin-phase3h/standard-hardware-artifact-roots.txt
```

Required Phase 3G inputs:

```bash
test -f /tmp/changxin-phase3g/lane_matrix_single_ugv_inspection.json
test -f /tmp/changxin-phase3g/site_acceptance_ros1_signature_same_machine.json
test -d /tmp/changxin-phase3f/hardware_artifacts/phase3f-ugv0-manual-confirm-dispatch
```

Exit gate:

- standard evidence directory exists
- Phase 3G lane matrix exists
- Phase 3G same-machine ROS1 signature report exists
- Phase 3F hardware artifact exists

## Stage 2: Run Combined Goal Evidence

Owner: 4060 Codex.

Run with the standard evidence directory plus explicit Phase 3G aligned reports:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py \
  --evidence-dir /tmp/changxin-distributed-fleet-evidence \
  --lane-matrix-report /tmp/changxin-phase3g/lane_matrix_single_ugv_inspection.json \
  --site-acceptance-report /tmp/changxin-phase3g/site_acceptance_ros1_signature_same_machine.json \
  --hardware-run-artifact /tmp/changxin-phase3f/hardware_artifacts/phase3f-ugv0-manual-confirm-dispatch \
  --summary \
  --print-discovered-inputs \
  | tee /tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_summary.json
python3 -m json.tool /tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_summary.json \
  > /tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_summary.pretty.json
sha256sum /tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_summary.json
python3 /tmp/changxin-phase3h/phase3h_extract_status.py \
  /tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_summary.json \
  | tee /tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_status.json
sha256sum /tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_status.json

PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py \
  --evidence-dir /tmp/changxin-distributed-fleet-evidence \
  --lane-matrix-report /tmp/changxin-phase3g/lane_matrix_single_ugv_inspection.json \
  --site-acceptance-report /tmp/changxin-phase3g/site_acceptance_ros1_signature_same_machine.json \
  --hardware-run-artifact /tmp/changxin-phase3f/hardware_artifacts/phase3f-ugv0-manual-confirm-dispatch \
  --print-discovered-inputs \
  | tee /tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_full.json
python3 -m json.tool /tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_full.json \
  > /tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_full.pretty.json
sha256sum /tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_full.json
```

Exit gate:

- `unit_hardware_execution_artifact_verified=pass` remains true
- remaining missing/failed items are listed from the combined run
- status extraction JSON is written by the temporary script
- if `ok=true`, record `next_phase_ready`
- if `ok=false`, do not treat unrelated missing items as UGV hardware failures

## Stage 3: Optional No-ROS Dev Mock Backfill

Owner: 4060 Codex.

Only run this if the combined checker still reports
`dev_mock_golden_suite_recorded=missing`.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_dev_mock_golden_suite.py \
  --artifact-root /tmp/changxin-phase3h/dev_mock_golden_suite_artifacts \
  | tee /tmp/changxin-phase3h/dev_mock_golden_suite.json
python3 -m json.tool /tmp/changxin-phase3h/dev_mock_golden_suite.json \
  > /tmp/changxin-phase3h/dev_mock_golden_suite.pretty.json
sha256sum /tmp/changxin-phase3h/dev_mock_golden_suite.json
```

Then rerun the combined checker with:

```bash
--dev-mock-golden-suite-report /tmp/changxin-phase3h/dev_mock_golden_suite.json
```

Also rerun the temporary status extractor on the rerun summary:

```bash
python3 /tmp/changxin-phase3h/phase3h_extract_status.py \
  /tmp/changxin-phase3h/<rerun-summary-json> \
  | tee /tmp/changxin-phase3h/<rerun-status-json>
```

Exit gate:

- this stage is no-ROS and no-hardware
- dev mock golden suite report has `ok=true`
- if other missing items remain, list them separately

## Stage 4: Report

Report:

- `git log -2 --oneline`
- `git status --short`
- standard evidence directory inventory path/hash
- combined summary/full path/hash
- status extraction JSON path/hash
- whether `unit_hardware_execution_artifact_verified=pass`
- whether overall `ok=true`
- if overall `ok=false`, exact remaining missing/failed items
- whether Stage 3 dev mock backfill was run
- boundary confirmation:
  - `new_rosservice_call=false`
  - `gateway_dry_run_called=false`
  - `gateway_dispatch_called=false`
  - `controlled_motion_authorized=false`
  - `move_base_used=false`
  - `rostopic_pub=false`
  - `repo_architecture_changed=false`
  - `non_convex_alpha_docs_touched=false`
  - `committed_machine_specific_ros_env=false`

## Phase 3H Result

Status as of 2026-06-05: Phase 3H passed on the 4060 WSL2 unit lane.

```text
overall ok=true
rc=0
unit_hardware_execution_artifact_verified=pass
remaining missing/failed items=[]
dev_mock golden-suite backfill run=false
```

Key artifacts:

```text
summary=/tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_summary.json
summary_sha256=a5a715dd3a109f4ce75206c54f03f28fec7838f5ad3461e7223a66e07a6a1610

full=/tmp/changxin-phase3h/goal_evidence_standard_plus_phase3g_full.json
full_sha256=8fff410c5cbd4ba1f5cc6530ee7fe44e78edb3daae16001ec4262f88fb5537e1

receipt=/tmp/changxin-phase3h/phase3h_receipt_summary.json
receipt_sha256=413d62293733ab6f526ea2770f57a77d4c1790c4ad01f33e33bed78549f9ce0d
```

Interpretation:

- Phase 3G's isolated missing items were not UGV hardware failures.
- The standard evidence directory plus Phase 3G aligned reports close the full
  goal-evidence checker.
- The phase gate is `next_phase_ready`.
