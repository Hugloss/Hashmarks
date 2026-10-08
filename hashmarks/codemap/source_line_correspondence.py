"""Pure, request-local source line correspondence projections.

Canonical read admission, revision, generation and policy belong to CodeMap's
repository member observer. No file access, second index or persistent state.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import cast

from hashmarks.operation_contract import operation_schema


def validated_source_lines(lines: Sequence[int]) -> list[int]:
    """Fail before source reads on invalid explicit line requests."""
    if (
        isinstance(lines, (str, bytes))
        or len(lines) > 32
        or any(type(line) is not int or line < 1 for line in lines)
    ):
        raise ValueError("lines must be up to 32 positive integers")
    return sorted(set(lines))


def source_shape(raw: bytes, *, long_line_threshold: int) -> dict[str, object]:
    """Measure physical source properties over the canonical stable byte capture."""
    parts = raw.split(b"\n")
    physical = parts[:-1] if raw.endswith(b"\n") else parts if raw else []
    widths = [len(part) for part in physical]
    return {
        "bytes": len(raw),
        "physical_lines": len(physical),
        "lf_terminators": raw.count(b"\n"),
        "crlf_terminators": sum(part.endswith(b"\r") for part in parts[:-1]),
        "final_lf": raw.endswith(b"\n"),
        "utf8_bom": raw.startswith(b"\xef\xbb\xbf"),
        "maximum_physical_line_bytes": max(widths, default=0),
        "long_line_threshold_bytes": long_line_threshold,
        "long_line_count": sum(width > long_line_threshold for width in widths),
        "basis": "stable-canonical-member-bytes",
    }


def source_line_anchors(
    raw: bytes,
    *,
    requested: Sequence[int],
    member: Mapping[str, object],
) -> tuple[list[dict[str, object]], str]:
    """Prove exact physical-line multiplicity within one fully observed member."""
    physical = raw.split(b"\n")
    if raw.endswith(b"\n"):
        physical.pop()
    counts = Counter(line for line in physical if line.strip())
    rows: list[dict[str, object]] = []
    coverage = "complete"
    for line in requested:
        if line > len(physical) or not physical[line - 1].strip():
            coverage = "unknown"
            rows.append(
                {
                    "line": line,
                    "state": "unknown",
                    "reason": "line-unavailable-or-blank",
                }
            )
            continue
        content = physical[line - 1]
        rows.append(
            {
                "line": line,
                "state": "observed",
                "path": member["path"],
                "member_revision": member["member_revision"],
                "line_sha256": sha256(
                    b"hashmarks.source-line.v1\0" + content
                ).hexdigest(),
                "matching_physical_lines": counts[content],
                "line_bytes": len(content),
                "basis": "exact-physical-line-bytes",
            }
        )
    return rows, coverage


def _source_endpoint_reason(
    diagnostic: Mapping[str, object],
    source: Mapping[str, object],
) -> str | None:
    member = source.get("member")
    if not isinstance(member, Mapping):
        return "missing-canonical-member"
    required = (
        source.get("schema") == operation_schema("source_observation", "member"),
        source.get("availability") == "observed",
        source.get("freshness") in {"current", "unknown"},
        member.get("state") == "known-present",
        source.get("line_coverage") == "complete",
        source.get("completeness") == "complete",
        bool(source.get("observation_identity")),
        bool(member.get("member_revision")),
        source.get("generation") == diagnostic.get("codemap_generation"),
    )
    if not all(required):
        return "source-observation-not-current-complete-and-bound"
    return None


def _diagnostic_scope_reason(
    diagnostic: Mapping[str, object], path: object
) -> str | None:
    collection = diagnostic.get("collection")
    if (
        not isinstance(collection, Mapping)
        or collection.get("state") not in {"fresh-complete", "fresh-partial"}
        or diagnostic.get("outcome") not in {"pass", "fail"}
    ):
        return "diagnostic-collection-not-qualified"
    scope = diagnostic.get("scope_paths")
    if not isinstance(scope, list) or path not in scope:
        return "diagnostic-scope-unbound"
    return None


def _diagnostic_context_reason(
    before: Mapping[str, object], after: Mapping[str, object]
) -> str | None:
    required = ("repository_identity", "producer", "environment_identity")
    if any(
        not before.get(key) or before.get(key) != after.get(key) for key in required
    ):
        return "diagnostic-context-changed"
    return None


def _source_lineage_reason(
    before_source: Mapping[str, object],
    after_source: Mapping[str, object],
) -> str | None:
    prior = cast("Mapping[str, object]", before_source["member"])
    later = cast("Mapping[str, object]", after_source["member"])
    if prior.get("path") != later.get("path"):
        return "different-source-path"
    if prior["member_revision"] == later["member_revision"]:
        return "identical-member-revision"
    if before_source.get("generation") == after_source.get("generation"):
        return "source-change-not-generation-bound"
    return None


def _source_pair_reason(
    before_diagnostic: Mapping[str, object],
    after_diagnostic: Mapping[str, object],
    before_source: Mapping[str, object],
    after_source: Mapping[str, object],
) -> str | None:
    for diagnostic, source in (
        (before_diagnostic, before_source),
        (after_diagnostic, after_source),
    ):
        reason = _source_endpoint_reason(diagnostic, source)
        if reason is not None:
            return reason
    reason = _source_lineage_reason(before_source, after_source)
    if reason is not None:
        return reason
    reason = _diagnostic_context_reason(before_diagnostic, after_diagnostic)
    if reason is not None:
        return reason
    for diagnostic in (before_diagnostic, after_diagnostic):
        member = cast("Mapping[str, object]", before_source["member"])
        reason = _diagnostic_scope_reason(diagnostic, member["path"])
        if reason is not None:
            return reason
    return None


def _anchor_for(
    observation: Mapping[str, object], line: object
) -> Mapping[str, object] | None:
    anchors = observation.get("line_anchors")
    if not isinstance(anchors, list):
        return None
    matches = [
        row for row in anchors if isinstance(row, Mapping) and row.get("line") == line
    ]
    return matches[0] if len(matches) == 1 else None


def _indexed_diagnostics(
    packet: Mapping[str, object],
) -> dict[object, Mapping[str, object]]:
    rows = packet.get("diagnostics")
    if not isinstance(rows, list):
        return {}
    return {
        row["identity"]: row
        for row in rows
        if isinstance(row, Mapping) and "identity" in row
    }


def _candidate_diagnostic_reason(
    prior: Mapping[str, object] | None,
    later: Mapping[str, object] | None,
    path: object,
) -> str | None:
    if not isinstance(prior, Mapping) or not isinstance(later, Mapping):
        return "candidate-path-not-source-bound"
    if prior.get("path") != path or later.get("path") != path:
        return "candidate-path-not-source-bound"
    column = prior.get("column")
    if type(column) is not int or column < 1 or later.get("column") != column:
        return "diagnostic-column-not-preserved"
    return None


def _candidate_anchor_reason(
    previous: Mapping[str, object] | None,
    current: Mapping[str, object] | None,
    before_source: Mapping[str, object],
    after_source: Mapping[str, object],
) -> str | None:
    if (
        not isinstance(previous, Mapping)
        or not isinstance(current, Mapping)
        or previous.get("state") != "observed"
        or current.get("state") != "observed"
    ):
        return "source-line-anchor-unavailable"
    for anchor, source in ((previous, before_source), (current, after_source)):
        member = cast("Mapping[str, object]", source["member"])
        if anchor.get("member_revision") != member.get("member_revision") or anchor.get(
            "path"
        ) != member.get("path"):
            return "source-anchor-binding-mismatch"
    if (
        previous.get("matching_physical_lines") != 1
        or current.get("matching_physical_lines") != 1
    ):
        return "source-line-not-unique"
    if previous.get("line_sha256") != current.get("line_sha256") or not previous.get(
        "line_sha256"
    ):
        return "source-line-bytes-changed"
    return None


def _candidate_correspondence(
    candidate: Mapping[str, object],
    *,
    old: Mapping[object, Mapping[str, object]],
    new: Mapping[object, Mapping[str, object]],
    before_source: Mapping[str, object],
    after_source: Mapping[str, object],
    pair_reason: str | None,
) -> tuple[bool, dict[str, object]]:
    before_id = candidate.get("before_identity")
    after_id = candidate.get("after_identity")
    member = before_source.get("member")
    path = member.get("path") if isinstance(member, Mapping) else None
    previous = _anchor_for(before_source, candidate.get("before_line"))
    current = _anchor_for(after_source, candidate.get("after_line"))
    reason = pair_reason or _candidate_diagnostic_reason(
        old.get(before_id), new.get(after_id), path
    )
    if reason is None:
        reason = _candidate_anchor_reason(
            previous, current, before_source, after_source
        )
    entry = {"before_identity": before_id, "after_identity": after_id}
    if reason is not None:
        return False, {**entry, "reason": reason}
    old_anchor = cast("Mapping[str, object]", previous)
    new_anchor = cast("Mapping[str, object]", current)
    return True, {
        **entry,
        "path": path,
        "before_line": candidate["before_line"],
        "after_line": candidate["after_line"],
        "before_member_revision": old_anchor["member_revision"],
        "after_member_revision": new_anchor["member_revision"],
        "source_line_sha256": old_anchor["line_sha256"],
        "basis": "unique-exact-physical-line-bytes-and-same-column",
        "state": "source-line-correspondence",
        "diagnostic_identity_authority": False,
        "repository_freshness": {
            "before": before_source.get("freshness"),
            "after": after_source.get("freshness"),
        },
    }


def diagnostic_line_correspondence(
    *,
    candidates: Sequence[Mapping[str, object]],
    before_diagnostic: Mapping[str, object],
    after_diagnostic: Mapping[str, object],
    before_source: Mapping[str, object],
    after_source: Mapping[str, object],
) -> dict[str, object]:
    """Relate uniquely preserved moved physical lines, not diagnostic identity."""
    reason = _source_pair_reason(
        before_diagnostic, after_diagnostic, before_source, after_source
    )
    old = _indexed_diagnostics(before_diagnostic)
    new = _indexed_diagnostics(after_diagnostic)
    supported: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    for candidate in candidates:
        matched, row = _candidate_correspondence(
            candidate,
            old=old,
            new=new,
            before_source=before_source,
            after_source=after_source,
            pair_reason=reason,
        )
        if matched:
            supported.append(row)
        else:
            unresolved.append(row)
    return {
        "schema": "hashmarks.diagnostic-source-line-correspondence.v1",
        "supported": supported,
        "unresolved": unresolved,
        "basis": "caller-retained-canonical-source-observations",
        "diagnostic_identity_authority": False,
        "execution_effect": "none",
    }
