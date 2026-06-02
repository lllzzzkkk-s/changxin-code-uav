from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from task_planning.config import EnvironmentProfile


GATE_SEQUENCE = [
    "read_only_observation",
    "mock_gateway_dispatch",
    "bench_dry_run_no_motion",
    "constrained_real_gateway_command",
    "controlled_mission_dry_run",
    "failure_injection_recovery",
]
REAL_GATEWAY_START_STAGE = "bench_dry_run_no_motion"


@dataclass(frozen=True)
class HardwareGateStep:
    stage: str
    purpose: str
    requires_profile: str
    requires_operator_approval: bool
    allowed_backend: List[str]
    command_templates: List[str]
    pass_criteria: List[str]
    forbidden: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HardwareGatePlan:
    profile: Dict[str, Any]
    requested_stage: str
    steps: List[HardwareGateStep]
    validation_errors: List[str]
    schema: str = "HardwareGatePlan.v1"

    @property
    def ok(self) -> bool:
        return not self.validation_errors

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "requested_stage": self.requested_stage,
            "profile": dict(self.profile),
            "validation_errors": list(self.validation_errors),
            "steps": [step.as_dict() for step in self.steps],
        }


def build_hardware_gate_plan(profile: EnvironmentProfile, *, through_stage: str = "read_only_observation") -> HardwareGatePlan:
    errors: List[str] = []
    if profile.mission_profile != "work_hardware":
        errors.append("hardware gates require MISSION_PROFILE=work_hardware")
    if through_stage not in GATE_SEQUENCE:
        errors.append(f"unsupported hardware gate stage: {through_stage}")
        selected_stages: List[str] = []
    else:
        selected_stages = GATE_SEQUENCE[:GATE_SEQUENCE.index(through_stage) + 1]
    if profile.model_provider not in {"mock", "remote_http"}:
        errors.append("work hardware gates cannot require a local large model")
    if profile.platform_backend == "ros1_gateway" and not profile.hardware_approval_required:
        errors.append("real ROS1 gateway stages require HARDWARE_APPROVAL_REQUIRED=true")
    if (
        selected_stages
        and GATE_SEQUENCE.index(selected_stages[-1]) >= GATE_SEQUENCE.index(REAL_GATEWAY_START_STAGE)
        and profile.platform_backend != "ros1_gateway"
    ):
        errors.append("bench dry-run and later hardware gates require PLATFORM_BACKEND=ros1_gateway profile")

    steps = [_step_for_stage(stage) for stage in selected_stages]
    return HardwareGatePlan(
        profile=profile.as_dict(),
        requested_stage=through_stage,
        steps=steps,
        validation_errors=errors,
    )


