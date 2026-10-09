"""Source-local qualification for direct producer relationship endpoints."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import unquote, urlsplit

from hashmarks.digest import FILE_DOMAIN, hash_bytes
from hashmarks.paths import normalize_relative_path

from .semantic_relationship_model import CANDIDATE_LIMIT, content_identity

if TYPE_CHECKING:
    from .engine import CodeMap


def uri_member(uri: object, workspace: Any) -> str | None:
    if not isinstance(uri, str):
        raise ValueError("LSP location URI must be a string")
    value = urlsplit(uri)
    if value.scheme != "file" or value.netloc not in ("", "localhost"):
        return None
    if value.query or value.fragment or "\x00" in unquote(value.path):
        raise ValueError("LSP file URI is malformed")
    from pathlib import Path

    try:
        relative = Path(unquote(value.path)).relative_to(workspace)
    except ValueError:
        return None
    return normalize_relative_path(relative.as_posix(), allow_root=False)


def validated_position(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != {"line", "character"}:
        raise ValueError("relationship position requires line and character")
    if any(type(value[key]) is not int or not 0 <= value[key] < 2**31 for key in value):
        raise ValueError("relationship positions must be nonnegative LSP integers")
    return dict(value)


def validated_range(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"start", "end"}:
        raise ValueError("relationship range requires start and end")
    start, end = validated_position(value["start"]), validated_position(value["end"])
    if (start["line"], start["character"]) > (end["line"], end["character"]):
        raise ValueError("relationship range is reversed")
    return {"start": start, "end": end}


def character_offset(text: str, units: int, encoding: str) -> int | None:
    total = 0
    for index, character in enumerate(text):
        if total == units:
            return index
        total += (
            len(character.encode(encoding)) // (2 if encoding == "utf-16-le" else 1)
            if encoding != "utf-32"
            else 1
        )
        if total > units:
            return None
    return len(text) if total == units else None


class RelationshipSourceResolver:
    """Reuse one canonical stable member read for each admitted path."""

    def __init__(self, codemap: CodeMap) -> None:
        self.codemap = codemap
        self.members: dict[str, tuple[dict[str, Any], bytes | None]] = {}

    def admitted(self, path: str) -> bool:
        row = self.codemap._session_file_row(path)
        return (
            row is not None
            and row.get("evidence_visibility") != "deny"
            and self.codemap._path_admitted_for_analysis(path)
            and self.codemap.policy.decide(path).evidence_visibility.value != "deny"
        )

    def member(self, path: str) -> tuple[dict[str, Any], bytes | None]:
        if path not in self.members:
            self.members[path] = self.codemap._bounded_source_observation(
                path, 1_048_576
            )
        return self.members[path]

    def binding(self, path: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        member, raw = self.member(path)
        representation = snapshot.get("revision_kind", "member-bytes")
        observed = member.get("member_revision") if raw is not None else None
        if raw is not None and representation == "utf8-document-text":
            try:
                text = raw.decode(snapshot.get("text_encoding", "utf-8"))
                observed = hash_bytes(text.encode("utf-8"), domain=FILE_DOMAIN).hash
            except (UnicodeError, LookupError):
                observed = None
        claimed = snapshot.get("revision")
        state = (
            "unknown"
            if claimed is None or observed is None
            else "matching"
            if claimed == observed
            else "different"
        )
        return {
            "path": path,
            "state": state,
            "claimed_revision": claimed,
            "observed_revision": observed,
            "representation": representation,
            "provenance": snapshot.get("provenance"),
            "observed_at_import": snapshot.get("observed_at_import"),
            "source_observation_identity": content_identity(
                {"member": member, "generation": self.codemap.store.generation()}
            ),
            "member_state": member.get("state"),
            "reason": member.get("reason"),
            "authority": "producer-claim-to-stable-member-correspondence-only",
        }

    def position_qualified(
        self,
        path: str,
        locator: Mapping[str, Any],
        snapshot: Mapping[str, Any],
        name: str,
    ) -> bool:
        position = locator["start"]
        encoding = locator.get("position_encoding", "unknown")
        _member, raw = self.member(path)
        if raw is None or encoding not in ("utf-8", "utf-16", "utf-32"):
            return False
        try:
            # LSP lines end at CR, LF or CRLF, not Unicode paragraph separators.
            lines = re.split(
                r"\r\n|\r|\n", raw.decode(snapshot.get("text_encoding", "utf-8"))
            )
        except (UnicodeError, LookupError):
            return False
        line = position["line"]
        if line >= len(lines):
            return False
        codec = "utf-16-le" if encoding == "utf-16" else encoding
        offset = character_offset(lines[line], position["character"], codec)
        return offset is not None and _name_at_offset(lines[line], name, offset)

    def candidates(
        self,
        path: str,
        locator: Mapping[str, Any] | None,
        snapshot: Mapping[str, Any],
        *,
        name: str | None = None,
    ) -> dict[str, Any]:
        if not self.admitted(path) or locator is None:
            return {
                "state": "unresolved",
                "candidates": [],
                "truncated": False,
                "negative_evidence_admissible": False,
            }
        position = locator["start"]
        rows = [
            row
            for row in cast(
                "list[dict[str, Any]]", self.codemap._session_symbols_for_path(path)
            )
            if int(row["start_line"]) == position["line"] + 1
            and (name is None or row["name"] == name)
            and row.get("evidence_visibility") != "deny"
        ]
        truncated = len(rows) > CANDIDATE_LIMIT
        binding = self.binding(path, snapshot)
        qualified = (
            len(rows) == 1
            and binding["state"] == "matching"
            and self.position_qualified(path, locator, snapshot, str(rows[0]["name"]))
        )
        return {
            "state": "incomplete-candidate-search"
            if truncated
            else "unique-candidate"
            if len(rows) == 1 and qualified
            else "ambiguous-candidates"
            if len(rows) > 1
            else "unresolved",
            "candidates": [
                {
                    "symbol_id": f"{path}::{row['qualname']}",
                    "path": path,
                    "line": row["start_line"],
                    "declaration": {
                        key: row.get(key)
                        for key in (
                            "name",
                            "qualname",
                            "kind",
                            "start_line",
                            "end_line",
                        )
                    },
                    "source_binding": binding,
                }
                for row in rows[:CANDIDATE_LIMIT]
            ],
            "truncated": truncated,
            "source_binding": binding,
            "negative_evidence_admissible": False,
        }


def _name_at_offset(text: str, name: str, offset: int) -> bool:
    end = offset + len(name)
    return (
        text[offset:end] == name
        and (offset == 0 or not (text[offset - 1].isalnum() or text[offset - 1] == "_"))
        and (end == len(text) or not (text[end].isalnum() or text[end] == "_"))
    )
