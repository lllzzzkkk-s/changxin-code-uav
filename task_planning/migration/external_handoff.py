from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


@dataclass(frozen=True)
class ExternalEvidenceSlot:
    name: str
    lane: str
    purpose: str
    target_paths: List[str]
    constraints: List[str]
    commands: List[str]
    needed_now: bool

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ExternalEvidenceHandoff:
    evidence_dir: Path
    requirements_path: Path
    next_steps_path: Path
    slots: List[ExternalEvidenceSlot]
    missing_required: List[str]
    case_id: str
    schema: str = "DistributedFleetExternalEvidenceHandoff.v1"

    def as_dict(self) -> Dict[str, object]:
        return {
            "schema": self.schema,
            "evidence_dir": str(self.evidence_dir),
            "requirements_path": str(self.requirements_path),
            "next_steps_path": str(self.next_steps_path),
            "case_id": self.case_id,
            "missing_required": list(self.missing_required),
            "slots": [slot.as_dict() for slot in self.slots],
        }


def build_external_evidence_handoff(
    *,
    repo_root: Path,
    evidence_dir: Path,
    case_id: str = "uav_ugv_coordination",
    missing_required: Sequence[str] = (),
) -> ExternalEvidenceHandoff:
    repo_root = repo_root.resolve()
    evidence_dir = evidence_dir.expanduser().resolve()
    missing = _dedupe(missing_required)

    for rel_path in [
        "reports",
        "artifact_packages",
        "hardware_artifacts",
        "external_inputs/home_model_lab",
        "external_inputs/migration_bundle",
        "external_inputs/unit_ros1",
        "external_inputs/unit_hardware",
    ]:
        (evidence_dir / rel_path).mkdir(parents=True, exist_ok=True)

    slots = _external_slots(case_id=case_id, missing_required=set(missing))
    handoff = ExternalEvidenceHandoff(
        evidence_dir=evidence_dir,
        requirements_path=evidence_dir / "reports" / "external_evidence_requirements.json",
        next_steps_path=evidence_dir / "NEXT_EXTERNAL_EVIDENCE.md",
        slots=slots,
        missing_required=missing,
        case_id=case_id,
    )

    data = handoff.as_dict()
    data["repo_root"] = str(repo_root)
    handoff.requirements_path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    handoff.next_steps_path.write_text(
        _handoff_markdown(case_id=case_id, evidence_dir=evidence_dir, missing_required=missing, slots=slots),
        encoding="utf-8",
    )
    return handoff


