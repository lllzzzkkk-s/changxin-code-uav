#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from uav.llm_control.ros_adapters.bench_precheck import (
    DEFAULT_ACTION_TOPICS,
    BenchPrecheckConfig,
    build_b_stage_bench_precheck_report,
    graph_snapshot_from_ros_cli,
)
from uav.llm_control.safety.action_gate import ActionApproval
from uav.llm_control.schemas.models import BatterySnapshot, FcuSnapshot, LocalizationSnapshot, RcSnapshot, StateSnapshot


def main() -> int:
    args = parse_args()
    evidence_dir = Path(args.evidence_dir).expanduser()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    graph_capture = capture_live_graph()
    write_text(evidence_dir / "g3e-01-live-graph.txt", graph_capture["text"])
    if graph_capture["returncode"] != 0:
        write_summary(evidence_dir, args, precheck_report=None, graph_ok=False)
        print(f"ROS graph check failed; see {evidence_dir / 'g3e-01-live-graph.txt'}", file=sys.stderr)
        return 3

    graph = graph_snapshot_from_ros_cli(graph_capture["nodes_stdout"], graph_capture["topics_stdout"])
    echo_report = passive_echo_topics(DEFAULT_ACTION_TOPICS, timeout_s=args.echo_timeout_s)
    write_text(evidence_dir / "g3e-02-action-topic-passive-echo.txt", echo_report["text"])

    now = float(args.now)
    snapshot = build_snapshot(args, now=now)
    envelope = {
        "meta": {"request_id": args.request_id},
        "intent": {"name": "move_relative"},
        "arguments": {"frame": "world", "direction": "forward", "distance_m": args.distance_m},
    }
    approval = ActionApproval(
        operator_id=args.operator_id,
        confirmation_phrase=f"CONFIRM {args.request_id} move_relative /goal",
        approved_at=now,
        expires_at=now + args.approval_ttl_s,
        sim_evidence_id=args.sim_evidence_id,
        rollback_plan_id=args.rollback_plan_id,
        action_summary=args.action_summary,
    )
    config = BenchPrecheckConfig(
        required_nodes=required_nodes_for_scope(args),
        required_subscribed_topics=required_subscribed_topics_for_scope(args),
    )
    precheck_report = build_b_stage_bench_precheck_report(
        envelope,
        snapshot,
        approval,
        graph,
        action_topic_message_received=bool(echo_report["message_received"]),
        now=now,
        requested_timeout_s=args.requested_timeout_s,
        config=config,
    ).as_dict()
    write_json(evidence_dir / "g3e-03-bench-precheck-report.json", precheck_report)
    write_summary(evidence_dir, args, precheck_report=precheck_report, graph_ok=True)
    print((evidence_dir / "g3e-04-summary.txt").read_text())

    return 0 if precheck_report["status"] == "bench_precheck_passed" else 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only B-stage bench profile precheck. This script never publishes ROS topics.",
    )
    parser.add_argument("--evidence-dir", default="~/uav-g3e-evidence")
    parser.add_argument("--request-id", default="g3e-b-stage-bench-precheck")
    parser.add_argument("--operator-id", default="operator-a")
    parser.add_argument("--sim-evidence-id", default="g3d-live-sim-gate")
    parser.add_argument("--rollback-plan-id", default="bench-disable-publisher-and-kill-launch")
    parser.add_argument("--action-summary", default="B-stage bench profile precheck without publish")
    parser.add_argument("--source", choices=("lio", "vio"), default="lio")
    parser.add_argument("--x", type=float, default=-15.0)
    parser.add_argument("--y", type=float, default=0.0)
    parser.add_argument("--z", type=float, default=1.0)
    parser.add_argument("--yaw", type=float, default=0.0)
    parser.add_argument("--distance-m", type=float, default=0.3)
    parser.add_argument("--requested-timeout-s", type=float, default=1.5)
    parser.add_argument("--approval-ttl-s", type=float, default=2.0)
    parser.add_argument("--echo-timeout-s", type=float, default=5.0)
    parser.add_argument("--now", type=float, default=time.time())
    parser.add_argument(
        "--graph-scope",
        choices=("planner-only", "operator-trigger"),
        default="operator-trigger",
        help=(
            "planner-only checks the planner/traj_server path and /goal subscriber only; "
            "operator-trigger also requires the operator trigger path such as /back_trigger."
        ),
    )
    parser.add_argument(
        "--required-node",
        action="append",
        default=[],
        help="Additional required ROS node. Defaults are selected by --graph-scope.",
    )
    parser.add_argument(
        "--required-subscriber-topic",
        action="append",
        default=[],
        help="Additional required subscribed topic. Defaults are selected by --graph-scope.",
    )
    return parser.parse_args()


