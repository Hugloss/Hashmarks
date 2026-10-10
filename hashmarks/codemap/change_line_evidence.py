"""B01–B05: exact changed-line observations composed with existing impact owners.

The caller supplies edited ranges. Hashmarks proves only range/source/index
correspondence, never that an edit occurred, call path executed, or test covers it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from hashmarks.paths import normalize_relative_path

if TYPE_CHECKING:
    from .engine import CodeMap

MAX_CHANGED_SPANS = 16
MAX_CHANGED_SPAN_LINES = 128
MAX_OVERLAPPING_SYMBOLS = 32


def _checked_line_bounds(start: object, end: object) -> tuple[int, int]:
    if type(start) is not int or type(end) is not int:
        raise ValueError("changed line span requires integer line bounds")
    if not 1 <= start <= end or end - start + 1 > MAX_CHANGED_SPAN_LINES:
        raise ValueError("changed line span requires 1–128 positive lines")
    return start, end


def _admit_span(raw: object, allowed: set[str]) -> dict[str, Any]:
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
) -> tuple[dict[str, Any], ...]:
    """Fail before refresh on untrusted range shapes and out-of-scope members."""
    if spans is None:
        return ()
    if not isinstance(spans, list) or len(spans) > MAX_CHANGED_SPANS:
        raise ValueError("changed_line_spans must be a list of at most 16 ranges")
    selected: list[dict[str, Any]] = []
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
    row: Mapping[str, object], span: Mapping[str, Any]
) -> dict[str, object]:
    start, end = int(row["start_line"]), int(row["end_line"])
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
    codemap: CodeMap, spans: Sequence[Mapping[str, Any]]
) -> dict[str, object]:
    """Compose source revision with a bounded canonical index range query."""
    rows: list[dict[str, object]] = []
    for span in spans:
        path = str(span["path"])
        member, raw = codemap._repository_member_observation(path, include_bytes=True)
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
        line_count = len(codemap._physical_lines(raw))
        if span["end_line"] > line_count:
            rows.append(_unavailable(span, member, "span-outside-current-source"))
            continue
        candidates = codemap.store.symbols_overlapping_lines(
            path,
            span["start_line"],
            span["end_line"],
            limit=MAX_OVERLAPPING_SYMBOLS + 1,
        )
        # Reading outside the indexed source is not proof of its correspondence.
        after, _ = codemap._repository_member_observation(path, include_bytes=True)
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
