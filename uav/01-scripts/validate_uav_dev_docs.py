from __future__ import annotations

import csv
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC_ROOT = ROOT / "uav" / "20-dev-docs"

REQUIRED_FILES = [
    DOC_ROOT / "README.md",
    DOC_ROOT / "01-developer-guide.md",
    DOC_ROOT / "02-interface-table.csv",
    DOC_ROOT / "03-feature-deployment-matrix.csv",
    DOC_ROOT / "04-screenshot-state-appendix.md",
    DOC_ROOT / "05-developer-navigation.md",
    DOC_ROOT / "06-evidence-index.csv",
    DOC_ROOT / "07-material-gaps.csv",
]

REQUIRED_COLUMNS = {
    "02-interface-table.csv": [
        "id",
        "category",
        "name",
        "type",
        "direction",
        "message_or_format",
        "key_fields",
        "upstream",
        "downstream",
        "preconditions",
        "typical_use",
        "example",
        "machine_status",
        "risks",
        "evidence_id",
        "source_path",
    ],
    "03-feature-deployment-matrix.csv": [
        "feature_name",
        "wiki_or_pdf_mentioned",
        "repo_source_present",
        "onboard_deployed",
        "directly_runnable",
        "required_hardware",
        "primary_entrypoint",
        "verification_method",
        "include_in_main_quickref",
        "notes",
        "evidence_id",
    ],
    "06-evidence-index.csv": [
        "evidence_id",
        "category",
        "claim",
        "source_type",
        "source_path",
        "locator",
        "notes",
    ],
    "07-material-gaps.csv": [
        "state_group",
        "required_shot",
        "currently_available",
        "evidence_source",
        "gap_reason",
        "collection_instruction",
        "priority",
    ],
}


def validate_files() -> list[str]:
    errors = []
    for path in REQUIRED_FILES:
        if not path.exists():
            errors.append(f"missing file: {path.relative_to(ROOT)}")
    return errors


def validate_csv_headers() -> list[str]:
    errors = []
    for rel_name, expected in REQUIRED_COLUMNS.items():
        path = DOC_ROOT / rel_name
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames != expected:
                errors.append(f"bad header for {rel_name}: {reader.fieldnames}")
    return errors


def main() -> int:
    errors = []
    errors.extend(validate_files())
    errors.extend(validate_csv_headers())
    if errors:
        print("VALIDATION FAILED")
        for error in errors:
            print(error)
        return 1
    print("VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
