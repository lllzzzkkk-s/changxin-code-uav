from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from task_planning.migration.machine_identity import resolve_hashed_machine_id


MIGRATION_FILE_PATTERNS = (
    "AGENTS.md",
    "docs/superpowers/specs/2026-05-19-fleet-pddl-bt-architecture.md",
    "docs/superpowers/specs/2026-05-19-pddl-bt-execution-model.md",
    "docs/superpowers/specs/2026-05-19-platform-gateway-contract.md",
    "docs/superpowers/specs/2026-05-25-local-llm-mission-ops-architecture.md",
    "docs/superpowers/specs/2026-05-26-distributed-fleet-testing-migration-architecture.md",
    "docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md",
    "docs/superpowers/specs/2026-05-29-windows-safe-unit-receiving-kit.md",
    "docs/superpowers/specs/2026-06-02-distributed-fleet-phase-2-to-langgraph-roadmap.md",
    "docs/superpowers/specs/2026-06-02-phase-2-proof-to-operations-plan.md",
    "docs/superpowers/specs/2026-06-03-ugv-phase-2a-mac-to-4060-handoff.md",
    "docs/superpowers/plans/2026-06-03-phase-2b-no-hardware-operations-reporting.md",
    "docs/superpowers/specs/2026-06-03-phase-2b-operator-view-signals.md",
    "profiles/*.env",
    "profiles/*.env.template",
    "task_planning/**/*.py",
    "platform_gateway/**/*.py",
    "platform_gateway/ros/**/*.md",
    "platform_gateway/ros/**/*.srv",
    "platform_gateway/ros/catkin_pkg/**/CMakeLists.txt",
    "platform_gateway/ros/catkin_pkg/**/package.xml",
    "tests/task_planning/*.py",
    "tools/audit_ros1_gateway_services.py",
    "tools/check_model_lab_endpoint.py",
    "tools/check_distributed_fleet_phase_gate.py",
    "tools/check_distributed_fleet_goal_evidence.py",
    "tools/check_phase2_no_motion_acceptance.py",
    "tools/check_task_planning_readiness.py",
    "tools/check_task_planning_site_acceptance.py",
    "tools/collect_distributed_fleet_evidence.py",
    "tools/init_external_evidence_handoff.py",
    "tools/import_distributed_fleet_external_evidence.py",
    "tools/package_distributed_fleet_handoff.py",
    "tools/run_mock_model_lab_endpoint.py",
    "tools/run_dev_mock_golden_suite.py",
    "tools/evaluate_model_lab_case.py",
    "tools/extract_task_command_from_artifact.py",
    "tools/package_task_planning_artifacts.py",
    "tools/package_task_planning_migration.py",
    "tools/plan_work_hardware_gate.py",
    "tools/prepare_ros1_gateway_workspace.py",
    "tools/platform_gateway_service_core.py",
    "tools/record_unit_hardware_dispatch_artifact.py",
    "tools/replay_task_planning_artifact.py",
    "tools/run_ros1_platform_gateway_node.py",
    "tools/run_prevalidated_task_schema.py",
    "tools/run_task_planning_lane_matrix.py",
    "tools/run_task_planning_golden.py",
    "tools/verify_task_planning_migration_bundle.py",
    "tools/verify_distributed_fleet_handoff_package.py",
    "tools/verify_task_planning_artifacts.py",
    "tools/unit_receiving_wsl2.sh",
    "tools/windows_unit_receiving_entry.ps1",
)

EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", "runs"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".xlsx", ".docx", ".tar", ".gz", ".zip"}


@dataclass(frozen=True)
class MigrationBundle:
    root: Path
    archive: Path
    manifest: Path
    file_count: int

    def as_dict(self) -> Dict[str, object]:
        return {
            "schema": "MigrationBundle.v1",
            "root": str(self.root),
            "archive": str(self.archive),
            "manifest": str(self.manifest),
            "file_count": self.file_count,
        }


