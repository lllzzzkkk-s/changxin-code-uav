from __future__ import annotations

import uuid
from typing import Any, Dict, Mapping, Optional

from platform_gateway.mock_gateway import MockPlatformGateway
from task_planning.contracts import CapabilityRegistry, FailureReport
from task_planning.execution import BehaviorTreeRuntime, MissionRunEvent
from task_planning.mission_ops.mock_llm_client import MockLLMClient
from task_planning.mission_ops.model_client import ModelClient
from task_planning.mission_ops.run_ledger import OperatorApprovalState
from task_planning.mission_ops.state import MissionOpsState
from task_planning.mission_ops.state_store import JsonMissionOpsStateStore
from task_planning.mission_ops.tools import (
    compile_plan_to_bt_tool,
    compile_task_schema_tool,
    generate_pddl_problem_tool,
    request_replan_tool,
    run_pddl_planner_tool,
    triage_failure_tool,
    update_blackboard_tool,
    validate_pddl_problem_tool,
    validate_plan_tool,
    validate_task_schema_tool,
)


class MissionManager:
    def __init__(
        self,
        *,
        state_store: JsonMissionOpsStateStore,
        model_client: Optional[ModelClient] = None,
        gateway: Optional[MockPlatformGateway] = None,
        registry: Optional[CapabilityRegistry] = None,
    ) -> None:
        self.state_store = state_store
        self.model_client = model_client or MockLLMClient()
        self.registry = registry or CapabilityRegistry.scout_and_confirm_default()
        self.gateway = gateway or MockPlatformGateway(self.registry)

    def start(self, run_input: Mapping[str, Any], config: Mapping[str, Any]) -> MissionOpsState:
        run_id = str(uuid.uuid4())
        intent = str(run_input.get("intent", ""))
        state = MissionOpsState(
            run_id=run_id,
            mission_id="",
            current_state="DRAFT_INTENT",
            input_artifact_refs={"intent": intent, "config": dict(config)},
            approval_state=OperatorApprovalState.not_required().as_dict(),
        )
        self._save(state)

        context_snapshot = dict(run_input.get("context_snapshot") or {})
        state = self._transition(state, "RETRIEVE_CONTEXT", output_update={"context_snapshot": context_snapshot})
        state = self._transition(state, "CALL_MODEL_CLIENT_FOR_TASK_SCHEMA")
        task_schema = compile_task_schema_tool(self.model_client, intent, context_snapshot)
        outputs = self._outputs(state, task_schema=task_schema.as_dict())

        state = self._transition(
            state,
            "VALIDATE_TASK_SCHEMA",
            mission_id=task_schema.mission_request.mission_id,
            outputs=outputs,
        )
        errors = validate_task_schema_tool(task_schema, self.registry)
        if errors:
            return self._transition(state, "NEEDS_CLARIFICATION", outputs=self._outputs(state, validation_errors=errors), approval_required=True, error=errors[0])

        blackboard = update_blackboard_tool(task_schema, self.registry)
        state = self._transition(state, "UPDATE_BLACKBOARD", outputs=self._outputs(state, blackboard=blackboard.as_dict()))

        problem = generate_pddl_problem_tool(task_schema)
        state = self._transition(state, "GENERATE_PDDL_PROBLEM", outputs=self._outputs(state, pddl_problem=problem.as_dict()))
        problem_errors = validate_pddl_problem_tool(problem)
        if problem_errors:
            return self._transition(state, "VALIDATE_PROBLEM", error=problem_errors[0])
        state = self._transition(state, "VALIDATE_PROBLEM")

        plan = run_pddl_planner_tool(problem)
        state = self._transition(state, "RUN_PDDL_PLANNER", outputs=self._outputs(state, plan=plan.as_dict()))
        plan_errors = validate_plan_tool(plan, self.registry)
        if plan_errors:
            return self._transition(state, "VALIDATE_PLAN", error=plan_errors[0])
        state = self._transition(state, "VALIDATE_PLAN")

        behavior_tree = compile_plan_to_bt_tool(plan, task_schema.mission_request.mission_id)
        state = self._transition(state, "COMPILE_PLAN_TO_BT", outputs=self._outputs(state, behavior_tree=behavior_tree.as_dict()))

        require_approval = bool(config.get("require_operator_approval", False))
        if require_approval:
            approval_state = OperatorApprovalState.required_unapproved(
                mission_id=task_schema.mission_request.mission_id,
            ).as_dict()
            event = MissionRunEvent(
                run_id=state.run_id,
                mission_id=task_schema.mission_request.mission_id,
                event_type="operator_approval_required",
                payload=approval_state,
            ).as_dict()
            return self._transition(
                state,
                "OPERATOR_APPROVAL",
                outputs=self._outputs(state, execution_events=[event]),
                approval_required=True,
                approval_state=approval_state,
                execution_event_refs={"count": 1},
            )

        state = self._transition(state, "DRY_RUN_GATEWAY")
        runtime_result = BehaviorTreeRuntime(gateway=self.gateway).run(behavior_tree, run_id=state.run_id)
        runtime_outputs = {
            "gateway_acks": [ack.as_dict() for ack in runtime_result.command_acks],
            "task_progress": [progress.as_dict() for progress in runtime_result.task_progress],
            "execution_events": [event.as_dict() for event in runtime_result.events],
        }
        if runtime_result.failure_report is not None:
            runtime_outputs["failure_report"] = runtime_result.failure_report.as_dict()
            runtime_outputs["replan_request"] = {
                "schema": "ReplanRequest.v1",
                "mode": "central_replan",
                "failure_type": runtime_result.failure_report.failure_type,
                "task_id": runtime_result.failure_report.task_id,
                "platform_id": runtime_result.failure_report.platform_id,
                "reason": runtime_result.failure_report.reason,
            }
        state = self._transition(state, "DRY_RUN_GATEWAY", outputs=self._outputs(state, **runtime_outputs))
        if runtime_result.failure_report is not None:
            return self._transition(
                state,
                "DISPATCH_OR_HOLD",
                approval_required=False,
                execution_event_refs={"count": len(runtime_result.events)},
                error=runtime_result.failure_report.reason,
            )
        return self._transition(
            state,
            "DISPATCH_OR_HOLD",
            approval_required=False,
            approval_state=OperatorApprovalState.not_required().as_dict(),
            execution_event_refs={"count": len(runtime_result.events)},
        )

    def resume(self, run_id: str, run_input: Mapping[str, Any]) -> MissionOpsState:
        state = self.state_store.load(run_id)
        if "failure_report" in run_input:
            failure = FailureReport.from_dict(run_input["failure_report"])
            state = self._transition(state, "TRIAGE_FAILURE", outputs=self._outputs(state, failure_report=failure.as_dict()))
            blackboard = state.output_artifact_refs.get("blackboard") or {}
            advice = triage_failure_tool(self.model_client, failure, blackboard)
            replan_request = request_replan_tool(advice, failure)
            execution_events = list(state.output_artifact_refs.get("execution_events") or [])
            execution_events.extend([
                MissionRunEvent(
                    run_id=state.run_id,
                    mission_id=failure.mission_id,
                    event_type="failure_report_recorded",
                    task_id=failure.task_id,
                    platform_id=failure.platform_id,
                    payload=failure.as_dict(),
                ).as_dict(),
                MissionRunEvent(
                    run_id=state.run_id,
                    mission_id=failure.mission_id,
                    event_type="central_replan_requested",
                    task_id=failure.task_id,
                    platform_id=failure.platform_id,
                    payload=replan_request,
                ).as_dict(),
            ])
            return self._transition(
                state,
                "REQUEST_REPLAN",
                outputs=self._outputs(
                    state,
                    failure_triage=advice.as_dict(),
                    replan_request=replan_request,
                    execution_events=execution_events,
                ),
                approval_required=True,
                execution_event_refs={"count": len(execution_events)},
            )
        return self._transition(state, state.current_state, error="unsupported resume input")

    def get_state(self, run_id: str) -> MissionOpsState:
        return self.state_store.load(run_id)

    def _transition(
        self,
        state: MissionOpsState,
        current_state: str,
        *,
        mission_id: Optional[str] = None,
        outputs: Optional[Dict[str, Any]] = None,
        output_update: Optional[Dict[str, Any]] = None,
        approval_required: Optional[bool] = None,
        approval_state: Optional[Dict[str, Any]] = None,
        execution_event_refs: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> MissionOpsState:
        merged_outputs = state.output_artifact_refs
        if outputs is not None:
            merged_outputs = outputs
        if output_update is not None:
            merged_outputs = self._outputs(state, **output_update)
        next_state = state.transition(
            current_state,
            mission_id=mission_id,
            output_artifact_refs=merged_outputs,
            approval_required=approval_required,
            approval_state=approval_state,
            execution_event_refs=execution_event_refs,
            error=error,
        )
        self._save(next_state)
        return next_state

    def _outputs(self, state: MissionOpsState, **updates: Any) -> Dict[str, Any]:
        outputs = dict(state.output_artifact_refs)
        outputs.update(updates)
        return outputs

    def _save(self, state: MissionOpsState) -> None:
        self.state_store.save(state)