def required_nodes_for_scope(args: argparse.Namespace) -> tuple:
    base = ["/drone_0_diff_planner_node", "/drone_0_traj_server", "/rosout"]
    return tuple(base + list(args.required_node))


def required_subscribed_topics_for_scope(args: argparse.Namespace) -> tuple:
    if args.graph_scope == "planner-only":
        base = ["/goal"]
    else:
        base = ["/goal", "/back_trigger"]
    return tuple(base + list(args.required_subscriber_topic))


def build_snapshot(args: argparse.Namespace, *, now: float) -> StateSnapshot:
    return StateSnapshot(
        captured_at=now,
        fcu=FcuSnapshot(connected=True, armed=True, mode="OFFBOARD", updated_at=now),
        battery=BatterySnapshot(voltage=24.1, percentage=0.75, updated_at=now),
        rc=RcSnapshot(channels=[1000, 1500, 1500, 1500, 1000, 1000, 1800, 1500], updated_at=now),
        localization=LocalizationSnapshot(
            source=args.source,
            position={"x": args.x, "y": args.y, "z": args.z},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            yaw=args.yaw,
            updated_at=now,
        ),
    )


def capture_live_graph() -> Dict[str, Any]:
    nodes = run_cli(("rosnode", "list"), timeout_s=5.0)
    topics = run_cli(("rostopic", "list", "-v"), timeout_s=5.0)
    return {
        "returncode": 0 if nodes["returncode"] == 0 and topics["returncode"] == 0 else 1,
        "nodes_stdout": nodes["stdout"],
        "topics_stdout": topics["stdout"],
        "text": "### rosnode list\n" + nodes["text"] + "\n### rostopic list -v\n" + topics["text"],
    }


def passive_echo_topics(topics: Sequence[str], *, timeout_s: float) -> Dict[str, Any]:
    message_received = False
    blocks = []
    for topic in topics:
        result = run_cli(("rostopic", "echo", "-n", "1", topic), timeout_s=timeout_s)
        blocks.append(f"===== {topic} =====\n")
        blocks.append(result["text"])
        if result["timed_out"]:
            blocks.append(f"NO_MESSAGE_WITHIN_{int(timeout_s)}S\n")
        elif result["returncode"] == 0 and result["stdout"].strip():
            message_received = True
            blocks.append("MESSAGE_RECEIVED\n")
        else:
            blocks.append(f"NO_MESSAGE_WITHIN_{int(timeout_s)}S\n")
    return {"message_received": message_received, "text": "".join(blocks)}


def run_cli(cmd: Sequence[str], *, timeout_s: float) -> Dict[str, Any]:
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout_s)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        return {
            "returncode": completed.returncode,
            "timed_out": False,
            "stdout": stdout,
            "stderr": stderr,
            "text": stdout + stderr,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        return {
            "returncode": 124,
            "timed_out": True,
            "stdout": stdout,
            "stderr": stderr,
            "text": stdout + stderr,
        }


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def write_text(path: Path, text: str) -> None:
    path.write_text(text)


def write_summary(
    evidence_dir: Path,
    args: argparse.Namespace,
    *,
    precheck_report: Optional[Mapping[str, Any]],
    graph_ok: bool,
) -> None:
    lines = [
        "profile: b-stage-bench",
        f"request_id: {args.request_id}",
        f"graph_scope: {args.graph_scope}",
        f"ros_graph_ok: {graph_ok}",
    ]
    if precheck_report is not None:
        gate = precheck_report["gate_report"]
        lines.extend(
            [
                f"bench_status: {precheck_report['status']}",
                f"graph_ok: {precheck_report['graph_ok']}",
                f"gate_allowed: {precheck_report['gate_allowed']}",
                f"publish_attempted: {precheck_report['publish_attempted']}",
                f"action_topic_message_received: {precheck_report['action_topic_message_received']}",
                f"missing_nodes: {precheck_report['missing_nodes']}",
                f"missing_subscribed_topics: {precheck_report['missing_subscribed_topics']}",
                f"topic: {gate['gate_decision']['topic']}",
                f"message_type: {gate['gate_decision']['message_type']}",
                f"reasons: {gate['gate_decision']['reasons']}",
                f"target_position: {gate['command']['resolution'].get('target_position')}",
                f"localization_source: {gate['command']['resolution'].get('localization_source')}",
            ]
        )
    (evidence_dir / "g3e-04-summary.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
