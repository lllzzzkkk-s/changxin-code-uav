# Phase 2B No-Hardware Operations Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable no-motion acceptance report and operator-facing diagnostics for Phase 2 artifacts without connecting to ROS or dispatching hardware.

**Architecture:** Phase 2B stays in the ground-station, no-hardware layer. It reads existing Phase 2A artifacts, run ledgers, validation reports, command acks, task progress, and execution events, then emits deterministic JSON and Markdown summaries for humans and future operator-view work. It does not instantiate `Ros1ServiceGateway`, run `rosservice`, publish ROS topics, or start Phase 3 gateway lifecycle work.

**Tech Stack:** Python dataclasses, `unittest`, JSON artifact readers under `task_planning/mission_ops/`, CLI tools under `tools/`, Markdown docs under `docs/superpowers/`, existing `MissionArtifactBundle.v1` and `ExecutionEventLog.v1`.

---

## Scope Check

Phase 2B implements one subsystem: no-hardware reporting and operator-facing diagnostics.

Do not implement these in Phase 2B:

- ROS1 service discovery
- gateway lifecycle start/stop
- `/gateway/dry_run`
- `/gateway/dispatch`
- `/cmd_vel`, `/move_base`, `/mavros/*`, `/setpoints_cmd`
- Qt GUI code
- LangGraph runtime
- platform-local mission planning
- controlled motion

## File Structure

- Create: `task_planning/mission_ops/acceptance_report.py`
  - Responsibility: load one or more Phase 2A artifact roots and produce `Phase2NoMotionAcceptanceReport.v1` with artifact health, runtime events, approval state, no-motion boundary checks, and Phase 1 baseline identity.
- Modify: `task_planning/mission_ops/__init__.py`
  - Responsibility: export report dataclasses and builder functions.
- Create: `tools/check_phase2_no_motion_acceptance.py`
  - Responsibility: CLI wrapper that writes or prints the no-motion acceptance report.
- Modify: `task_planning/mission_ops/replay.py`
  - Responsibility: add `ArtifactReplayDiagnosticSummary.v1` so replay can explain rejected acks, failure reports, replan requests, approval-required stops, and event counts without requiring manual JSON inspection.
- Modify: `tools/replay_task_planning_artifact.py`
  - Responsibility: add `--summary` to print replay diagnostics instead of only raw validation status.
- Create: `tests/task_planning/test_phase2_acceptance_report.py`
  - Responsibility: test no-motion report generation, Phase 1/Phase 2 identity separation, no raw ROS command detection, and Markdown output.
- Modify: `tests/task_planning/test_replay_and_hardware_gates.py`
  - Responsibility: test replay diagnostic summary output and CLI behavior.
- Create: `docs/superpowers/specs/2026-06-03-phase-2b-operator-view-signals.md`
  - Responsibility: document operator-view data fields and forbidden controls without adding UI code.
- Modify: `docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md`
  - Responsibility: append Phase 2B verification results after implementation succeeds.

## New Schemas

Use these schema names consistently:

- `Phase2NoMotionAcceptanceReport.v1`
- `Phase2NoMotionAcceptanceReportMarkdown.v1`
- `ArtifactReplayDiagnosticSummary.v1`

Minimum `Phase2NoMotionAcceptanceReport.v1` fields:

- `schema`
- `ok`
- `generated_at`
- `phase1_baseline`
- `phase2_run`
- `artifact_health`
- `runtime_summary`
- `approval_summary`
- `no_motion_boundary`
- `operator_view`
- `validation_errors`

Minimum `ArtifactReplayDiagnosticSummary.v1` fields:

- `schema`
- `ok`
- `artifact_root`
- `current_state`
- `event_counts`
- `accepted_commands`
- `rejected_commands`
- `progress_count`
- `failure_report`
- `replan_requested`
- `approval_required`
- `validation_errors`

## Task 1: Write Phase 2B Acceptance Report Tests First

**Files:**
- Create: `tests/task_planning/test_phase2_acceptance_report.py`

- [ ] **Step 1: Add a fixture helper that creates a Phase 2A artifact**

Use the existing runner and golden case helper:

```python
from pathlib import Path

from task_planning.config import load_profile
from task_planning.mission_ops.golden_cases import golden_case_by_id
from task_planning.mission_ops.runner import MissionOpsRunner


def _write_dev_mock_artifact(root: Path) -> Path:
    profile = load_profile(Path("profiles/dev_mock.env"))
    env = dict(profile.as_env_dict())
    env["MISSION_ARTIFACT_ROOT"] = str(root / "runs")
    result = MissionOpsRunner().run(golden_case_by_id("single_ugv_inspection").run_input(), env)
    assert result.artifact_bundle_path
    return Path(result.artifact_bundle_path)
```

