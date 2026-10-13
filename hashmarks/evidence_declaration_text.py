"""Lossless readable tables for already admitted lexical declaration scopes."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from hashmarks.codemap.task_evidence_initial import decode_initial_collection


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _metadata(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in context.items()
        if key not in {"declarations", "declarations_encoding"}
    }


def declaration_common_qualifiers(
    contexts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Factor only JSON-identical fields; booleans never match numeric values."""
    if not contexts:
        return {}
    metadata = [_metadata(context) for context in contexts]
    return {
        key: value
        for key, value in metadata[0].items()
        if all(key in item and _dump(item[key]) == _dump(value) for item in metadata)
    }


def _symbol_prefix(rows: list[dict[str, Any]]) -> str:
    symbols = [row.get("symbol") for row in rows]
    if not symbols or not all(
        isinstance(symbol, str) and "." in symbol for symbol in symbols
    ):
        return ""
    prefixes = {str(symbol).rsplit(".", 1)[0] + "." for symbol in symbols}
    return next(iter(prefixes)) if len(prefixes) == 1 else ""


def _table_rows(
    rows: list[dict[str, Any]], common: dict[str, Any], prefix: str
) -> tuple[list[str], bool, list[list[Any]]]:
    fields = set.intersection(*(set(row) for row in rows)) if rows else set()
    fields -= common.keys()
    columns = [key for key in ("symbol", "start_line", "end_line") if key in fields]
    columns.extend(sorted(fields - set(columns)))
    extras = any(set(row) - common.keys() - set(columns) for row in rows)
    result = []
    for row in rows:
        values = [row[key] for key in columns]
        if prefix:
            values[columns.index("symbol")] = row["symbol"][len(prefix) :]
        if extras:
            values.append(
                {
                    key: value
                    for key, value in row.items()
                    if key not in common and key not in columns
                }
            )
        result.append(values)
    return columns, extras, result


def declaration_scope_text(
    context: Mapping[str, Any], ref: str, *, shared: Mapping[str, Any] | None = None
) -> list[str]:
    """Rows follow native order; a scope pointer plus row index locates each fact."""
    rows = context.get("declarations", [])
    if isinstance(context.get("declarations_encoding"), dict):
        rows = decode_initial_collection(rows, context["declarations_encoding"])
    common = {}
    if rows and all(
        "path" in row and row["path"] == rows[0].get("path") for row in rows
    ):
        common["path"] = rows[0]["path"]
    prefix = _symbol_prefix(rows)
    columns, extras, table = _table_rows(rows, common, prefix)
    metadata = {
        key: value
        for key, value in _metadata(context).items()
        if key not in (shared or {})
    }
    return [
        f"{'Declarations @ ' + ref if ref else 'Declarations'}: {_dump(metadata)}",
        f"Common={_dump(common)}; prefix={_dump(prefix)}; columns={_dump(columns)}; extras={_dump(extras)}",
        *(_dump(row) for row in table),
    ]


def declaration_contexts(
    rows: Sequence[Mapping[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    return [
        (f"/retrieval/results/{index}/{family}", row[family])
        for index, row in enumerate(rows)
        for family in ("class_declarations", "enclosing_declarations")
        if isinstance(row.get(family), dict)
    ]


def declaration_scopes_text(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    contexts = declaration_contexts(rows)
    if not contexts:
        return []
    common = declaration_common_qualifiers([context for _, context in contexts])
    lines = [
        f"Declaration common qualifiers: {_dump(common)}",
        "Table rows preserve declaration order; references use <scope>/declarations/<row>; prefix applies only to symbol; extras preserve missing fields.",
    ]
    for ref, context in contexts:
        lines.extend(declaration_scope_text(context, ref, shared=common))
    return lines
