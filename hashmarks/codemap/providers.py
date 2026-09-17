from __future__ import annotations

from dataclasses import dataclass, replace
from importlib import metadata
from typing import Any, Callable

from .model import ParsedArtifact, SymbolRecord
from .python_ast import estimate_tokens


TREE_SITTER_RANGE_SCHEMA = "hashmarks.tree-sitter-ranges.v1"


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

    _LANGUAGE_NAMES = {
        "python": "python",
        "javascript": "javascript",
        "typescript": "typescript",
        "go": "go",
        "rust": "rust",
        "java": "java",
        "kotlin": "kotlin",
        "c": "c",
        "cpp": "cpp",
        "csharp": "c_sharp",
        "ruby": "ruby",
        "php": "php",
        "swift": "swift",
    }

    _SYMBOL_TYPES = {
        "function_definition": "function",
        "class_definition": "class",
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
        "function_expression": "function",
        "arrow_function": "function",
        "function_item": "function",
        "struct_item": "struct",
        "enum_item": "enum",
        "trait_item": "trait",
        "function_declaration": "function",
        "method_declaration": "method",
        "type_declaration": "type",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "method_declaration": "method",
        "constructor_declaration": "constructor",
    }

    def __init__(
        self,
        parser_factory: Callable[[str], Any] | None = None,
        *,
        version: str | None = None,
        detail: str | None = None,
    ) -> None:
        self._parser_factory = parser_factory
        self.version = version
        self.detail = detail
        self._parsers: dict[str, Any] = {}

    @classmethod
    def auto(cls) -> "TreeSitterRangeProvider":
        try:
            from tree_sitter_language_pack import get_parser  # type: ignore
        except Exception as exc:  # optional dependency must never block CodeMap
            return cls(None, detail=f"tree-sitter-language-pack unavailable: {exc.__class__.__name__}")
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

    def _parser(self, language: str):
        name = self._LANGUAGE_NAMES[language]
        parser = self._parsers.get(name)
        if parser is not None:
            return parser
        assert self._parser_factory is not None
        parser = self._parser_factory(name)
        self._parsers[name] = parser
        return parser

    @staticmethod
    def _name_node(node: Any):
        getter = getattr(node, "child_by_field_name", None)
        if getter is not None:
            for field in ("name", "declarator"):
                try:
                    value = getter(field)
                except Exception:
                    value = None
                if value is not None:
                    # Declarators may contain the identifier rather than being it.
                    if getattr(value, "type", "") in {"identifier", "type_identifier", "property_identifier", "field_identifier"}:
                        return value
                    for child in getattr(value, "children", ()):
                        if getattr(child, "type", "") in {"identifier", "type_identifier", "property_identifier", "field_identifier"}:
                            return child
        for child in getattr(node, "children", ()):
            if getattr(child, "type", "") in {"identifier", "type_identifier", "property_identifier", "field_identifier"}:
                return child
        return None

    @staticmethod
    def _text(source_bytes: bytes, node: Any) -> str:
        return source_bytes[int(node.start_byte): int(node.end_byte)].decode("utf-8", errors="replace")

    def _collect(self, source: str, language: str) -> list[SymbolRecord]:
        parser = self._parser(language)
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)
        found: list[SymbolRecord] = []

        def visit(node: Any, parent: str | None = None) -> None:
            node_type = str(getattr(node, "type", ""))
            current_parent = parent
            if node_type in self._SYMBOL_TYPES:
                name_node = self._name_node(node)
                if name_node is not None:
                    name = self._text(source_bytes, name_node).strip()
                    if name:
                        kind = self._SYMBOL_TYPES[node_type]
                        qualname = name if parent is None else f"{parent}.{name}"
                        start_line = int(node.start_point[0]) + 1
                        end_line = int(node.end_point[0]) + 1
                        full = self._text(source_bytes, node)
                        # Keep only the declaration/header for the compact outline.
                        header = full.split("{", 1)[0].split(":\n", 1)[0].strip()
                        if "\n" in header:
                            header = " ".join(part.strip() for part in header.splitlines() if part.strip())
                        if len(header) > 400:
                            header = header[:397] + "..."
                        found.append(SymbolRecord(
                            name=name,
                            qualname=qualname,
                            kind=kind,
                            signature=header or name,
                            start_line=start_line,
                            end_line=end_line,
                            signature_tokens=estimate_tokens(header or name),
                            body_tokens=estimate_tokens(full),
                            parent=parent,
                        ))
                        if kind in {"class", "interface", "trait", "struct", "enum"}:
                            current_parent = qualname
            for child in getattr(node, "named_children", getattr(node, "children", ())):
                visit(child, current_parent)

        visit(tree.root_node)
        return found

    @staticmethod
    def _merge(base: tuple[SymbolRecord, ...], structural: list[SymbolRecord]) -> tuple[SymbolRecord, ...]:
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
                best = min(candidates, key=lambda candidate: abs(candidate.start_line - row.start_line))
            if best is None:
                merged.append(row)
                continue
            used.add((best.qualname, best.start_line))
            merged.append(replace(
                row,
                start_line=best.start_line,
                end_line=max(best.start_line, best.end_line),
                body_tokens=best.body_tokens,
                signature=row.signature or best.signature,
                signature_tokens=row.signature_tokens or best.signature_tokens,
            ))
        # Add structural symbols missed by the advisory parser. These are still
        # derived CodeMap evidence, never identity authority.
        for row in structural:
            if (row.qualname, row.start_line) not in used and not any(existing.name == row.name and existing.start_line == row.start_line for existing in merged):
                merged.append(row)
        merged.sort(key=lambda row: (row.start_line, row.qualname))
        return tuple(merged)

    def enrich(self, artifact: ParsedArtifact, source: str, language: str) -> ParsedArtifact:
        if not self.supports(language):
            return artifact
        try:
            structural = self._collect(source, language)
        except Exception:
            # Optional precision may fail closed to the existing parser. A bad
            # grammar/plugin must never make CodeMap unavailable.
            return artifact
        signature = self.signature(language)
        parser = artifact.parser if signature is None else f"{artifact.parser}+{signature}"
        return replace(artifact, parser=parser, symbols=self._merge(artifact.symbols, structural))
