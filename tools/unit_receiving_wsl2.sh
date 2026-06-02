#!/usr/bin/env bash
set -o pipefail

HANDOFF_PACKAGE=""
EVIDENCE_DIR="/tmp/changxin-distributed-fleet-evidence"
LOG_DIR="/tmp/changxin-unit-receiving-logs"
ARTIFACT_PACKAGES=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --handoff-package)
      HANDOFF_PACKAGE="${2:-}"
      shift 2
      ;;
    --artifact-package)
      ARTIFACT_PACKAGES+=("${2:-}")
      shift 2
      ;;
    --evidence-dir)
      EVIDENCE_DIR="${2:-}"
      shift 2
      ;;
    --log-dir)
      LOG_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      cat <<'USAGE'
Usage:
  bash tools/unit_receiving_wsl2.sh --handoff-package <distributed-fleet-handoff-package.tar.gz> [--artifact-package <task-planning-artifacts.tar.gz> ...]

This script runs inside WSL2. It verifies transferred packages and writes:
  - /tmp/changxin-distributed-fleet-evidence
  - C:\changxin-evidence\logs when --log-dir is passed as /mnt/c/changxin-evidence/logs
USAGE
      exit 0
      ;;
    *)
      echo "FAIL: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_ROOT="/tmp/changxin-unit-receiving"
EXTRACT_DIR="$RUN_ROOT/handoff-extract"
HANDOFF_VERIFY_DIR="$RUN_ROOT/handoff-verify"
ARTIFACT_VERIFY_DIR="$RUN_ROOT/artifact-verify"
STEPS_JSONL=""

step_number=0

step() {
  step_number=$((step_number + 1))
  echo
  echo "STEP $step_number: $1"
  echo "EXPECTED: $2"
}

pass() {
  echo "PASS: $1"
}

fail() {
  local message="$1"
  echo "FAIL: $message" >&2
  if [ -n "$STEPS_JSONL" ]; then
    "$PYTHON_BIN" - "$STEPS_JSONL" "$step_number" "fail" "$message" <<'PY' || true
import json
import sys
path, step_number, status, message = sys.argv[1:5]
with open(path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps({
        "step": int(step_number),
        "status": status,
        "message": message,
    }, ensure_ascii=False) + "\n")
PY
  fi
  exit 1
}

record_pass() {
  local message="$1"
  if [ -n "$STEPS_JSONL" ]; then
    "$PYTHON_BIN" - "$STEPS_JSONL" "$step_number" "pass" "$message" <<'PY'
import json
import sys
path, step_number, status, message = sys.argv[1:5]
with open(path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps({
        "step": int(step_number),
        "status": status,
        "message": message,
    }, ensure_ascii=False) + "\n")
PY
  fi
}

run_json_command() {
  local name="$1"
  local output_path="$2"
  local stderr_path="$3"
  shift 3
  "$@" >"$output_path" 2>"$stderr_path"
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    fail "$name failed with exit code $rc; stderr: $stderr_path"
  fi
}

if [ -z "$HANDOFF_PACKAGE" ]; then
  fail "--handoff-package is required"
fi
if [ ! -f "$HANDOFF_PACKAGE" ]; then
  fail "handoff package is missing: $HANDOFF_PACKAGE"
fi
case "$HANDOFF_PACKAGE" in
  *.tar.gz) ;;
  *) fail "handoff package must end with .tar.gz: $HANDOFF_PACKAGE" ;;
esac
for artifact in "${ARTIFACT_PACKAGES[@]}"; do
  if [ ! -f "$artifact" ]; then
    fail "artifact package is missing: $artifact"
  fi
  case "$artifact" in
    *.tar.gz) ;;
    *) fail "artifact package must end with .tar.gz: $artifact" ;;
  esac
done

mkdir -p "$LOG_DIR" "$RUN_ROOT"

step "WSL2 boundary" "script is running in Linux/WSL2 and will run verifier Python here, not in Windows native PowerShell."
if grep -qi microsoft /proc/version 2>/dev/null; then
  pass "WSL2-like kernel detected"
else
  pass "Linux shell detected; continuing because verifier commands are Linux-side"
fi
record_pass "Linux-side verifier boundary accepted"

