"""Bounded syntax projections from the existing native parser's source tree.

This module interprets native node fields, never source text as a second parser.
It neither resolves symbols nor constructs an alias, call, or dependency graph.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from hashmarks.operation_contract import operation_schema

if TYPE_CHECKING:
    from .providers import StructuralNode, StructuralTree

ECMASCRIPT_SOURCE_SCHEMA = operation_schema("source_ecmascript")
MAX_SYNTAX_NODES = 100_000
EXPRESSION_PREVIEW_BYTES = 256
FACT_KINDS = (
    "import-binding",
    "export-binding",
    "binding",
    "destructured-binding",
    "assignment",
    "property-access",
    "call-site",
)
_CALLABLE_SCOPES = frozenset(
    {
        "function_declaration",
        "function_expression",
        "generator_function_declaration",
        "generator_function",
        "arrow_function",
        "method_definition",
    }
)
_SCOPE_TYPES = _CALLABLE_SCOPES | frozenset(
    {
        "program",
        "statement_block",
        "class_body",
        "catch_clause",
        "for_statement",
        "for_in_statement",
        "switch_body",
    }
)
_TYPE_CONTEXTS = frozenset(
    {
        "type_annotation",
        "type_alias_declaration",
        "type_query",
        "type_arguments",
        "type_parameters",
        "interface_declaration",
        "implements_clause",
        "extends_type_clause",
    }
)
_NAME_TYPES = frozenset(
    {
        "identifier",
        "property_identifier",
        "private_property_identifier",
        "shorthand_property_identifier_pattern",
        "type_identifier",
    }
)


class SyntaxObservationBound(ValueError):
    """A native tree exceeded the documented request-local traversal bound."""


def syntax_range(node: StructuralNode) -> dict[str, object]:
    """Native offsets refer to the original UTF-8 bytes, never decoded columns."""
    return {
        "start_byte": node.start_byte,
        "end_byte": node.end_byte,
    }


@dataclass(frozen=True, slots=True)
class _Visit:
    node: StructuralNode
    scope: StructuralNode
    parent: StructuralNode | None = None
    context: str = "value-syntax"
    module: StructuralNode | None = None
    declaration: StructuralNode | None = None

    def entered(self) -> _Visit:
        context = self.context
        if self.node.type in _TYPE_CONTEXTS:
            context = "type-syntax"
        elif self.node.type == "ambient_declaration":
            context = "ambient-syntax"
        return replace(
            self,
            scope=self.node if self.node.type in _SCOPE_TYPES else self.scope,
            context=context,
            module=(
                self.node
                if self.node.type in {"import_statement", "export_statement"}
                else self.module
            ),
            declaration=(
                self.node
                if self.node.type == "variable_declarator"
                else None
                if self.node.type in _CALLABLE_SCOPES
                or self.node.type == "formal_parameters"
                else self.declaration
            ),
        )


class _SyntaxProjection:
    """One byte capture's bounded display and native-field projection."""

    def __init__(self, raw: bytes) -> None:
        self.raw = raw

    def expression(self, node: StructuralNode | None) -> dict[str, object] | None:
        if node is None:
            return None
        end = min(node.end_byte, node.start_byte + EXPRESSION_PREVIEW_BYTES)
        return {
            "syntax_type": node.type,
            "range": syntax_range(node),
            "text": self.raw[node.start_byte : end].decode("utf-8", errors="ignore"),
            "text_truncated": end != node.end_byte,
        }

    def name(self, node: StructuralNode | None) -> str | None:
        """Expose only complete native identifier tokens, without name resolution."""
        expression = self.expression(node)
        if expression is None or expression["text_truncated"]:
            return None
        if "\\" in str(expression["text"]):
            return None
        if node is not None and node.type in _NAME_TYPES:
            return str(expression["text"])
        return None

    def property(
        self, node: StructuralNode | None, *, computed: bool = False
    ) -> dict[str, object]:
        """Computed expressions remain unresolved; simple string tokens are literal."""
        if node is not None and node.type == "computed_property_name":
            computed = True
            node = next(iter(node.named_children), None)
        return {
            "expression": self.expression(node),
            "name": None if computed else self.name(node),
            "literal_text": self._literal_text(node),
        }

    def _literal_text(self, node: StructuralNode | None) -> str | None:
        """Unescaped native string contents only; no evaluation or escape decoding."""
        if node is None or node.type != "string":
            return None
        expression = self.expression(node)
        assert expression is not None
        if expression["text_truncated"]:
            return None
        if any(child.type != "string_fragment" for child in node.named_children):
            return None
        return str(expression["text"])[1:-1]

    @staticmethod
    def _has_token(node: StructuralNode | None, token: str) -> bool:
        return node is not None and any(child.type == token for child in node.children)

    def _module_binding(self, visit: _Visit) -> dict[str, object] | None:
        if visit.module is None:
            return None
        node = visit.node
        name = node.child_by_field_name("name")
        alias = node.child_by_field_name("alias")
        return {
            "kind": "export-binding"
            if node.type == "export_specifier"
            else "import-binding",
            "source": self.expression(visit.module.child_by_field_name("source")),
            "name": self.name(name),
            "alias": self.name(alias or name),
            "name_expression": self.expression(name),
            "alias_expression": self.expression(alias or name),
            "type_only": self._has_token(node, "type")
            or self._has_token(visit.module, "type"),
        }

    def _namespace_binding(self, visit: _Visit) -> dict[str, object] | None:
        if visit.module is None:
            return None
        binding = next(iter(visit.node.named_children), None)
        return {
            "kind": "import-binding",
            "source": self.expression(visit.module.child_by_field_name("source")),
            "name": "*",
            "alias": self.name(binding),
            "name_expression": None,
            "alias_expression": self.expression(binding),
            "type_only": self._has_token(visit.module, "type"),
        }

    def _default_binding(self, visit: _Visit) -> dict[str, object] | None:
        if visit.parent is None or visit.parent.type != "import_clause":
            return None
        if visit.module is None:
            return None
        return {
            "kind": "import-binding",
            "source": self.expression(visit.module.child_by_field_name("source")),
            "name": "default",
            "alias": self.name(visit.node),
            "name_expression": None,
            "alias_expression": self.expression(visit.node),
            "type_only": self._has_token(visit.module, "type"),
        }

    def _binding(self, visit: _Visit) -> dict[str, object]:
        declaration_kind = None
        if visit.parent is not None:
            declaration_kind = next(
                (
                    child.type
                    for child in visit.parent.children
                    if child.type in {"const", "let", "var"}
                ),
                None,
            )
        return {
            "kind": "binding",
            "declaration_kind": declaration_kind,
            "binding": self.expression(visit.node.child_by_field_name("name")),
            "initializer": self.expression(visit.node.child_by_field_name("value")),
        }

    def _destructuring(self, visit: _Visit) -> dict[str, object] | None:
        node = visit.node
        key = node.child_by_field_name("key")
        binding = node.child_by_field_name("value")
        default = None
        if node.type == "shorthand_property_identifier_pattern":
            if visit.parent is None or visit.parent.type != "object_pattern":
                return None
            key = binding = node
        elif node.type == "object_assignment_pattern":
            key = binding = node.child_by_field_name("left")
            default = node.child_by_field_name("right")
        elif node.type == "rest_pattern":
            if visit.parent is None or visit.parent.type != "object_pattern":
                return None
            binding = next(iter(node.named_children), None)
        return self._destructured_record(visit, key, binding, default)

    def _destructured_record(
        self,
        visit: _Visit,
        key: StructuralNode | None,
        binding: StructuralNode | None,
        default: StructuralNode | None,
    ) -> dict[str, object]:
        if binding is not None and binding.type == "assignment_pattern":
            default = binding.child_by_field_name("right")
            binding = binding.child_by_field_name("left")
        return {
            "kind": "destructured-binding",
            "property": self.property(key),
            "computed": key is not None and key.type == "computed_property_name",
            "binding": self.expression(binding),
            "default": self.expression(default),
            "rest": visit.node.type == "rest_pattern",
            "pattern_range": syntax_range(visit.parent) if visit.parent else None,
            "declaration_range": syntax_range(visit.declaration)
            if visit.declaration
            else None,
        }

    def _assignment(self, visit: _Visit) -> dict[str, object]:
        operator = visit.node.child_by_field_name("operator")
        if operator is None:
            operator = next(
                (child for child in visit.node.children if child.type == "="), None
            )
        return {
            "kind": "assignment",
            "left": self.expression(visit.node.child_by_field_name("left")),
            "right": self.expression(visit.node.child_by_field_name("right")),
            "operator": self.expression(operator),
        }

    def _property_access(self, visit: _Visit) -> dict[str, object]:
        computed = visit.node.type == "subscript_expression"
        return {
            "kind": "property-access",
            "object": self.expression(visit.node.child_by_field_name("object")),
            "property": self.property(
                visit.node.child_by_field_name("index" if computed else "property"),
                computed=computed,
            ),
            "computed": computed,
            "optional": self._has_token(visit.node, "optional_chain"),
        }

    def _call(self, visit: _Visit) -> dict[str, object]:
        construct = visit.node.type == "new_expression"
        arguments = visit.node.child_by_field_name("arguments")
        return {
            "kind": "call-site",
            "call_kind": "construct" if construct else "call",
            "callee": self.expression(
                visit.node.child_by_field_name(
                    "constructor" if construct else "function"
                )
            ),
            "arguments": self.expression(arguments),
            "optional": self._has_token(visit.node, "?.")
            or self._has_token(visit.node, "optional_chain"),
            "resolved_target": None,
        }

    def fact(self, visit: _Visit) -> dict[str, object] | None:
        builder = {
            "import_specifier": self._module_binding,
            "export_specifier": self._module_binding,
            "namespace_import": self._namespace_binding,
            "identifier": self._default_binding,
            "variable_declarator": self._binding,
            "pair_pattern": self._destructuring,
            "shorthand_property_identifier_pattern": self._destructuring,
            "object_assignment_pattern": self._destructuring,
            "rest_pattern": self._destructuring,
            "assignment_expression": self._assignment,
            "augmented_assignment_expression": self._assignment,
            "member_expression": self._property_access,
            "subscript_expression": self._property_access,
            "call_expression": self._call,
            "new_expression": self._call,
        }.get(visit.node.type)
        detail = None if builder is None else builder(visit)
        if detail is None:
            return None
        return {
            **detail,
            "syntax_type": visit.node.type,
            "range": syntax_range(visit.node),
            "scope": {
                "syntax_type": visit.scope.type,
                "range": syntax_range(visit.scope),
            },
            "syntax_context": visit.context,
            "parent_syntax_type": visit.parent.type if visit.parent else None,
        }


def ecmascript_facts(
    tree: StructuralTree, raw: bytes, limit: int
) -> tuple[list[dict[str, object]], int]:
    """Count covered syntax facts and retain a deterministic bounded projection."""
    projection = _SyntaxProjection(raw)
    pending = [_Visit(tree.root_node, tree.root_node)]
    found: list[dict[str, object]] = []
    count = visited = 0
    while pending:
        visit = pending.pop().entered()
        visited += 1
        if visited > MAX_SYNTAX_NODES:
            raise SyntaxObservationBound("native-syntax-node-bound")
        fact = projection.fact(visit)
        if fact is not None:
            count += 1
            if len(found) < limit:
                found.append(fact)
        children = visit.node.named_children
        if visited + len(pending) + len(children) > MAX_SYNTAX_NODES:
            raise SyntaxObservationBound("native-syntax-node-bound")
        pending.extend(
            replace(visit, node=child, parent=visit.node)
            for child in reversed(children)
        )
    return found, count
