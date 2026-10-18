"""B01–B05: exact changed-line observations composed with existing impact owners.

The caller supplies edited ranges. Hashmarks proves only range/source/index
correspondence, never that an edit occurred, call path executed, or test covers it.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, TypedDict

from hashmarks.paths import normalize_relative_path
from hashmarks.python_ast_cache import read_python_ast

from .change_decorator_evidence import observe_python_decorator_associations
from .function_boundary_syntax import observe_function_boundaries

if TYPE_CHECKING:
    from .repository_source import RepositorySource

MAX_CHANGED_SPANS = 16
MAX_CHANGED_SPAN_LINES = 128
MAX_OVERLAPPING_SYMBOLS = 32
MAX_FUNCTION_BOUNDARY_SOURCE_BYTES = 1_048_576


def _python_tree_input_reason(path: str, raw: bytes) -> str | None:
    if not path.endswith(".py"):
        return "not-python"
    if len(raw) > MAX_FUNCTION_BOUNDARY_SOURCE_BYTES:
        return "function-boundary-source-over-bound"
    # Physical-line observations use LF boundaries. Standalone CR cannot be
    # silently reinterpreted as those same source locations.
    if b"\r" in raw.replace(b"\r\n", b""):
        return "physical-line-encoding-unqualified"
    return None


def _current_python_tree(
    source: RepositorySource, path: str, raw: bytes
) -> tuple[ast.Module | None, str | None]:
    """Use the shared parser cache only when it matches canonical source bytes."""
    reason = _python_tree_input_reason(path, raw)
    if reason is not None:
        return None, reason
    member_source = source._repository_member_source(path)
    if isinstance(member_source, dict):
        return None, "canonical-member-unavailable"
    try:
        snapshot = read_python_ast(member_source.path)
        if snapshot.source != raw.decode("utf-8").replace("\r\n", "\n"):
            return None, "ast-snapshot-source-mismatch"
        return snapshot.tree, None
    except (OSError, UnicodeError, SyntaxError, ValueError, RecursionError):
        return None, "python-function-syntax-unavailable"


def _function_boundary_observation(
    tree: ast.Module | None,
    reason: str | None,
    candidates: Sequence[Mapping[str, Any]],
    span: ChangedLineSpan,
) -> dict[str, Any] | None:
    if reason == "not-python":
        return None
    if tree is None:
        return {
            "state": "unresolved",
            "reason": reason,
            "observations": [],
            "negative_evidence_admissible": False,
        }
    try:
        return observe_function_boundaries(tree, candidates, span)
    except (RecursionError, ValueError):
        return {
            "state": "unresolved",
            "reason": "function-boundary-observation-unavailable",
            "observations": [],
            "negative_evidence_admissible": False,
        }


def _checked_line_bounds(start: object, end: object) -> tuple[int, int]:
    if type(start) is not int or type(end) is not int:
        raise ValueError("changed line span requires integer line bounds")
    if not 1 <= start <= end or end - start + 1 > MAX_CHANGED_SPAN_LINES:
        raise ValueError("changed line span requires 1–128 positive lines")
    return start, end


class ChangedLineSpan(TypedDict):
    path: str
    start_line: int
    end_line: int


def _admit_span(raw: object, allowed: set[str]) -> ChangedLineSpan:
    if not isinstance(raw, Mapping) or set(raw) != {"path", "start_line", "end_line"}:
        raise ValueError("changed line span requires path/start_line/end_line")
    if not isinstance(raw["path"], str):
        raise ValueError("changed line span path must be a string")
    path = normalize_relative_path(raw["path"], allow_root=False)
    start, end = _checked_line_bounds(raw["start_line"], raw["end_line"])
    if path not in allowed:
        raise ValueError("changed line span must refer to a reported changed path")
    return {"path": path, "start_line": start, "end_line": end}


def normalize_changed_line_spans(
    spans: object,
    changed_paths: Sequence[str],
) -> tuple[ChangedLineSpan, ...]:
    """Fail before refresh on untrusted range shapes and out-of-scope members."""
    if spans is None:
        return ()
    if not isinstance(spans, list) or len(spans) > MAX_CHANGED_SPANS:
        raise ValueError("changed_line_spans must be a list of at most 16 ranges")
    selected: list[ChangedLineSpan] = []
    seen: set[tuple[str, int, int]] = set()
    for raw in spans:
        span = _admit_span(raw, set(changed_paths))
        key = (span["path"], span["start_line"], span["end_line"])
        if key in seen:
            raise ValueError("changed line spans must be distinct")
        seen.add(key)
        selected.append(span)
    return tuple(
        sorted(
            selected, key=lambda row: (row["path"], row["start_line"], row["end_line"])
        )
    )


def _unavailable(
    request: Mapping[str, Any], member: Mapping[str, object], reason: str
) -> dict[str, object]:
    return {
        **request,
        "state": "unresolved",
        "reason": reason,
        "member_state": member.get("state", "unknown"),
        "symbol_coverage": "unknown",
        "symbols": [],
        "negative_evidence_admissible": False,
    }


def _direct_symbol(
    row: Mapping[str, object], span: ChangedLineSpan
) -> dict[str, object]:
    start, end = row["start_line"], row["end_line"]
    assert isinstance(start, int) and isinstance(end, int)
    subject = f"{span['path']}::{row['qualname']}"
    return {
        "subject": subject,
        "path": span["path"],
        "name": row["name"],
        "qualname": row["qualname"],
        "kind": row["kind"],
        "start_line": start,
        "end_line": end,
        "overlap": {
            "start_line": max(start, span["start_line"]),
            "end_line": min(end, span["end_line"]),
        },
        "relationship_detail": {"target": subject, "result_mode": "relationships"},
        "basis": "direct-indexed-symbol-range-intersection",
        "semantic_impact": "not-asserted",
    }


def observe_changed_line_spans(
    source: RepositorySource, spans: Sequence[ChangedLineSpan]
) -> dict[str, object]:
    """Compose source revision with a bounded canonical index range query."""
    rows: list[dict[str, object]] = []
    for span in spans:
        path = str(span["path"])
        member, raw = source.member(path, include_bytes=True)
        if (
            member.get("state") != "known-present"
            or member.get("index_state") != "indexed"
            or raw is None
        ):
            rows.append(
                _unavailable(span, member, str(member.get("reason") or "not-indexed"))
            )
            continue
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            rows.append(_unavailable(span, member, "not-utf8-text"))
            continue
        line_count = len(source._physical_lines(raw))
        if span["end_line"] > line_count:
            rows.append(_unavailable(span, member, "span-outside-current-source"))
            continue
        candidates = source.store.symbols_overlapping_lines(
            path,
            span["start_line"],
            span["end_line"],
            limit=MAX_OVERLAPPING_SYMBOLS + 1,
        )
        tree, syntax_reason = _current_python_tree(source, path, raw)
        function_boundaries = _function_boundary_observation(
            tree, syntax_reason, candidates[:MAX_OVERLAPPING_SYMBOLS], span
        )
        decorator_evidence = observe_python_decorator_associations(
            source.store,
            path,
            raw,
            {"start_line": span["start_line"], "end_line": span["end_line"]},
            allow_source_syntax=member.get("evidence_visibility") == "source",
            tree=tree,
        )
        # Reading outside the indexed source is not proof of its correspondence.
        after, _ = source.member(path, include_bytes=True)
        if (
            after.get("state") != "known-present"
            or after.get("member_revision") != member.get("member_revision")
            or after.get("index_state") != "indexed"
        ):
            rows.append(_unavailable(span, after, "source-changed-during-observation"))
            continue
        truncated = len(candidates) > MAX_OVERLAPPING_SYMBOLS
        rows.append(
            {
                **span,
                "state": "source-index-correspondence-observed",
                "member_state": "known-present",
                "member_revision": member["member_revision"],
                "evidence_visibility": member["evidence_visibility"],
                "symbol_coverage": "bounded"
                if truncated
                else "complete-index-range-query",
                "symbol_observed_count": len(candidates),
                "symbol_retained_count": min(len(candidates), MAX_OVERLAPPING_SYMBOLS),
                "symbols": [
                    _direct_symbol(candidate, span)
                    for candidate in candidates[:MAX_OVERLAPPING_SYMBOLS]
                ],
                "negative_evidence_admissible": False,
                **(
                    {"function_boundary_syntax": function_boundaries}
                    if function_boundaries is not None
                    else {}
                ),
                **(
                    {"decorator_associations": decorator_evidence}
                    if decorator_evidence is not None
                    else {}
                ),
            }
        )
    return {
        "input_authority": "caller-reported-line-spans",
        "correspondence": "source-revision-and-indexed-line-intersection-only",
        "runtime_impact": "not-asserted",
        "verification_coverage": "not-asserted",
        "negative_evidence_admissible": False,
        "bounds": {
            "spans": MAX_CHANGED_SPANS,
            "lines_per_span": MAX_CHANGED_SPAN_LINES,
            "symbols_per_span": MAX_OVERLAPPING_SYMBOLS,
        },
        "observations": rows,
    }
