from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from typing import TYPE_CHECKING

from .model import CODEMAP_SCHEMA, EdgeRecord, ParsedArtifact, SymbolRecord
from .providers import ECMASCRIPT_GRAMMARS, source_grammar
from .python_ast import (
    PYTHON_PARSER,
    estimate_tokens,
    lexical_records,
    parse_python,
    python_parser_signature,
)

if TYPE_CHECKING:
    from .providers import SourceRangeProvider

NODE_PARSER = "hashmarks.ecmascript-syntax.v7"
GO_PARSER = "hashmarks.go-outline.v4"
RUST_PARSER = "hashmarks.rust-outline.v4"
PATH_ONLY_PARSER = "hashmarks.path-only.v4"


def parser_id(language: str) -> str:
    if language == "python":
        return PYTHON_PARSER
    if language in ECMASCRIPT_GRAMMARS:
        return NODE_PARSER
    if language == "go":
        return GO_PARSER
    if language == "rust":
        return RUST_PARSER
    return PATH_ONLY_PARSER


def parser_signature(
    language: str,
    range_provider: SourceRangeProvider | None = None,
    *,
    path: str | None = None,
) -> str:
    base = python_parser_signature() if language == "python" else parser_id(language)
    if range_provider is None:
        return base
    extra = range_provider.signature(
        source_grammar(path) or language if path is not None else language
    )
    return base if extra is None else f"{base}+{extra}"


def artifact_key_for(
    file_digest: str,
    language: str,
    *,
    range_provider: SourceRangeProvider | None = None,
    path: str | None = None,
) -> str:
    grammar = source_grammar(path) or language if path is not None else language
    return _artifact_key(
        file_digest,
        language,
        grammar,
        parser_signature(language, range_provider, path=path),
    )


def _artifact_key(file_digest: str, language: str, grammar: str, parser: str) -> str:
    payload = json.dumps(
        {
            "schema": CODEMAP_SCHEMA,
            "parser": parser,
            "grammar": grammar,
            "file_digest": file_digest,
            "language": language,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    # Retire artifacts that ingestion could bind to a digest from another read.
    return hashlib.sha256(b"hashmarks.codemap-artifact.v2\0" + payload).hexdigest()


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


def _go_outline(source: str, *, file_digest: str) -> ParsedArtifact:
    symbols: list[SymbolRecord] = []
    edges: list[EdgeRecord] = []
    in_import = False
    for line_no, raw in enumerate(source.split("\n"), 1):
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
    for line_no, raw in enumerate(source.split("\n"), 1):
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
    """Retain retrieval text without claiming source structure or its absence."""
    return ParsedArtifact(
        artifact_key=artifact_key_for(file_digest, language),
        file_digest=file_digest,
        language=language,
        parser=NODE_PARSER if language in ECMASCRIPT_GRAMMARS else PATH_ONLY_PARSER,
        full_tokens=estimate_tokens(source),
        outline="",
        lexical=lexical_records(source),
        parse_error="native-syntax-unavailable"
        if language in ECMASCRIPT_GRAMMARS
        else None,
    )


def parse_source(
    source: str | bytes,
    *,
    file_digest: str,
    language: str,
    range_provider: SourceRangeProvider | None = None,
    path: str | None = None,
) -> ParsedArtifact:
    grammar = source_grammar(path) or language if path is not None else language
    expected_parser = parser_signature(language, range_provider, path=path)
    expected = _artifact_key(file_digest, language, grammar, expected_parser)
    text = (
        source.decode("utf-8", errors="replace")
        if isinstance(source, bytes)
        else source
    )
    if language == "python":
        artifact = parse_python(source, file_digest=file_digest)
    elif language == "go":
        artifact = _go_outline(text, file_digest=file_digest)
    elif language == "rust":
        artifact = _rust_outline(text, file_digest=file_digest)
    else:
        artifact = _path_only(text, file_digest=file_digest, language=language)

    if range_provider is not None:
        artifact = range_provider.enrich(artifact, source, grammar)
    if (
        language in ECMASCRIPT_GRAMMARS | {"python"}
        and parser_signature(language, range_provider, path=path) != expected_parser
    ):
        artifact = replace(
            artifact,
            symbols=(),
            edges=(),
            outline="",
            parse_error="native-syntax-provider-changed",
        )
    unique_symbols = _unique_symbol_occurrences(artifact.symbols)
    if unique_symbols != artifact.symbols:
        artifact = replace(artifact, symbols=unique_symbols)
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
