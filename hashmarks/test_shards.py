from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ._version import __version__
from .digest import hash_file
from .python_ast_cache import read_python_ast
from .validation_inputs import require_mapping_for_validation

SCHEMA = "hashmarks.test-shards.v3"
ENVELOPE_SCHEMA = "hashmarks.repository-work-selection.v1"
SELECTION_INPUT_SCHEMA = "hashmarks.test-shard-selection-input.v1"
MEMBERSHIP_SCHEMA = "hashmarks.test-shard-membership.v1"
SHARD_ALGORITHM = "hashmarks.pytest-test-node-shards.v4"

_SHA256_IDENTITY = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPOSITORY_CONTENT_IDENTITY = re.compile(r"^sha256:[0-9a-f]{64}:[0-9]+$")
HASHMARKS_AUTHORITIES = (
    "repository-content-identity",
    "deterministic-test-membership",
    "process-isolation-requirements",
    "selection-plan-identity",
)
EXECUTION_LAYER_AUTHORITIES = (
    "process-launch",
    "deadline",
    "retry-resume",
    "concurrency",
    "scheduling",
    "environment-recovery",
    "result-authority",
)

_ENVELOPE_FIELDS = frozenset(
    {"schema", "producer", "repository", "selection", "authority", "envelope_identity"}
)
_PRODUCER_FIELDS = frozenset(
    {"name", "version", "algorithm", "implementation_identity", "artifact_identity"}
)
_REPOSITORY_FIELDS = frozenset({"content_identity", "selection_input_identity"})
_SELECTION_FIELDS = frozenset(
    {"schema", "shard_count", "test_node_count", "shards", "plan_identity"}
)
_SHARD_FIELDS = frozenset({"index", "nodeids", "weight_bytes", "isolated_process"})
_AUTHORITY_FIELDS = frozenset({"hashmarks", "execution_layer"})

_FORBIDDEN_EXECUTION_POLICY_KEYS = frozenset(
    {
        "argv",
        "command",
        "commands",
        "timeout",
        "timeout_seconds",
        "deadline",
        "deadline_seconds",
        "retry",
        "retry_count",
        "retry_delay",
        "retry_delay_seconds",
        "workers",
        "worker_count",
        "concurrency",
        "schedule",
        "machine",
        "machine_id",
        "executor",
        "executor_id",
        "process",
        "process_id",
        "environment_recovery",
    }
)

# Static selection evidence for tests that must never share a selected shard.
#
# This is deliberately NOT runtime timeout/retry policy. Hashmarks only says
# these repository-owned nodes require singleton/process isolation. The
# external execution layer still decides deadlines, retries, runtime
# subdivision, scheduling, and resume behavior.
PROCESS_SENSITIVE_NODEIDS = (
    "tests/test_codemap.py::test_codemap_watcher_keeps_map_hot_without_identity_daemon",
)

# These are benchmark/measurement assertions, not release-correctness owners.
# Keep them statically identifiable so bounded promotion can separate correctness
# from intentionally expensive empirical measurements without changing runtime
# timeout/retry policy.
EXPENSIVE_BENCHMARK_NODEIDS = (
    "tests/test_agent_metrics_suite.py::test_blind_worker_ab_is_reproducible_and_scores_both_workers",
    "tests/test_agent_metrics_suite.py::test_worker_behavior_ab_is_answer_blind_and_reproducible",
    "tests/test_agent_metrics_suite.py::test_worker_inspection_ab_recovers_ambiguity_without_hidden_answers",
    "tests/test_agent_metrics_suite.py::test_worker_multistep_ab_improves_edit_safety_and_preserves_verification",
    "tests/test_agent_metrics_suite.py::test_worker_failed_verification_ab_recovers_without_hidden_answers",
    "tests/test_agent_metrics_suite.py::test_selective_scout_targets_only_observed_ambiguity",
)

ISOLATED_NODEIDS = tuple(
    dict.fromkeys((*PROCESS_SENSITIVE_NODEIDS, *EXPENSIVE_BENCHMARK_NODEIDS))
)