step "Extract handoff baseline evidence" "handoff archive contains an evidence scaffold; it is copied to /tmp but not counted as unit-side validation by itself."
rm -rf "$EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"
tar -xzf "$HANDOFF_PACKAGE" -C "$EXTRACT_DIR" || fail "failed to extract handoff package"
PACKAGE_ROOTS=("$EXTRACT_DIR"/*)
if [ "${#PACKAGE_ROOTS[@]}" -ne 1 ] || [ ! -d "${PACKAGE_ROOTS[0]}" ]; then
  fail "handoff package must extract to one top-level directory"
fi
PACKAGE_ROOT="${PACKAGE_ROOTS[0]}"
if [ ! -d "$PACKAGE_ROOT/evidence" ]; then
  fail "handoff package does not contain evidence/"
fi
case "$EVIDENCE_DIR" in
  /tmp/changxin-distributed-fleet-evidence|/tmp/changxin-distributed-fleet-evidence/*) ;;
  *) fail "refusing to replace non-standard evidence dir: $EVIDENCE_DIR" ;;
esac
rm -rf "$EVIDENCE_DIR"
mkdir -p "$(dirname "$EVIDENCE_DIR")"
cp -a "$PACKAGE_ROOT/evidence" "$EVIDENCE_DIR"
mkdir -p "$EVIDENCE_DIR/reports" "$EVIDENCE_DIR/artifact_packages" "$EVIDENCE_DIR/hardware_artifacts"
STEPS_JSONL="$EVIDENCE_DIR/reports/unit_receiving_steps.jsonl"
: > "$STEPS_JSONL"
cat > "$EVIDENCE_DIR/reports/unit_receiving_scope.txt" <<'EOF'
This evidence directory started from the transferred handoff package baseline scaffold.
The baseline scaffold is not unit-side validation by itself.
Unit receiving evidence begins with reports/handoff_package_verification.json and any package verification generated by this WSL2 script.
This script does not send ROS commands and does not let an LLM control ROS.
EOF
pass "baseline scaffold copied to $EVIDENCE_DIR"
record_pass "baseline scaffold copied without marking external proofs complete"

step "Verify handoff package" "reports/handoff_package_verification.json has ok=true and verification_context=receiving_machine from this WSL2 host."
mkdir -p "$HANDOFF_VERIFY_DIR"
run_json_command \
  "handoff package verification" \
  "$EVIDENCE_DIR/reports/handoff_package_verification.json" \
  "$LOG_DIR/handoff-package-verification.stderr.log" \
  "$PYTHON_BIN" "$REPO_ROOT/tools/verify_distributed_fleet_handoff_package.py" \
  "$HANDOFF_PACKAGE" \
  --work-dir "$HANDOFF_VERIFY_DIR" \
  --verification-context receiving_machine
"$PYTHON_BIN" - "$EVIDENCE_DIR/reports/handoff_package_verification.json" <<'PY' || fail "handoff package verification JSON did not pass receiving-machine checks"
import json
import sys
data = json.loads(open(sys.argv[1], encoding="utf-8").read())
assert data.get("ok") is True
assert data.get("verification_context") == "receiving_machine"
assert data.get("source_machine_id")
assert data.get("verifier_machine_id")
assert data.get("source_machine_id") != data.get("verifier_machine_id")
PY
pass "handoff package verified on receiving machine"
record_pass "handoff package verification report is receiving-machine proof for migration transfer only"

step "Verify optional artifact packages" "each supplied artifact package is checksum-staged by PowerShell, then verified/imported with verification_context=unit_workplace_receiving."
if [ "${#ARTIFACT_PACKAGES[@]}" -eq 0 ]; then
  pass "no artifact package supplied; artifact_package_verified_after_transfer remains missing"
  record_pass "artifact package step skipped without fabricating proof"
else
  mkdir -p "$ARTIFACT_VERIFY_DIR"
  import_args=(
    "$PYTHON_BIN" "$REPO_ROOT/tools/import_distributed_fleet_external_evidence.py"
    --evidence-dir "$EVIDENCE_DIR"
    --handoff-package-verification-report "$EVIDENCE_DIR/reports/handoff_package_verification.json"
  )
  for artifact in "${ARTIFACT_PACKAGES[@]}"; do
    import_args+=(--artifact-package "$artifact")
  done
  run_json_command \
    "artifact package import and verification" \
    "$EVIDENCE_DIR/reports/unit_receiving_external_import.json" \
    "$LOG_DIR/artifact-package-import.stderr.log" \
    "${import_args[@]}"
  if [ ! -f "$EVIDENCE_DIR/reports/artifact_package_verification.json" ]; then
    fail "artifact package verification report was not written"
  fi
  "$PYTHON_BIN" - "$EVIDENCE_DIR/reports/artifact_package_verification.json" <<'PY' || fail "artifact package verification report did not pass unit_workplace_receiving checks"
import json
import sys
data = json.loads(open(sys.argv[1], encoding="utf-8").read())
assert data.get("ok") is True
if data.get("schema") == "TaskPlanningArtifactPackageVerificationSet.v1":
    assert data.get("verification_context") == "unit_workplace_receiving"
    assert data.get("verifications")
    for item in data["verifications"]:
        assert item.get("verification_context") == "unit_workplace_receiving"
        assert item.get("source_machine_id")
        assert item.get("verifier_machine_id")
        assert item.get("source_machine_id") != item.get("verifier_machine_id")
else:
    assert data.get("verification_context") == "unit_workplace_receiving"
    assert data.get("source_machine_id") != data.get("verifier_machine_id")
PY
  pass "artifact package verification/import completed"
  record_pass "artifact packages verified as unit workplace receiving evidence"
fi

step "Check phase gate" "phase_gate.status remains waiting_for_external_proofs unless all real external proofs have actually been imported."
run_json_command \
  "phase gate check" \
  "$EVIDENCE_DIR/reports/unit_receiving_phase_gate_check.json" \
  "$LOG_DIR/phase-gate.stderr.log" \
  "$PYTHON_BIN" "$REPO_ROOT/tools/check_distributed_fleet_phase_gate.py" \
  --evidence-dir "$EVIDENCE_DIR" \
  --print-discovered-inputs
PHASE_STATUS="$("$PYTHON_BIN" - "$EVIDENCE_DIR/reports/unit_receiving_phase_gate_check.json" <<'PY'
import json
import sys
data = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(data["phase_gate"]["status"])
PY
)"
if [ "$PHASE_STATUS" != "waiting_for_external_proofs" ]; then
  fail "unexpected phase_gate.status=$PHASE_STATUS for this receiving kit; do not claim completion from this run"
fi
pass "phase_gate.status=$PHASE_STATUS"
record_pass "phase gate is still waiting for real external proofs"

step "Check goal evidence" "missing-only report lists unresolved external proofs; nonzero exit is expected while proofs remain missing."
set +e
"$PYTHON_BIN" "$REPO_ROOT/tools/check_distributed_fleet_goal_evidence.py" \
  --evidence-dir "$EVIDENCE_DIR" \
  --missing-only \
  --print-discovered-inputs \
  > "$EVIDENCE_DIR/reports/unit_receiving_goal_evidence_missing.json" \
  2> "$LOG_DIR/goal-evidence.stderr.log"
GOAL_RC=$?
if [ "$GOAL_RC" -eq 0 ]; then
  fail "goal evidence unexpectedly returned success; this kit should not complete all five external proofs"
fi
"$PYTHON_BIN" - "$EVIDENCE_DIR/reports/unit_receiving_goal_evidence_missing.json" <<'PY' || fail "goal evidence missing-only report did not contain unresolved required items"
import json
import sys
data = json.loads(open(sys.argv[1], encoding="utf-8").read())
assert data.get("ok") is False
items = data.get("items") or []
assert items
missing_names = {item.get("name") for item in items}
assert "home_5090_model_lab_evaluated" in missing_names or "unit_hardware_execution_artifact_verified" in missing_names
PY
pass "goal evidence still has missing required external proof; no proof was fabricated"
record_pass "goal evidence remained incomplete as expected"

step "Write receiving summary" "summary records paths and boundary decisions for the next agent."
export UNIT_RECEIVING_HANDOFF="$HANDOFF_PACKAGE"
export UNIT_RECEIVING_EVIDENCE_DIR="$EVIDENCE_DIR"
export UNIT_RECEIVING_LOG_DIR="$LOG_DIR"
export UNIT_RECEIVING_PHASE_STATUS="$PHASE_STATUS"
export UNIT_RECEIVING_GOAL_RC="$GOAL_RC"
export UNIT_RECEIVING_ARTIFACTS="$(printf '%s\n' "${ARTIFACT_PACKAGES[@]}")"
"$PYTHON_BIN" - "$EVIDENCE_DIR/reports/unit_receiving_summary.json" <<'PY'
import json
import os
import sys
summary = {
    "schema": "WindowsSafeUnitReceivingSummary.v1",
    "ok": True,
    "handoff_package": os.environ["UNIT_RECEIVING_HANDOFF"],
    "artifact_packages": [line for line in os.environ.get("UNIT_RECEIVING_ARTIFACTS", "").splitlines() if line],
    "evidence_dir": os.environ["UNIT_RECEIVING_EVIDENCE_DIR"],
    "log_dir": os.environ["UNIT_RECEIVING_LOG_DIR"],
    "phase_gate_status": os.environ["UNIT_RECEIVING_PHASE_STATUS"],
    "goal_evidence_exit_code": int(os.environ["UNIT_RECEIVING_GOAL_RC"]),
    "windows_native_scope": "PowerShell did receive/hash/path/WSL launch only",
    "wsl2_scope": "WSL2 verified packages and evidence without sending ROS commands",
    "not_proved_by_this_run": [
        "artifact_package_verified_after_transfer unless one or more artifact packages were supplied and verified here",
        "home_5090_model_lab_evaluated unless a real home report and matching package are separately imported",
        "unit_ros1_gateway_signatures_observed",
        "unit_hardware_execution_artifact_verified",
    ],
    "safety_boundary": "No LLM direct ROS control; no platform-local mission planning; no Mac/source verification treated as unit proof.",
}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(summary, fh, indent=2, sort_keys=True, ensure_ascii=False)
PY
cp "$EVIDENCE_DIR/reports/unit_receiving_summary.json" "$LOG_DIR/unit_receiving_summary.json"
pass "summary written to $EVIDENCE_DIR/reports/unit_receiving_summary.json and $LOG_DIR/unit_receiving_summary.json"
record_pass "receiving summary written"

echo
echo "FINAL PASS: Windows-safe unit receiving verification completed."
echo "EVIDENCE_DIR: $EVIDENCE_DIR"
echo "LOG_DIR: $LOG_DIR"
echo "PHASE_GATE_STATUS: $PHASE_STATUS"
echo "NOTE: This run did not fabricate missing home 5090, ROS1 signature, or hardware dispatch proof."
