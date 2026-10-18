"""Structural-locality packet values and their existing serialization identity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import TypedDict

from hashmarks.operation_contract import operation_schema

LOCALITY_SCHEMA = operation_schema("structural_locality")
LOCALITY_DELTA_SCHEMA = operation_schema("structural_locality_delta")


class LocalityNodeFacts(TypedDict):
    path: str
    qualname: str
    name: str
    kind: str
    signature: str
    lines: list[int]
    navigation_depth: int
    file_digest: str
    forwarding_only: bool | None
    forwarding_provider: str
    exact_callers: list[dict[str, object]]
    exact_caller_count: int
    caller_reference_bound_complete: bool
    unresolved_caller_candidates: list[dict[str, object]]


class LocalityNode(LocalityNodeFacts):
    symbol_id: str
    symbol_source_identity: str
    symbol_evidence_identity: str


def locality_coordinate(value: object) -> int:
    """Coerce an indexed coordinate without supplying a missing position."""
    if not isinstance(value, (int, str, float, bytes, bytearray)):
        raise TypeError("structural source coordinates must be numeric")
    return int(value)


def locality_identity(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


CallTargetResolver = Callable[
    [Mapping[str, object]],
    tuple[dict[str, object] | None, list[str], bool, bool],
]
