# Windows-Safe Unit Receiving Kit

Date: 2026-05-29

## Purpose

This kit gives the unit RTX 4060 Windows Codex session one PowerShell entry point for receiving the distributed-fleet handoff package and optional artifact packages. Windows PowerShell only performs file intake, SHA256 checks, path checks, and WSL2 startup. All repository Python verification runs in WSL2 bash.

This kit does not prove unit ROS1 gateway signatures or real hardware execution by itself. It must not treat a home Mac/source-machine check as unit receiving proof.

## Boundary

- Windows native PowerShell:
  - receives archive paths
  - verifies operator-supplied SHA256 values
  - stages files under `C:\changxin-evidence\logs\incoming`
  - writes logs under `C:\changxin-evidence\logs`
  - starts WSL2
- Windows native PowerShell does not:
  - run ROS
  - run repository Python verifiers
  - import external proof files
  - call an LLM
- WSL2 bash:
  - verifies the distributed fleet handoff package with `verification_context=receiving_machine`
  - optionally verifies artifact packages with `verification_context=unit_workplace_receiving`
  - checks phase gate
  - checks goal evidence missing items
  - writes `/tmp/changxin-distributed-fleet-evidence`

The mission architecture remains:

```text
center PDDL -> task-level BT/state machine -> platform gateway -> local ROS1
```

No model is deployed to UAV/UGV platforms, and no LLM may directly publish ROS topics, call ROS services, or output `/mavros/*`, `/cmd_vel`, or `/setpoints_cmd`.

## One PowerShell Entry

Run this from a Windows checkout of `changxin-code` on the unit RTX 4060 machine:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\tools\windows_unit_receiving_entry.ps1 `
  -HandoffPackage C:\incoming\distributed-fleet-handoff-package.tar.gz `
  -HandoffSha256 <64-char-sha256> `
  -ArtifactPackage C:\incoming\task-planning-artifacts.tar.gz `
  -ArtifactSha256 <64-char-sha256>
```

If no artifact package has arrived yet, omit `-ArtifactPackage` and `-ArtifactSha256`. The artifact proof remains missing; that is a valid receiving state and not a failure of the handoff intake.

Use `-WslDistro <name>` only when the unit Windows machine has more than one WSL distribution and the default is not the intended Ubuntu/ROS1 environment.

## Output Locations

- Windows logs: `C:\changxin-evidence\logs`
- Windows staged input archives: `C:\changxin-evidence\logs\incoming`
- WSL2 evidence directory: `/tmp/changxin-distributed-fleet-evidence`
- Main receiving summary:
  - `/tmp/changxin-distributed-fleet-evidence/reports/unit_receiving_summary.json`
  - `C:\changxin-evidence\logs\unit_receiving_summary.json`

## Steps, Expected Output, Pass/Fail

| Step | Expected output | Pass condition | Fail condition |
| --- | --- | --- | --- |
| Windows intake scope | `PASS: No Windows-native ROS commands or repository Python commands are run by this script.` | PowerShell reaches archive path checks. | The script tries to run ROS, Python verifier, or another complex repo command on Windows. |
| Check input archives | `PASS: validated N archive path(s)` | Every supplied path exists and ends with `.tar.gz`. | Missing path, directory path, or non-`.tar.gz` path. |
| Verify SHA256 | `PASS: all supplied archive hashes matched` | `Get-FileHash -Algorithm SHA256` matches every supplied hash. | Any hash mismatch. |
| Stage files for WSL2 | `PASS: staged handoff package and N artifact package(s)` | Files are copied under `C:\changxin-evidence\logs\incoming`. | Staging path cannot be created or copied. |
| Start WSL2 verifier | `PASS: WSL2 verifier completed` | `wsl.exe` starts and `tools/unit_receiving_wsl2.sh` exits 0. | WSL2 missing, wrong distro, or Linux verifier fails. |
| WSL2 boundary | `PASS: WSL2-like kernel detected` or `PASS: Linux shell detected` | Verification is running in Linux/WSL2, not Windows native. | Script cannot start Linux verifier. |
| Extract handoff baseline evidence | `PASS: baseline scaffold copied to /tmp/changxin-distributed-fleet-evidence` | Handoff contains `evidence/`; it is copied as a scaffold only. | Handoff archive is malformed. |
| Verify handoff package | `PASS: handoff package verified on receiving machine` | `reports/handoff_package_verification.json` has `ok=true`, `verification_context=receiving_machine`, and different source/verifier machine ids. | Same-machine proof, checksum failure, schema failure, or package mismatch. |
| Verify optional artifact packages | `PASS: artifact package verification/import completed` or `PASS: no artifact package supplied; artifact_package_verified_after_transfer remains missing` | Supplied artifact packages verify with `verification_context=unit_workplace_receiving`; if none are supplied, no artifact proof is fabricated. | Invalid package, same-machine artifact verification, missing lane-matrix case match, or checksum/schema failure. |
| Check phase gate | `PASS: phase_gate.status=waiting_for_external_proofs` | Phase gate remains `waiting_for_external_proofs` for this receiving kit run. | `local_implementation_required`, `external_evidence_rejected`, or unexpected completion claim. |
| Check goal evidence | `PASS: goal evidence still has missing required external proof; no proof was fabricated` | Missing-only report lists unresolved required items. | Goal evidence unexpectedly returns complete from this kit alone. |
| Write receiving summary | `PASS: summary written ...` | Summary JSON is written in both WSL evidence and Windows logs. | Summary cannot be written. |

## What This Kit Can Prove

- The handoff package was verified after transfer on the unit receiving side.
- Optional artifact packages were verified after transfer on the unit receiving side, if supplied.
- The current phase gate and missing goal evidence were checked from WSL2.

## What This Kit Does Not Prove

- It does not prove home RTX 5090 model-lab evaluation unless a real `home_5090_live` report and matching verified model-lab artifact package are separately imported.
- It does not prove unit ROS1 gateway signatures.
- It does not prove real hardware execution.
- It does not turn Mac/source-machine baseline evidence into unit receiving proof.
- It does not let an LLM control ROS.

## Follow-On Work In WSL2/ROS1

After this kit completes, the unit-side agent can continue from `/tmp/changxin-distributed-fleet-evidence`:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py \
  --evidence-dir /tmp/changxin-distributed-fleet-evidence \
  --missing-only \
  --print-discovered-inputs
```

For ROS1 gateway signatures, use the existing unit execution runbook and a local `ros1_gateway` profile. That later stage is still read-only until the operator explicitly approves a real dispatch.
