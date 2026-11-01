from __future__ import annotations

import json
from collections import OrderedDict
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, replace
from importlib import metadata
from pathlib import PurePath
from typing import TYPE_CHECKING, Literal, Protocol, cast, runtime_checkable

from .ecmascript_syntax import SyntaxObservationBound, module_declarations
from .model import EdgeRecord, ParsedArtifact, SymbolRecord
from .python_ast import estimate_tokens
from .source_languages import SOURCE_LANGUAGES

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from contextlib import AbstractContextManager

TREE_SITTER_RANGE_SCHEMA = "hashmarks.tree-sitter-ranges.v3"
ECMASCRIPT_GRAMMARS = frozenset({"javascript", "typescript", "tsx"})
SYNTAX_SESSION_MAX_TREES = 32
SYNTAX_SESSION_MAX_SOURCE_BYTES = 8_388_608
_SyntaxKey = tuple[str, str, bytes]
_LanguageName = Literal[
    "python",
    "javascript",
    "typescript",
    "tsx",
    "go",
    "rust",
    "java",
    "kotlin",
    "c",
    "cpp",
    "csharp",
    "ruby",
    "php",
    "swift",
]
_IDENTIFIER_TYPES = frozenset(
    {
        "identifier",
        "type_identifier",
        "property_identifier",
        "field_identifier",
        "private_property_identifier",
        "nested_identifier",
    }
)


class StructuralNode(Protocol):
    @property
    def type(self) -> str: ...
    @property
    def start_byte(self) -> int: ...
    @property
    def end_byte(self) -> int: ...
    @property
    def start_point(self) -> tuple[int, int]: ...
    @property
    def end_point(self) -> tuple[int, int]: ...
    @property
    def children(self) -> Sequence[StructuralNode]: ...
    @property
    def named_children(self) -> Sequence[StructuralNode]: ...
    def child_by_field_name(self, name: str, /) -> StructuralNode | None: ...


class StructuralTree(Protocol):
    @property
    def root_node(self) -> StructuralNode: ...


class StructuralParser(Protocol):
    def parse(self, source: bytes, /) -> StructuralTree: ...


