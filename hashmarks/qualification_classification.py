from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

CLASSIFICATION_SCHEMA = "hashmarks.qualification-classification.v1"
POLICY_SCHEMA = "hashmarks.qualification-classification-policy.v1"
ALLOWED_KINDS = frozenset(
    {"release-correctness", "process-sensitive", "empirical-benchmark"}
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _identity(domain: str, value: object) -> str:
    return (
        "sha256:"
        + hashlib.sha256(domain.encode() + b"\0" + _canonical_bytes(value)).hexdigest()
    )


def _validate_kind(value: object, *, context: str) -> None:
    if value not in ALLOWED_KINDS:
        raise ValueError(
            f"invalid qualification classification kind in {context}: {value}"
        )


def _validate_override(row: object, seen: set[str]) -> None:
    if not isinstance(row, Mapping):
        raise ValueError("qualification classification override must be an object")
    nodeid = row.get("nodeid")
    if not isinstance(nodeid, str) or not nodeid:
        raise ValueError("qualification classification override requires nodeid")
    if nodeid in seen:
        raise ValueError(f"duplicate qualification classification override: {nodeid}")
    _validate_kind(row.get("kind"), context=f"override {nodeid}")
    seen.add(nodeid)


def _validate_path_rule(row: object, seen: set[str]) -> None:
    if not isinstance(row, Mapping):
        raise ValueError("qualification classification path rule must be an object")
    prefix = row.get("path_prefix")
    if not isinstance(prefix, str) or not prefix:
        raise ValueError("qualification classification path rule requires path_prefix")
    if prefix in seen:
        raise ValueError(f"duplicate qualification classification path rule: {prefix}")
    _validate_kind(row.get("kind"), context=f"path rule {prefix}")
    seen.add(prefix)


def _policy_lists(value: dict[str, object]) -> tuple[list[object], list[object]]:
    overrides = value.get("node_overrides")
    rules = value.get("path_rules")
    if not isinstance(overrides, list) or not isinstance(rules, list) or not rules:
        raise ValueError(
            "qualification classification requires overrides and path rules"
        )
    return overrides, rules


def _validate_policy(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("schema") != POLICY_SCHEMA:
        raise ValueError("invalid qualification classification policy")
    if value.get("unmatched_node_policy") != "fail-closed":
        raise ValueError(
            "qualification classification unmatched_node_policy must be fail-closed"
        )
    overrides, rules = _policy_lists(value)
    seen_overrides: set[str] = set()
    for row in overrides:
        _validate_override(row, seen_overrides)
    seen_rules: set[str] = set()
    for row in rules:
        _validate_path_rule(row, seen_rules)
    try:
        _canonical_bytes(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "qualification classification policy must be strict JSON-portable"
        ) from exc
    return value


def load_classification_policy(root: Path) -> dict[str, object]:
    path = root.resolve() / "qualification-classification.json"
    return _validate_policy(json.loads(path.read_text(encoding="utf-8")))


def classification_policy_identity(root: Path) -> str:
    policy = load_classification_policy(root)
    return _identity(POLICY_SCHEMA, policy)


def _path_rule_for_node(
    nodeid: str,
    rules: list[object],
) -> Mapping[str, object] | None:
    path = nodeid.split("::", 1)[0]
    matches = [
        row
        for row in rules
        if isinstance(row, Mapping)
        and isinstance(row.get("path_prefix"), str)
        and path.startswith(str(row["path_prefix"]))
    ]
    if not matches:
        return None
    return max(matches, key=lambda row: len(str(row["path_prefix"])))


def classify_nodeids(root: Path, nodeids: Sequence[str]) -> dict[str, object]:
    from .test_shards import repository_content_identity

    root = root.resolve()
    policy = load_classification_policy(root)
    overrides = {
        str(row["nodeid"]): row
        for row in policy["node_overrides"]
        if isinstance(row, Mapping)
    }
    rules = policy["path_rules"]
    assert isinstance(rules, list)
    rows: list[dict[str, object]] = []
    for nodeid in sorted(nodeids):
        override = overrides.get(nodeid)
        source = override or _path_rule_for_node(nodeid, rules)
        if source is None:
            raise ValueError(f"unclassified qualification node: {nodeid}")
        is_override = override is not None
        rows.append(
            {
                "nodeid": nodeid,
                "kind": str(source["kind"]),
                "preferred_granularity": str(
                    source.get("preferred_granularity", "file")
                ),
                "classification_source": "node-override"
                if is_override
                else "repository-path-rule",
                "reason": str(source.get("reason", "repository classification rule")),
            }
        )
    payload: dict[str, object] = {
        "schema": CLASSIFICATION_SCHEMA,
        "repository_identity": repository_content_identity(root),
        "policy_identity": classification_policy_identity(root),
        "classifications": rows,
    }
    payload["classification_identity"] = _identity(CLASSIFICATION_SCHEMA, payload)
    return payload


def classification_map(
    root: Path, nodeids: Sequence[str]
) -> dict[str, dict[str, object]]:
    artifact = classify_nodeids(root, nodeids)
    return {
        str(row["nodeid"]): dict(row)
        for row in artifact["classifications"]
        if isinstance(row, Mapping)
    }