def _step_for_stage(stage: str) -> HardwareGateStep:
    if stage == "read_only_observation":
        return HardwareGateStep(
            stage=stage,
            purpose="Confirm the work laptop can see the intended ROS1 environment without publishing commands.",
            requires_profile="work_hardware",
            requires_operator_approval=False,
            allowed_backend=["mock", "ros1_gateway"],
            command_templates=[
                "echo \"$ROS_MASTER_URI\"",
                "echo \"$ROS_IP\"",
                "rostopic list",
                "rostopic echo -n 1 /fleet/<platform_id>/heartbeat",
                "rostopic echo -n 1 /fleet/<platform_id>/state",
            ],
            pass_criteria=[
                "ROS_MASTER_URI and ROS_IP identify the intended platform gateway environment.",
                "Heartbeat or state can be observed without publishing.",
                "No task command, setpoint, velocity, shell, or raw ROS control message is sent.",
            ],
            forbidden=_forbidden_controls(),
        )
    if stage == "mock_gateway_dispatch":
        return HardwareGateStep(
            stage=stage,
            purpose="Run validated BT task commands through the mock gateway before any real gateway dispatch.",
            requires_profile="work_hardware",
            requires_operator_approval=True,
            allowed_backend=["mock"],
            command_templates=[
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile profiles/work_hardware.env --case uav_ugv_coordination",
            ],
            pass_criteria=[
                "The run stops at operator approval or dry-run boundary.",
                "gateway_trace.json records publish_attempted=false for every command.",
                "All TaskCommand entries are capability-level commands.",
            ],
            forbidden=_forbidden_controls(),
        )
    if stage == "bench_dry_run_no_motion":
        return HardwareGateStep(
            stage=stage,
            purpose="Exercise the real gateway in no-motion bench mode before any platform movement.",
            requires_profile="work_hardware",
            requires_operator_approval=True,
            allowed_backend=["ros1_gateway"],
            command_templates=[
                "python3 tools/plan_work_hardware_gate.py --profile <local-work-hardware-ros1-gateway.env> --through-stage bench_dry_run_no_motion",
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/extract_task_command_from_artifact.py <artifact_bundle_path> --platform-id <platform_id> --format rosservice-yaml > /tmp/changxin-task-command.yaml",
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/check_task_planning_site_acceptance.py --profile <local-work-hardware-ros1-gateway.env> --platform-id <platform_id> --run-rosservice-list --run-service-signatures --require-rosservice-audit --require-service-signatures",
                "confirm rosservice_audit.command_environment_source=profile in the site acceptance report",
                "optional archive copy: rosservice list/type/args can still be teed to /tmp/changxin-rosservice-*.txt for operator records",
                "rosservice call /fleet/<platform_id>/gateway/dry_run \"$(cat /tmp/changxin-task-command.yaml)\"",
            ],
            pass_criteria=[
                "The real gateway accepts or rejects the validated TaskCommand without movement.",
                "Site acceptance verified TaskCommandJson service type and task_command_json request args using the selected local ROS1 profile.",
                "Local safety gate result is returned as CommandAck.v1.",
                "No raw ROS topic is accepted from the center.",
            ],
            forbidden=_forbidden_controls(),
        )
    if stage == "constrained_real_gateway_command":
        return HardwareGateStep(
            stage=stage,
            purpose="Send one constrained capability-level command after bench dry-run success.",
            requires_profile="work_hardware",
            requires_operator_approval=True,
            allowed_backend=["ros1_gateway"],
            command_templates=[
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/extract_task_command_from_artifact.py <artifact_bundle_path> --platform-id <platform_id> --format rosservice-yaml > /tmp/changxin-task-command.yaml",
                "rosservice call /fleet/<platform_id>/gateway/dispatch \"$(cat /tmp/changxin-task-command.yaml)\"",
            ],
            pass_criteria=[
                "The platform executes only the approved capability-level command.",
                "CommandAck.v1 and TaskProgress.v1 are captured.",
                "The platform remains inside the test envelope and local safety gate can stop or reject.",
            ],
            forbidden=_forbidden_controls(),
        )
    if stage == "controlled_mission_dry_run":
        return HardwareGateStep(
            stage=stage,
            purpose="Run a controlled mission with validated artifacts and manual approval before movement.",
            requires_profile="work_hardware",
            requires_operator_approval=True,
            allowed_backend=["ros1_gateway"],
            command_templates=[
                "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile <local-work-hardware-ros1-gateway.env> --case uav_ugv_coordination",
                "rosservice call /fleet/mission/dispatch_validated_artifact '{artifact_root: <artifact_bundle_path>}'",
            ],
            pass_criteria=[
                "The mission artifact was generated before dispatch and passed validation.",
                "Every dispatch is represented by TaskCommand.v1, CommandAck.v1, and TaskProgress.v1.",
                "The model is not required locally on the work laptop.",
            ],
            forbidden=_forbidden_controls(),
        )
    return HardwareGateStep(
        stage=stage,
        purpose="Inject a controlled failure and verify central replan from FailureReport.",
        requires_profile="work_hardware",
        requires_operator_approval=True,
        allowed_backend=["ros1_gateway"],
        command_templates=[
            "rosservice call /fleet/<platform_id>/gateway/inject_failure '{failure_type: path_blocked, recoverable: true}'",
            "PYTHONDONTWRITEBYTECODE=1 python3 tools/run_task_planning_golden.py --profile <local-work-hardware-ros1-gateway.env> --case failure_and_replan",
        ],
        pass_criteria=[
            "FailureReport.v1 is generated and captured.",
            "The center requests replan instead of allowing platform-local mission expansion.",
            "The platform can hold, stop, or return according to the existing BT subtree policy.",
        ],
        forbidden=_forbidden_controls(),
    )


def _forbidden_controls() -> List[str]:
    return [
        "Do not publish /mavros/* from the center.",
        "Do not publish /cmd_vel from the center.",
        "Do not publish /setpoints_cmd from the center.",
        "Do not send arbitrary shell commands through a gateway.",
        "Do not let the platform generate a new mission or PDDL plan locally.",
        "Do not require a local large model on the work 4060 laptop.",
    ]