@dataclass
class _ValidationState:
    reasons: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    unexpected_fields: list[str] = field(default_factory=list)

    def add_fields(
        self,
        value: Mapping[str, object],
        expected: frozenset[str],
        *,
        path: str,
        missing_reason: str,
        unexpected_reason: str,
    ) -> None:
        missing, unexpected = _field_set_issues(value, expected, path=path)
        self.missing_fields.extend(missing)
        self.unexpected_fields.extend(unexpected)
        if missing:
            self.reasons.append(missing_reason)
        if unexpected:
            self.reasons.append(unexpected_reason)

    def unique_reasons(self) -> list[str]:
        return list(dict.fromkeys(self.reasons))


@dataclass
class _ShardValidationState:
    validation: _ValidationState = field(default_factory=_ValidationState)
    seen: set[str] = field(default_factory=set)
    indexes: list[int] = field(default_factory=list)
    isolated_seen: set[str] = field(default_factory=set)
    membership_valid: bool = True


def release_correctness_nodeids(root: Path) -> tuple[str, ...]:
    """Return deterministic correctness membership from repository-owned classification."""
    from .qualification_classification import classification_map

    root = root.resolve()
    nodeids = tuple(nodeid for nodeid, _weight in _nodeids(root))
    classes = classification_map(root, nodeids)
    return tuple(
        nodeid for nodeid in nodeids if classes[nodeid]["kind"] == "release-correctness"
    )


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _packet_identity(domain: str, value: Mapping[str, object]) -> str:
    digest = hashlib.sha256()
    digest.update(domain.encode("utf-8"))
    digest.update(b"\0")
    digest.update(_canonical_bytes(value))
    return "sha256:" + digest.hexdigest()


