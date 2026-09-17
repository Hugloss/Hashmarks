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
class ScipOccurrence:
    path: str
    symbol: str
    display_name: str
    line: int
    end_line: int
    definition: bool


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


def parse_scip_json(value: dict[str, Any]) -> tuple[str, tuple[ScipOccurrence, ...]]:
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    tool = _field(metadata, "toolInfo", "tool_info", {})
    if not isinstance(tool, dict):
        tool = {}
    name = str(tool.get("name") or "scip")
    version = str(tool.get("version") or "unknown")
    producer = f"{name}:{version}"
    out: list[ScipOccurrence] = []
    documents = value.get("documents") or ()
    for document in documents:
        if not isinstance(document, dict):
            continue
        path = str(_field(document, "relativePath", "relative_path", "") or "")
        if not path:
            continue
        for occurrence in document.get("occurrences") or ():
            if not isinstance(occurrence, dict):
                continue
            symbol = str(occurrence.get("symbol") or "")
            if not symbol:
                continue
            roles = int(_field(occurrence, "symbolRoles", "symbol_roles", 0) or 0)
            start, end = _range_lines(occurrence)
            out.append(
                ScipOccurrence(
                    path=path.replace("\\", "/"),
                    symbol=symbol,
                    display_name=_display_name(symbol),
                    line=start,
                    end_line=end,
                    definition=bool(roles & 0x1),
                )
            )
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
