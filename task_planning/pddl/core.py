from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from task_planning.contracts import MissionRequest


@dataclass(frozen=True)
class PddlProblem:
    mission_id: str
    pddl: str
    objects: Dict[str, List[str]]
    goals: List[str]
    metadata: Optional[Dict[str, Any]] = None
    schema: str = "PddlProblem.v1"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlanStep:
    index: int
    action: str
    arguments: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PddlPlan:
    mission_id: str
    steps: List[PlanStep]
    metadata: Optional[Dict[str, Any]] = None
    schema: str = "PddlPlan.v1"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "mission_id": self.mission_id,
            "steps": [step.as_dict() for step in self.steps],
            "metadata": dict(self.metadata or {}),
        }


def scout_and_confirm_domain() -> str:
    return """(define (domain scout-and-confirm)
  (:requirements :strips :typing)
  (:types robot uav ugv area target)
  (:predicates
    (available ?robot - robot)
    (is-uav ?robot - robot)
    (is-ugv ?robot - robot)
    (area-known ?area - area)
    (target-detected ?target - target)
    (target-confirmed ?target - target)
    (approached ?target - target)
    (can-scan ?uav - uav ?area - area)
    (can-confirm ?ugv - ugv ?target - target)
    (platform-safe ?robot - robot)
  )
  (:action scan-area
    :parameters (?uav - uav ?area - area)
    :precondition (and (available ?uav) (can-scan ?uav ?area) (platform-safe ?uav))
    :effect (target-detected target_01)
  )
  (:action confirm-target
    :parameters (?ugv - ugv ?target - target)
    :precondition (and (available ?ugv) (target-detected ?target) (can-confirm ?ugv ?target) (platform-safe ?ugv))
    :effect (target-confirmed ?target)
  )
  (:action identify-target
    :parameters (?ugv - ugv ?target - target)
    :precondition (and (available ?ugv) (can-confirm ?ugv ?target) (platform-safe ?ugv))
    :effect (target-detected ?target)
  )
  (:action approach-target
    :parameters (?ugv - ugv ?target - target)
    :precondition (and (available ?ugv) (target-detected ?target) (can-confirm ?ugv ?target) (platform-safe ?ugv))
    :effect (and (target-confirmed ?target) (approached ?target))
  )
  (:action relay-or-overwatch
    :parameters (?uav - uav ?target - target)
    :precondition (and (available ?uav) (target-confirmed ?target) (platform-safe ?uav))
    :effect (available ?uav)
  )
)"""


def generate_problem(request: MissionRequest) -> PddlProblem:
    area = request.areas[0]
    target = request.targets[0]
    objects = {
        "uav": ["uav_0"],
        "ugv": ["ugv_0"],
        "area": [area],
        "target": [target],
    }
    object_approach = request.constraints.get("mission_variant") == "single_ugv_object_approach"
    goals = [f"(approached {target})"] if object_approach else [f"(target-confirmed {target})"]
    pddl = f"""(define (problem {request.mission_id})
  (:domain scout-and-confirm)
  (:objects
    uav_0 - uav
    ugv_0 - ugv
    {area} - area
    {target} - target
  )
  (:init
    (available uav_0)
    (available ugv_0)
    (is-uav uav_0)
    (is-ugv ugv_0)
    (area-known {area})
    (can-scan uav_0 {area})
    (can-confirm ugv_0 {target})
    (platform-safe uav_0)
    (platform-safe ugv_0)
  )
  (:goal (and {goals[0]}))
)"""
    return PddlProblem(
        mission_id=request.mission_id,
        pddl=pddl,
        objects=objects,
        goals=goals,
        metadata=dict(request.constraints),
    )


def mock_plan(problem: PddlProblem) -> PddlPlan:
    area = problem.objects["area"][0]
    target = problem.objects["target"][0]
    if problem.goals == [f"(approached {target})"]:
        return PddlPlan(
            mission_id=problem.mission_id,
            steps=[
                PlanStep(index=1, action="identify-target", arguments=["ugv_0", target]),
                PlanStep(index=2, action="approach-target", arguments=["ugv_0", target]),
            ],
            metadata=dict(problem.metadata or {}),
        )
    return PddlPlan(
        mission_id=problem.mission_id,
        steps=[
            PlanStep(index=1, action="scan-area", arguments=["uav_0", area]),
            PlanStep(index=2, action="confirm-target", arguments=["ugv_0", target]),
            PlanStep(index=3, action="relay-or-overwatch", arguments=["uav_0", target]),
        ],
        metadata=dict(problem.metadata or {}),
    )
