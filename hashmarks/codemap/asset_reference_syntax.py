"""Positive literal asset references over already-qualified source bytes.

This deliberately bounded syntax is not Markdown rendering, Python execution,
or evidence that other asset consumers do not exist.
"""

from __future__ import annotations

import ast
import posixpath
import re
from collections.abc import Iterator
from pathlib import PurePosixPath
from typing import cast
from urllib.parse import unquote, urlsplit

from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS
from .verification_file_reads import literal_repository_file_reads

_INLINE_LINK = re.compile(
    r"(?<![\\!])(?P<image>!)?\[[^\]\\\n]*\]\("
    r"(?P<destination><[^<>\n]+>|[^\s()<>]+)"
    r'(?:\s+(?:"[^"\n]*"|\x27[^\x27\n]*\x27))?\)'
)
_FENCE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})")
_HTML_REGION = re.compile(
    r"<!--|<!\[CDATA\[|<\?|<![A-Z]|<(?P<raw>script|pre|style|textarea|code)\b",
    re.IGNORECASE,
)
_HTML_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9:-]*(?=[\s>]|/>)")
_HTML_ENDINGS = {"<!--": r"-->", "<![CDATA[": r"\]\]>", "<?": r"\?>"}


def _relative_destination(reader: str, destination: str) -> str | None:
    value = destination.removeprefix("<").removesuffix(">")
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    path = unquote(parsed.path)
    if path.startswith("/") or "\\" in path or "\x00" in path:
        return None
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(reader), path))
    return None if resolved == ".." or resolved.startswith("../") else resolved


def _markdown_fence(
    fence: tuple[str, int] | None, marker: re.Match[str], line: str
) -> tuple[str, int] | None:
    current = (marker["marker"][0], len(marker["marker"]))
    if fence is None:
        return current
    if (
        current[0] == fence[0]
        and current[1] >= fence[1]
        and not line[: marker.start("marker")].strip()
        and not line[marker.end("marker") :].strip()
    ):
        return None
    return fence


def _markdown_html(line: str, ending: str | None) -> tuple[str | None, bool]:
    """Refuse opaque HTML regions and conservatively refuse other HTML lines."""
    hidden = ending is not None
    while True:
        if ending is not None:
            closing = re.search(ending, line, re.IGNORECASE)
            if closing is None:
                return ending, True
            line = line[closing.end() :]
            ending = None
        opening = _HTML_REGION.search(line)
        if opening is None:
            break
        hidden = True
        raw = opening["raw"]
        ending = rf"</{raw}\s*>" if raw else _HTML_ENDINGS.get(opening[0], r">")
        line = line[opening.end() :]
    tag = _HTML_TAG.search(line)
    if tag is not None:
        return (r"^\s*$" if not line[: tag.start()].strip() else None), True
    return None, hidden


def _inline_code_ticks(line: str, ticks: int | None) -> int | None:
    for marker in re.finditer(r"`+", line):
        size = len(marker[0])
        if ticks is None:
            ticks = size
        elif size == ticks:
            ticks = None
    return ticks


def _markdown_lines(text: str) -> Iterator[tuple[int, str]]:
    fence: tuple[str, int] | None = None
    html_ending: str | None = None
    ticks: int | None = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = _FENCE.match(line) if ticks is None and html_ending is None else None
        if marker is not None:
            fence = _markdown_fence(fence, marker, line)
            continue
        if fence is not None:
            continue
        if ticks is None:
            html_ending, hidden = _markdown_html(line, html_ending)
            if hidden:
                continue
        hidden = ticks is not None or "`" in line
        ticks = _inline_code_ticks(line, ticks)
        if not hidden and not line.startswith(("    ", "\t")) and len(line) <= 8192:
            yield number, line


def _markdown_references(
    text: str, reader: str, target: str
) -> list[dict[str, object]]:
    references: list[dict[str, object]] = []
    for number, line in _markdown_lines(text):
        for match in _INLINE_LINK.finditer(line):
            if _relative_destination(reader, match["destination"]) == target:
                references.append(
                    {
                        "line": number,
                        "end_line": number,
                        "start_byte_column": len(
                            line[: match.start("destination")].encode("utf-8")
                        ),
                        "end_byte_column": len(
                            line[: match.end("destination")].encode("utf-8")
                        ),
                        "relation_kind": "markdown-inline-image"
                        if match["image"]
                        else "markdown-inline-link",
                        "qualification": "syntax-qualified",
                        "destination": match["destination"],
                    }
                )
                if (
                    len(references)
                    > VERIFICATION_RELEVANCE_DEFAULTS.literal_file_read_sites
                ):
                    return references
    return references


def _qualified_spans(
    references: list[dict[str, object]],
) -> dict[int, list[tuple[int, int | None]]]:
    spans: dict[int, list[tuple[int, int | None]]] = {}
    for reference in references:
        start = cast("int", reference["line"])
        end = cast("int", reference["end_line"])
        for number in range(start, end + 1):
            spans.setdefault(number, []).append(
                (
                    cast("int", reference["start_byte_column"])
                    if number == start
                    else 0,
                    cast("int", reference["end_byte_column"])
                    if number == end
                    else None,
                )
            )
    return spans


def _literal_references(
    text: str, target: str, qualified: list[dict[str, object]]
) -> list[dict[str, object]]:
    basename = PurePosixPath(target).name
    literal = basename.encode("utf-8")
    spans = _qualified_spans(qualified)
    references: list[dict[str, object]] = []
    for number, line in enumerate(text.splitlines(), 1):
        remaining = bytearray(line.encode("utf-8"))
        for start, end in spans.get(number, ()):
            stop = len(remaining) if end is None else end
            remaining[start:stop] = b" " * (stop - start)
        if literal in remaining:
            references.append(
                {
                    "line": number,
                    "relation_kind": "literal-reference",
                    "qualification": "literal-only",
                    "literal": basename,
                }
            )
            if (
                len(references)
                > VERIFICATION_RELEVANCE_DEFAULTS.literal_file_read_sites
            ):
                break
    return references


def asset_references(
    text: str, reader: str, target: str, *, python_import_qualified: bool
) -> tuple[list[dict[str, object]], str]:
    """Interpret only the captured string; reads and import identity stay external."""
    suffix = PurePosixPath(reader).suffix.lower()
    if suffix == ".md":
        rows = _markdown_references(text, reader, target)
        syntax = "markdown-inline-local-destinations"
    elif suffix == ".py" and python_import_qualified:
        try:
            tree = ast.parse(text, filename=reader)
        except (SyntaxError, ValueError):
            rows = []
            syntax = "python-syntax-unavailable"
        else:
            rows = [
                {
                    **read,
                    "relation_kind": "python-literal-file-read",
                    "qualification": "syntax-qualified",
                }
                for read in literal_repository_file_reads(
                    tree, reader, target, tests_only=False
                )
            ]
            syntax = "unshadowed-pathlib-literal-read"
    else:
        rows = []
        syntax = "literal-only"
    rows.extend(_literal_references(text, target, rows))
    return rows[: VERIFICATION_RELEVANCE_DEFAULTS.literal_file_read_sites + 1], syntax
