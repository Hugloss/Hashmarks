"""Request-local, source-bound qualification of LSP call-site ranges.

Call hierarchy declaration locators and fromRanges are different authorities.
Neither launches an LSP client nor upgrades producer claims to source facts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .semantic_relationship_source import (
    RelationshipSourceResolver,
    character_offset,
    uri_member,
)


def _inside(item_range: Mapping[str, Any], call_range: Mapping[str, Any]) -> bool:
    def key(position: Mapping[str, int]) -> tuple[int, int]:
        return position["line"], position["character"]

    return key(item_range["start"]) <= key(call_range["start"]) and key(
        call_range["end"]
    ) <= key(item_range["end"])


def _range_exists(source: str, row: Mapping[str, Any], *, encoding: str) -> bool:
    lines = re.split(r"\r\n|\r|\n", source)
    codec = "utf-16-le" if encoding == "utf-16" else encoding
    for key in ("start", "end"):
        position = row[key]
        line = position["line"]
        if line >= len(lines):
            return False
        if character_offset(lines[line], position["character"], codec) is None:
            return False
    return True


def _declaration_context(
    path: str,
    caller: Mapping[str, Any],
    capture: Mapping[str, Any],
    site_ranges: list[dict[str, Any]],
    resolver: RelationshipSourceResolver,
    source: str,
) -> dict[str, object]:
    """Observe lexical containment independently of the producer's item range."""
    context: dict[str, object] = {
        "state": "unresolved",
        "authority": "indexed-lexical-range-correspondence-only",
        "negative_evidence_admissible": False,
    }
    member, _raw = resolver.member(path)
    indexed = resolver.reads.file_row(path)
    if indexed is None or indexed.get("file_digest") != member.get("member_revision"):
        context["state"] = "index-revision-unqualified"
        return context
    resolution = resolver.candidates(
        path,
        {**caller["selectionRange"], "position_encoding": capture["position_encoding"]},
        capture["documents"][path],
        name=caller["name"],
    )
    if resolution["state"] != "unique-candidate":
        return context
    candidate = resolution["candidates"][0]
    declaration = candidate["declaration"]
    start, end = declaration["start_line"], declaration["end_line"]
    lines = re.split(r"\r\n|\r|\n", source)
    if (
        type(start) is not int
        or type(end) is not int
        or not 1 <= start <= end <= len(lines)
    ):
        return context
    encoding = capture["position_encoding"]
    codec = "utf-16-le" if encoding == "utf-16" else encoding
    end_units = (
        len(lines[end - 1])
        if encoding == "utf-32"
        else len(lines[end - 1].encode(codec)) // (2 if encoding == "utf-16" else 1)
    )
    scope = {
        "start": {"line": start - 1, "character": 0},
        "end": {"line": end - 1, "character": end_units},
    }
    return {
        **context,
        "state": "within-declaration-range"
        if all(_inside(scope, site) for site in site_ranges)
        else "outside-declaration-range",
        "path": path,
        "symbol_id": candidate["symbol_id"],
        "declaration_range": scope,
        "source_binding": candidate["source_binding"],
    }


def _range_geometry(
    source: str,
    caller: Mapping[str, Any],
    site_ranges: list[dict[str, Any]],
    encoding: str,
) -> tuple[str, bool]:
    """Keep producer-range containment separate from source-coordinate validity."""
    if not site_ranges:
        return "empty-call-sites", False
    valid = all(_range_exists(source, site, encoding=encoding) for site in site_ranges)
    if not all(_inside(caller["range"], site) for site in site_ranges):
        return "outside-caller-item", valid
    return ("source-range-matching", True) if valid else ("invalid-position", False)


def _source_state(
    path: str,
    caller: Mapping[str, Any],
    capture: Mapping[str, Any],
    site_ranges: list[dict[str, Any]],
    resolver: RelationshipSourceResolver,
    basis: dict[str, Any],
) -> None:
    """Refine a caller-revision claim into an explicitly qualified range state."""
    snapshot = capture["documents"].get(path)
    if snapshot is None:
        basis["state"] = "snapshot-unavailable"
        return
    binding = resolver.binding(path, snapshot)
    basis["source_binding"] = binding
    if binding["state"] != "matching":
        basis["state"] = (
            "revision-different" if binding["state"] == "different" else "unknown"
        )
        return
    _member, raw = resolver.member(path)
    try:
        source = (
            raw.decode(snapshot.get("text_encoding", "utf-8"))
            if raw is not None
            else None
        )
    except (UnicodeError, LookupError):
        source = None
    if source is None:
        return
    basis["state"], valid = _range_geometry(
        source, caller, site_ranges, capture["position_encoding"]
    )
    if valid:
        basis["declaration_context"] = _declaration_context(
            path, caller, capture, site_ranges, resolver, source
        )


def qualify_call_site_source(
    capture: Mapping[str, Any],
    row: Mapping[str, Any],
    resolver: RelationshipSourceResolver,
) -> dict[str, Any]:
    """Bind fromRanges to the *caller* snapshot, never the callee declaration."""
    caller = (
        row["item"]
        if capture["request"]["method"] == "callHierarchy/incomingCalls"
        else capture["request"]["params"]["item"]
    )
    path = uri_member(caller["uri"], resolver.source.workspace)
    basis: dict[str, Any] = {
        "path": path,
        "ranges": row["fromRanges"],
        "position_encoding": capture["position_encoding"],
        "source_binding": None,
        "state": "unknown",
        "authority": "caller-supplied-call-site-source-correspondence-only",
        "negative_evidence_admissible": False,
    }
    if path is None:
        basis["state"] = "outside-repository"
    elif not resolver.admitted(path):
        basis["state"] = "unadmitted"
    else:
        _source_state(path, caller, capture, row["fromRanges"], resolver, basis)
    return basis
