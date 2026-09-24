from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from .test_shards import EXPENSIVE_BENCHMARK_NODEIDS, PROCESS_SENSITIVE_NODEIDS

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


def load_classification_policy(root: Path) -> dict[str, object]:
    """Build the repository-owned policy from the same node lists used by sharding."""
    return {
        "authority": "repository-owned",
        "measurement_mutation": "forbidden",
        "node_overrides": [
            *(
                {
                    "kind": "process-sensitive",
                    "nodeid": nodeid,
                    "preferred_granularity": "singleton",
                    "reason": "watcher/process lifecycle semantics",
                }
                for nodeid in PROCESS_SENSITIVE_NODEIDS
            ),
            *(
                {
                    "kind": "empirical-benchmark",
                    "nodeid": nodeid,
                    "preferred_granularity": "singleton",
                    "reason": "repository-intelligence empirical measurement",
                }
                for nodeid in EXPENSIVE_BENCHMARK_NODEIDS
            ),
        ],
        "path_rules": [
            {
                "kind": "release-correctness",
                "path_prefix": "tests/",
                "preferred_granularity": "file",
                "reason": "repository-owned test-suite correctness rule",
            }
        ],
        "schema": POLICY_SCHEMA,
        "unmatched_node_policy": "fail-closed",
    }


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
