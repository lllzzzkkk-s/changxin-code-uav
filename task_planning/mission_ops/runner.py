from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from platform_gateway.mock_gateway import MockPlatformGateway
from platform_gateway.ros1_service_gateway import Ros1ServiceGateway
from task_planning.config import EnvironmentProfile
from task_planning.contracts import CapabilityRegistry
from task_planning.mission_ops.artifacts import write_artifact_bundle
from task_planning.mission_ops.http_model_client import OpenAICompatibleModelClient
from task_planning.mission_ops.mission_manager import MissionManager
from task_planning.mission_ops.mock_llm_client import MockLLMClient
from task_planning.mission_ops.model_client import ModelClient
from task_planning.mission_ops.run_ledger import (
    JsonMissionRunLedger,
    MissionRunEvent,
    MissionRunRecord,
    OperatorApprovalState,
)
from task_planning.mission_ops.state import MissionOpsState
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore


@dataclass(frozen=True)
class MissionOpsResult:
    run_id: str
    status: str
    state: MissionOpsState
    artifact_bundle_path: Optional[str] = None


class MissionOpsRunner:
    def run(self, run_input: Mapping[str, Any], config: Mapping[str, Any]) -> MissionOpsResult:
        raise NotImplementedError

    def resume(self, run_id: str, run_input: Mapping[str, Any]) -> MissionOpsResult:
        raise NotImplementedError

    def get_state(self, run_id: str) -> MissionOpsState:
        raise NotImplementedError


class MissionManagerRunner(MissionOpsRunner):
    def __init__(
        self,
        *,
        state_store: JsonMissionOpsStateStore,
        model_client: Optional[ModelClient] = None,
        gateway: Optional[MockPlatformGateway] = None,
        registry: Optional[CapabilityRegistry] = None,
    ) -> None:
        self._explicit_model_client = model_client is not None
        self._explicit_gateway = gateway is not None
        self._run_profiles = {}
        self._run_inputs = {}
        self._run_gateway_traces = {}
        self.manager = MissionManager(
            state_store=state_store,
            model_client=model_client or MockLLMClient(),
            gateway=gateway,
            registry=registry,
        )

    def run(self, run_input: Mapping[str, Any], config: Mapping[str, Any]) -> MissionOpsResult:
        profile = self._profile_from_config(config)
        manager_config = dict(config)
        if profile is not None:
            self._configure_model_client(profile)
            self._configure_platform_gateway(profile)
            if profile.mission_profile == "work_hardware" and profile.hardware_approval_required:
                manager_config["require_operator_approval"] = True
        trace_start = len(self.manager.gateway.dispatch_log)
        state = self.manager.start(run_input, manager_config)
        gateway_trace = self.manager.gateway.dispatch_log[trace_start:]
        if state.error:
            status = "failed"
        elif state.current_state == "OPERATOR_APPROVAL":
            status = "approval_required"
        elif state.current_state == "DISPATCH_OR_HOLD":
            status = "dry_run_complete"
        else:
            status = "running"
        artifact_path = self._write_artifacts_if_configured(state, profile, run_input, gateway_trace)
        if profile is not None:
            self._run_profiles[state.run_id] = profile
            self._run_inputs[state.run_id] = dict(run_input)
            self._run_gateway_traces[state.run_id] = list(gateway_trace)
        return MissionOpsResult(run_id=state.run_id, status=status, state=state, artifact_bundle_path=artifact_path)

    def resume(self, run_id: str, run_input: Mapping[str, Any]) -> MissionOpsResult:
        state = self.manager.resume(run_id, run_input)
        if state.current_state == "REQUEST_REPLAN" and not state.error:
            status = "replan_requested"
        elif state.error:
            status = "failed"
        else:
            status = "running"
        profile = self._run_profiles.get(run_id)
        original_input = self._run_inputs.get(run_id, dict(run_input))
        gateway_trace = self._run_gateway_traces.get(run_id, [])
        artifact_path = self._write_artifacts_if_configured(state, profile, original_input, gateway_trace)
        return MissionOpsResult(run_id=state.run_id, status=status, state=state, artifact_bundle_path=artifact_path)

    def get_state(self, run_id: str) -> MissionOpsState:
        return self.manager.get_state(run_id)

    def _profile_from_config(self, config: Mapping[str, Any]) -> Optional[EnvironmentProfile]:
        if "MISSION_PROFILE" not in config and "mission_profile" not in config:
            return None
        return EnvironmentProfile.from_mapping(config)

    def _configure_model_client(self, profile: EnvironmentProfile) -> None:
        if self._explicit_model_client:
            return
        if profile.model_provider == "mock":
            self.manager.model_client = MockLLMClient()
            return
        self.manager.model_client = OpenAICompatibleModelClient.from_profile(profile)

    def _validate_runtime_backend(self, profile: EnvironmentProfile) -> None:
        if profile.platform_backend == "ros1_gateway" and isinstance(self.manager.gateway, MockPlatformGateway):
            raise ValueError("PLATFORM_BACKEND=ros1_gateway requires a non-mock gateway implementation")

    def _configure_platform_gateway(self, profile: EnvironmentProfile) -> None:
        if profile.platform_backend != "ros1_gateway":
            return
        if self._explicit_gateway:
            self._validate_runtime_backend(profile)
            return
        self.manager.gateway = Ros1ServiceGateway.from_profile(profile, registry=self.manager.registry)

    def _write_artifacts_if_configured(
        self,
        state: MissionOpsState,
        profile: Optional[EnvironmentProfile],
        run_input: Mapping[str, Any],
        gateway_trace: Any,
    ) -> Optional[str]:
        if profile is None or not profile.mission_artifact_root:
            return None
        bundle = write_artifact_bundle(
            state=state,
            profile=profile,
            run_input=run_input,
            gateway_trace=gateway_trace,
        )
        self._write_ledger_record(state=state, profile=profile, run_input=run_input, artifact_path=str(bundle.root))
        return str(bundle.root)

    def _write_ledger_record(
        self,
        *,
        state: MissionOpsState,
        profile: EnvironmentProfile,
        run_input: Mapping[str, Any],
        artifact_path: str,
    ) -> None:
        ledger = JsonMissionRunLedger(Path(artifact_path).parent / "_ledger")
        record = MissionRunRecord(
            run_id=state.run_id,
            case_id=str(run_input.get("case_id", "")),
            mission_id=state.mission_id,
            profile=profile.mission_profile,
            model_provider=profile.model_provider,
            platform_backend=profile.platform_backend,
            phase_baseline="next_phase_ready",
            artifact_bundle_path=artifact_path,
            current_state=state.current_state,
            operator_approval=OperatorApprovalState.from_dict(state.approval_state),
            events=[MissionRunEvent.from_dict(event) for event in state.output_artifact_refs.get("execution_events") or []],
        )
        ledger.save(record)
