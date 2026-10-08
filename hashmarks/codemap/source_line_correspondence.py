"""Pure, request-local source line correspondence projections.

Canonical read admission, revision, generation and policy belong to CodeMap's
repository member observer. No file access, second index or persistent state.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import cast


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
            rows.append({"line": line, "state": "unknown",
                         "reason": "line-unavailable-or-blank"})
            continue
        content = physical[line - 1]
        rows.append({
            "line": line,
            "state": "observed",
            "path": member["path"],
            "member_revision": member["member_revision"],
            "line_sha256": sha256(b"hashmarks.source-line.v1\0" + content).hexdigest(),
            "matching_physical_lines": counts[content],
            "line_bytes": len(content),
            "basis": "exact-physical-line-bytes",
        })
    return rows, coverage


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
        member = source.get("member")
        if not isinstance(member, Mapping):
            return "missing-canonical-member"
        if (
            source.get("schema") != "hashmarks.source-observation.v1"
            or source.get("availability") != "observed"
            or source.get("freshness") != "current"
            or source.get("line_coverage") != "complete"
            or source.get("completeness") != "complete"
            or not source.get("observation_identity")
            or not member.get("member_revision")
            or source.get("generation") != diagnostic.get("codemap_generation")
        ):
            return "source-observation-not-current-complete-and-bound"
    prior = cast("Mapping[str, object]", before_source["member"])
    later = cast("Mapping[str, object]", after_source["member"])
    if prior.get("path") != later.get("path"):
        return "different-source-path"
    if prior["member_revision"] == later["member_revision"]:
        return "identical-member-revision"
    for diagnostic in (before_diagnostic, after_diagnostic):
        coll = diagnostic.get("collection")
        if (
            not isinstance(coll, Mapping)
            or coll.get("state") not in {"fresh-complete", "fresh-partial"}
            or diagnostic.get("outcome") not in {"pass", "fail"}
        ):
            return "diagnostic-collection-not-qualified"
        scope = diagnostic.get("scope_paths")
        if not isinstance(scope, list) or prior["path"] not in scope:
            return "diagnostic-scope-unbound"
    if (
        not before_diagnostic.get("repository_identity")
        or before_diagnostic.get("repository_identity")
        != after_diagnostic.get("repository_identity")
        or not before_diagnostic.get("producer")
        or before_diagnostic.get("producer") != after_diagnostic.get("producer")
        or not before_diagnostic.get("environment_identity")
        or before_diagnostic.get("environment_identity")
        != after_diagnostic.get("environment_identity")
    ):
        return "diagnostic-context-changed"
    return None


def _anchor_for(
    observation: Mapping[str, object], line: object
) -> Mapping[str, object] | None:
    anchors = observation.get("line_anchors")
    if not isinstance(anchors, list):
        return None
    matches = [
        row for row in anchors
        if isinstance(row, Mapping) and row.get("line") == line
    ]
    return matches[0] if len(matches) == 1 else None


def diagnostic_line_correspondence(
    *,
    candidates: Sequence[Mapping[str, object]],
    before_diagnostic: Mapping[str, object],
    after_diagnostic: Mapping[str, object],
    before_source: Mapping[str, object],
    after_source: Mapping[str, object],
) -> dict[str, object]:
    """Report uniquely preserved moved physical lines, not diagnostic identity."""
    reason = _source_pair_reason(
        before_diagnostic, after_diagnostic, before_source, after_source
    )
    prior_member = before_source.get("member")
    prior_path = prior_member.get("path") if isinstance(prior_member, Mapping) else None
    supported: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    before_rows = before_diagnostic.get("diagnostics")
    after_rows = after_diagnostic.get("diagnostics")
    old = {
        row["identity"]: row for row in before_rows
        if isinstance(row, Mapping) and "identity" in row
    } if isinstance(before_rows, list) else {}
    new = {
        row["identity"]: row for row in after_rows
        if isinstance(row, Mapping) and "identity" in row
    } if isinstance(after_rows, list) else {}
    for candidate in candidates:
        before_id = candidate.get("before_identity")
        after_id = candidate.get("after_identity")
        old_row = old.get(before_id)
        new_row = new.get(after_id)
        match_reason = reason
        previous = _anchor_for(before_source, candidate.get("before_line"))
        current = _anchor_for(after_source, candidate.get("after_line"))
        if match_reason is None and (
            not isinstance(old_row, Mapping)
            or not isinstance(new_row, Mapping)
            or old_row.get("path") != prior_path
            or new_row.get("path") != prior_path
        ):
            match_reason = "candidate-path-not-source-bound"
        if match_reason is None and (
            not isinstance(old_row, Mapping)
            or not isinstance(new_row, Mapping)
            or not isinstance(old_row.get("column"), int)
            or old_row.get("column") != new_row.get("column")
            or cast("int", old_row["column"]) < 1
        ):
            match_reason = "diagnostic-column-not-preserved"
        if match_reason is None and (
            previous is None
            or current is None
            or previous.get("state") != "observed"
            or current.get("state") != "observed"
        ):
            match_reason = "source-line-anchor-unavailable"
        if match_reason is None and (
            previous.get("member_revision")
            != cast("Mapping[str, object]", before_source["member"]).get("member_revision")
            or current.get("member_revision")
            != cast("Mapping[str, object]", after_source["member"]).get("member_revision")
            or previous.get("path") != prior_path
            or current.get("path") != prior_path
        ):
            match_reason = "source-anchor-binding-mismatch"
        if match_reason is None and (
            previous.get("matching_physical_lines") != 1
            or current.get("matching_physical_lines") != 1
        ):
            match_reason = "source-line-not-unique"
        if match_reason is None and (
            previous.get("line_sha256") != current.get("line_sha256")
            or not previous.get("line_sha256")
        ):
            match_reason = "source-line-bytes-changed"
        entry = {"before_identity": before_id, "after_identity": after_id}
        if match_reason is None:
            supported.append({
                **entry,
                "path": prior_path,
                "before_line": candidate["before_line"],
                "after_line": candidate["after_line"],
                "before_member_revision": previous["member_revision"],
                "after_member_revision": current["member_revision"],
                "source_line_sha256": previous["line_sha256"],
                "basis": "unique-exact-physical-line-bytes-and-same-column",
                "state": "source-line-correspondence",
                "diagnostic_identity_authority": False,
            })
        else:
            unresolved.append({**entry, "reason": match_reason})
    return {
        "schema": "hashmarks.diagnostic-source-line-correspondence.v1",
        "supported": supported,
        "unresolved": unresolved,
        "basis": "caller-retained-canonical-source-observations",
        "diagnostic_identity_authority": False,
        "execution_effect": "none",
    }
