from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hashmarks.digest import FILE_DOMAIN, hash_bytes

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class ScipRelationship:
    """A direct producer-asserted SCIP symbol relationship."""

    kind: str
    target_symbol: str


@dataclass(frozen=True)
class ScipOccurrence:
    path: str
    symbol: str
    display_name: str
    line: int
    end_line: int
    definition: bool
    relationships: tuple[ScipRelationship, ...] = ()
    relationships_truncated: bool = False
    relationship_only: bool = False
    locator: dict[str, Any] | None = None
    document_metadata: dict[str, Any] | None = None
    declaration_metadata: dict[str, Any] | None = None


def _field(
    value: dict[str, Any], camel: str, snake: str | None = None, default=None
) -> Any:
    if camel in value:
        return value[camel]
    if snake and snake in value:
        return value[snake]
    return default


def _range_lines(occurrence: dict[str, Any]) -> tuple[int, int]:
    single = _field(occurrence, "singleLineRange", "single_line_range")
    if isinstance(single, dict):
        line = int(_field(single, "line", default=0)) + 1
        return line, line
    multi = _field(occurrence, "multiLineRange", "multi_line_range")
    if isinstance(multi, dict):
        return int(_field(multi, "startLine", "start_line", 0)) + 1, int(
            _field(multi, "endLine", "end_line", 0)
        ) + 1
    packed = occurrence.get("range")
    if isinstance(packed, list) and len(packed) in {3, 4}:
        start = int(packed[0]) + 1
        end = start if len(packed) == 3 else int(packed[2]) + 1
        return start, end
    return 1, 1


def _display_name(symbol: str) -> str:
    if symbol.startswith("local "):
        return symbol
    # SCIP descriptors end in / # . () etc. Prefer the final backtick-escaped
    # or identifier-like descriptor name without attempting to reimplement the
    # full SCIP symbol grammar.
    backticks = re.findall(r"`([^`]*)`", symbol)
    tail = symbol.rsplit(" ", 1)[-1]
    descriptor_tail = tail.rsplit("`", 1)[-1] if "`" in tail else tail
    parts = re.findall(
        r"([A-Za-z_$][A-Za-z0-9_$-]*)\s*(?:\([^)]*\)|[#./:])", descriptor_tail
    )
    if parts:
        return parts[-1]
    clean = re.sub(r"\([^)]*\)|[#./:]", " ", descriptor_tail).strip().split()
    if clean:
        return clean[-1]
    return backticks[-1] if backticks else symbol


_SCIP_RELATION_FLAGS = (
    ("isReference", "is_reference", "reference"),
    ("isImplementation", "is_implementation", "implementation"),
    ("isTypeDefinition", "is_type_definition", "type_definition"),
    ("isDefinition", "is_definition", "definition"),
)


def _scip_relation_rows(info: dict[str, Any]):
    """Yield only flags explicitly asserted by this SCIP SymbolInformation."""
    for relation in info.get("relationships") or ():
        if not isinstance(relation, dict):
            continue
        target = str(relation.get("symbol") or "")
        if not target:
            continue
        for camel, snake, kind in _SCIP_RELATION_FLAGS:
            if _field(relation, camel, snake, False) is True:
                yield ScipRelationship(kind=kind, target_symbol=target)


def _scip_document_relationships(
    document: dict[str, Any],
) -> dict[str, tuple[ScipRelationship, ...]]:
    """Retain a deterministic, bounded prefix per producer symbol."""
    collected: dict[str, set[ScipRelationship]] = {}
    for info in document.get("symbols") or ():
        if not isinstance(info, dict):
            continue
        owner = str(info.get("symbol") or "")
        if not owner:
            continue
        bucket = collected.setdefault(owner, set())
        for row in _scip_relation_rows(info):
            bucket.add(row)
            if len(bucket) > 65:
                bucket.remove(
                    max(bucket, key=lambda item: (item.kind, item.target_symbol))
                )
    return {
        symbol: tuple(sorted(rows, key=lambda item: (item.kind, item.target_symbol)))
        for symbol, rows in collected.items()
    }


def _scip_occurrence(
    path: str,
    occurrence: dict[str, Any],
    relationships: dict[str, tuple[ScipRelationship, ...]],
    information: dict[str, dict[str, Any]],
    document_metadata: dict[str, Any],
) -> ScipOccurrence:
    symbol = str(occurrence["symbol"])
    roles = int(_field(occurrence, "symbolRoles", "symbol_roles", 0) or 0)
    start, end = _range_lines(occurrence)
    is_definition = bool(roles & 0x1)
    direct = relationships.get(symbol, ()) if is_definition else ()
    return ScipOccurrence(
        path=path,
        symbol=symbol,
        display_name=str(
            information.get(symbol, {}).get("display_name") or _display_name(symbol)
        ),
        line=start,
        end_line=end,
        definition=is_definition,
        relationships=direct[:64],
        relationships_truncated=len(direct) > 64,
        locator=_scip_locator(occurrence, document_metadata["position_encoding"]),
        document_metadata=document_metadata,
        declaration_metadata=information.get(symbol),
    )


