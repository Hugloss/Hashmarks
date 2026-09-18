from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from typing import TYPE_CHECKING

from .model import CODEMAP_SCHEMA, EdgeRecord, ParsedArtifact, SymbolRecord
from .python_ast import PYTHON_PARSER, estimate_tokens, lexical_records, parse_python

if TYPE_CHECKING:
    from .providers import TreeSitterRangeProvider

NODE_PARSER = "hashmarks.ecmascript-outline.v3"
GO_PARSER = "hashmarks.go-outline.v2"
RUST_PARSER = "hashmarks.rust-outline.v2"
PATH_ONLY_PARSER = "hashmarks.path-only.v3"


def parser_id(language: str) -> str:
    if language == "python":
        return PYTHON_PARSER
    if language in {"javascript", "typescript"}:
        return NODE_PARSER
    if language == "go":
        return GO_PARSER
    if language == "rust":
        return RUST_PARSER
    return PATH_ONLY_PARSER


def parser_signature(
    language: str, range_provider: TreeSitterRangeProvider | None = None
) -> str:
    base = parser_id(language)
    if range_provider is None:
        return base
    extra = range_provider.signature(language)
    return base if extra is None else f"{base}+{extra}"


def artifact_key_for(
    file_digest: str,
    language: str,
    *,
    range_provider: TreeSitterRangeProvider | None = None,
) -> str:
    payload = json.dumps(
        {
            "schema": CODEMAP_SCHEMA,
            "parser": parser_signature(language, range_provider),
            "file_digest": file_digest,
            "language": language,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(b"hashmarks.codemap-artifact.v1\0" + payload).hexdigest()


def _symbol(
    *,
    name: str,
    kind: str,
    signature: str,
    line: int,
    parent: str | None = None,
) -> SymbolRecord:
    qualname = name if parent is None else f"{parent}.{name}"
    return SymbolRecord(
        name=name,
        qualname=qualname,
        kind=kind,
        signature=signature.rstrip(),
        start_line=line,
        end_line=line,
        signature_tokens=estimate_tokens(signature),
        body_tokens=estimate_tokens(signature),
        parent=parent,
    )


def _node_declaration(stripped: str, line_no: int) -> SymbolRecord | None:
    """Classify one advisory JS/TS declaration without inferring its RHS."""
    match = re.match(
        r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)",
        stripped,
    )
    if match:
        return _symbol(
            name=match.group(1),
            kind="function",
            signature=stripped.split("{")[0].rstrip(),
            line=line_no,
        )
    match = re.match(
        r"^(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)\b", stripped
    )
    if match:
        return _symbol(
            name=match.group(1),
            kind="class",
            signature=stripped.split("{")[0].rstrip(),
            line=line_no,
        )
    match = re.match(
        r"^(?:export\s+)?(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)\b", stripped
    )
    if match:
        keyword = (
            stripped.split(None, 2)[1]
            if stripped.startswith("export ")
            else stripped.split(None, 1)[0]
        )
        return _symbol(
            name=match.group(1),
            kind=keyword,
            signature=stripped.split("{")[0].rstrip(),
            line=line_no,
        )
    match = re.match(
        r"^(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
        stripped,
    )
    if match:
        return _symbol(
            name=match.group(1),
            kind="function",
            signature=stripped.split("=>", 1)[0].rstrip() + " =>",
            line=line_no,
        )
    # React/hooks and modern TypeScript expose code landmarks as const
    # bindings. Keep them as advisory structure without inferring the RHS.
    match = re.match(
        r"^(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=", stripped
    )
    if match:
        prefix = stripped.split("=", 1)[0].rstrip()
        return _symbol(
            name=match.group(1),
            kind="binding",
            signature=prefix + " = …",
            line=line_no,
        )
    return None


def _node_outline(source: str, *, file_digest: str, language: str) -> ParsedArtifact:
    symbols: list[SymbolRecord] = []
    edges: list[EdgeRecord] = []
    for line_no, raw in enumerate(source.splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        for pattern in (
            r"\bfrom\s+['\"]([^'\"]+)['\"]",
            r"^import\s+['\"]([^'\"]+)['\"]",
            r"\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)",
        ):
            for match in re.finditer(pattern, stripped):
                edges.append(
                    EdgeRecord(None, "import", match.group(1), line_no, "lexical")
                )
        symbol = _node_declaration(stripped, line_no)
        if symbol is not None:
            symbols.append(symbol)

    outline = "\n".join(
        f"{symbol.signature}  [{symbol.start_line}]" for symbol in symbols
    )
    return ParsedArtifact(
        artifact_key=artifact_key_for(file_digest, language),
        file_digest=file_digest,
        language=language,
        parser=NODE_PARSER,
        full_tokens=estimate_tokens(source),
        outline=outline,
        symbols=tuple(symbols),
        edges=tuple(edges),
        lexical=lexical_records(source),
    )


def _go_outline(source: str, *, file_digest: str) -> ParsedArtifact:
    symbols: list[SymbolRecord] = []
    edges: list[EdgeRecord] = []
    in_import = False
    for line_no, raw in enumerate(source.splitlines(), 1):
        stripped = raw.strip()
        if stripped.startswith("import ("):
            in_import = True
            continue
        if in_import and stripped == ")":
            in_import = False
            continue
        if stripped.startswith("import ") or in_import:
            match = re.search(r'"([^"]+)"', stripped)
            if match:
                edges.append(
                    EdgeRecord(None, "import", match.group(1), line_no, "lexical")
                )
        match = re.match(
            r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(", stripped
        )
        if match:
            kind = "method" if stripped.startswith("func (") else "function"
            symbols.append(
                _symbol(
                    name=match.group(1),
                    kind=kind,
                    signature=stripped.split("{")[0].rstrip(),
                    line=line_no,
                )
            )
            continue
        match = re.match(
            r"^type\s+([A-Za-z_][A-Za-z0-9_]*)\s+(struct|interface)\b", stripped
        )
        if match:
            symbols.append(
                _symbol(
                    name=match.group(1),
                    kind=match.group(2),
                    signature=stripped.split("{")[0].rstrip(),
                    line=line_no,
                )
            )
    outline = "\n".join(
        f"{symbol.signature}  [{symbol.start_line}]" for symbol in symbols
    )
    return ParsedArtifact(
        artifact_key=artifact_key_for(file_digest, "go"),
        file_digest=file_digest,
        language="go",
        parser=GO_PARSER,
        full_tokens=estimate_tokens(source),
        outline=outline,
        symbols=tuple(symbols),
        edges=tuple(edges),
        lexical=lexical_records(source),
    )


def _rust_outline(source: str, *, file_digest: str) -> ParsedArtifact:
    symbols: list[SymbolRecord] = []
    edges: list[EdgeRecord] = []
    for line_no, raw in enumerate(source.splitlines(), 1):
        stripped = raw.strip()
        match = re.match(r"^(?:pub(?:\([^)]*\))?\s+)?use\s+([^;]+);", stripped)
        if match:
            edges.append(
                EdgeRecord(None, "import", match.group(1).strip(), line_no, "lexical")
            )
        match = re.match(
            r"^(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            stripped,
        )
        if match:
            symbols.append(
                _symbol(
                    name=match.group(1),
                    kind="function",
                    signature=stripped.split("{")[0].rstrip(),
                    line=line_no,
                )
            )
            continue
        match = re.match(
            r"^(?:pub(?:\([^)]*\))?\s+)?(struct|enum|trait)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
            stripped,
        )
        if match:
            symbols.append(
                _symbol(
                    name=match.group(2),
                    kind=match.group(1),
                    signature=stripped.split("{")[0].rstrip(),
                    line=line_no,
                )
            )
    outline = "\n".join(
        f"{symbol.signature}  [{symbol.start_line}]" for symbol in symbols
    )
    return ParsedArtifact(
        artifact_key=artifact_key_for(file_digest, "rust"),
        file_digest=file_digest,
        language="rust",
        parser=RUST_PARSER,
        full_tokens=estimate_tokens(source),
        outline=outline,
        symbols=tuple(symbols),
        edges=tuple(edges),
        lexical=lexical_records(source),
    )


def _unique_symbol_occurrences(
    symbols: tuple[SymbolRecord, ...],
) -> tuple[SymbolRecord, ...]:
    """Make persisted symbol occurrence keys deterministic and unique.

    Source languages can legally contain repeated lexical qualnames: Python local
    helper redefinitions/properties, overload-style declarations, and advisory
    polyglot parsers can all surface this.  WorkspaceMapStore intentionally uses
    ``(path, qualname)`` as its compact lookup key, so repeated occurrences get a
    line-qualified derived qualname instead of making a cold CodeMap sync fail.

    The first occurrence keeps the natural qualname for ergonomic lookup. Later
    occurrences preserve ``name`` and ``parent`` but receive ``@L<line>`` (and a
    deterministic numeric suffix only if the line also collides). CodeMap is
    derived state; these occurrence suffixes are never canonical Identity input.
    """
    used: set[str] = set()
    out: list[SymbolRecord] = []
    for row in sorted(
        symbols,
        key=lambda value: (
            value.start_line,
            value.end_line,
            value.qualname,
            value.kind,
        ),
    ):
        qualname = row.qualname
        if qualname in used:
            base = f"{qualname}@L{row.start_line}"
            candidate = base
            ordinal = 2
            while candidate in used:
                candidate = f"{base}-{ordinal}"
                ordinal += 1
            row = replace(row, qualname=candidate)
        used.add(row.qualname)
        out.append(row)
    return tuple(out)


def _path_only(source: str, *, file_digest: str, language: str) -> ParsedArtifact:
    return ParsedArtifact(
        artifact_key=artifact_key_for(file_digest, language),
        file_digest=file_digest,
        language=language,
        parser=PATH_ONLY_PARSER,
        full_tokens=estimate_tokens(source),
        outline="",
        lexical=lexical_records(source),
    )


def parse_source(
    source: str,
    *,
    file_digest: str,
    language: str,
    range_provider: TreeSitterRangeProvider | None = None,
) -> ParsedArtifact:
    if language == "python":
        artifact = parse_python(source, file_digest=file_digest)
    elif language in {"javascript", "typescript"}:
        artifact = _node_outline(source, file_digest=file_digest, language=language)
    elif language == "go":
        artifact = _go_outline(source, file_digest=file_digest)
    elif language == "rust":
        artifact = _rust_outline(source, file_digest=file_digest)
    else:
        artifact = _path_only(source, file_digest=file_digest, language=language)

    if range_provider is not None:
        artifact = range_provider.enrich(artifact, source, language)
    unique_symbols = _unique_symbol_occurrences(artifact.symbols)
    if unique_symbols != artifact.symbols:
        artifact = replace(artifact, symbols=unique_symbols)
    expected = artifact_key_for(file_digest, language, range_provider=range_provider)
    expected_parser = parser_signature(language, range_provider)
    if artifact.artifact_key != expected or artifact.parser != expected_parser:
        artifact = ParsedArtifact(
            artifact_key=expected,
            file_digest=artifact.file_digest,
            language=artifact.language,
            parser=expected_parser,
            full_tokens=artifact.full_tokens,
            outline=artifact.outline,
            symbols=artifact.symbols,
            edges=artifact.edges,
            lexical=artifact.lexical,
            parse_error=artifact.parse_error,
        )
    return artifact
