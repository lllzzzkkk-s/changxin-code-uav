#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.mission_ops.mock_openai_endpoint import MOCK_MODEL_NAME, make_mock_openai_handler


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a local OpenAI-compatible mock endpoint for home_model_lab plumbing tests only.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model", default=MOCK_MODEL_NAME)
    parser.add_argument(
        "--schema-mode",
        default="baseline",
        choices=["baseline", "alternate_target", "needs_clarification"],
        help="Response mode for compile_task_schema requests.",
    )
    args = parser.parse_args()

    handler = make_mock_openai_handler(model_name=args.model, schema_mode=args.schema_mode)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    bound_host, bound_port = server.server_address
    print(json.dumps({
        "schema": "MockModelLabEndpoint.v1",
        "base_url": f"http://{bound_host}:{bound_port}/v1",
        "model": args.model,
        "schema_mode": args.schema_mode,
        "warning": "mock_endpoint_only_not_home_5090_evidence",
    }, indent=2, sort_keys=True), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