def _implementation_identity() -> str:
    path = Path(__file__)
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_optional_artifact_identity(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not _SHA256_IDENTITY.fullmatch(normalized):
        raise ValueError("producer_artifact_identity must be sha256:<64 lowercase hex>")
    return normalized


def _test_files(root: Path) -> list[Path]:
    return sorted(
        (path for path in (root / "tests").glob("test_*.py") if path.is_file()),
        key=lambda path: path.as_posix(),
    )


def _class_test_nodeids(rel: str, node: ast.ClassDef) -> list[str]:
    if not node.name.startswith("Test"):
        return []
    return [
        f"{rel}::{node.name}::{child.name}"
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        and child.name.startswith("test_")
    ]


def _top_level_test_nodeids(rel: str, tree: ast.Module) -> list[str]:
    tests: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                tests.append(f"{rel}::{node.name}")
        elif isinstance(node, ast.ClassDef):
            tests.extend(_class_test_nodeids(rel, node))
    return tests


def _file_test_nodeids(root: Path, path: Path) -> list[tuple[str, int]]:
    snapshot = read_python_ast(path)
    rel = path.relative_to(root).as_posix()
    tests = _top_level_test_nodeids(rel, snapshot.tree)
    size = len(snapshot.source.encode("utf-8"))
    if not tests:
        return [(rel, max(1, size))]
    per_test = max(1, size // len(tests))
    return [(nodeid, per_test) for nodeid in tests]


def _nodeids(root: Path) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for path in _test_files(root):
        rows.extend(_file_test_nodeids(root, path))
    return rows


def selection_input_identity(root: Path) -> str:
    """Bind the exact bytes and static isolation rules that can change shard membership."""
    root = root.resolve()
    tests = []
    for path in _test_files(root):
        digest = hash_file(path)
        tests.append(
            {
                "path": path.relative_to(root).as_posix(),
                "digest": digest.as_key(),
            }
        )
    payload: dict[str, object] = {
        "schema": SELECTION_INPUT_SCHEMA,
        "algorithm": SHARD_ALGORITHM,
        "isolated_nodeids": list(ISOLATED_NODEIDS),
        "tests": tests,
    }
    return _packet_identity(SELECTION_INPUT_SCHEMA, payload)


_REPOSITORY_IDENTITY_EXCLUDED_DIRS = frozenset(
    {
        ".venv",
        ".hashmarks",
        ".pytest_cache",
        "__pycache__",
    }
)
_REPOSITORY_IDENTITY_EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo"})


def _is_excluded_identity_path(path: Path, excluded_roots: tuple[Path, ...]) -> bool:
    for excluded in excluded_roots:
        if path == excluded or excluded in path.parents:
            return True
    return False


def _repository_identity_files(
    root: Path,
    *,
    excluded_paths: tuple[Path, ...] = (),
) -> tuple[Path, ...]:
    root = root.resolve()
    excluded_roots = tuple(path.resolve() for path in excluded_paths)
    files: list[Path] = []
    # Prune runtime trees before traversal. Filtering after root.rglob() still walks
    # every .venv/.hashmarks/cache entry, which makes source identity pathologically
    # slow on WSL/Windows mounts even though those bytes can never own the identity.
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directory = Path(current)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in _REPOSITORY_IDENTITY_EXCLUDED_DIRS
            and not _is_excluded_identity_path(directory / name, excluded_roots)
        )
        for name in sorted(filenames):
            path = directory / name
            if path.suffix in _REPOSITORY_IDENTITY_EXCLUDED_SUFFIXES:
                continue
            if _is_excluded_identity_path(path, excluded_roots):
                continue
            if path.is_file():
                files.append(path)
    return tuple(sorted(files, key=lambda path: path.relative_to(root).as_posix()))


def repository_content_identity(
    root: Path,
    *,
    excluded_paths: tuple[Path, ...] = (),
) -> str:
    """Return extraction-stable canonical repository source identity.

    Runtime materialization such as .venv, .hashmarks, pytest caches and
    bytecode must never alter repository provenance.
    """
    root = root.resolve()
    digest = hashlib.sha256()
    digest.update(b"hashmarks.repository-content.v2\0")
    files = _repository_identity_files(root, excluded_paths=excluded_paths)
    for path in files:
        rel = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return f"sha256:{digest.hexdigest()}:{len(files)}"


def _validate_shard_count(shard_count: int, node_count: int) -> None:
    if shard_count < 1:
        raise ValueError("shard_count must be >= 1")
    if shard_count > node_count:
        raise ValueError("shard_count must not exceed test node count")


def _isolated_buckets(
    nodes: list[tuple[str, int]], shard_count: int
) -> tuple[list[list[str]], list[int], int]:
    by_node = dict(nodes)
    isolated = [nodeid for nodeid in ISOLATED_NODEIDS if nodeid in by_node]
    if len(isolated) >= shard_count:
        raise ValueError("shard_count must leave at least one non-isolated shard")
    return (
        [[nodeid] for nodeid in isolated],
        [by_node[nodeid] for nodeid in isolated],
        len(isolated),
    )


def _least_loaded_bucket(
    buckets: list[list[str]], weights: list[int], start: int, stop: int
) -> int:
    return min(
        range(start, stop),
        key=lambda index: (weights[index], len(buckets[index]), index),
    )


def _balanced_shard_buckets(
    nodes: list[tuple[str, int]], shard_count: int
) -> tuple[list[list[str]], list[int], int]:
    buckets, weights, isolated_count = _isolated_buckets(nodes, shard_count)
    while len(buckets) < shard_count:
        buckets.append([])
        weights.append(0)
    isolated = {nodeid for bucket in buckets[:isolated_count] for nodeid in bucket}
    for nodeid, weight in sorted(nodes, key=lambda row: (-row[1], row[0])):
        if nodeid in isolated:
            continue
        index = _least_loaded_bucket(buckets, weights, isolated_count, shard_count)
        buckets[index].append(nodeid)
        weights[index] += weight
    return buckets, weights, isolated_count


def _shard_rows(
    buckets: list[list[str]], weights: list[int], isolated_count: int
) -> list[dict[str, object]]:
    return [
        {
            "index": index,
            "nodeids": sorted(bucket),
            "weight_bytes": weights[index],
            "isolated_process": index < isolated_count,
        }
        for index, bucket in enumerate(buckets)
    ]


def plan(root: Path, shard_count: int) -> dict[str, object]:
    root = root.resolve()
    nodes = _nodeids(root)
    if not nodes:
        raise ValueError("no pytest tests found")
    _validate_shard_count(shard_count, len(nodes))
    buckets, weights, isolated_count = _balanced_shard_buckets(nodes, shard_count)
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "shard_count": shard_count,
        "test_node_count": len(nodes),
        "shards": _shard_rows(buckets, weights, isolated_count),
    }
    payload["plan_identity"] = (
        "sha256:" + hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    )
    return payload


