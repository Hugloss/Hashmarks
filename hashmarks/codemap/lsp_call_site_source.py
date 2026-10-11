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
    if not site_ranges:
        basis["state"] = "empty-call-sites"
    elif not all(_inside(caller["range"], site) for site in site_ranges):
        basis["state"] = "outside-caller-item"
    elif not all(
        _range_exists(source, site, encoding=capture["position_encoding"])
        for site in site_ranges
    ):
        basis["state"] = "invalid-position"
    else:
        basis["state"] = "source-range-matching"


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
    path = uri_member(caller["uri"], resolver.codemap.workspace)
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