- [ ] **Step 2: Write `test_acceptance_report_separates_phase1_archive_from_phase2_run`**

Expected test body:

```python
def test_acceptance_report_separates_phase1_archive_from_phase2_run(self):
    with tempfile.TemporaryDirectory() as tmp:
        artifact = _write_dev_mock_artifact(Path(tmp))
        report = build_phase2_no_motion_acceptance_report(
            artifact_roots=[artifact],
            phase1_archive_path="D:\\changxin\\final-archives\\changxin-distributed-fleet-final-proof-20260602.tar.gz",
            phase1_archive_sha256="66465e2a1377e9f2dd11dc4136db9b92fa5d6e369f9f1c06c4a8a4c0ca850366",
        )

    self.assertTrue(report.ok, report.as_dict())
    self.assertEqual("Phase2NoMotionAcceptanceReport.v1", report.schema)
    self.assertEqual("66465e2a1377e9f2dd11dc4136db9b92fa5d6e369f9f1c06c4a8a4c0ca850366", report.phase1_baseline["sha256"])
    self.assertEqual(str(artifact), report.phase2_run["artifact_roots"][0])
    self.assertEqual("mock", report.no_motion_boundary["platform_backend"])
    self.assertFalse(report.no_motion_boundary["ros_connected"])
    self.assertFalse(report.no_motion_boundary["dispatch_performed"])
```

- [ ] **Step 3: Write `test_acceptance_report_rejects_raw_motion_command_strings`**

Expected behavior:

- mutate `bt_artifact.json` to include a command capability or parameter containing `/cmd_vel`
- build report
- assert `report.ok is False`
- assert validation errors include `raw motion command token`

- [ ] **Step 4: Write `test_acceptance_report_markdown_contains_operator_summary`**

Expected behavior:

- call `render_phase2_no_motion_acceptance_markdown(report)`
- assert Markdown includes `No-Motion Boundary`, `Approval`, `Execution Events`, and `Not Hardware Proof`

- [ ] **Step 5: Run the new test before implementation**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.task_planning.test_phase2_acceptance_report -v
```

Expected before implementation: import failure for `task_planning.mission_ops.acceptance_report`.

## Task 2: Implement Acceptance Report Core

**Files:**
- Create: `task_planning/mission_ops/acceptance_report.py`
- Modify: `task_planning/mission_ops/__init__.py`

- [ ] **Step 1: Add dataclass `Phase2NoMotionAcceptanceReport`**

Minimum implementation shape:

```python
@dataclass(frozen=True)
class Phase2NoMotionAcceptanceReport:
    phase1_baseline: Dict[str, Any]
    phase2_run: Dict[str, Any]
    artifact_health: Dict[str, Any]
    runtime_summary: Dict[str, Any]
    approval_summary: Dict[str, Any]
    no_motion_boundary: Dict[str, Any]
    operator_view: Dict[str, Any]
    validation_errors: List[str]
    generated_at: str = field(default_factory=utc_timestamp)
    schema: str = "Phase2NoMotionAcceptanceReport.v1"

    @property
    def ok(self) -> bool:
        return not self.validation_errors

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self) | {"ok": self.ok}
```

- [ ] **Step 2: Add `build_phase2_no_motion_acceptance_report`**

Required behavior:

- load each artifact with `load_artifact_bundle`
- collect validation errors from artifact replay
- count execution events by type
- count accepted and rejected command acks
- count task progress items
- read approval state from `validation_report.json`, `run_summary.md`, and `execution_events.json`
- reject raw motion strings in all JSON artifacts using token list:
  - `/cmd_vel`
  - `/move_base`
  - `/mavros/`
  - `/setpoints_cmd`
- set `ros_connected=false`
- set `dispatch_performed=false`
- set `hardware_proof=false`

- [ ] **Step 3: Add Markdown renderer**

Function:

```python
def render_phase2_no_motion_acceptance_markdown(report: Phase2NoMotionAcceptanceReport) -> str:
    data = report.as_dict()
    lines = [
        "# Phase 2 No-Motion Acceptance",
        "",
        "## Phase 1 Baseline",
        f"- archive: `{data['phase1_baseline'].get('archive_path', '')}`",
        f"- sha256: `{data['phase1_baseline'].get('sha256', '')}`",
        "",
        "## Phase 2 Run",
        f"- artifact_roots: `{data['phase2_run'].get('artifact_roots', [])}`",
        "",
        "## No-Motion Boundary",
        f"- ros_connected: `{data['no_motion_boundary'].get('ros_connected')}`",
        f"- dispatch_performed: `{data['no_motion_boundary'].get('dispatch_performed')}`",
        f"- hardware_proof: `{data['no_motion_boundary'].get('hardware_proof')}`",
        "",
        "## Execution Events",
        f"- event_counts: `{data['runtime_summary'].get('event_counts', {})}`",
        "",
        "## Approval",
        f"- approval_required: `{data['approval_summary'].get('required')}`",
        f"- approval_source: `{data['approval_summary'].get('source', '')}`",
        "",
        "## Not Hardware Proof",
        "This report is no-hardware acceptance evidence only.",
        "",
        "## Validation Errors",
        *[f"- `{error}`" for error in data["validation_errors"]],
    ]
    return "\n".join(lines)