def _scip_locator(occurrence: dict[str, Any], encoding: str) -> dict[str, Any]:
    packed = occurrence.get("range")
    if isinstance(packed, list) and len(packed) in (3, 4):
        end_line = packed[0] if len(packed) == 3 else packed[2]
        end_character = packed[2] if len(packed) == 3 else packed[3]
        return {
            "start": {"line": int(packed[0]), "character": int(packed[1])},
            "end": {"line": int(end_line), "character": int(end_character)},
            "position_encoding": encoding,
        }
    start, end = _range_lines(occurrence)
    single = _field(occurrence, "singleLineRange", "single_line_range", {})
    multi = _field(occurrence, "multiLineRange", "multi_line_range", {})
    detail = single if single else multi
    return {
        "start": {
            "line": start - 1,
            "character": int(_field(detail, "startCharacter", "start_character", 0)),
        },
        "end": {
            "line": end - 1,
            "character": int(_field(detail, "endCharacter", "end_character", 0)),
        },
        "position_encoding": encoding,
    }


def _scip_document_metadata(document: dict[str, Any]) -> dict[str, Any]:
    encoding = _field(document, "positionEncoding", "position_encoding", 0)
    encodings = {
        1: "utf-8",
        2: "utf-16",
        3: "utf-32",
        "UTF8CodeUnitOffsetFromLineStart": "utf-8",
        "UTF16CodeUnitOffsetFromLineStart": "utf-16",
        "UTF32CodeUnitOffsetFromLineStart": "utf-32",
    }
    text = document.get("text")
    return {
        "position_encoding": encodings.get(encoding, "unknown"),
        "producer_text_revision": hash_bytes(
            text.encode("utf-8"), domain=FILE_DOMAIN
        ).hash
        if isinstance(text, str)
        else None,
        "producer_text_representation": "utf8-document-text",
    }


def _scip_symbol_information(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(info["symbol"]): {
            "display_name": _field(info, "displayName", "display_name"),
            "kind": info.get("kind"),
        }
        for info in document.get("symbols") or ()
        if isinstance(info, dict) and isinstance(info.get("symbol"), str)
    }


def _scip_unlocated_claims(
    path: str,
    relationships: dict[str, tuple[ScipRelationship, ...]],
    occurrences: list[ScipOccurrence],
    information: dict[str, dict[str, Any]],
    metadata: dict[str, Any],
) -> list[ScipOccurrence]:
    definitions = {row.symbol for row in occurrences if row.definition}
    locators = {row.symbol: row for row in reversed(occurrences)}
    result = []
    for symbol, claims in relationships.items():
        if symbol in definitions or not claims:
            continue
        located = locators.get(symbol)
        result.append(
            ScipOccurrence(
                path=path,
                symbol=symbol,
                display_name=str(
                    information.get(symbol, {}).get("display_name")
                    or _display_name(symbol)
                ),
                line=located.line if located else 0,
                end_line=located.end_line if located else 0,
                definition=False,
                relationships=claims[:64],
                relationships_truncated=len(claims) > 64,
                relationship_only=True,
                locator=located.locator if located else None,
                document_metadata=metadata,
                declaration_metadata=information.get(symbol),
            )
        )
    return result


def _scip_document_occurrences(document: dict[str, Any]) -> list[ScipOccurrence]:
    path = str(_field(document, "relativePath", "relative_path", "") or "")
    if not path:
        return []
    path = path.replace("\\", "/")
    relationships = _scip_document_relationships(document)
    information = _scip_symbol_information(document)
    metadata = _scip_document_metadata(document)
    occurrences = [
        _scip_occurrence(path, occurrence, relationships, information, metadata)
        for occurrence in document.get("occurrences") or ()
        if isinstance(occurrence, dict) and occurrence.get("symbol")
    ]
    return occurrences + _scip_unlocated_claims(
        path, relationships, occurrences, information, metadata
    )


def parse_scip_json(value: dict[str, Any]) -> tuple[str, tuple[ScipOccurrence, ...]]:
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    tool = _field(metadata, "toolInfo", "tool_info", {})
    if not isinstance(tool, dict):
        tool = {}
    name = str(tool.get("name") or "scip")
    version = str(tool.get("version") or "unknown")
    producer = f"{name}:{version}"
    out: list[ScipOccurrence] = []
    for document in value.get("documents") or ():
        if isinstance(document, dict):
            rows = _scip_document_occurrences(document)
            encoding = _field(
                metadata, "textDocumentEncoding", "text_document_encoding", 0
            )
            text_encoding = {
                1: "utf-8",
                2: "utf-16",
                "UTF8": "utf-8",
                "UTF16": "utf-16",
            }.get(encoding, "unknown")
            for row in rows:
                if row.document_metadata is not None:
                    row.document_metadata["text_encoding"] = text_encoding
            out.extend(rows)
    return producer, tuple(out)


def load_scip_json(
    path: Path, *, workspace: Path, timeout: float = 20.0
) -> tuple[str, tuple[ScipOccurrence, ...], tuple[str, ...]]:
    path = path.resolve(strict=False)
    if path.suffix.lower() == ".json":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read SCIP JSON {path}: {exc}") from exc
        producer, occurrences = parse_scip_json(value)
        return producer, occurrences, ()
    scip = shutil.which("scip")
    if scip is None:
        raise RuntimeError(
            "scip CLI is required to consume binary .scip indexes; use `scip print --json index.scip > index.json` or install scip"
        )
    try:
        completed = subprocess.run(
            [scip, "print", "--json", str(path)],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"scip print failed: {exc}") from exc
    if completed.returncode != 0:
        detail = (
            completed.stderr.strip().splitlines()[-1]
            if completed.stderr.strip()
            else f"exit {completed.returncode}"
        )
        raise RuntimeError(f"scip print failed: {detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("scip print returned invalid JSON") from exc
    producer, occurrences = parse_scip_json(value)
    return producer, occurrences, ()
