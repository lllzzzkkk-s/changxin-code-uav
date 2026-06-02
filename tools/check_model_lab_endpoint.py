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

from task_planning.config import load_profile
from task_planning.contracts import CapabilityRegistry, validate_mission_request
from task_planning.mission_ops.http_model_client import OpenAICompatibleModelClient
from task_planning.mission_ops.model_client import NeedsClarification


def check_model_lab_endpoint(profile_path: Path, *, intent: str) -> Dict[str, Any]:
    profile = load_profile(profile_path)
    validation_errors = []
    if profile.mission_profile != "home_model_lab":
        validation_errors.append("model lab check requires MISSION_PROFILE=home_model_lab")
    if profile.platform_backend != "mock":
        validation_errors.append("model lab check must keep PLATFORM_BACKEND=mock")
    if validation_errors:
        return _result(profile, validation_errors=validation_errors)

    client = OpenAICompatibleModelClient.from_profile(profile)
    result = client.compile_task_schema(intent, {"mission_id": "model_lab_smoke"})
    if isinstance(result, NeedsClarification):
        return _result(
            profile,
            validation_errors=["model returned NeedsClarification"],
            extra={"needs_clarification": result.as_dict()},
        )
    validation_errors = validate_mission_request(result.mission_request, CapabilityRegistry.scout_and_confirm_default())
    return _result(profile, validation_errors=validation_errors, extra={"task_schema": result.as_dict()})


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the home model-lab OpenAI-compatible endpoint without hardware dispatch.")
    parser.add_argument("--profile", required=True, type=Path, help="Path to profiles/home_model_lab.env or equivalent.")
    parser.add_argument("--intent", default="搜索 A 区并派无人车确认目标", help="Mission intent for schema compilation.")
    args = parser.parse_args()

    result = check_model_lab_endpoint(args.profile, intent=args.intent)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["ok"] else 1


def _result(profile, *, validation_errors, extra=None):
    data = {
        "schema": "ModelLabEndpointCheck.v1",
        "ok": not validation_errors,
        "mission_profile": profile.mission_profile,
        "model_provider": profile.model_provider,
        "model_name": profile.model_name,
        "model_lab_evidence_kind": profile.model_lab_evidence_kind,
        "platform_backend": profile.platform_backend,
        "validation_errors": list(validation_errors),
    }
    data.update(extra or {})
    return data


if __name__ == "__main__":
    raise SystemExit(main())
