from __future__ import annotations

from dataclasses import dataclass, replace
from importlib import metadata
from typing import TYPE_CHECKING, Literal, Protocol

from .model import ParsedArtifact, SymbolRecord
from .python_ast import estimate_tokens

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

TREE_SITTER_RANGE_SCHEMA = "hashmarks.tree-sitter-ranges.v2"
_LanguageName = Literal[
    "python",
    "javascript",
    "typescript",
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


class TreeSitterRangeProvider:
    """Optional structural range enrichment for CodeMap.

    The provider is deliberately optional and lazy. Hashmarks does not depend on
    tree-sitter, and the Identity/Impact import graph never imports this module.
    When ``tree-sitter-language-pack`` is installed, CodeMap can use it to get
    robust symbol body ranges for supported languages while retaining Hashmarks'
    existing advisory/native evidence for names/imports/references.
    """

    _LANGUAGE_NAMES: dict[str, _LanguageName] = {
        "python": "python",
        "javascript": "javascript",
        "typescript": "typescript",
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
        "variable_declarator": "binding",
        "public_field_definition": "method",
    }

    def __init__(
        self,
        parser_factory: Callable[[_LanguageName], StructuralParser] | None = None,
        *,
        version: str | None = None,
        detail: str | None = None,
    ) -> None:
        self._parser_factory = parser_factory
        self.version = version
        self.detail = detail
        self._parsers: dict[str, StructuralParser] = {}

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
        except metadata.PackageNotFoundError:
            version = "unknown"
        return cls(get_parser, version=version)

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
        return f"{TREE_SITTER_RANGE_SCHEMA}:{self.version or 'unknown'}:{self._LANGUAGE_NAMES[language]}"

    def _parser(self, language: str) -> StructuralParser:
        name = self._LANGUAGE_NAMES[language]
        parser = self._parsers.get(name)
        if parser is not None:
            return parser
        assert self._parser_factory is not None
        parser = self._parser_factory(name)
        self._parsers[name] = parser
        return parser

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

    def _collect(self, source: str, language: str) -> list[SymbolRecord]:
        parser = self._parser(language)
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)
        if getattr(tree.root_node, "has_error", False):
            raise ValueError("native syntax tree contains errors")
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
            for child in node.named_children:
                visit(child, current_parent)

        visit(tree.root_node)
        return found

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
        self, artifact: ParsedArtifact, source: str, language: str
    ) -> ParsedArtifact:
        if not self.supports(language):
            return artifact
        try:
            structural = self._collect(source, language)
        except Exception:
            # Optional precision may fail closed to the existing parser. A bad
            # grammar/plugin must never make CodeMap unavailable.
            return artifact
        signature = self.signature(language)
        parser = (
            artifact.parser if signature is None else f"{artifact.parser}+{signature}"
        )
        # JS/TS native declarations include lexical scope and binding syntax.
        # Mixing the flat advisory names back in creates false global symbols.
        symbols = (
            tuple(structural)
            if language in {"javascript", "typescript"}
            else self._merge(artifact.symbols, structural)
        )
        return replace(artifact, parser=parser, symbols=symbols)