def build_migration_bundle(
    *,
    repo_root: Path,
    output_dir: Path,
    bundle_name: str = "task-planning-migration-bundle",
    source_machine_id: Optional[str] = None,
) -> MigrationBundle:
    repo_root = repo_root.resolve()
    resolved_source_machine_id = resolve_hashed_machine_id(source_machine_id, "source_machine_id")
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_root = output_dir / bundle_name
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True)

    rel_files = _collect_files(repo_root, MIGRATION_FILE_PATTERNS)
    for rel_path in rel_files:
        source = repo_root / rel_path
        target = bundle_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    migration_doc = _migration_doc(rel_files)
    (bundle_root / "MIGRATION.md").write_text(migration_doc, encoding="utf-8")
    rel_files = ["MIGRATION.md"] + rel_files

    manifest_data = _manifest(
        bundle_name=bundle_name,
        bundle_root=bundle_root,
        rel_files=rel_files,
        source_machine_id=resolved_source_machine_id,
    )
    manifest_path = bundle_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2, sort_keys=True), encoding="utf-8")

    archive_path = output_dir / f"{bundle_name}.tar.gz"
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(bundle_root, arcname=bundle_name)

    return MigrationBundle(
        root=bundle_root,
        archive=archive_path,
        manifest=manifest_path,
        file_count=len(rel_files) + 1,
    )


def _collect_files(repo_root: Path, patterns: Sequence[str]) -> List[str]:
    files = set()
    for pattern in patterns:
        for path in repo_root.glob(pattern):
            if path.is_file() and _include_file(path.relative_to(repo_root)):
                files.add(path.relative_to(repo_root).as_posix())
    missing = [
        pattern
        for pattern in patterns
        if not any(repo_root.glob(pattern)) and "*" not in pattern
    ]
    if missing:
        raise FileNotFoundError(f"missing migration inputs: {missing}")
    return sorted(files)


def _include_file(rel_path: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in rel_path.parts):
        return False
    if rel_path.suffix in EXCLUDED_SUFFIXES:
        return False
    return True