def work_selection_envelope(
    root: Path,
    shard_count: int,
    *,
    producer_artifact_identity: str | None = None,
) -> dict[str, object]:
    """Bind one immutable v3 shard plan to its exact repository/producer evidence.

    This is repository-evidence transport only.  It contains no process command,
    timeout, retry, concurrency, scheduling, machine, or recovery policy.
    """
    root = root.resolve()
    artifact_identity = _validate_optional_artifact_identity(producer_artifact_identity)
    shard_plan = plan(root, shard_count)
    producer: dict[str, object] = {
        "name": "hashmarks",
        "version": __version__,
        "algorithm": SHARD_ALGORITHM,
        "implementation_identity": _implementation_identity(),
        "artifact_identity": artifact_identity,
    }
    repository: dict[str, object] = {
        "content_identity": repository_content_identity(root),
        "selection_input_identity": selection_input_identity(root),
    }
    payload: dict[str, object] = {
        "schema": ENVELOPE_SCHEMA,
        "producer": producer,
        "repository": repository,
        "selection": shard_plan,
        "authority": {
            "hashmarks": list(HASHMARKS_AUTHORITIES),
            "execution_layer": list(EXECUTION_LAYER_AUTHORITIES),
        },
    }
    payload["envelope_identity"] = _packet_identity(ENVELOPE_SCHEMA, payload)
    return payload


