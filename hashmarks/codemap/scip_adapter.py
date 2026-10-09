from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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


def _field(value: dict[str, Any], camel: str, snake: str | None = None, default=None):
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
                bucket.remove(max(bucket, key=lambda item: (item.kind, item.target_symbol)))
    return {
        symbol: tuple(sorted(rows, key=lambda item: (item.kind, item.target_symbol)))
        for symbol, rows in collected.items()
    }


def _scip_occurrence(
    path: str,
    occurrence: dict[str, Any],
    relationships: dict[str, tuple[ScipRelationship, ...]],
) -> ScipOccurrence:
    symbol = str(occurrence["symbol"])
    roles = int(_field(occurrence, "symbolRoles", "symbol_roles", 0) or 0)
    start, end = _range_lines(occurrence)
    is_definition = bool(roles & 0x1)
    direct = relationships.get(symbol, ()) if is_definition else ()
    return ScipOccurrence(
        path=path,
        symbol=symbol,
        display_name=_display_name(symbol),
        line=start,
        end_line=end,
        definition=is_definition,
        relationships=direct[:64],
        relationships_truncated=len(direct) > 64,
    )


def _scip_document_occurrences(document: dict[str, Any]) -> list[ScipOccurrence]:
    path = str(_field(document, "relativePath", "relative_path", "") or "")
    if not path:
        return []
    path = path.replace("\\", "/")
    relationships = _scip_document_relationships(document)
    return [
        _scip_occurrence(path, occurrence, relationships)
        for occurrence in document.get("occurrences") or ()
        if isinstance(occurrence, dict) and occurrence.get("symbol")
    ]


def parse_scip_json(value: dict[str, Any]) -> tuple[str, tuple[ScipOccurrence, ...]]:
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    tool = _field(metadata, "toolInfo", "tool_info", {})
    if not isinstance(tool, dict):
        tool = {}
    producer = f"{str(tool.get('name') or 'scip')}:{str(tool.get('version') or 'unknown')}"
    out: list[ScipOccurrence] = []
    for document in value.get("documents") or ():
        if isinstance(document, dict):
            out.extend(_scip_document_occurrences(document))
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