def _manifest(
    *,
    bundle_name: str,
    bundle_root: Path,
    rel_files: Iterable[str],
    source_machine_id: str,
) -> Dict[str, object]:
    files = []
    for rel_path in rel_files:
        path = bundle_root / rel_path
        files.append({
            "path": rel_path,
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        })
    return {
        "schema": "TaskPlanningMigrationManifest.v1",
        "bundle_name": bundle_name,
        "source_machine_id": source_machine_id,
        "files": files,
        "commands": {
            "dev_mock": "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile profiles/dev_mock.env --case uav_ugv_coordination",
            "dev_mock_golden_suite": "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_dev_mock_golden_suite.py --artifact-root /tmp/changxin-dev-mock-golden-suite",
            "replay": "PYTHONDONTWRITEBYTECODE=1 python3 tools/replay_task_planning_artifact.py <artifact_root>",
            "server_sim": "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile profiles/server_sim.env --case uav_ugv_coordination",
            "lane_matrix": "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_lane_matrix.py --artifact-root /tmp/changxin-lane-matrix --case uav_ugv_coordination",
            "audit_ros1_gateway_services": "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile <local-work-hardware-ros1-gateway.env> --platform-id uav_0 --run-rosservice-list --run-service-signatures --require-rosservice-audit --require-service-signatures",
            "prepare_ros1_gateway_workspace": "PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py --catkin-src <catkin_ws>/src",
            "work_hardware_gate": "PYTHONDONTWRITEBYTECODE=1 python3 tools/plan_work_hardware_gate.py --profile profiles/work_hardware.env --through-stage mock_gateway_dispatch",
            "model_lab": "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_model_lab_endpoint.py --profile profiles/home_model_lab.env",
            "mock_model_lab_endpoint": "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_mock_model_lab_endpoint.py --port 8000",
            "mock_model_lab_check": "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_model_lab_endpoint.py --profile profiles/home_model_lab_mock_endpoint.env",
            "model_lab_evaluation": "PYTHONDONTWRITEBYTECODE=1 python3 tools/evaluate_model_lab_case.py --profile profiles/home_model_lab.env --case uav_ugv_coordination --output-dir /tmp/changxin-model-lab",
            "package_artifacts": "PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_artifacts.py --artifact /tmp/changxin-model-lab/uav_ugv_coordination --output-dir /tmp/changxin-artifact-packages",
            "extract_task_command": "PYTHONDONTWRITEBYTECODE=1 python3 tools/extract_task_command_from_artifact.py <artifact_bundle_path> --platform-id <platform_id> --format rosservice-yaml",
            "record_unit_hardware_dispatch_artifact": "PYTHONDONTWRITEBYTECODE=1 python3 tools/record_unit_hardware_dispatch_artifact.py --source-artifact <prevalidated_artifact_root> --profile <local-work-hardware-ros1-gateway.env> --output-dir <evidence-dir>/hardware_artifacts --platform-id <platform_id> --task-id <task_id> --dispatch-service /fleet/<platform_id>/gateway/dispatch --dispatch-stdout-file /tmp/changxin-dispatch-response.txt --task-progress-file /tmp/changxin-task-progress.json --operator-approved",
            "verify_artifacts": "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py <artifact-package.tar.gz> --work-dir /tmp/changxin-artifact-verify --verification-context unit_workplace_receiving > <artifact_package_verification.json>",
            "prevalidated_schema_replay": "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_prevalidated_task_schema.py --profile profiles/work_hardware.env --task-schema /tmp/changxin-model-lab/uav_ugv_coordination/model_task_schema.json --case uav_ugv_coordination --artifact-root /tmp/changxin-prevalidated-runs",
            "phase2_no_motion_acceptance": "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_phase2_no_motion_acceptance.py --artifact-root <artifact_root> --phase1-archive-path 'D:\\changxin\\final-archives\\changxin-distributed-fleet-final-proof-20260602.tar.gz' --phase1-archive-sha256 66465e2a1377e9f2dd11dc4136db9b92fa5d6e369f9f1c06c4a8a4c0ca850366 --output-dir /tmp/changxin-phase2b-no-motion-acceptance",
            "readiness": "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_readiness.py --profile profiles/work_hardware.env",
            "site_acceptance": "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile profiles/work_hardware.env",
            "phase_gate": "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_phase_gate.py --evidence-dir /tmp/changxin-distributed-fleet-evidence --print-discovered-inputs",
            "goal_evidence": "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence",
            "goal_evidence_missing_only": "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence --missing-only --print-discovered-inputs",
            "collect_evidence": "PYTHONDONTWRITEBYTECODE=1 python3 tools/collect_distributed_fleet_evidence.py --output-dir /tmp/changxin-distributed-fleet-evidence",
            "external_evidence_handoff": "PYTHONDONTWRITEBYTECODE=1 python3 tools/init_external_evidence_handoff.py --evidence-dir /tmp/changxin-distributed-fleet-evidence",
            "import_external_evidence": "PYTHONDONTWRITEBYTECODE=1 python3 tools/import_distributed_fleet_external_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence --model-lab-evaluation <model_lab_evaluation.json> --migration-verification-report <migration_verification.json> --handoff-package-verification-report <handoff_package_verification.json> --artifact-package-verification-report <artifact_package_verification.json> --site-acceptance-ros1-report <site_acceptance_work_hardware_ros1.json> --artifact-package <artifact-package.tar.gz> --hardware-run-artifact <hardware-run-artifact-root>",
            "handoff_package": "PYTHONDONTWRITEBYTECODE=1 python3 tools/package_distributed_fleet_handoff.py --output-dir /tmp/changxin-handoff-package",
            "verify_handoff_package_on_source": "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_distributed_fleet_handoff_package.py <distributed-fleet-handoff-package.tar.gz> --work-dir /tmp/changxin-handoff-verify --verification-context source_machine",
            "verify_handoff_package_after_transfer": "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_distributed_fleet_handoff_package.py <distributed-fleet-handoff-package.tar.gz> --work-dir /tmp/changxin-handoff-verify --verification-context receiving_machine",
            "verify_handoff_package": "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_distributed_fleet_handoff_package.py <distributed-fleet-handoff-package.tar.gz> --work-dir /tmp/changxin-handoff-verify --verification-context receiving_machine",
            "verify_bundle": "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_migration_bundle.py <bundle.tar.gz> --work-dir /tmp/changxin-migration-verify --verification-context receiving_machine",
            "windows_unit_receiving": r"powershell -ExecutionPolicy Bypass -File .\tools\windows_unit_receiving_entry.ps1 -HandoffPackage C:\incoming\distributed-fleet-handoff-package.tar.gz -HandoffSha256 <64-char-sha256> -ArtifactPackage C:\incoming\task-planning-artifacts.tar.gz -ArtifactSha256 <64-char-sha256>",
        },
    }