def _forbidden_execution_policy_paths(value: object, *, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            child_path = f"{path}.{key}"
            if key in _FORBIDDEN_EXECUTION_POLICY_KEYS:
                found.append(child_path)
            found.extend(_forbidden_execution_policy_paths(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(
                _forbidden_execution_policy_paths(child, path=f"{path}[{index}]")
            )
    return found


def _field_set_issues(
    value: Mapping[str, object],
    expected: frozenset[str],
    *,
    path: str,
) -> tuple[list[str], list[str]]:
    keys = {str(key) for key in value}
    missing = [f"{path}.{key}" for key in sorted(expected - keys)]
    unexpected = [f"{path}.{key}" for key in sorted(keys - expected)]
    return missing, unexpected


def node_membership_identity(nodeids: Sequence[str]) -> str:
    """Return a grouping-independent identity for one exact test-node membership set."""
    if isinstance(nodeids, (str, bytes)) or not nodeids:
        raise ValueError("nodeids must be a nonempty sequence")
    normalized: list[str] = []
    seen: set[str] = set()
    for nodeid in nodeids:
        if not isinstance(nodeid, str) or not nodeid.strip():
            raise ValueError("nodeids must be nonblank strings")
        if nodeid in seen:
            raise ValueError(f"nodeids contain duplicate member: {nodeid}")
        seen.add(nodeid)
        normalized.append(nodeid)
    payload: dict[str, object] = {
        "schema": MEMBERSHIP_SCHEMA,
        "nodeids": sorted(normalized),
    }
    return _packet_identity(MEMBERSHIP_SCHEMA, payload)


def selection_membership_identity(value: Mapping[str, object]) -> str:
    """Return an order/grouping-independent identity for the selected test-node set.

    External execution layers may regroup a timed-out shard, but omission or
    duplication changes/fails this identity.  Hashmarks does not perform the
    regrouping itself.
    """
    rows = value.get("shards")
    if not isinstance(rows, list) or not rows:
        raise ValueError("selection requires nonempty shards")
    nodeids: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("selection shard row must be an object")
        values = row.get("nodeids")
        if not isinstance(values, list) or not values:
            raise ValueError("selection shard requires nonempty nodeids")
        nodeids.extend(values)
    return node_membership_identity(nodeids)


def _positive_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
    return None


def _selection_rows(
    value: object, shard_count: int | None, state: _ShardValidationState
) -> list[object]:
    if not isinstance(value, list):
        state.validation.reasons.append("invalid-shards")
        return []
    if shard_count is not None and len(value) != shard_count:
        state.validation.reasons.append("shard-count-mismatch")
    state.membership_valid = bool(value)
    return value


def _selection_header(
    value: Mapping[str, object], state: _ShardValidationState
) -> tuple[int | None, int | None, list[object]]:
    check = state.validation
    check.add_fields(
        value,
        _SELECTION_FIELDS,
        path="$.selection",
        missing_reason="missing-selection-field",
        unexpected_reason="unexpected-selection-field",
    )
    if value.get("schema") != SCHEMA:
        check.reasons.append("unsupported-selection-schema")
    shard_count = _positive_int(value.get("shard_count"))
    test_node_count = _positive_int(value.get("test_node_count"))
    if shard_count is None:
        check.reasons.append("invalid-shard-count")
    if test_node_count is None:
        check.reasons.append("invalid-test-node-count")
    rows = _selection_rows(value.get("shards"), shard_count, state)
    return shard_count, test_node_count, rows


def _validate_nodeid_membership(
    nodeids: object, state: _ShardValidationState
) -> list[str] | None:
    if not isinstance(nodeids, list) or not nodeids:
        state.validation.reasons.append("invalid-shard-nodeids")
        state.membership_valid = False
        return None
    local: set[str] = set()
    for nodeid in nodeids:
        if not isinstance(nodeid, str) or not nodeid.strip():
            state.validation.reasons.append("invalid-nodeid")
            state.membership_valid = False
            continue
        if nodeid in local or nodeid in state.seen:
            state.validation.reasons.append("duplicate-nodeid")
            state.membership_valid = False
        local.add(nodeid)
        state.seen.add(nodeid)
    return nodeids


def _validate_shard_scalars(
    row: Mapping[str, object], state: _ShardValidationState
) -> bool | None:
    index = row.get("index")
    weight = row.get("weight_bytes")
    isolated = row.get("isolated_process")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        state.validation.reasons.append("invalid-shard-index")
    else:
        state.indexes.append(index)
    if not isinstance(weight, int) or isinstance(weight, bool) or weight < 1:
        state.validation.reasons.append("invalid-shard-weight")
    if not isinstance(isolated, bool):
        state.validation.reasons.append("invalid-isolated-process")
        return None
    return isolated


def _record_isolation(
    nodeids: list[str] | None, isolated: bool | None, state: _ShardValidationState
) -> None:
    if isolated is not True or nodeids is None:
        return
    if len(nodeids) != 1:
        state.validation.reasons.append("isolated-shard-must-be-singleton")
    else:
        state.isolated_seen.add(nodeids[0])


def _validate_shard_row(
    row: object, row_number: int, state: _ShardValidationState
) -> None:
    if not isinstance(row, Mapping):
        state.validation.reasons.append("invalid-shard-row")
        state.membership_valid = False
        return
    state.validation.add_fields(
        row,
        _SHARD_FIELDS,
        path=f"$.selection.shards[{row_number}]",
        missing_reason="missing-shard-field",
        unexpected_reason="unexpected-shard-field",
    )
    isolated = _validate_shard_scalars(row, state)
    nodeids = _validate_nodeid_membership(row.get("nodeids"), state)
    _record_isolation(nodeids, isolated, state)


def _validate_selection_totals(
    shard_count: int | None, test_node_count: int | None, state: _ShardValidationState
) -> None:
    if shard_count is not None and sorted(state.indexes) != list(range(shard_count)):
        state.validation.reasons.append("noncontiguous-shard-indexes")
    if test_node_count is not None and len(state.seen) != test_node_count:
        state.validation.reasons.append("test-node-count-mismatch")
    required = {nodeid for nodeid in ISOLATED_NODEIDS if nodeid in state.seen}
    if state.isolated_seen != required:
        state.validation.reasons.append("process-isolation-requirements-mismatch")


def _selection_identity(
    value: Mapping[str, object], state: _ShardValidationState
) -> str | None:
    try:
        expected = _plan_identity(value)
    except (TypeError, ValueError):
        state.validation.reasons.append("selection-plan-not-canonical-json")
        return None
    if value.get("plan_identity") != expected:
        state.validation.reasons.append("selection-plan-identity-mismatch")
    return expected


def _selection_membership(
    value: Mapping[str, object], state: _ShardValidationState
) -> str | None:
    if not state.membership_valid or not state.seen:
        return None
    try:
        return selection_membership_identity(value)
    except ValueError:
        return None


def validate_test_shard_plan(value: Mapping[str, object]) -> dict[str, object]:
    """Strictly validate v3 selection semantics without launching pytest."""
    value, root_reasons = require_mapping_for_validation(
        value, reason="invalid-selection-plan"
    )
    state = _ShardValidationState()
    state.validation.reasons.extend(root_reasons)
    shard_count, test_node_count, rows = _selection_header(value, state)
    for row_number, row in enumerate(rows):
        _validate_shard_row(row, row_number, state)
    _validate_selection_totals(shard_count, test_node_count, state)
    expected = _selection_identity(value, state)
    membership_identity = _selection_membership(value, state)
    check = state.validation
    return {
        "valid": not check.reasons,
        "reasons": check.unique_reasons(),
        "expected_plan_identity": expected,
        "membership_identity": membership_identity,
        "missing_fields": check.missing_fields,
        "unexpected_fields": check.unexpected_fields,
    }


def _envelope_identity(
    value: Mapping[str, object], state: _ValidationState
) -> str | None:
    state.add_fields(
        value,
        _ENVELOPE_FIELDS,
        path="$",
        missing_reason="missing-envelope-field",
        unexpected_reason="unexpected-envelope-field",
    )
    if value.get("schema") != ENVELOPE_SCHEMA:
        state.reasons.append("unsupported-schema")
    claimed = str(value.get("envelope_identity") or "")
    body = dict(value)
    body.pop("envelope_identity", None)
    try:
        expected = _packet_identity(ENVELOPE_SCHEMA, body)
    except (TypeError, ValueError):
        state.reasons.append("envelope-not-canonical-json")
        return None
    if claimed != expected:
        state.reasons.append("envelope-identity-mismatch")
    return expected


def _valid_sha_identity(value: object) -> bool:
    return isinstance(value, str) and _SHA256_IDENTITY.fullmatch(value) is not None


def _validate_producer_identities(
    value: Mapping[str, object], state: _ValidationState
) -> None:
    if not _valid_sha_identity(value.get("implementation_identity")):
        state.reasons.append("invalid-producer-implementation-identity")
    artifact = value.get("artifact_identity")
    if artifact is not None and not _valid_sha_identity(artifact):
        state.reasons.append("invalid-producer-artifact-identity")


def _validate_producer(value: object, state: _ValidationState) -> None:
    if not isinstance(value, Mapping):
        state.reasons.append("invalid-producer")
        return
    state.add_fields(
        value,
        _PRODUCER_FIELDS,
        path="$.producer",
        missing_reason="missing-producer-field",
        unexpected_reason="unexpected-producer-field",
    )
    if value.get("name") != "hashmarks":
        state.reasons.append("invalid-producer-name")
    version = value.get("version")
    if not isinstance(version, str) or not version.strip():
        state.reasons.append("invalid-producer-version")
    if value.get("algorithm") != SHARD_ALGORITHM:
        state.reasons.append("unsupported-producer-algorithm")
    _validate_producer_identities(value, state)


def _validate_repository(value: object, state: _ValidationState) -> None:
    if not isinstance(value, Mapping):
        state.reasons.append("invalid-repository-binding")
        return
    state.add_fields(
        value,
        _REPOSITORY_FIELDS,
        path="$.repository",
        missing_reason="missing-repository-field",
        unexpected_reason="unexpected-repository-field",
    )
    content = value.get("content_identity")
    if not isinstance(content, str) or not _REPOSITORY_CONTENT_IDENTITY.fullmatch(
        content
    ):
        state.reasons.append("invalid-repository-content-identity")
    selection_input = value.get("selection_input_identity")
    if not isinstance(selection_input, str) or not _SHA256_IDENTITY.fullmatch(
        selection_input
    ):
        state.reasons.append("invalid-selection-input-identity")


def _validate_selection(value: object, state: _ValidationState) -> dict[str, object]:
    if not isinstance(value, Mapping):
        state.reasons.append("invalid-selection")
        return {
            "valid": False,
            "reasons": ["invalid-selection"],
            "membership_identity": None,
            "missing_fields": [],
            "unexpected_fields": [],
        }
    result = validate_test_shard_plan(value)
    state.reasons.extend(str(reason) for reason in result["reasons"])
    state.missing_fields.extend(str(path) for path in result.get("missing_fields", []))
    state.unexpected_fields.extend(
        str(path) for path in result.get("unexpected_fields", [])
    )
    return result


def _validate_authority(value: object, state: _ValidationState) -> None:
    if not isinstance(value, Mapping):
        state.reasons.append("invalid-authority-declaration")
        return
    state.add_fields(
        value,
        _AUTHORITY_FIELDS,
        path="$.authority",
        missing_reason="missing-authority-field",
        unexpected_reason="unexpected-authority-field",
    )
    if value.get("hashmarks") != list(HASHMARKS_AUTHORITIES):
        state.reasons.append("hashmarks-authority-mismatch")
    if value.get("execution_layer") != list(EXECUTION_LAYER_AUTHORITIES):
        state.reasons.append("execution-layer-authority-mismatch")


def validate_work_selection_envelope(value: Mapping[str, object]) -> dict[str, object]:
    """Strictly validate repository-work-selection evidence without admitting execution."""
    value, root_reasons = require_mapping_for_validation(
        value, reason="invalid-work-selection-envelope"
    )
    state = _ValidationState()
    state.reasons.extend(root_reasons)
    expected = _envelope_identity(value, state)
    _validate_producer(value.get("producer"), state)
    _validate_repository(value.get("repository"), state)
    plan_validation = _validate_selection(value.get("selection"), state)
    _validate_authority(value.get("authority"), state)
    forbidden_paths = _forbidden_execution_policy_paths(value)
    if forbidden_paths:
        state.reasons.append("execution-policy-field-present")
    return {
        "valid": not state.reasons,
        "reasons": state.unique_reasons(),
        "expected_envelope_identity": expected,
        "membership_identity": plan_validation.get("membership_identity"),
        "forbidden_execution_policy_paths": forbidden_paths,
        "missing_fields": list(dict.fromkeys(state.missing_fields)),
        "unexpected_fields": list(dict.fromkeys(state.unexpected_fields)),
    }


def _unbound_repository_result(structural: Mapping[str, object]) -> dict[str, object]:
    return {
        **structural,
        "repository_bound": False,
        "current_repository_content_identity": None,
        "current_selection_input_identity": None,
        "current_plan_identity": None,
    }


def _binding_inputs(
    value: Mapping[str, object],
) -> tuple[Mapping[str, object], Mapping[str, object], int] | None:
    repository = value.get("repository")
    selection = value.get("selection")
    if not isinstance(repository, Mapping) or not isinstance(selection, Mapping):
        return None
    shard_count = _positive_int(selection.get("shard_count"))
    if shard_count is None:
        return None
    return repository, selection, shard_count


def _current_selection_plan(
    root: Path, shard_count: int, reasons: list[str]
) -> dict[str, object] | None:
    try:
        return plan(root, shard_count)
    except ValueError:
        reasons.append("current-selection-unavailable")
        return None


def _binding_mismatch_reasons(
    repository: Mapping[str, object],
    selection: Mapping[str, object],
    current_content: str,
    current_input: str,
    current_plan: Mapping[str, object] | None,
) -> list[str]:
    reasons: list[str] = []
    if repository.get("content_identity") != current_content:
        reasons.append("repository-content-identity-mismatch")
    if repository.get("selection_input_identity") != current_input:
        reasons.append("selection-input-identity-mismatch")
    if current_plan is not None and selection != current_plan:
        reasons.append("selection-does-not-reproduce")
    return reasons


def validate_work_selection_repository_binding(
    root: Path,
    value: Mapping[str, object],
) -> dict[str, object]:
    """Re-prove one structurally valid envelope against current repository bytes."""
    value, _root_reasons = require_mapping_for_validation(
        value, reason="invalid-work-selection-envelope"
    )
    structural = validate_work_selection_envelope(value)
    inputs = _binding_inputs(value)
    if inputs is None:
        return _unbound_repository_result(structural)
    repository, selection, shard_count = inputs
    root = root.resolve()
    current_content = repository_content_identity(root)
    current_input = selection_input_identity(root)
    reasons = list(structural["reasons"])
    current_plan = _current_selection_plan(root, shard_count, reasons)
    reasons.extend(
        _binding_mismatch_reasons(
            repository, selection, current_content, current_input, current_plan
        )
    )
    reasons = list(dict.fromkeys(str(reason) for reason in reasons))
    return {
        **structural,
        "valid": not reasons,
        "reasons": reasons,
        "repository_bound": not reasons,
        "current_repository_content_identity": current_content,
        "current_selection_input_identity": current_input,
        "current_plan_identity": current_plan.get("plan_identity")
        if current_plan is not None
        else None,
    }


def _plan_identity(payload: Mapping[str, object]) -> str:
    body = {
        "schema": payload.get("schema"),
        "shard_count": payload.get("shard_count"),
        "test_node_count": payload.get("test_node_count"),
        "shards": payload.get("shards"),
    }
    return "sha256:" + hashlib.sha256(_canonical_bytes(body)).hexdigest()


def _validate_shard_index(shard_count: int, shard_index: int) -> None:
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError(f"shard_index must be between 0 and {shard_count - 1}")


def _selected_shard(
    payload: Mapping[str, object], shard_count: int, shard_index: int
) -> tuple[str, ...]:
    _validate_shard_index(shard_count, shard_index)
    row = payload["shards"][shard_index]  # type: ignore[index]
    return tuple(row["nodeids"])  # type: ignore[index]


def select(root: Path, shard_count: int, shard_index: int) -> tuple[str, ...]:
    _validate_shard_index(shard_count, shard_index)
    return _selected_shard(plan(root, shard_count), shard_count, shard_index)


def _emit_shard_plan(payload: Mapping[str, object], *, as_json: bool) -> None:
    """Render immutable shard membership for the selection CLI."""
    if as_json:
        print(json.dumps(payload, sort_keys=True))  # noqa: T201 - intentional command output
        return
    for row in payload["shards"]:  # type: ignore[union-attr]
        print(  # noqa: T201 - intentional command output
            f"{row['index']}: {len(row['nodeids'])} tests / {row['weight_bytes']} source-weight bytes"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic pytest test-node shard selector"
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--shards", type=int, default=16)
    parser.add_argument("--shard", type=int)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--envelope",
        action="store_true",
        help="emit a generation-bound repository-work-selection envelope around the unchanged v3 plan",
    )
    parser.add_argument(
        "--producer-artifact-identity",
        help="optional sha256:<hex> identity for the exact released Hashmarks artifact producing the envelope",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if args.envelope:
        if args.shard is not None:
            raise SystemExit("--envelope cannot be combined with --shard")
        payload = work_selection_envelope(
            root,
            args.shards,
            producer_artifact_identity=args.producer_artifact_identity,
        )
        print(  # noqa: T201 - intentional command output
            json.dumps(payload, sort_keys=True)
            if args.json
            else json.dumps(payload, indent=2, sort_keys=True)
        )
        return 0
    payload = plan(root, args.shards)
    if args.shard is None:
        _emit_shard_plan(payload, as_json=args.json)
        return 0
    try:
        selected = _selected_shard(payload, args.shards, args.shard)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.json:
        print(  # noqa: T201 - intentional command output
            json.dumps(
                {
                    "schema": SCHEMA,
                    "plan_identity": payload["plan_identity"],
                    "shard": args.shard,
                    "nodeids": selected,
                },
                sort_keys=True,
            )
        )
    else:
        print(" ".join(selected))  # noqa: T201 - intentional command output
    return 0


__all__ = [
    "ENVELOPE_SCHEMA",
    "EXECUTION_LAYER_AUTHORITIES",
    "HASHMARKS_AUTHORITIES",
    "ISOLATED_NODEIDS",
    "SCHEMA",
    "SELECTION_INPUT_SCHEMA",
    "MEMBERSHIP_SCHEMA",
    "SHARD_ALGORITHM",
    "plan",
    "repository_content_identity",
    "select",
    "selection_input_identity",
    "selection_membership_identity",
    "node_membership_identity",
    "validate_test_shard_plan",
    "validate_work_selection_repository_binding",
    "validate_work_selection_envelope",
    "work_selection_envelope",
]