def _external_slots(*, case_id: str, missing_required: Iterable[str]) -> List[ExternalEvidenceSlot]:
    missing = set(missing_required)
    return [
        ExternalEvidenceSlot(
            name="migration_bundle_verified_after_transfer",
            lane="receiving_machine",
            purpose="Prove the migration archive or handoff package was verified after transfer, not only on the source machine.",
            target_paths=[
                "reports/migration_verification.json",
                "reports/handoff_package_verification.json",
            ],
            constraints=[
                "Run on the receiving machine after the bundle is copied there with verification_context=receiving_machine.",
                "If receiving a distributed fleet handoff package, verify that package and its embedded migration bundle.",
                "Do not treat source-machine verification as transfer evidence.",
                "Verification reports must include verifier-produced archive/extract_dir paths, checked file counts, manifest or embedded migration manifest audit fields, and empty verifier error lists; a bare ok=true JSON is not transfer proof.",
            ],
            commands=[
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_migration_bundle.py <bundle.tar.gz> --work-dir /tmp/changxin-migration-verify --verification-context receiving_machine > <evidence-dir>/reports/migration_verification.json",
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_distributed_fleet_handoff_package.py <distributed-fleet-handoff-package.tar.gz> --work-dir /tmp/changxin-handoff-verify --verification-context receiving_machine > <evidence-dir>/reports/handoff_package_verification.json",
            ],
            needed_now="migration_bundle_verified_after_transfer" in missing,
        ),
        ExternalEvidenceSlot(
            name="home_5090_model_lab_evaluated",
            lane="home_model_lab",
            purpose="Evaluate the home 5090 local HTTP model as a schema compiler only.",
            target_paths=[
                "reports/model_lab_evaluation.json",
                "artifact_packages/*.tar.gz",
            ],
            constraints=[
                "MISSION_PROFILE=home_model_lab",
                "MODEL_PROVIDER=local_http",
                "PLATFORM_BACKEND=mock",
                "MODEL_LAB_EVIDENCE_KIND=home_5090_live",
                f"The evaluation report case_id must be {case_id} and must match reports/lane_matrix.json.",
                "The evaluation report must include machine_id and an accelerator_probe showing RTX 5090 from nvidia-smi.",
                "The evaluation report must include baseline_equivalent, diffs, and empty validation_errors so the mock/golden baseline comparison is machine-readable.",
                "Package the full model-lab artifact directory, not only model_lab_evaluation.json.",
                "The matching artifact package must contain a model_lab_evaluation artifact whose case_id and metadata match the evaluation report.",
                "The matching artifact package must be verified through reports/artifact_package_verification.json with verification_context=unit_workplace_receiving; a source-machine package check is not enough to bind home_5090_model_lab_evaluated.",
                "No ROS gateway, no hardware dispatch, no direct model-to-ROS control.",
            ],
            commands=[
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_model_lab_endpoint.py --profile profiles/home_model_lab.env",
                f"PYTHONDONTWRITEBYTECODE=1 python3 tools/evaluate_model_lab_case.py --profile profiles/home_model_lab.env --case {case_id} --output-dir /tmp/changxin-model-lab",
                f"cp /tmp/changxin-model-lab/{case_id}/model_lab_evaluation.json <evidence-dir>/reports/model_lab_evaluation.json",
                f"PYTHONDONTWRITEBYTECODE=1 python3 tools/package_task_planning_artifacts.py --artifact /tmp/changxin-model-lab/{case_id} --output-dir <evidence-dir>/artifact_packages",
            ],
            needed_now="home_5090_model_lab_evaluated" in missing,
        ),
        ExternalEvidenceSlot(
            name="artifact_package_verified_after_transfer",
            lane="unit_workplace_receiving",
            purpose="Prove a transferred model-lab or server artifact package is intact before any work-hardware use.",
            target_paths=[
                "artifact_packages/*.tar.gz",
                "reports/artifact_package_verification.json",
            ],
            constraints=[
                "Package artifacts before transfer.",
                "Verify packages on the receiving unit/workplace machine before prevalidated replay or ROS1 gateway preparation.",
                "The verification report must include source_machine_id and verifier_machine_id, and those ids must differ.",
                f"Every verified artifact-level case_id must be {case_id} and must match reports/lane_matrix.json.",
                "For home_model_lab proof, the verified model_lab_evaluation artifact metadata must match reports/model_lab_evaluation.json fields: mission_profile, model_provider, platform_backend, model_lab_evidence_kind, and machine_id.",
                "Artifact package verification reports must include archive/extract_dir/package_root, checked_files > 0, manifest_errors=[], artifact_validations, and unit_workplace_receiving source/verifier machine ids.",
                "Import pre-produced unit/workplace package verification reports with --artifact-package-verification-report so the receiving-machine verifier identity is preserved.",
            ],
            commands=[
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_task_planning_artifacts.py <evidence-dir>/artifact_packages/<package>.tar.gz --work-dir <evidence-dir>/_artifact_package_verify --verification-context unit_workplace_receiving > <evidence-dir>/reports/artifact_package_verification.json",
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/import_distributed_fleet_external_evidence.py --evidence-dir <evidence-dir> --artifact-package <artifact-package.tar.gz> --artifact-package-verification-report <artifact_package_verification.json>",
                f"PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile profiles/work_hardware.env --artifact-package <evidence-dir>/artifact_packages/<package>.tar.gz --artifact-work-dir <evidence-dir>/_artifact_package_verify --require-artifact-package --case {case_id}",
            ],
            needed_now="artifact_package_verified_after_transfer" in missing,
        ),
        ExternalEvidenceSlot(
            name="unit_ros1_gateway_signatures_observed",
            lane="unit_workplace_ros1",
            purpose="Prove real ROS1 gateway service names and TaskCommandJson request signatures are visible.",
            target_paths=["reports/site_acceptance_work_hardware_ros1.json"],
            constraints=[
                "Use a local profile copied from profiles/work_hardware_ros1_gateway.env.template with real ROS_MASTER_URI and ROS_IP.",
                "Read-only ROS observations first.",
                "Verify rosservice type ends with TaskCommandJson.",
                "Verify rosservice args include task_command_json.",
                "The site acceptance report must include machine_id so the ROS1 signature proof is tied to the collecting unit/workplace machine.",
                "Direct site acceptance collection should report rosservice_audit.command_environment_source=profile; file replay should report captured_files.",
                "Do not send control commands during signature collection.",
            ],
            commands=[
                "cp profiles/work_hardware_ros1_gateway.env.template <local-work-hardware-ros1-gateway.env>  # fill real ROS_MASTER_URI and ROS_IP locally",
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile <local-work-hardware-ros1-gateway.env> --platform-id uav_0 --platform-id ugv_0 --run-rosservice-list --run-service-signatures --require-rosservice-audit --require-service-signatures > <evidence-dir>/reports/site_acceptance_work_hardware_ros1.json",
                "Optional archive copy: rosservice list/type/args can still be teed to /tmp/changxin-rosservice-*.txt for operator records.",
            ],
            needed_now="unit_ros1_gateway_signatures_observed" in missing,
        ),
        ExternalEvidenceSlot(
            name="unit_hardware_execution_artifact_verified",
            lane="unit_workplace_hardware",
            purpose="Prove a real unit/work hardware run produced a valid work_hardware ros1_gateway artifact bundle.",
            target_paths=["hardware_artifacts/<run_id>/"],
            constraints=[
                "Requires explicit local operator approval before movement.",
                "The final artifact must preserve operator_approved=true in machine-readable evidence.",
                "The final artifact must preserve operator_approval_source=local_unit_operator and machine_id from the execution endpoint.",
                "Use validated TaskCommand, PDDL/BT, platform gateway, and local safety gates.",
                "Requires a successful /gateway/dispatch ROS1 service trace, not dry_run-only evidence.",
                "Requires accepted CommandAck and TaskProgress artifacts from the execution endpoint.",
                "Requires execution_context=unit_workplace_hardware and CommandAck/TaskProgress matching the dispatch mission/task/platform.",
                "Requires validation_report.schema=ValidationReport.v1, current_state=HARDWARE_DISPATCH_RECORDED, and errors=[] in the final artifact.",
                "Requires validation_report.source_validation_report.schema=ValidationReport.v1, current_state=OPERATOR_APPROVAL, and errors=[] from the pre-dispatch artifact.",
                f"Requires mission_input.run_input.case_id={case_id} matching reports/lane_matrix.json.",
                "The home 5090 endpoint must not be required for this lane.",
            ],
            commands=[
                "After operator approval and constrained real gateway dispatch, copy the produced mission artifact root into <evidence-dir>/hardware_artifacts/<run_id>/",
                "Prefer assembling the proof artifact with: PYTHONDONTWRITEBYTECODE=1 python3 tools/record_unit_hardware_dispatch_artifact.py --source-artifact <prevalidated_artifact_root> --profile <local-work-hardware-ros1-gateway.env> --output-dir <evidence-dir>/hardware_artifacts --platform-id <platform_id> --task-id <task_id> --dispatch-service /fleet/<platform_id>/gateway/dispatch --dispatch-stdout-file /tmp/changxin-dispatch-response.txt --task-progress-file /tmp/changxin-task-progress.json --operator-approved",
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir <evidence-dir>",
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir <evidence-dir> --missing-only --print-discovered-inputs",
            ],
            needed_now="unit_hardware_execution_artifact_verified" in missing,
        ),
    ]