class SourceSyntaxError(ValueError):
    """The canonical parser could not admit the supplied source bytes."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _SyntaxReuse:
    """Disposable, bounded trees over exact inputs; never source authority."""

    def __init__(self) -> None:
        self.entries: OrderedDict[_SyntaxKey, StructuralTree | str] = OrderedDict()
        self.source_bytes = 0
        self.active = True

    def get(self, key: _SyntaxKey) -> StructuralTree | str | None:
        value = self.entries.get(key) if self.active else None
        if value is not None:
            self.entries.move_to_end(key)
        return value

    def remember(self, key: _SyntaxKey, value: StructuralTree | str) -> None:
        size = len(key[2])
        if not self.active or size > SYNTAX_SESSION_MAX_SOURCE_BYTES:
            return
        self.entries[key] = value
        self.source_bytes += size
        while (
            len(self.entries) > SYNTAX_SESSION_MAX_TREES
            or self.source_bytes > SYNTAX_SESSION_MAX_SOURCE_BYTES
        ):
            evicted, _ = self.entries.popitem(last=False)
            self.source_bytes -= len(evicted[2])

    def clear(self) -> None:
        self.entries.clear()
        self.source_bytes = 0
        self.active = False


def source_grammar(path: str) -> str | None:
    """Select the native grammar once, independently of the public language family."""
    suffix = PurePath(path).suffix.lower()
    return "tsx" if suffix == ".tsx" else SOURCE_LANGUAGES.get(suffix)


def _identifier_node_or_child(value: StructuralNode) -> StructuralNode | None:
    if value.type in _IDENTIFIER_TYPES:
        return value
    for child in value.children:
        if child.type in _IDENTIFIER_TYPES:
            return child
    return None


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    available: bool
    version: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "available": self.available,
            "version": self.version,
            "detail": self.detail,
        }


class SourceRangeProvider(Protocol):
    """The range producer operations consumed by ingestion and capability views."""

    def signature(self, language: str) -> str | None: ...
    def enrich(
        self, artifact: ParsedArtifact, source: str | bytes, language: str
    ) -> ParsedArtifact: ...
    def status(self) -> ProviderStatus: ...


@runtime_checkable
class SourceSyntaxProvider(Protocol):
    """Optional native syntax capability on the existing range provider."""

    def signature(self, language: str) -> str | None: ...
    def status(self) -> ProviderStatus: ...
    def syntax_tree(self, source: bytes, language: str) -> StructuralTree | None: ...


class TreeSitterRangeProvider:
    """Optional structural range enrichment for CodeMap.

    The provider is deliberately optional and lazy. Hashmarks does not depend on
    tree-sitter, and the Identity/Impact import graph never imports this module.
    When ``tree-sitter-language-pack`` is installed, CodeMap can use it to get
    robust symbol body ranges for supported languages. ECMAScript declarations
    and module references come exclusively from this admitted syntax; unavailable
    native parsing never falls back to a second structural interpreter.
    """

    _LANGUAGE_NAMES: dict[str, _LanguageName] = {
        "python": "python",
        "javascript": "javascript",
        "typescript": "typescript",
        "tsx": "tsx",
        "go": "go",
        "rust": "rust",
        "java": "java",
        "kotlin": "kotlin",
        "c": "c",
        "cpp": "cpp",
        "csharp": "csharp",
        "ruby": "ruby",
        "php": "php",
        "swift": "swift",
    }

    _SYMBOL_TYPES = {
        "function_definition": "function",
        "class_definition": "class",
        "method_definition": "method",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
        "function_expression": "function",
        "arrow_function": "function",
        "function_item": "function",
        "struct_item": "struct",
        "enum_item": "enum",
        "trait_item": "trait",
        "function_declaration": "function",
        "type_declaration": "type",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "method_declaration": "method",
        "constructor_declaration": "constructor",
        "internal_module": "namespace",
        "abstract_class_declaration": "class",
        "function_signature": "function",
        "method_signature": "method",
        "abstract_method_signature": "method",
        "variable_declarator": "binding",
        "public_field_definition": "method",
    }

    def __init__(
        self,
        parser_factory: Callable[[_LanguageName], StructuralParser] | None = None,
        *,
        version: str | None = None,
        detail: str | None = None,
        binding_version: str | None = None,
    ) -> None:
        self._parser_factory = parser_factory
        self.version = version
        self.detail = detail
        self._binding_version = binding_version
        self._parsers: dict[str, StructuralParser] = {}
        self._syntax_reuse: ContextVar[_SyntaxReuse | None] = ContextVar(
            "hashmarks_native_syntax_reuse", default=None
        )

    @classmethod
    def auto(cls) -> TreeSitterRangeProvider:
        try:
            from tree_sitter_language_pack import get_parser
        except Exception as exc:  # optional dependency must never block CodeMap
            return cls(
                None,
                detail=f"tree-sitter-language-pack unavailable: {exc.__class__.__name__}",
            )
        try:
            version = metadata.version("tree-sitter-language-pack")
            binding_version = metadata.version("tree-sitter")
        except metadata.PackageNotFoundError:
            return cls(None, detail="native parser version metadata unavailable")
        return cls(
            get_parser,
            version=version,
            binding_version=binding_version,
            detail=f"tree-sitter binding {binding_version}",
        )

    @property
    def available(self) -> bool:
        return self._parser_factory is not None

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name="tree-sitter-ranges",
            available=self.available,
            version=self.version,
            detail=self.detail,
        )

    def supports(self, language: str) -> bool:
        return self.available and language in self._LANGUAGE_NAMES

    def signature(self, language: str) -> str | None:
        if not self.supports(language):
            return None
        version = self.version or "unknown"
        if self._binding_version is not None:
            version = json.dumps(
                [version, self._binding_version], separators=(",", ":")
            )
        return f"{TREE_SITTER_RANGE_SCHEMA}:{version}:{self._LANGUAGE_NAMES[language]}"

    def _parser(self, language: str) -> StructuralParser:
        name = self._LANGUAGE_NAMES[language]
        parser = self._parsers.get(name)
        if parser is not None:
            return parser
        assert self._parser_factory is not None
        parser = self._parser_factory(name)
        self._parsers[name] = parser
        return parser

    @contextmanager
    def syntax_session(self) -> Iterator[None]:
        """Reuse syntax only within this context's current observation operation."""
        existing = self._syntax_reuse.get()
        if existing is not None and existing.active:
            yield
            return
        reuse = _SyntaxReuse()
        token = self._syntax_reuse.set(reuse)
        try:
            yield
        finally:
            self._syntax_reuse.reset(token)
            reuse.clear()

    def _parse_syntax(self, source: bytes, language: str) -> StructuralTree:
        if b"\x00" in source:
            raise SourceSyntaxError("null-byte-text")
        try:
            source.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceSyntaxError("invalid-utf8") from exc
        tree = self._parser(language).parse(source)
        if getattr(tree.root_node, "has_error", False):
            raise SourceSyntaxError("native-syntax-parse-failed")
        return tree

    def syntax_tree(self, source: bytes, language: str) -> StructuralTree | None:
        """Parse once per retained exact input in the active bounded operation.

        A tree is reusable only for the same source bytes, grammar and provider
        signature in this provider instance. Sessions never establish member
        freshness or persist trees; eviction may require another native parse.
        """
        signature = self.signature(language)
        if signature is None:
            return None
        key = (language, signature, source)
        reuse = self._syntax_reuse.get()
        cached = reuse.get(key) if reuse is not None else None
        if isinstance(cached, str):
            raise SourceSyntaxError(cached)
        if cached is not None:
            return cached
        try:
            tree = self._parse_syntax(source, language)
            if self.signature(language) != signature:
                raise SourceSyntaxError("native-syntax-provider-changed")
        except SourceSyntaxError as exc:
            if reuse is not None:
                reuse.remember(key, exc.reason)
            raise
        if reuse is not None:
            reuse.remember(key, tree)
        return tree

    @staticmethod
    def _name_node(node: StructuralNode) -> StructuralNode | None:
        for field in ("name", "declarator"):
            try:
                value = node.child_by_field_name(field)
            except Exception:
                continue
            if value is not None:
                identifier = _identifier_node_or_child(value)
                if identifier is not None:
                    return identifier
        if getattr(node, "type", "") in {"arrow_function", "function_expression"}:
            return None  # Anonymous parameters are not declaration names.
        return next(
            (child for child in node.children if child.type in _IDENTIFIER_TYPES), None
        )

    def _declared_kind(self, node: StructuralNode) -> str | None:
        kind = self._SYMBOL_TYPES.get(node.type)
        if node.type not in {"variable_declarator", "public_field_definition"}:
            return kind
        # Destructuring and computed expressions have no single declared
        # identifier in this projection. Only native callable values are methods.
        declared = node.child_by_field_name("name")
        if declared is None or declared.type not in _IDENTIFIER_TYPES:
            return None
        value = node.child_by_field_name("value")
        callable_value = value is not None and value.type in {
            "arrow_function",
            "function_expression",
        }
        if node.type == "public_field_definition":
            return "method" if callable_value else None
        return "function" if callable_value else kind

    @staticmethod
    def _text(source_bytes: bytes, node: StructuralNode) -> str:
        return source_bytes[int(node.start_byte) : int(node.end_byte)].decode(
            "utf-8", errors="replace"
        )

    def _symbol_from_tree_node(
        self, node: StructuralNode, parent: str | None, source_bytes: bytes
    ) -> SymbolRecord | None:
        kind = self._declared_kind(node)
        if kind is None:
            return None
        name_node = self._name_node(node)
        if name_node is None:
            return None
        name = self._text(source_bytes, name_node).strip()
        if not name:
            return None
        qualname = name if parent is None else f"{parent}.{name}"
        start_line = int(node.start_point[0]) + 1
        end_line = int(node.end_point[0]) + 1
        full = self._text(source_bytes, node)
        header = full.split("{", 1)[0].split(":\n", 1)[0].strip()
        if "\n" in header:
            header = " ".join(
                part.strip() for part in header.splitlines() if part.strip()
            )
        if len(header) > 400:
            header = header[:397] + "..."
        return SymbolRecord(
            name=name,
            qualname=qualname,
            kind=kind,
            signature=header or name,
            start_line=start_line,
            end_line=end_line,
            signature_tokens=estimate_tokens(header or name),
            body_tokens=estimate_tokens(full),
            parent=parent,
        )

    @staticmethod
    def _declaration(node: StructuralNode) -> StructuralNode:
        if node.type == "export_statement":
            return node.child_by_field_name("declaration") or node
        return node

    def _overload_key(
        self, node: StructuralNode, raw: bytes
    ) -> tuple[str, str, bool] | None:
        kinds = {
            "function_signature": "function",
            "function_declaration": "function",
            "method_signature": "method",
            "method_definition": "method",
        }
        kind = kinds.get(node.type)
        name = node.child_by_field_name("name")
        return (
            (
                kind,
                self._text(raw, name),
                any(child.type == "static" for child in node.children),
            )
            if kind and name is not None
            else None
        )

    def _declaration_children(
        self, node: StructuralNode, raw: bytes
    ) -> list[StructuralNode]:
        """Join adjacent native overload declarations within one lexical scope."""
        children: list[StructuralNode] = []
        implementation: tuple[str, str, bool] | None = None
        for child in reversed(node.named_children):
            declaration = self._declaration(child)
            key = self._overload_key(declaration, raw)
            signature = declaration.type in {"function_signature", "method_signature"}
            if signature and key is not None and key == implementation:
                continue
            children.append(child)
            if declaration.type == "comment":
                continue
            implementation = (
                key if declaration.child_by_field_name("body") is not None else None
            )
        return list(reversed(children))

    def _symbols(
        self, tree: StructuralTree, source_bytes: bytes, language: str
    ) -> list[SymbolRecord]:
        found: list[SymbolRecord] = []

        def visit(node: StructuralNode, parent: str | None = None) -> None:
            current_parent = parent
            symbol = self._symbol_from_tree_node(node, parent, source_bytes)
            if symbol is not None:
                found.append(symbol)
                if symbol.kind in {
                    "class",
                    "interface",
                    "trait",
                    "struct",
                    "enum",
                    "namespace",
                    "function",
                    "method",
                    "constructor",
                }:
                    current_parent = symbol.qualname
            children = (
                self._declaration_children(node, source_bytes)
                if language in {"typescript", "tsx"}
                else node.named_children
            )
            for child in children:
                visit(child, current_parent)

        visit(tree.root_node)
        return found

    def _collect(self, source: str, language: str) -> list[SymbolRecord]:
        source_bytes = source.encode("utf-8")
        tree = self.syntax_tree(source_bytes, language)
        return [] if tree is None else self._symbols(tree, source_bytes, language)

    @staticmethod
    def _module_edges(tree: StructuralTree, raw: bytes) -> tuple[EdgeRecord, ...]:
        # Native import/export declarations prove source references. Calls named
        # require/import remain call syntax, not resolved module bindings.
        return tuple(
            EdgeRecord(
                None,
                "import",
                str(row["module_specifier"]),
                cast("int", row["line"]),
                "native",
            )
            for row in module_declarations(tree, raw)
            if isinstance(row["module_specifier"], str)
        )

    @staticmethod
    def _unavailable(artifact: ParsedArtifact, reason: str) -> ParsedArtifact:
        if artifact.language not in ECMASCRIPT_GRAMMARS:
            return artifact
        return replace(artifact, symbols=(), edges=(), outline="", parse_error=reason)

    @staticmethod
    def _merge(
        base: tuple[SymbolRecord, ...], structural: list[SymbolRecord]
    ) -> tuple[SymbolRecord, ...]:
        if not structural:
            return base
        by_name: dict[str, list[SymbolRecord]] = {}
        for row in structural:
            by_name.setdefault(row.name, []).append(row)
        merged: list[SymbolRecord] = []
        used: set[tuple[str, int]] = set()
        for row in base:
            candidates = by_name.get(row.name, ())
            best = None
            if candidates:
                best = min(
                    candidates,
                    key=lambda candidate: abs(candidate.start_line - row.start_line),
                )
            if best is None:
                merged.append(row)
                continue
            used.add((best.qualname, best.start_line))
            merged.append(
                replace(
                    row,
                    start_line=best.start_line,
                    end_line=max(best.start_line, best.end_line),
                    body_tokens=best.body_tokens,
                    signature=row.signature or best.signature,
                    signature_tokens=row.signature_tokens or best.signature_tokens,
                )
            )
        # Add structural symbols missed by the advisory parser. These are still
        # derived CodeMap evidence, never identity authority.
        for row in structural:
            if (row.qualname, row.start_line) not in used and not any(
                existing.name == row.name and existing.start_line == row.start_line
                for existing in merged
            ):
                merged.append(row)
        merged.sort(key=lambda row: (row.start_line, row.qualname))
        return tuple(merged)

    def enrich(
        self, artifact: ParsedArtifact, source: str | bytes, language: str
    ) -> ParsedArtifact:
        signature = self.signature(language)
        if signature is None:
            return self._unavailable(artifact, "native-syntax-unavailable")
        try:
            raw = source.encode("utf-8") if isinstance(source, str) else source
            tree = self.syntax_tree(raw, language)
            if tree is None:
                return self._unavailable(artifact, "native-syntax-unavailable")
            edges = (
                self._module_edges(tree, raw)
                if language in ECMASCRIPT_GRAMMARS
                else artifact.edges
            )
            structural = self._symbols(tree, raw, language)
        except SyntaxObservationBound:
            return self._unavailable(artifact, "native-syntax-node-bound")
        except Exception as exc:
            # Isolate optional-provider failure; ECMAScript has no alternate
            # structural parser that could strengthen unavailable syntax.
            reason = (
                exc.reason
                if isinstance(exc, SourceSyntaxError)
                else "native-syntax-parse-failed"
            )
            return self._unavailable(artifact, reason)
        if self.signature(language) != signature:
            return self._unavailable(artifact, "native-syntax-provider-changed")
        parser = f"{artifact.parser}+{signature}"
        # JS/TS native declarations include lexical scope and binding syntax.
        # Mixing the flat advisory names back in creates false global symbols.
        symbols = (
            tuple(structural)
            if language in ECMASCRIPT_GRAMMARS
            else self._merge(artifact.symbols, structural)
        )
        return replace(
            artifact,
            parser=parser,
            symbols=symbols,
            edges=edges,
            outline=(
                "\n".join(f"{row.signature}  [{row.start_line}]" for row in symbols)
                if language in ECMASCRIPT_GRAMMARS
                else artifact.outline
            ),
            parse_error=None
            if language in ECMASCRIPT_GRAMMARS
            else artifact.parse_error,
        )


def syntax_session(provider: SourceRangeProvider) -> AbstractContextManager[None]:
    """Share the canonical provider's operation lifecycle when it is available."""
    if isinstance(provider, TreeSitterRangeProvider):
        return provider.syntax_session()
    return nullcontext()