def _migration_doc(rel_files: Sequence[str]) -> str:
    return "\n".join([
        "# Task Planning Migration Bundle",
        "",
        "This bundle contains the mock-first distributed fleet testing slice for changxin-code.",
        "",
        "## Execution Boundary",
        "",
        "- The unit/workplace platform is the hardware execution endpoint.",
        "- The home RTX 5090 server is only a model-capability lab and must keep `PLATFORM_BACKEND=mock`.",
        "- `profiles/home_model_lab_mock_endpoint.env` and `tools/run_mock_model_lab_endpoint.py` test HTTP plumbing only; they are not `home_5090_live` evidence.",
        "- The work laptop can run phase-1 checks without a local large model by using `MockLLMClient`, artifacts, and the staged `work_hardware` gates.",
        "- On the unit/workplace machine, start from `docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md`.",
        "- On the unit RTX 4060 Windows machine, use `tools/windows_unit_receiving_entry.ps1` as the Windows-safe entry point; PowerShell only receives files, checks hashes, and starts WSL2.",
        "",
        "## First Checks",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_readiness.py --profile profiles/dev_mock.env",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile profiles/dev_mock.env",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/collect_distributed_fleet_evidence.py --output-dir /tmp/changxin-distributed-fleet-evidence",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/init_external_evidence_handoff.py --evidence-dir /tmp/changxin-distributed-fleet-evidence",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/package_distributed_fleet_handoff.py --output-dir /tmp/changxin-handoff-package",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_distributed_fleet_handoff_package.py /path/to/distributed-fleet-handoff-package.tar.gz --work-dir /tmp/changxin-handoff-verify --verification-context source_machine",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/import_distributed_fleet_external_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence --model-lab-evaluation <model_lab_evaluation.json> --handoff-package-verification-report <handoff_package_verification.json> --artifact-package <artifact-package.tar.gz> --artifact-package-verification-report <artifact_package_verification.json>",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_phase_gate.py --evidence-dir /tmp/changxin-distributed-fleet-evidence --print-discovered-inputs",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence --missing-only --print-discovered-inputs",
        "PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests/task_planning",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile profiles/dev_mock.env --case uav_ugv_coordination",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_dev_mock_golden_suite.py --artifact-root /tmp/changxin-dev-mock-golden-suite",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_lane_matrix.py --artifact-root /tmp/changxin-lane-matrix --case uav_ugv_coordination",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_phase2_no_motion_acceptance.py --artifact-root <artifact_root> --phase1-archive-path 'D:\\changxin\\final-archives\\changxin-distributed-fleet-final-proof-20260602.tar.gz' --phase1-archive-sha256 66465e2a1377e9f2dd11dc4136db9b92fa5d6e369f9f1c06c4a8a4c0ca850366 --output-dir /tmp/changxin-phase2b-no-motion-acceptance",
        "```",
        "",
        "If this bundle was received as a `.tar.gz`, verify the archive first from a changxin-code checkout or from another copy of this tool:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_migration_bundle.py /path/to/task-planning-migration-bundle.tar.gz --work-dir /tmp/changxin-migration-verify --verification-context receiving_machine",
        "```",
        "",
        "## Windows-Safe Unit Receiving",
        "",
        "On the unit RTX 4060 Windows machine, do not run ROS or repository Python in native PowerShell. Use PowerShell only for intake, hash checks, path checks, and starting WSL2:",
        "",
        "```powershell",
        r"Set-ExecutionPolicy -Scope Process Bypass -Force",
        r".\tools\windows_unit_receiving_entry.ps1 `",
        r"  -HandoffPackage C:\incoming\distributed-fleet-handoff-package.tar.gz `",
        r"  -HandoffSha256 <64-char-sha256> `",
        r"  -ArtifactPackage C:\incoming\task-planning-artifacts.tar.gz `",
        r"  -ArtifactSha256 <64-char-sha256>",
        "```",
        "",
        "This writes Windows logs to `C:\\changxin-evidence\\logs` and WSL2 evidence to `/tmp/changxin-distributed-fleet-evidence`. The WSL2 script verifies the handoff package, optional artifact packages, phase gate, and goal evidence. It must leave `phase_gate.status=waiting_for_external_proofs` unless real external proofs have actually been imported; the receiving kit alone must not fabricate home 5090, unit ROS1 signature, or hardware dispatch evidence.",
        "",
        "## Unit/Workplace First Gate",
        "",
        "On the unit/workplace machine, start with a no-ROS-write gate plan and mock gateway run:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_readiness.py --profile profiles/work_hardware.env",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile profiles/work_hardware.env",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/plan_work_hardware_gate.py --profile profiles/work_hardware.env --through-stage mock_gateway_dispatch",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile profiles/work_hardware.env --case uav_ugv_coordination",
        "```",
        "",
        "Only after those pass should the local operator source the actual ROS1 workspace, confirm `ROS_MASTER_URI` and `ROS_IP`, and move to the read-only ROS observations listed by the hardware gate plan.",
        "",
        "Prepare the ROS1 service package in the unit/workplace catkin workspace with a dry-run first:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py --catkin-src ~/catkin_ws/src",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/prepare_ros1_gateway_workspace.py --catkin-src ~/catkin_ws/src --apply",
        "```",
        "",
        "Copy `profiles/work_hardware_ros1_gateway.env.template` to a local profile and fill in the real `ROS_MASTER_URI` and `ROS_IP` only after the catkin workspace is sourced and the service symbol imports.",
        "",
        "Audit gateway service names with read-only ROS commands before any service call:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile <local-work-hardware-ros1-gateway.env> --platform-id uav_0 --platform-id ugv_0 --run-rosservice-list --run-service-signatures --require-rosservice-audit --require-service-signatures",
        "# Optional archive copy: rosservice list/type/args can still be teed to /tmp/changxin-rosservice-*.txt for operator records.",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/extract_task_command_from_artifact.py <artifact_bundle_path> --platform-id uav_0 --format rosservice-yaml > /tmp/changxin-task-command.yaml",
        "# After explicit local operator approval and a real dispatch capture, assemble the final proof artifact:",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/record_unit_hardware_dispatch_artifact.py --source-artifact <prevalidated_artifact_root> --profile <local-work-hardware-ros1-gateway.env> --output-dir <evidence-dir>/hardware_artifacts --platform-id uav_0 --task-id <task_id> --dispatch-service /fleet/uav_0/gateway/dispatch --dispatch-stdout-file /tmp/changxin-dispatch-response.txt --task-progress-file /tmp/changxin-task-progress.json --operator-approved",
        "```",
        "",
        "The home 5090 lane is never in the hardware execution path. Copy its artifacts to the unit/workplace lane for validation and comparison; do not make the robot execution path depend on the home server being online.",
        "",
        "To test the OpenAI-compatible HTTP integration before the real 5090 endpoint exists, run the mock endpoint in one shell and use the mock profile in another. Reports from this profile use `MODEL_LAB_EVIDENCE_KIND=mock_endpoint` and must not be imported as real `home_5090_live` proof:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_mock_model_lab_endpoint.py --port 8000",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_model_lab_endpoint.py --profile profiles/home_model_lab_mock_endpoint.env",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/evaluate_model_lab_case.py --profile profiles/home_model_lab_mock_endpoint.env --case uav_ugv_coordination --output-dir /tmp/changxin-model-lab-mock",
        "```",
        "",
        "The standard evidence directory also contains `NEXT_EXTERNAL_EVIDENCE.md` and `reports/external_evidence_requirements.json`. These are handoff scaffolds for another agent or machine; they define target paths such as `reports/model_lab_evaluation.json`, `artifact_packages/*.tar.gz`, `reports/site_acceptance_work_hardware_ros1.json`, and `hardware_artifacts/<run_id>/` without pretending those external proofs already exist.",
        "",
        "To send the whole current slice to another agent or machine, build one handoff package containing the migration bundle, the local baseline evidence directory, and `NEXT_EXTERNAL_EVIDENCE.md`:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/package_distributed_fleet_handoff.py --output-dir /tmp/changxin-handoff-package",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_distributed_fleet_handoff_package.py /path/to/distributed-fleet-handoff-package.tar.gz --work-dir /tmp/changxin-handoff-verify --verification-context source_machine",
        "```",
        "",
        "When external proof files arrive from the home 5090, another server, or the unit/workplace machine, import them into the standard evidence directory instead of hand-copying names:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/import_distributed_fleet_external_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence --model-lab-evaluation <model_lab_evaluation.json> --migration-verification-report <migration_verification.json> --handoff-package-verification-report <handoff_package_verification.json> --artifact-package-verification-report <artifact_package_verification.json> --site-acceptance-ros1-report <site_acceptance_work_hardware_ros1.json> --artifact-package <artifact-package.tar.gz> --hardware-run-artifact <hardware-run-artifact-root>",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir /tmp/changxin-distributed-fleet-evidence --missing-only --print-discovered-inputs",
        "```",
        "",
        "Package transferred evidence before it leaves the home/server lane, then verify it on the unit/workplace receiving side:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_artifacts.py --artifact /tmp/changxin-model-lab/uav_ugv_coordination --output-dir /tmp/changxin-artifact-packages",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py /path/to/task-planning-artifacts.tar.gz --work-dir /tmp/changxin-artifact-verify --verification-context unit_workplace_receiving",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile profiles/work_hardware.env --artifact-package /path/to/task-planning-artifacts.tar.gz --artifact-work-dir /tmp/changxin-artifact-verify --require-artifact-package --case uav_ugv_coordination",
        "```",
        "",
        "## Lanes",
        "",
        "- `dev_mock`: required baseline; no model and no hardware.",
        "- `home_model_lab`: model capability only; must keep platform backend mock.",
        "- `server_sim`: replay and compare artifacts.",
        "- `work_hardware`: unit/workplace lane; starts with gate planning and ROS1 gateway dry-run.",
        "",
        "The `dev_mock` golden suite covers single UGV inspection, UAV reconnaissance, UAV/UGV coordination, failure and replan, and disconnect-continuation cases. It is the first local proof that the deterministic phase-1 path works before model-lab or hardware evidence is added.",
        "",
        "## Home Model-Lab Evaluation",
        "",
        "When the home 5090 OpenAI-compatible endpoint is available, evaluate it without hardware dispatch:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_model_lab_endpoint.py --profile profiles/home_model_lab.env",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/evaluate_model_lab_case.py --profile profiles/home_model_lab.env --case uav_ugv_coordination --output-dir /tmp/changxin-model-lab",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_artifacts.py --artifact /tmp/changxin-model-lab/uav_ugv_coordination --output-dir /tmp/changxin-artifact-packages",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_prevalidated_task_schema.py --profile profiles/work_hardware.env --task-schema /tmp/changxin-model-lab/uav_ugv_coordination/model_task_schema.json --case uav_ugv_coordination --artifact-root /tmp/changxin-prevalidated-runs",
        "```",
        "",
        "The evaluator writes portable JSON artifacts and compares the model-generated `MissionRequest` against the mock baseline. Differences are evidence for review, not permission to bypass validators, PDDL, BT, or platform gateways.",
        "",
        "Replay a validated model-lab schema on the unit/workplace lane with no model call:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_prevalidated_task_schema.py --profile profiles/work_hardware.env --task-schema /tmp/changxin-model-lab/uav_ugv_coordination/model_task_schema.json --case uav_ugv_coordination --artifact-root /tmp/changxin-prevalidated-runs",
        "```",
        "",
        "On the unit/workplace lane, collect the current acceptance evidence before moving from mock/pre-dispatch to ROS1 gateway work:",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile profiles/work_hardware.env",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile <local-work-hardware-ros1-gateway.env> --platform-id uav_0 --platform-id ugv_0 --run-rosservice-list --run-service-signatures --require-rosservice-audit --require-service-signatures",
        "```",
        "",
        "## ROS1 Gateway Package",
        "",
        "Copy or symlink `platform_gateway/ros/catkin_pkg/platform_gateway_msgs` into the unit/workplace catkin workspace, then run `catkin_make` and start `tools/run_ros1_platform_gateway_node.py` with the generated service symbol.",
        "",
        "## Included Files",
        "",
        *[f"- `{path}`" for path in rel_files],
        "",
    ])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