def _handoff_markdown(
    *,
    case_id: str,
    evidence_dir: Path,
    missing_required: Sequence[str],
    slots: Sequence[ExternalEvidenceSlot],
) -> str:
    missing_lines = [f"- `{name}`" for name in missing_required] or ["- none in the supplied goal report"]
    slot_sections: List[str] = []
    for slot in slots:
        marker = "needed now" if slot.needed_now else "keep slot ready"
        slot_sections.extend([
            f"## {slot.name}",
            "",
            f"Lane: `{slot.lane}` ({marker})",
            "",
            slot.purpose,
            "",
            "Targets:",
            "",
            *[f"- `{path}`" for path in slot.target_paths],
            "",
            "Constraints:",
            "",
            *[f"- {constraint}" for constraint in slot.constraints],
            "",
            "Commands:",
            "",
            "```bash",
            *slot.commands,
            "```",
            "",
        ])

    return "\n".join([
        "# Next External Evidence",
        "",
        f"Evidence directory: `{evidence_dir}`",
        f"Case: `{case_id}`",
        "",
        "This file is a handoff scaffold. It creates directories and target names for external proof, but it does not claim that the home 5090 model lab, transferred bundle, unit ROS1 gateway, or real hardware run has happened.",
        "",
        "The home 5090 lane must keep `PLATFORM_BACKEND=mock`. The unit/workplace hardware lane must be able to run from mock or prevalidated schemas when the home server is offline.",
        "",
        "Standard directory contract:",
        "",
        "- `reports/model_lab_evaluation.json`",
        "- `reports/migration_verification.json`",
        "- `reports/handoff_package_verification.json`",
        "- `reports/site_acceptance_work_hardware_ros1.json`",
        "- `artifact_packages/*.tar.gz`",
        "- `hardware_artifacts/<run_id>/`",
        "",
        "Missing required items from the current goal report:",
        "",
        *missing_lines,
        "",
        "After external reports or packages are copied into the standard paths, rerun:",
        "",
        f"All external proof for this handoff must stay on case `{case_id}`. A bare `ok=true` JSON is not proof; migration, handoff, and artifact-package proof must come from the verifier tools with manifest/checksum fields and receiving-machine source/verifier machine ids. `home_5090_model_lab_evaluated` requires both `reports/model_lab_evaluation.json` and a `unit_workplace_receiving`-verified model-lab artifact package whose model_lab_evaluation artifact has the same case_id and matching metadata. `tools/record_unit_hardware_dispatch_artifact.py` can assemble the unit/workplace dispatch response, accepted ack, local operator approval, execution endpoint machine id, and task progress capture into the standard artifact contract without sending ROS commands. `tools/import_distributed_fleet_external_evidence.py` then validates JSON report schemas, requires ROS1 signature reports to come from `PLATFORM_BACKEND=ros1_gateway`, verifies artifact package manifests/checksums/source-vs-verifier machine ids, rejects model-lab reports and artifact packages whose `case_id` does not match `reports/lane_matrix.json`, and rejects hardware artifacts that are not real `work_hardware` + `ros1_gateway` dispatch artifacts with `operator_approved=true`, `operator_approval_source=local_unit_operator`, `machine_id`, `execution_context=unit_workplace_hardware`, same-case mission input, `validation_report.schema=ValidationReport.v1`, `validation_report.current_state=HARDWARE_DISPATCH_RECORDED`, `validation_report.errors=[]`, source validation still tied to `ValidationReport.v1` and `OPERATOR_APPROVAL`, accepted ack, and task progress matching the dispatch mission/task/platform before copying evidence into the standard directory.",
        "",
        "```bash",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/import_distributed_fleet_external_evidence.py --evidence-dir <evidence-dir> --model-lab-evaluation <model_lab_evaluation.json> --migration-verification-report <migration_verification.json> --handoff-package-verification-report <handoff_package_verification.json> --artifact-package-verification-report <artifact_package_verification.json> --site-acceptance-ros1-report <site_acceptance_work_hardware_ros1.json> --artifact-package <artifact-package.tar.gz> --hardware-run-artifact <hardware-run-artifact-root>",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir <evidence-dir>",
        "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_distributed_fleet_goal_evidence.py --evidence-dir <evidence-dir> --missing-only --print-discovered-inputs",
        "```",
        "",
        *slot_sections,
    ])


def _dedupe(items: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
