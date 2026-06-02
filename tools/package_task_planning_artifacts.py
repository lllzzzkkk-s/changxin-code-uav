#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_planning.migration import build_artifact_package


def main() -> int:
    parser = argparse.ArgumentParser(description="Package task-planning run or model-lab artifacts for transfer to another machine.")
    parser.add_argument(
        "--artifact",
        action="append",
        required=True,
        type=Path,
        help="Artifact directory to include. Repeat for multiple mission runs or model-lab evaluations.",
    )
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory where the package folder and tar.gz are written.")
    parser.add_argument("--package-name", default="task-planning-artifacts", help="Top-level package/archive name.")
    parser.add_argument(
        "--source-machine-id",
        help="Override the 64-character hashed source machine id recorded in the artifact package manifest.",
    )
    args = parser.parse_args()

    package = build_artifact_package(
        artifact_paths=args.artifact,
        output_dir=args.output_dir,
        package_name=args.package_name,
        source_machine_id=args.source_machine_id,
    )
    print(json.dumps(package.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
