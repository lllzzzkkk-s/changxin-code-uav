from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from uav.llm_control.ros_adapters.action_gate_dry_run import build_action_gate_dry_run_report
from uav.llm_control.safety.action_gate import ActionApproval
from uav.llm_control.safety.profiles import b_stage_bench_profile
from uav.llm_control.schemas.models import StateSnapshot


DEFAULT_REQUIRED_NODES = (
    "/drone_0_diff_planner_node",
    "/drone_0_traj_server",
    "/rosout",
)
DEFAULT_REQUIRED_SUBSCRIBED_TOPICS = (
    "/goal",
    "/back_trigger",
)
DEFAULT_ACTION_TOPICS = (
    "/goal",
    "/move_base_simple/goal",
    "/back_trigger",
    "/px4ctrl/takeoff_land",
    "/setpoints_cmd",
)


@dataclass(frozen=True)
class BenchGraphSnapshot:
    nodes: Sequence[str]
    published_topics: Sequence[str]
    subscribed_topics: Sequence[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "published_topics": list(self.published_topics),
            "subscribed_topics": list(self.subscribed_topics),
        }


@dataclass(frozen=True)
class BenchPrecheckConfig:
    required_nodes: Sequence[str] = DEFAULT_REQUIRED_NODES
    required_subscribed_topics: Sequence[str] = DEFAULT_REQUIRED_SUBSCRIBED_TOPICS
    action_topics: Sequence[str] = DEFAULT_ACTION_TOPICS

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BenchPrecheckReport:
    status: str
    graph_ok: bool
    gate_allowed: bool
    publish_attempted: bool
    action_topic_message_received: bool
    missing_nodes: Sequence[str]
    missing_subscribed_topics: Sequence[str]
    config: Dict[str, Any]
    graph: Dict[str, Any]
    gate_report: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_b_stage_bench_precheck_report(
    envelope: Mapping[str, Any],
    snapshot: StateSnapshot,
    approval: Optional[ActionApproval],
    graph: BenchGraphSnapshot,
    *,
    action_topic_message_received: bool,
    now: float,
    requested_timeout_s: float,
    config: Optional[BenchPrecheckConfig] = None,
) -> BenchPrecheckReport:
    cfg = config or BenchPrecheckConfig()
    missing_nodes = _missing(cfg.required_nodes, graph.nodes)
    missing_subscribed_topics = _missing(cfg.required_subscribed_topics, graph.subscribed_topics)
    graph_ok = not missing_nodes and not missing_subscribed_topics

    gate_report = build_action_gate_dry_run_report(
        envelope,
        snapshot,
        approval,
        now=now,
        requested_timeout_s=requested_timeout_s,
        config=b_stage_bench_profile(),
    ).as_dict()
    gate_allowed = bool(gate_report["gate_allowed"])
    precheck_passed = graph_ok and gate_allowed and not action_topic_message_received

    return BenchPrecheckReport(
        status="bench_precheck_passed" if precheck_passed else "bench_precheck_failed",
        graph_ok=graph_ok,
        gate_allowed=gate_allowed,
        publish_attempted=False,
        action_topic_message_received=bool(action_topic_message_received),
        missing_nodes=missing_nodes,
        missing_subscribed_topics=missing_subscribed_topics,
        config=cfg.as_dict(),
        graph=graph.as_dict(),
        gate_report=gate_report,
    )


def _missing(required: Sequence[str], observed: Sequence[str]) -> List[str]:
    observed_set = set(observed)
    return [item for item in required if item not in observed_set]


def graph_snapshot_from_ros_cli(nodes_text: str, topics_text: str) -> BenchGraphSnapshot:
    return BenchGraphSnapshot(
        nodes=_parse_rosnode_list(nodes_text),
        published_topics=_parse_rostopic_section(topics_text, heading="Published topics:"),
        subscribed_topics=_parse_rostopic_section(topics_text, heading="Subscribed topics:"),
    )


def _parse_rosnode_list(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip().startswith("/")]


def _parse_rostopic_section(text: str, *, heading: str) -> List[str]:
    topics: List[str] = []
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == heading:
            in_section = True
            continue
        if line.endswith("topics:") and line != heading:
            in_section = False
            continue
        if not in_section:
            continue
        match = re.match(r"^\*\s+(\S+)\s+\[", line)
        if match:
            topics.append(match.group(1))
    return topics
