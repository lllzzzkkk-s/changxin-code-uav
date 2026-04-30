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

from uav.llm_control.ros_adapters.action_gate_dry_run import build_action_gate_dry_run_report
from uav.llm_control.safety.action_gate import ActionApproval
from uav.llm_control.safety.profiles import (
    a_stage_sim_dry_run_profile,
    b_stage_bench_profile,
    c_stage_real_profile,
)
from uav.llm_control.schemas.models import BatterySnapshot, FcuSnapshot, LocalizationSnapshot, RcSnapshot, StateSnapshot


ACTION_TOPICS = (
    "/goal",
    "/move_base_simple/goal",
    "/back_trigger",
    "/px4ctrl/takeoff_land",
    "/setpoints_cmd",
)

PROFILES = {
    "a-stage-sim-dry-run": a_stage_sim_dry_run_profile,
    "b-stage-bench": b_stage_bench_profile,
    "c-stage-real": c_stage_real_profile,
}


def main() -> int:
    args = parse_args()
    evidence_dir = Path(args.evidence_dir).expanduser()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    graph = capture_live_graph()
    write_text(evidence_dir / "g3d-01-live-graph.txt", graph["text"])
    if graph["returncode"] != 0:
        write_summary(evidence_dir, args, gate_report=None, echo_report=None, graph_ok=False)
        print(f"ROS graph check failed; see {evidence_dir / 'g3d-01-live-graph.txt'}", file=sys.stderr)
        return 3

    now = float(args.now)
    profile = PROFILES[args.profile]()
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

    gate_report = build_action_gate_dry_run_report(
        envelope,
        snapshot,
        approval,
        now=now,
        requested_timeout_s=args.requested_timeout_s,
        config=profile,
    ).as_dict()
    write_json(evidence_dir / "g3d-02-action-gate-report.json", gate_report)

    echo_report = passive_echo_topics(ACTION_TOPICS, timeout_s=args.echo_timeout_s)
    write_text(evidence_dir / "g3d-03-action-topic-passive-echo.txt", echo_report["text"])

    write_summary(evidence_dir, args, gate_report=gate_report, echo_report=echo_report, graph_ok=True)
    print((evidence_dir / "g3d-04-summary.txt").read_text())
    return 0 if gate_report["gate_allowed"] and not echo_report["message_received"] else 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only G3-D live-sim action gate check. This script never publishes ROS topics.",
    )
    parser.add_argument("--evidence-dir", default="~/uav-g3d-evidence")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="a-stage-sim-dry-run")
    parser.add_argument("--request-id", default="g3d-live-a-profile-gate")
    parser.add_argument("--operator-id", default="operator-a")
    parser.add_argument("--sim-evidence-id", default="g3c-20-22")
    parser.add_argument("--rollback-plan-id", default="kill-live-sim-launch-pid")
    parser.add_argument("--action-summary", default="G3-D live headless sim action gate dry-run")
    parser.add_argument("--source", default="sim")
    parser.add_argument("--x", type=float, default=-15.0)
    parser.add_argument("--y", type=float, default=0.0)
    parser.add_argument("--z", type=float, default=1.0)
    parser.add_argument("--yaw", type=float, default=0.0)
    parser.add_argument("--distance-m", type=float, default=1.0)
    parser.add_argument("--requested-timeout-s", type=float, default=2.0)
    parser.add_argument("--approval-ttl-s", type=float, default=3.0)
    parser.add_argument("--echo-timeout-s", type=float, default=5.0)
    parser.add_argument("--now", type=float, default=time.time())
    return parser.parse_args()


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
    blocks = []
    nodes = run_cli(("rosnode", "list"), timeout_s=5.0)
    topics = run_cli(("rostopic", "list", "-v"), timeout_s=5.0)
    blocks.append("### rosnode list\n")
    blocks.append(nodes["text"])
    blocks.append("\n### rostopic list -v\n")
    blocks.append(topics["text"])
    return {
        "returncode": 0 if nodes["returncode"] == 0 and topics["returncode"] == 0 else 1,
        "text": "".join(blocks),
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
    gate_report: Optional[Mapping[str, Any]],
    echo_report: Optional[Mapping[str, Any]],
    graph_ok: bool,
) -> None:
    lines = [
        f"profile: {args.profile}",
        f"request_id: {args.request_id}",
        f"ros_graph_ok: {graph_ok}",
    ]
    if gate_report is not None:
        lines.extend(
            [
                f"gate_status: {gate_report['status']}",
                f"gate_allowed: {gate_report['gate_allowed']}",
                f"publish_attempted: {gate_report['publish_attempted']}",
                f"topic: {gate_report['gate_decision']['topic']}",
                f"message_type: {gate_report['gate_decision']['message_type']}",
                f"reasons: {gate_report['gate_decision']['reasons']}",
                f"target_position: {gate_report['command']['resolution'].get('target_position')}",
            ]
        )
    if echo_report is not None:
        lines.append(f"action_topic_message_received: {echo_report['message_received']}")
    (evidence_dir / "g3d-04-summary.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
