"""Producer-owned filesystem observations; no runtime or safety authority."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import TypedDict, cast

from hashmarks.paths import normalize_relative_path

SCHEMA = "hashmarks.python-filesystem-lifecycle-observation.v1"
RULES = "python-filesystem-source-bindings.v1"


@dataclass(frozen=True)
class LifecycleBounds:
    max_depth: int = 8
    calls_per_symbol: int = 64
    references_per_symbol: int = 256
    symbols_per_anchor: int = 256
    candidate_paths: int = 10_000
    observations: int = 256

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


DEFAULT_BOUNDS = LifecycleBounds()


class IdentityComparison(TypedDict):
    path: str
    symbol: str
    lines: list[int]
    member_revision: str
    kind: str
    api: str
    fields: list[str]
    operators: list[str]
    qualification: str


class LifecyclePacket(TypedDict):
    schema: str
    repository_identity: str
    generation: int
    stale: bool | None
    producer: dict[str, str]
    scope: list[str]
    source_revisions: dict[str, str]
    bounds: dict[str, int]
    coverage: dict[str, object]
    operations: list[dict[str, object]]
    observations: list[dict[str, object]]
    unresolved: list[dict[str, object]]
    accounting: dict[str, int]
    authority: str
    execution_effect: str
    observation_identity: str


def lifecycle_identity(payload: Mapping[str, object]) -> str:
    semantic = {k: v for k, v in payload.items() if k != "observation_identity"}
    raw = json.dumps(
        semantic, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(SCHEMA.encode() + b"\0" + raw).hexdigest()


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValueError(f"invalid lifecycle {label}")
    return cast("dict[str, object]", value)


def _records(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"invalid lifecycle {label}")
    return [_mapping(row, label) for row in value]


def _validate_operation(row: dict[str, object], revisions: dict[str, object]) -> None:
    path = row.get("path")
    if not isinstance(path, str) or normalize_relative_path(path) != path:
        raise ValueError("invalid lifecycle operation path")
    if row.get("member_revision") != revisions.get(path) or path not in revisions:
        raise ValueError("unbound lifecycle operation")
    lines = row.get("lines")
    if (
        not isinstance(lines, list)
        or len(lines) != 2
        or any(type(n) is not int for n in lines)
        or not 1 <= lines[0] <= lines[1]
    ):
        raise ValueError("invalid lifecycle source range")
    if row.get("kind") not in {"check", "use", "mutation"}:
        raise ValueError("invalid lifecycle operation kind")


def validate_lifecycle_observation(payload: Mapping[str, object]) -> LifecyclePacket:
    """Validate content binding and evidence-only invariants, never runtime truth."""
    root = dict(payload)
    if set(root) != LifecyclePacket.__required_keys__:
        raise ValueError("invalid lifecycle fields")
    if root.get("schema") != SCHEMA:
        raise ValueError("unsupported lifecycle schema")
    if root.get("authority") != "repository-evidence-only":
        raise ValueError("invalid lifecycle authority")
    if root.get("execution_effect") != "none":
        raise ValueError("invalid lifecycle execution effect")
    if root.get("observation_identity") != lifecycle_identity(root):
        raise ValueError("lifecycle identity mismatch")
    _validate_headers(root)
    revisions = _mapping(root.get("source_revisions"), "source revisions")
    _validate_sources(root, revisions)
    operations = _records(root.get("operations"), "operations")
    for operation in operations:
        _validate_operation(operation, revisions)
    _validate_relationships(root, operations)
    _validate_coverage(root)
    return cast("LifecyclePacket", root)


def _validate_sources(root: dict[str, object], revisions: dict[str, object]) -> None:
    for path, revision in revisions.items():
        if normalize_relative_path(path, allow_root=False) != path:
            raise ValueError("invalid lifecycle source path")
        if (
            not isinstance(revision, str)
            or re.fullmatch(r"[0-9a-f]{64}", revision) is None
        ):
            raise ValueError("invalid lifecycle source revision")
    scope = root.get("scope")
    if not isinstance(scope, list) or any(not isinstance(path, str) for path in scope):
        raise ValueError("invalid lifecycle scope")
    for path in scope:
        if normalize_relative_path(path, allow_root=False) != path:
            raise ValueError("invalid lifecycle scope path")


def _validate_headers(root: dict[str, object]) -> None:
    generation = root.get("generation")
    if type(generation) is not int or generation < 0:
        raise ValueError("invalid lifecycle generation")
    if root.get("stale") is not None and type(root["stale"]) is not bool:
        raise ValueError("invalid lifecycle freshness")
    if not isinstance(root.get("repository_identity"), str):
        raise ValueError("invalid lifecycle repository identity")
    producer = _mapping(root.get("producer"), "producer")
    if producer.get("rules") != RULES or not producer.get("implementation_identity"):
        raise ValueError("invalid lifecycle producer")
    if (
        re.fullmatch(r"sha256:[0-9a-f]{64}", str(producer["implementation_identity"]))
        is None
    ):
        raise ValueError("invalid lifecycle producer identity")
    coverage = _mapping(root.get("coverage"), "coverage")
    if coverage.get("negative_evidence_admissible") is not False:
        raise ValueError("lifecycle negative evidence is not admissible")
    if coverage.get("runtime_protection") != "unverified":
        raise ValueError("lifecycle runtime protection overclaim")


def _validate_relationships(
    root: dict[str, object], operations: list[dict[str, object]]
) -> None:
    observations = _records(root.get("observations"), "observations")
    for row in observations:
        if row.get("check") not in operations or row.get("use") not in operations:
            raise ValueError("unbound lifecycle relationship")
        if row.get("runtime_identity") != "unverified":
            raise ValueError("lifecycle runtime identity overclaim")
        if row.get("relationship") != "same-source-reference":
            raise ValueError("unsupported lifecycle relationship")
        _validate_pair(row)
        for comparison in _records(
            row.get("identity_comparisons", []), "identity comparisons"
        ):
            _validate_operation(
                comparison, _mapping(root["source_revisions"], "source revisions")
            )
    _validate_accounting(root, observations)


def _validate_accounting(
    root: dict[str, object], observations: list[dict[str, object]]
) -> None:
    accounting = _mapping(root.get("accounting"), "accounting")
    if any(type(n) is not int or n < 0 for n in accounting.values()):
        raise ValueError("invalid lifecycle accounting")
    if accounting.get("returned") != len(observations):
        raise ValueError("lifecycle observation accounting mismatch")
    omitted = accounting.get("omitted")
    if (
        not isinstance(omitted, int)
        or accounting.get("observed") != len(observations) + omitted
    ):
        raise ValueError("lifecycle omission accounting mismatch")
    _records(root.get("unresolved"), "unresolved")


def _validate_pair(row: dict[str, object]) -> None:
    check = _mapping(row.get("check"), "check")
    use = _mapping(row.get("use"), "use")
    if check.get("kind") != "check" or use.get("kind") != "use":
        raise ValueError("invalid lifecycle relationship roles")
    if not check.get("reference") or check.get("reference") != use.get("reference"):
        raise ValueError("unproven lifecycle source-reference equality")
    if row.get("namespace_binding") not in {
        "unverified",
        "same-source-dir-fd-reference",
        "implicit-runtime-namespace",
    }:
        raise ValueError("invalid lifecycle namespace binding")
    unknowns = row.get("unverified")
    if not isinstance(unknowns, list) or not {
        "exclusive-namespace-ownership",
        "runtime-protection",
        "execution-feasibility",
    }.issubset(unknowns):
        raise ValueError("lifecycle uncertainty erased")


def _validate_coverage(root: dict[str, object]) -> None:
    bounds = _mapping(root.get("bounds"), "bounds")
    if set(bounds) != set(DEFAULT_BOUNDS.as_dict()) or any(
        type(n) is not int or n < 0 for n in bounds.values()
    ):
        raise ValueError("invalid lifecycle bounds")
    coverage = _mapping(root["coverage"], "coverage")
    accounting = _mapping(root["accounting"], "accounting")
    if type(coverage.get("truncated")) is not bool:
        raise ValueError("invalid lifecycle truncation")
    if coverage.get("completeness") not in {
        "incomplete",
        "complete-within-supported-scope",
    }:
        raise ValueError("invalid lifecycle completeness")
    partial = bool(
        root["unresolved"]
        or accounting.get("omitted")
        or accounting.get("bounded_paths")
    )
    if partial and coverage.get("completeness") != "incomplete":
        raise ValueError("lifecycle completeness overclaim")
    if (accounting.get("omitted") or accounting.get("bounded_paths")) and coverage[
        "truncated"
    ] is not True:
        raise ValueError("lifecycle truncation erased")