```

Required sections:

- `# Phase 2 No-Motion Acceptance`
- `Phase 1 Baseline`
- `Phase 2 Run`
- `No-Motion Boundary`
- `Execution Events`
- `Approval`
- `Not Hardware Proof`
- `Validation Errors`

- [ ] **Step 4: Export public symbols**

Add these exports to `task_planning/mission_ops/__init__.py`:

- `Phase2NoMotionAcceptanceReport`
- `build_phase2_no_motion_acceptance_report`
- `render_phase2_no_motion_acceptance_markdown`

- [ ] **Step 5: Run focused tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.task_planning.test_phase2_acceptance_report -v
```

Expected: all tests pass.

## Task 3: Add Acceptance Report CLI

**Files:**
- Create: `tools/check_phase2_no_motion_acceptance.py`
- Modify: `tests/task_planning/test_phase2_acceptance_report.py`

- [ ] **Step 1: Write CLI test**

Test behavior:

- create one dev_mock artifact
- run CLI with `--artifact-root <artifact>`
- pass Phase 1 archive path and SHA
- pass `--output-dir <tmp>/report`
- assert JSON and Markdown files exist
- assert JSON schema is `Phase2NoMotionAcceptanceReport.v1`
- assert exit code is `0`

- [ ] **Step 2: Implement CLI**

Arguments:

```text
--artifact-root <path>   repeatable
--phase1-archive-path <path string>
--phase1-archive-sha256 <sha256>
--output-dir <path>
--json-only
```

Output files:

```text
phase2_no_motion_acceptance.json
phase2_no_motion_acceptance.md
```

- [ ] **Step 3: Run CLI manually**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_phase2_no_motion_acceptance.py \
  --artifact-root /tmp/changxin-phase2a-dev-mock-golden-suite/<run_id> \
  --phase1-archive-path 'D:\changxin\final-archives\changxin-distributed-fleet-final-proof-20260602.tar.gz' \
  --phase1-archive-sha256 66465e2a1377e9f2dd11dc4136db9b92fa5d6e369f9f1c06c4a8a4c0ca850366 \
  --output-dir /tmp/changxin-phase2b-no-motion-acceptance
```

Expected:

- JSON report has `"ok": true`
- Markdown report states no ROS connection and no dispatch

## Task 4: Add Replay Diagnostic Summary

**Files:**
- Modify: `task_planning/mission_ops/replay.py`
- Modify: `tools/replay_task_planning_artifact.py`
- Modify: `tests/task_planning/test_replay_and_hardware_gates.py`

- [ ] **Step 1: Write `test_replay_summary_explains_event_and_approval_state`**

Expected assertions:

- summary schema is `ArtifactReplayDiagnosticSummary.v1`
- `event_counts["bt_runtime_completed"] >= 1` for dev_mock artifacts
- `accepted_commands >= 1`
- `approval_required is False` for dev_mock
- `validation_errors == []`

- [ ] **Step 2: Write `test_replay_summary_cli_outputs_operator_friendly_json`**

Run `tools/replay_task_planning_artifact.py <artifact> --summary` and assert:

- exit code `0`
- output JSON schema is `ArtifactReplayDiagnosticSummary.v1`
- output contains `event_counts`, `accepted_commands`, and `approval_required`

- [ ] **Step 3: Implement `summarize_artifact_bundle`**

Function:

