#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.mission_ops.intent_runner import run_task_planning_intent


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run one operator intent through MissionManager, Mock/ModelClient, validators, "
            "PDDL, BT, and a non-ROS gateway according to the selected profile."
        ),
    )
    parser.add_argument("--profile", required=True, type=Path, help="Path to profiles/*.env.")
    parser.add_argument("--intent", required=True, help="Operator natural-language mission intent.")
    parser.add_argument("--mission-id", help="Mission id to inject into context_snapshot.")
    parser.add_argument("--primary-platform", help="Primary platform id, for example ugv_0.")
    parser.add_argument("--case-id", default="", help="Optional case id written into mission_input.json and ledger.")
    parser.add_argument("--context-json", help="Additional JSON object merged into context_snapshot.")
    parser.add_argument("--context-file", type=Path, help="JSON object file merged into context_snapshot.")
    parser.add_argument("--agent-name", default="", help="Optional external agent framework name, for example openclaw or hermes.")
    parser.add_argument("--agent-draft-file", type=Path, help="TaskSchema.v1 draft JSON produced by the external agent.")
    parser.add_argument("--artifact-root", type=Path, help="Override MISSION_ARTIFACT_ROOT for this run.")
    args = parser.parse_args()

    try:
        context_snapshot = _context_snapshot(args)
        agent_draft = _agent_draft(args)
        report = run_task_planning_intent(
            profile_path=args.profile,
            intent=args.intent,
            context_snapshot=context_snapshot,
            case_id=args.case_id,
            artifact_root=args.artifact_root,
            repo_root=REPO_ROOT,
            agent_name=args.agent_name,
            agent_draft=agent_draft,
        )
    except Exception as exc:
        report_data = {
            "schema": "MissionIntentRun.v1",
            "ok": False,
            "intent": args.intent,
            "profile_path": str(args.profile.expanduser()),
            "mission_profile": "",
            "model_provider": "",
            "platform_backend": "",
            "context_snapshot": {},
            "case_id": args.case_id,
            "mission_id": "",
            "run_id": "",
            "status": "",
            "current_state": "",
            "artifact_bundle_path": "",
            "validation_errors": [str(exc)],
            "semantic_compiler": _semantic_compiler_metadata(args, agent_draft=None),
            "ros_connected": False,
            "hardware_dispatch_performed": False,
        }
        print(json.dumps(report_data, indent=2, sort_keys=True, ensure_ascii=False))
        return 1

    print(json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ok else 1


def _context_snapshot(args: argparse.Namespace) -> Dict[str, Any]:
    context: Dict[str, Any] = {}
    if args.context_file:
        file_context = json.loads(args.context_file.expanduser().read_text(encoding="utf-8"))
        if not isinstance(file_context, dict):
            raise ValueError("--context-file must contain a JSON object")
        context.update(file_context)
    if args.context_json:
        json_context = json.loads(args.context_json)
        if not isinstance(json_context, dict):
            raise ValueError("--context-json must be a JSON object")
        context.update(json_context)
    if args.mission_id:
        context["mission_id"] = args.mission_id
    if args.primary_platform:
        context["primary_platform"] = args.primary_platform
    return context


def _agent_draft(args: argparse.Namespace) -> Dict[str, Any] | None:
    if not args.agent_draft_file:
        return None
    draft = json.loads(args.agent_draft_file.expanduser().read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        raise ValueError("--agent-draft-file must contain a JSON object")
    return draft


def _semantic_compiler_metadata(args: argparse.Namespace, *, agent_draft: Dict[str, Any] | None) -> Dict[str, Any]:
    if args.agent_name or args.agent_draft_file:
        return {
            "schema": "SemanticCompilerBinding.v1",
            "kind": "agent_adapter",
            "agent_name": args.agent_name,
            "draft_schema": str((agent_draft or {}).get("schema", "")),
            "allowed_output_schema": "TaskSchema.v1",
        }
    return {
        "schema": "SemanticCompilerBinding.v1",
        "kind": "model_client",
        "model_provider": "",
    }


if __name__ == "__main__":
    raise SystemExit(main())
