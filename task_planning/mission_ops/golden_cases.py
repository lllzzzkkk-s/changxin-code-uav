from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from task_planning.contracts import FailureReport


@dataclass(frozen=True)
class GoldenMissionCase:
    case_id: str
    description: str
    intent: str
    context_snapshot: Dict[str, Any] = field(default_factory=dict)
    resume_failure_report: Optional[FailureReport] = None

    def run_input(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "context_snapshot": dict(self.context_snapshot),
            "case_id": self.case_id,
        }


def golden_mission_cases() -> List[GoldenMissionCase]:
    return [
        GoldenMissionCase(
            case_id="single_ugv_inspection",
            description="UGV-side confirmation path with the model boundary still producing a validated scout-and-confirm schema.",
            intent="让无人车去 A 区边缘做目标确认，必要时无人机只提供观察辅助",
            context_snapshot={"mission_id": "golden_single_ugv_inspection", "primary_platform": "ugv_0"},
        ),
        GoldenMissionCase(
            case_id="single_ugv_object_approach",
            description="Single UGV object identification and bounded approach pipeline from operator intent to TaskCommand.",
            intent="让小车识别附近的充电桩，然后走过去",
            context_snapshot={
                "mission_id": "golden_single_ugv_object_approach",
                "primary_platform": "ugv_0",
            },
        ),
        GoldenMissionCase(
            case_id="uav_reconnaissance",
            description="UAV reconnaissance first, with ground confirmation still compiled through PDDL and BT.",
            intent="无人机先搜索 A 区，发现目标后保持观察",
            context_snapshot={"mission_id": "golden_uav_reconnaissance", "primary_platform": "uav_0"},
        ),
        GoldenMissionCase(
            case_id="uav_ugv_coordination",
            description="One UAV plus one UGV coordination baseline for scout and confirm.",
            intent="搜索 A 区，发现目标后派无人车接近确认，无人机继续中继或观察",
            context_snapshot={"mission_id": "golden_uav_ugv_coordination"},
        ),
        GoldenMissionCase(
            case_id="failure_and_replan",
            description="Recoverable UGV path failure should produce central replan request from FailureReport.",
            intent="搜索 B 区并派无人车确认目标，如果道路不通就让无人机复查",
            context_snapshot={"mission_id": "golden_failure_and_replan"},
            resume_failure_report=FailureReport(
                mission_id="golden_failure_and_replan",
                task_id="task_002",
                platform_id="ugv_0",
                failure_type="path_blocked",
                recoverable=True,
                reason="local_planner_no_path",
                recommended_actions=["request_uav_rescan", "try_alternate_region_entry"],
            ),
        ),
        GoldenMissionCase(
            case_id="disconnect_continue_authorized_subtree",
            description="Disconnect scenario preserves continue_current_task policy without platform-local replanning.",
            intent="平台短暂断联时只继续已经授权的 BT 子树，不允许本地生成新任务",
            context_snapshot={
                "mission_id": "golden_disconnect_continue",
                "disconnect_policy": "continue_current_task",
                "forbid_platform_replan": True,
            },
        ),
    ]


def golden_case_by_id(case_id: str) -> GoldenMissionCase:
    for mission_case in golden_mission_cases():
        if mission_case.case_id == case_id:
            return mission_case
    raise KeyError(case_id)
