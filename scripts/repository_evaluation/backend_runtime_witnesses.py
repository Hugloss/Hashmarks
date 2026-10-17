"""Independent runtime/source oracles and retained-byte debugging witnesses.

This development QA owner never runs a backend scenario or the observer. Source
declarations are frozen before product observation; native runtime names and
repository symbol display names remain separate representations.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import TypedDict

from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.python_ast_cache import read_python_ast
from hashmarks.test_shards import repository_content_identity

from .backend_corpus import confined_file
from .backend_grading import FactObservation
from .backend_witnesses import captured_fact_witnesses
from .common import canonical_sha256
from .fact_grading import _json_equal, grade_facts


class RuntimeCorrelationRequest(TypedDict):
    bundles: list[dict[str, object]]
    include_relationships: bool


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("runtime oracle requires a JSON object")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("runtime oracle requires a nonempty string")
    return value


def _line(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("runtime oracle requires positive integer source lines")
    return value


def _declarations(
    tree: ast.AST, frame: Mapping[str, object]
) -> list[dict[str, object]]:
    # Python's code-object <locals> marker is not a lexical declaration name.
    # Removing that marker still requires exact scope, code-first-line and span.
    expected = _text(frame.get("qualname")).replace(".<locals>.", ".")
    first, line = _line(frame.get("code_first_line")), _line(frame.get("line"))
    result: list[dict[str, object]] = []

    def visit(node: ast.AST, scope: tuple[str, ...]) -> None:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = (*scope, node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorated_first = min(
                    [node.lineno, *(item.lineno for item in node.decorator_list)]
                )
                if (
                    ".".join(scope) == expected
                    and node.name == frame.get("name")
                    and decorated_first == first
                    and node.lineno <= line <= (node.end_lineno or node.lineno)
                ):
                    result.append(
                        {
                            "path": frame["path"],
                            "name": node.name,
                            "start_line": node.lineno,
                            "end_line": node.end_lineno,
                        }
                    )
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(tree, ())
    return result


def freeze_runtime_oracles(
    source: Path, capture: Mapping[str, object], *, repository: str, bundle_id: str
) -> dict[str, object]:
    """Bind every captured frame to independent source, without product output."""
    identity = repository_content_identity(source)
    if capture.get("source_identity") != identity:
        raise ValueError("runtime capture differs from the selected source archive")
    frames = capture.get("frames")
    if not isinstance(frames, list):
        raise ValueError("runtime capture requires an explicit frame array")
    if capture.get("stage") not in {"before", "after"}:
        raise ValueError("runtime capture requires an exact source stage")
    oracles: list[dict[str, object]] = []
    for ordinal, value in enumerate(frames):
        frame = _object(value)
        path = confined_file(source, _text(frame.get("path")))
        revision = hash_file(path, domain=FILE_DOMAIN).hash
        if revision != frame.get("source_revision"):
            raise ValueError("runtime frame differs from its source member")
        snapshot = read_python_ast(path)
        if max(_line(frame.get("line")), _line(frame.get("code_first_line"))) > len(
            snapshot.source.splitlines()
        ):
            raise ValueError("runtime frame lies outside the source member")
        declarations = _declarations(snapshot.tree, frame)
        oracles.append(
            {
                "anchor_id": f"frame-{ordinal}",
                "runtime_frame": dict(frame),
                "source_declaration": declarations[0]
                if len(declarations) == 1
                else None,
                "declaration_state": "exact"
                if len(declarations) == 1
                else "unsupported",
            }
        )
    if repository_content_identity(source) != identity:
        raise ValueError("source archive changed while freezing runtime oracles")
    return {
        "repository": _text(repository),
        "bundle_id": _text(bundle_id),
        "workflow": _text(capture.get("workflow")),
        "stage": _text(capture.get("stage")),
        "source_identity": identity,
        "runtime_capture_sha256": canonical_sha256(capture),
        "frames": oracles,
        "scope": "all captured repository frames; unsupported callables retained",
        "reviewed": False,
    }


def _scoped_check(
    identifier: str,
    anchor: str,
    pointer: str,
    expected: dict[str, object],
    path: str,
) -> dict[str, object]:
    return {
        "id": identifier,
        "pointer": "/bundles/0/anchors/*",
        "predicate": "includes_scoped_record",
        "value": {
            "scope": {"anchor_id": anchor},
            "pointer": pointer,
            "record": expected,
        },
        "support": "supported",
        "source_paths": [path],
    }


def runtime_frame_checks(
    oracles: Mapping[str, object], *, invalidated: bool = False
) -> list[dict[str, object]]:
    """Exact declaration identity is path/name/span, independently scope-proven.

    A repository's overload-disambiguated display qualname need not equal a
    Python code-object qualname. Neither short-name equality nor containment
    alone proves correspondence. Unsupported frames remain in the denominator.
    """
    frames = _oracle_frames(oracles)
    if not frames:
        return []
    checks: list[dict[str, object]] = [
        {
            "id": "runtime-bundle",
            "pointer": "/bundles/*/bundle_id",
            "predicate": "ordered_values_equal",
            "value": [_text(oracles.get("bundle_id"))],
            "support": "supported",
        },
        {
            "id": "runtime-anchor-membership",
            "pointer": "/bundles/0/anchors/*/anchor_id",
            "predicate": "ordered_values_equal",
            "value": sorted(_text(row["anchor_id"]) for row in frames),
            "support": "supported",
        },
    ]
    checks.extend(
        {
            "id": "runtime-" + field,
            "pointer": "/" + field,
            "predicate": "equals",
            "value": expected,
            "support": "supported",
            "authority_check": True,
        }
        for field, expected in (
            ("authority", "repository-intelligence-only"),
            ("interpretation_authority", "consumer-owned"),
            ("execution_effect", "none"),
            ("causation", "not-inferred"),
            ("storage", "request-scoped-not-persisted"),
        )
    )
    for value in frames:
        row = _object(value)
        anchor = _text(row.get("anchor_id"))
        frame = _object(row.get("runtime_frame"))
        path = _text(frame.get("path"))
        checks.append(
            _scoped_check(
                anchor + ":source-equivalence",
                anchor,
                "/source_equivalence",
                {"state": "mismatch" if invalidated else "proven"},
                path,
            )
        )
        if not invalidated and row.get("source_declaration") is not None:
            checks.extend(
                [
                    _scoped_check(
                        anchor + ":resolution",
                        anchor,
                        "/resolution",
                        {"state": "resolved-unique", "repository_path": path},
                        path,
                    ),
                    _scoped_check(
                        anchor + ":callable",
                        anchor,
                        "/resolution/candidates/*",
                        _object(row["source_declaration"]),
                        path,
                    ),
                ]
            )
    return checks


def _oracle_frames(oracles: Mapping[str, object]) -> list[dict[str, object]]:
    frames = oracles.get("frames")
    if not isinstance(frames, list):
        raise ValueError("runtime oracle requires explicit frame membership")
    rows = [_object(value) for value in frames]
    anchors = [_text(row.get("anchor_id")) for row in rows]
    if len(set(anchors)) != len(anchors):
        raise ValueError("runtime oracle contains duplicate frame membership")
    return rows


def retained_runtime_witnesses(
    output: Path,
    oracles: Mapping[str, object],
    context: FactObservation,
    *,
    invalidated: bool = False,
    family: str = "",
) -> list[dict[str, object]]:
    """Regrade existing API/CLI/MCP artifacts using the shared witness owner."""
    checks = runtime_frame_checks(oracles, invalidated=invalidated)
    if not checks:
        return []  # A success control supplies no frame-correspondence proof.
    context = runtime_witness_context(oracles, context)
    return captured_fact_witnesses(output, family, {"checks": checks}, context)


def runtime_witness_context(
    oracles: Mapping[str, object], context: FactObservation
) -> FactObservation:
    """Qualify runtime source/context binding once for all retained surfaces."""
    if context.stage != oracles.get("stage") or context.unit_id != oracles.get(
        "workflow"
    ):
        raise ValueError("runtime witness has a different workflow or source stage")
    expected = {}
    for row in _oracle_frames(oracles):
        frame = _object(row.get("runtime_frame"))
        path, revision = _text(frame.get("path")), _text(frame.get("source_revision"))
        if path in expected and expected[path] != revision:
            raise ValueError("runtime oracle contains conflicting member revisions")
        expected[path] = revision
    for binding in context.source_bindings:
        if binding["path"] in expected and (
            binding["repository"] != oracles.get("repository")
            or binding["revision"] != expected[binding["path"]]
            or binding.get("stage", context.stage) != context.stage
        ):
            raise ValueError(
                "runtime witness has a different repository source binding"
            )
    return replace(
        context,
        source_bindings=tuple(
            binding
            for binding in context.source_bindings
            if binding["path"] in expected
        ),
    )


def runtime_correlation_request(
    capture: Mapping[str, object], bundle_id: str, *, invalidated: bool = False
) -> RuntimeCorrelationRequest:
    """Project external frame claims only; source oracles never enter product input."""
    frames = capture.get("frames")
    if not isinstance(frames, list):
        raise ValueError("runtime capture requires an explicit frame array")
    anchors = []
    for ordinal, value in enumerate(frames):
        frame = _object(value)
        anchors.append(
            {
                "anchor_id": f"frame-{ordinal}",
                "path": _text(frame.get("path")),
                "line": _line(frame.get("line")),
                "member_revision": "0" * 64
                if invalidated
                else _text(frame.get("source_revision")),
                "metadata": {
                    "runtime_qualname": frame.get("qualname"),
                    "code_first_line": frame.get("code_first_line"),
                    **{
                        key: frame[key]
                        for key in ("exception_chain_index", "exception_type")
                        if key in frame
                    },
                },
            }
        )
    return {
        "bundles": [
            {
                "bundle_id": _text(bundle_id),
                "producer": {
                    "kind": "external-runtime-producer-claim",
                    "capture_sha256": canonical_sha256(capture),
                },
                "scope": {
                    "kind": "one supplied invocation; captured repository frames only"
                },
                "completeness": "complete",
                "truncation": "complete",
                "anchors": anchors,
            }
        ],
        "include_relationships": False,
    }


def validate_runtime_stage(
    source: Path,
    request: object,
    oracle: object,
    *,
    repository: str,
    workflow: str,
    stage: str,
) -> None:
    """Reprove frozen capture/source/check membership before campaign admission."""
    supplied, expected = _object(request), _object(oracle)
    if set(supplied) != {"bundle_id", "capture"}:
        raise ValueError("runtime observation requires one bundle and external capture")
    capture = _object(supplied["capture"])
    if capture.get("workflow") != workflow or capture.get("stage") != stage:
        raise ValueError("runtime capture has a different workflow or source stage")
    frozen = freeze_runtime_oracles(
        source, capture, repository=repository, bundle_id=_text(supplied["bundle_id"])
    )
    frozen["checks"] = {
        variant: runtime_frame_checks(frozen, invalidated=variant == "invalidated")
        for variant in ("qualified", "invalidated")
    }
    if not _json_equal(frozen, expected):
        raise ValueError("runtime oracle differs from independent capture/source proof")


def runtime_frame_observations(
    packet: dict[str, object], oracles: Mapping[str, object], *, stage: str
) -> list[dict[str, object]]:
    """Count frozen frames once; transport copies never increase breadth."""
    if stage not in {"before", "after"} or stage != oracles.get("stage"):
        raise ValueError("runtime frame observations require an exact source stage")
    frames = _oracle_frames(oracles)
    checks = runtime_frame_checks(oracles)
    results = []
    for value in frames:
        row = _object(value)
        anchor = _text(row.get("anchor_id"))
        selected = [
            check
            for check in checks
            if _text(check["id"]).startswith("runtime-")
            or _text(check["id"]).startswith(anchor + ":")
        ]
        observed = grade_facts(anchor, {"packet": packet}, {"checks": selected})
        results.append(
            {
                "unit_id": stage + ":" + anchor,
                "correspondence": row.get("source_declaration") is not None
                and observed["classification"] == "PASS",
                "declaration_state": row["declaration_state"],
            }
        )
    return results
