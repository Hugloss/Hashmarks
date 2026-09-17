\
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _snake_case(value: str) -> str:
    parts = [
        part for part in _CAMEL_BOUNDARY_RE.sub("_", value.replace("-", "_")).split("_")
        if part
    ]
    return "_".join(part.lower() for part in parts)


def _identifier_variants(token: str) -> tuple[str, ...]:
    leaf = token.rsplit(".", 1)[-1]
    snake = _snake_case(leaf)
    compact = re.sub(r"[^a-z0-9]+", "", leaf.lower())
    values = [token, leaf, snake, compact]
    if "." in token:
        values.extend([token.lower(), ".".join(_snake_case(part) for part in token.split("."))])
    return tuple(dict.fromkeys(value for value in values if len(value) >= 3))


def symbolic_task_terms(task: str) -> tuple[str, ...]:
    """Return bounded identifier variants used only for symbolic nomination."""
    values: list[str] = []
    for token in _IDENTIFIER_RE.findall(task):
        identifier_like = (
            "." in token
            or "_" in token
            or any(ch.isupper() for ch in token[1:])
        )
        if identifier_like:
            values.extend(_identifier_variants(token))
    return tuple(dict.fromkeys(values))[:24]


def _candidate_identity(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("path") or ""),
        str(row.get("name") or ""),
        str(row.get("qualname") or ""),
    )


def _nomination_candidates(
    candidates: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    unique: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in candidates:
        identity = _candidate_identity(row)
        if identity[0]:
            unique.setdefault(identity, {
                "path": identity[0],
                "name": identity[1] or None,
                "qualname": identity[2] or None,
                "kind": str(row.get("kind") or "symbol"),
            })
    return list(unique.values())


def _nomination_status(rows: Sequence[Mapping[str, object]]) -> str:
    paths = {str(row.get("path") or "") for row in rows if row.get("path")}
    if len(paths) == 1:
        return "resolved"
    return "ambiguous" if paths else "unresolved"


def symbolic_nomination_record(
    *,
    task: str,
    terms: Sequence[str],
    candidates: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Describe symbolic candidates without granting edit or verification authority."""
    rows = _nomination_candidates(candidates)
    return {
        "schema": "hashmarks.symbolic-task-nomination.v1",
        "task": task,
        "terms": list(terms),
        "status": _nomination_status(rows),
        "candidate_count": len(rows),
        "candidates": rows[:12],
        "authority": "nomination-only",
        "ranking_effect": "none",
        "execution_effect": "none",
    }