```python
def summarize_artifact_bundle(root: Union[str, Path]) -> ArtifactReplayDiagnosticSummary:
    bundle = load_artifact_bundle(root)
    data = bundle.data
    events = data.get("execution_events.json", {}).get("items", [])
    event_counts = Counter(str(event.get("event_type")) for event in events if isinstance(event, Mapping))
    acks = data.get("command_acks.json", {}).get("items", [])
    progress = data.get("task_progress.json", {}).get("items", [])
    failure = data.get("failure_report.json", {})
    replan = data.get("replan_decision.json", {})
    validation = data.get("validation_report.json", {})
    return ArtifactReplayDiagnosticSummary(
        artifact_root=str(root),
        current_state=str(validation.get("current_state") or ""),
        event_counts=dict(event_counts),
        accepted_commands=len([ack for ack in acks if ack.get("accepted") is True]),
        rejected_commands=len([ack for ack in acks if ack.get("accepted") is False]),
        progress_count=len(progress),
        failure_report=dict(failure),
        replan_requested=bool(replan and replan.get("status") != "not_requested"),
        approval_required="operator_approval_required" in event_counts,
        validation_errors=list(bundle.validation_errors),
    )
```

Use existing loaded artifacts:

- `validation_report.json`
- `execution_events.json`
- `command_acks.json`
- `task_progress.json`
- `failure_report.json`
- `replan_decision.json`

- [ ] **Step 4: Add CLI flag**

Add:

```python
parser.add_argument("--summary", action="store_true", help="Print operator-facing replay diagnostics.")
```

If `--summary` is set, print `summarize_artifact_bundle(args.artifact_root).as_dict()`.

## Task 5: Document Operator-View Signals Without UI Code

**Files:**
- Create: `docs/superpowers/specs/2026-06-03-phase-2b-operator-view-signals.md`

- [ ] **Step 1: Add signal contract sections**

Required sections:

- `Scope`
- `Allowed Data`
- `Forbidden Controls`
- `No-Motion Acceptance Fields`
- `Approval Fields`
- `Failure And Replan Fields`
- `Future Qt Integration Notes`

- [ ] **Step 2: Explicitly forbid raw controls**

The doc must state:

```text
The operator view may display `/cmd_vel`, `/move_base`, `/mavros/*`, or `/setpoints_cmd`
only as forbidden-token diagnostics. It must not publish, call, or construct those controls.
```

- [ ] **Step 3: Link the acceptance report schema**

Reference:

- `Phase2NoMotionAcceptanceReport.v1`
- `ArtifactReplayDiagnosticSummary.v1`
- `ExecutionEventLog.v1`
- `OperatorApprovalState.v1`

## Task 6: Run Phase 2B Acceptance Gates And Update Docs

**Files:**
- Modify: `docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md`
- Modify: `docs/superpowers/specs/2026-06-02-distributed-fleet-phase-2-to-langgraph-roadmap.md`

- [ ] **Step 1: Run focused tests**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.task_planning.test_phase2_acceptance_report \
  tests.task_planning.test_replay_and_hardware_gates \
  -v
```

Expected: pass.

- [ ] **Step 2: Run all task-planning tests**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests/task_planning
```

Expected: pass.

- [ ] **Step 3: Produce one acceptance report**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_phase2_no_motion_acceptance.py \
  --artifact-root /tmp/changxin-phase2a-dev-mock-golden-suite/<run_id> \
  --phase1-archive-path 'D:\changxin\final-archives\changxin-distributed-fleet-final-proof-20260602.tar.gz' \
  --phase1-archive-sha256 66465e2a1377e9f2dd11dc4136db9b92fa5d6e369f9f1c06c4a8a4c0ca850366 \
  --output-dir /tmp/changxin-phase2b-no-motion-acceptance
```

Expected:

- `/tmp/changxin-phase2b-no-motion-acceptance/phase2_no_motion_acceptance.json`
- `/tmp/changxin-phase2b-no-motion-acceptance/phase2_no_motion_acceptance.md`
- JSON `"ok": true`
- Markdown states `Not Hardware Proof`

- [ ] **Step 4: Update docs with results**

Append Phase 2B result only after tests and report generation pass. Keep Phase
3 pending until the user explicitly asks for ROS1 read-only service signature
audit or gateway lifecycle hardening.

## Final Acceptance Criteria

Phase 2B is complete only when all are true:

- A new agent can run one command to generate a no-motion acceptance report from Phase 2A artifacts.
- The report separates Phase 1 final archive identity from Phase 2 no-hardware run identity.
- The report marks ROS connection, gateway dispatch, hardware proof, and controlled motion as false.
- Replay summary explains event counts, accepted/rejected commands, failure reports, replan requests, and approval-required stops.
- Operator-view signal spec exists and forbids raw ROS controls.
- Unit tests pass.
- No code path in Phase 2B connects ROS, calls `rosservice`, publishes raw ROS topics, or performs hardware dispatch.
