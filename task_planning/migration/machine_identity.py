from __future__ import annotations

import hashlib
import platform
import uuid
from typing import Any, Dict, List, Optional


MACHINE_IDENTITY_SCHEMA = "MachineIdentity.v1"
MACHINE_IDENTITY_VERSION = "host_node_uuid_hash_v1"
HASHED_MACHINE_ID_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")


def current_machine_id() -> str:
    raw = f"{platform.node()}|{uuid.getnode()}|{platform.system()}|{platform.machine()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_hashed_machine_id(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return len(value) == HASHED_MACHINE_ID_LENGTH and all(char in _HEX_DIGITS for char in value)


def hashed_machine_id_errors(value: Any, field_name: str) -> List[str]:
    if not isinstance(value, str) or not value.strip():
        return [f"{field_name} is required"]
    if not is_hashed_machine_id(value):
        return [f"{field_name} must be a 64-character lowercase sha256 hex string"]
    return []


def resolve_hashed_machine_id(value: Optional[str], field_name: str) -> str:
    machine_id = value if value is not None else current_machine_id()
    errors = hashed_machine_id_errors(machine_id, field_name)
    if errors:
        raise ValueError("; ".join(errors))
    return machine_id


def current_machine_identity() -> Dict[str, str]:
    return {
        "schema": MACHINE_IDENTITY_SCHEMA,
        "version": MACHINE_IDENTITY_VERSION,
        "machine_id": current_machine_id(),
    }
