from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping, Protocol, Union

from task_planning.contracts import FailureReport, TaskSchema


@dataclass(frozen=True)
class NeedsClarification:
    question: str
    reason: str
    schema: str = "NeedsClarification.v1"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReplanAdvice:
    mode: str
    reason: str
    recommended_actions: list = field(default_factory=list)
    schema: str = "ReplanAdvice.v1"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ModelClient(Protocol):
    """Runtime-neutral model boundary for mock and future local LLM backends."""

    def compile_task_schema(
        self,
        intent: str,
        context_snapshot: Mapping[str, Any],
    ) -> Union[TaskSchema, NeedsClarification]:
        ...

    def triage_failure(
        self,
        failure_report: FailureReport,
        blackboard_snapshot: Mapping[str, Any],
    ) -> ReplanAdvice:
        ...

    def explain_validator_error(
        self,
        error: str,
        schema: Mapping[str, Any],
        context_snapshot: Mapping[str, Any],
    ) -> Dict[str, Any]:
        ...
