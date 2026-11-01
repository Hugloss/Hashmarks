"""Request-local lexical declarations over the canonical ECMAScript tree.

This inventory establishes lexical shadows and writes, not runtime values or
an independently persisted relationship graph. Unsupported bindings still
shadow an outer name, so a missing interpretation never manufactures a global.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .ecmascript_syntax import (
    CALLABLE_SCOPES,
    SyntaxProjection,
    SyntaxVisit,
    syntax_range,
    syntax_visits,
)
from .source_binding_contract import (
    MAX_ALIAS_DEPTH,
    MAX_BINDING_NODES,
    BindingObservationBound,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .providers import StructuralNode, StructuralTree

NodeKey = tuple[int, int, str]
_CLASS_NODES = frozenset({"class_declaration", "abstract_class_declaration", "class"})
_SCOPE_KINDS = {
    "program": "module",
    "statement_block": "block",
    "catch_clause": "catch",
    "for_statement": "loop",
    "for_in_statement": "loop",
    "switch_body": "block",
    "class_body": "class-body",
    "class_static_block": "class-static",
    "internal_module": "namespace",
    "with_statement": "dynamic",
}


def node_key(node: StructuralNode) -> NodeKey:
    return node.start_byte, node.end_byte, node.type


@dataclass(eq=False)
class LexicalScope:
    node: StructuralNode
    kind: str
    parent: LexicalScope | None
    name: str | None = None
    bindings: dict[str, list[Binding]] = field(default_factory=dict)
    dynamic: bool = False
    uncertain: set[str] = field(default_factory=set)
    unqualified_names: bool = False

    def record(self) -> dict[str, object]:
        return {"kind": self.kind, "range": syntax_range(self.node), "name": self.name}

    def execution(self) -> LexicalScope:
        scope = self
        while scope.parent is not None and scope.kind not in {
            "function",
            "module",
            "class-static",
        }:
            scope = scope.parent
        return scope

    def variable_owner(self) -> LexicalScope:
        scope = self
        while scope.parent is not None and scope.kind not in {
            "function-body",
            "module",
            "class-static",
            "namespace",
            "ambient-global",
        }:
            scope = scope.parent
        return scope


@dataclass(eq=False)
class Binding:
    name: str
    node: StructuralNode
    declaration: StructuralNode
    scope: LexicalScope
    kind: str
    initializer: StructuralNode | None = None
    properties: tuple[StructuralNode, ...] = ()
    default: StructuralNode | None = None
    reason: str | None = None
    import_target: dict[str, object] | None = None
    writes: list[StructuralNode] = field(default_factory=list)


@dataclass(frozen=True)
class _Pattern:
    node: StructuralNode
    properties: tuple[StructuralNode, ...] = ()
    default: StructuralNode | None = None
    reason: str | None = None


@dataclass
class FunctionParameters:
    node: StructuralNode
    scope: LexicalScope
    parameters: list[Binding | None] = field(default_factory=list)


def _pattern_children(pattern: _Pattern) -> list[_Pattern]:
    node = pattern.node
    left = node.child_by_field_name("left")
    if (
        node.type in {"assignment_pattern", "object_assignment_pattern"}
        and left is not None
    ):
        properties = pattern.properties + (
            (left,) if node.type == "object_assignment_pattern" else ()
        )
        return [
            _Pattern(
                left, properties, node.child_by_field_name("right"), pattern.reason
            )
        ]
    if node.type == "pair_pattern":
        value = node.child_by_field_name("value")
        key = node.child_by_field_name("key")
        return (
            []
            if value is None or key is None
            else [
                _Pattern(
                    value, (*pattern.properties, key), pattern.default, pattern.reason
                )
            ]
        )
    if node.type in {"required_parameter", "optional_parameter"}:
        value = node.child_by_field_name("pattern")
        return (
            []
            if value is None
            else [
                _Pattern(
                    value,
                    pattern.properties,
                    node.child_by_field_name("value"),
                    pattern.reason,
                )
            ]
        )
    if node.type == "object_pattern":
        return [
            _Pattern(
                child,
                (*pattern.properties, child)
                if child.type == "shorthand_property_identifier_pattern"
                else pattern.properties,
                pattern.default,
                pattern.reason,
            )
            for child in node.named_children
            if child.type != "comment"
        ]
    reason = pattern.reason
    if node.type in {"rest_pattern", "array_pattern"}:
        reason = "unsupported-destructuring"
    return [
        _Pattern(child, pattern.properties, pattern.default, reason)
        for child in node.named_children
        if child.type != "comment"
    ]


def pattern_names(
    node: StructuralNode, *, include_properties: bool = False
) -> Iterator[_Pattern]:
    pending = [_Pattern(node)]
    while pending:
        pattern = pending.pop()
        current = pattern.node
        if current.type in {"identifier", "shorthand_property_identifier_pattern"} or (
            include_properties
            and current.type in {"member_expression", "subscript_expression"}
        ):
            yield pattern
        elif current.type not in {
            "member_expression",
            "subscript_expression",
            "type_annotation",
        }:
            children = _pattern_children(pattern)
            for child in children:
                if len(child.properties) > MAX_ALIAS_DEPTH:
                    child = _Pattern(
                        child.node, (), child.default, "destructuring-depth-bound"
                    )
                pending.append(child)


class BindingInventory:
    """Collect complete lexical scope before resolving or clipping any use."""

    def __init__(self, tree: StructuralTree, raw: bytes) -> None:
        self.projection = SyntaxProjection(raw)
        self.visits = list(syntax_visits(tree))
        if len(self.visits) > MAX_BINDING_NODES:
            raise BindingObservationBound("binding-node-bound")
        self.scopes: dict[NodeKey, LexicalScope] = {}
        self.bindings: list[Binding] = []
        self.ambient_globals: dict[str, list[Binding]] = {}
        self.definitions: set[NodeKey] = set()
        self.functions: dict[NodeKey, FunctionParameters] = {}
        self.global_writes: set[str] = set()
        self.property_writes: list[tuple[StructuralNode, LexicalScope]] = []
        self._collect_scopes()
        self._collect_bindings()
        self._collect_writes()

    def _collect_scopes(self) -> None:
        for visit in self.visits:
            node = visit.node
            parent = self.scopes.get(node_key(visit.parent)) if visit.parent else None
            kind = (
                "function"
                if node.type in CALLABLE_SCOPES
                else "class"
                if node.type in _CLASS_NODES
                else _SCOPE_KINDS.get(node.type)
            )
            if kind == "block":
                kind = self._block_kind(visit)
            if kind is not None:
                parent = LexicalScope(
                    node,
                    kind,
                    parent,
                    self.projection.name(node.child_by_field_name("name")),
                    dynamic=kind == "dynamic",
                )
            assert parent is not None
            self.scopes[node_key(node)] = parent

    @staticmethod
    def _block_kind(visit: SyntaxVisit) -> str:
        parent = visit.parent
        if parent is not None:
            if parent.type in CALLABLE_SCOPES:
                return "function-body"
            if parent.type == "ambient_declaration" and any(
                child.type == "global" for child in parent.children
            ):
                return "ambient-global"
        return "block"

    def scope(self, node: StructuralNode) -> LexicalScope:
        return self.scopes[node_key(node)]

    def lookup(
        self, name: str, scope: LexicalScope
    ) -> tuple[list[Binding], str | None]:
        current: LexicalScope | None = scope
        while current is not None:
            if current.dynamic:
                return [], "dynamic-lexical-scope"
            if current.unqualified_names:
                return [], "binding-name-unqualified"
            if name in current.bindings:
                return current.bindings[name], None
            if name in current.uncertain:
                return [], "block-function-scope-unknown"
            current = current.parent
        if name in self.ambient_globals:
            return self.ambient_globals[name], "type-only-or-ambient-binding"
        return [], "global-name-reassigned" if name in self.global_writes else None

    def _add(self, binding: Binding) -> Binding:
        binding.scope.bindings.setdefault(binding.name, []).append(binding)
        if binding.scope.kind == "ambient-global":
            self.ambient_globals.setdefault(binding.name, []).append(binding)
        self.bindings.append(binding)
        self.definitions.add(node_key(binding.node))
        return binding

    def _pattern_bindings(
        self, node: StructuralNode, binding: Binding
    ) -> list[Binding]:
        found: list[Binding] = []
        for pattern in pattern_names(node):
            name = self.projection.name(pattern.node)
            if name is None:
                binding.scope.unqualified_names = True
                continue
            found.append(
                self._add(
                    Binding(
                        name,
                        pattern.node,
                        binding.declaration,
                        binding.scope,
                        binding.kind,
                        binding.initializer,
                        pattern.properties,
                        pattern.default,
                        binding.reason or pattern.reason,
                    )
                )
            )
        return found

    @staticmethod
    def _context_reason(visit: SyntaxVisit) -> str | None:
        return (
            "type-only-or-ambient-binding" if visit.context != "value-syntax" else None
        )

    def _variable(self, visit: SyntaxVisit) -> None:
        node = visit.node
        pattern = node.child_by_field_name("name")
        if pattern is None or visit.parent is None:
            return
        kind = next(
            (
                child.type
                for child in visit.parent.children
                if child.type in {"const", "let", "var"}
            ),
            "unsupported",
        )
        scope = self.scope(node)
        if kind == "var":
            scope = scope.variable_owner()
        base = Binding(
            "",
            pattern,
            node,
            scope,
            kind,
            node.child_by_field_name("value"),
            reason=self._context_reason(visit),
        )
        self._pattern_bindings(pattern, base)

    def _function_reason(self, visit: SyntaxVisit) -> str | None:
        reason = self._context_reason(visit)
        if reason is not None:
            return reason
        if (
            visit.node.type
            in {"function_declaration", "generator_function_declaration"}
            and visit.parent is not None
            and visit.parent.type
            not in {"program", "statement_block", "export_statement"}
        ):
            return "conditional-function-declaration"
        return None

    def _function(self, visit: SyntaxVisit) -> None:
        node = visit.node
        scope = self.scope(node)
        name_node = node.child_by_field_name("name")
        name = self.projection.name(name_node)
        if name_node is not None and name is None and node.type != "method_definition":
            (scope.parent or scope).unqualified_names = True
        if (
            name_node is not None
            and name is not None
            and node.type != "method_definition"
        ):
            declared = node.type in {
                "function_declaration",
                "generator_function_declaration",
            }
            owner = scope.parent if declared and scope.parent is not None else scope
            self._add(
                Binding(
                    name,
                    name_node,
                    node,
                    owner,
                    "function",
                    reason=self._function_reason(visit),
                )
            )
            if declared and owner.kind == "block":
                owner.execution().uncertain.add(name)
        parameters = node.child_by_field_name("parameters")
        single = node.child_by_field_name("parameter")
        entries = (
            list(parameters.named_children)
            if parameters is not None
            else [single]
            if single is not None
            else []
        )
        info = FunctionParameters(node, scope)
        for parameter in entries:
            if parameter.type == "comment":
                continue
            base = Binding(
                "",
                parameter,
                parameter,
                scope,
                "parameter",
                reason=self._context_reason(visit),
            )
            found = self._pattern_bindings(parameter, base)
            simple = (
                len(found) == 1 and not found[0].properties and found[0].reason is None
            )
            info.parameters.append(found[0] if simple else None)
        self.functions[node_key(node)] = info

    def _named_declaration(self, visit: SyntaxVisit) -> None:
        node = visit.node
        name_node = node.child_by_field_name("name")
        name = self.projection.name(name_node)
        if name_node is None or name is None:
            if name_node is not None:
                (self.scope(node).parent or self.scope(node)).unqualified_names = True
            return
        scope = self.scope(node)
        owner = (
            scope.parent
            if node.type in _CLASS_NODES | {"internal_module"}
            and scope.parent is not None
            and node.type != "class"
            else scope
        )
        reason = self._named_reason(visit)
        self._add(Binding(name, name_node, node, owner, "declaration", reason=reason))

    def _named_reason(self, visit: SyntaxVisit) -> str | None:
        reason = self._context_reason(visit)
        if reason is not None:
            return reason
        node = visit.node
        if node.type in {
            "function_signature",
            "interface_declaration",
            "type_alias_declaration",
        }:
            return "type-only-or-ambient-binding"
        decorated = (
            (node, visit.parent)
            if visit.parent is not None and visit.parent.type == "export_statement"
            else (node,)
        )
        if any(
            child.type == "decorator" for entry in decorated for child in entry.children
        ):
            return "decorated-declaration"
        return None

    def _import(self, visit: SyntaxVisit) -> None:
        fact = self.projection.fact(visit)
        if fact is None or fact["kind"] != "import-binding":
            return
        alias = fact["alias"]
        alias_expression = fact["alias_expression"]
        if not isinstance(alias, str) or alias_expression is None:
            self.scope(visit.node).unqualified_names = True
            return
        assert visit.module is not None
        node = visit.node.child_by_field_name(
            "alias"
        ) or visit.node.child_by_field_name("name")
        if node is None:
            node = (
                next(iter(visit.node.named_children), visit.node)
                if visit.node.type == "namespace_import"
                else visit.node
            )
        module = self.projection.literal_text(
            visit.module.child_by_field_name("source")
        )
        reason = (
            "type-only-or-ambient-binding"
            if fact["type_only"] or visit.context != "value-syntax"
            else "module-specifier-unqualified"
            if module is None
            else "import-name-unqualified"
            if fact["name"] is None
            else None
        )
        target = {
            "kind": "import",
            "module": module,
            "name": fact["name"],
            "level": 0,
            "properties": [],
            "module_resolution": "not-performed",
        }
        self._add(
            Binding(
                alias,
                node,
                visit.module,
                self.scope(visit.module),
                "import",
                reason=reason,
                import_target=target,
            )
        )
        for child in visit.node.named_children:
            if child.type == "identifier":
                self.definitions.add(node_key(child))

    def _special_pattern(self, visit: SyntaxVisit) -> None:
        node = visit.node
        field = "parameter" if node.type == "catch_clause" else "left"
        pattern = node.child_by_field_name(field)
        if pattern is None:
            return
        kind = next(
            (
                child.type
                for child in node.children
                if child.type in {"const", "let", "var"}
            ),
            None,
        )
        if node.type == "for_in_statement" and kind is None:
            return
        scope = self.scope(node)
        if kind == "var":
            scope = scope.variable_owner()
        self._pattern_bindings(
            pattern,
            Binding(
                "",
                pattern,
                node,
                scope,
                "iteration" if kind else "catch",
                reason=self._context_reason(visit),
            ),
        )

    def _unsupported_import(self, visit: SyntaxVisit) -> None:
        node = next(iter(visit.node.named_children), None)
        if node is not None:
            self._pattern_bindings(
                node,
                Binding(
                    "",
                    node,
                    visit.node,
                    self.scope(visit.node),
                    "import",
                    reason="unsupported-import-form",
                ),
            )

    def _collect_bindings(self) -> None:
        for visit in self.visits:
            kind = visit.node.type
            if kind == "variable_declarator":
                self._variable(visit)
            elif kind in CALLABLE_SCOPES:
                self._function(visit)
            elif kind in _CLASS_NODES | {
                "function_signature",
                "interface_declaration",
                "type_alias_declaration",
                "enum_declaration",
                "internal_module",
            }:
                self._named_declaration(visit)
            elif kind in {"catch_clause", "for_in_statement"}:
                self._special_pattern(visit)
            elif kind in {"import_alias", "import_require_clause"}:
                self._unsupported_import(visit)
            elif kind in {"import_specifier", "namespace_import", "identifier"}:
                self._import(visit)

    def _write(self, node: StructuralNode, scope: LexicalScope) -> None:
        for pattern in pattern_names(node, include_properties=True):
            if pattern.node.type in {"member_expression", "subscript_expression"}:
                self.property_writes.append((pattern.node, scope))
                continue
            name = self.projection.name(pattern.node)
            if name is None:
                scope.unqualified_names = True
                continue
            bindings, _ = self.lookup(name, scope)
            if bindings:
                for binding in bindings:
                    binding.writes.append(node)
            else:
                self.global_writes.add(name)

    def _collect_writes(self) -> None:
        for visit in self.visits:
            node = visit.node
            if node.type in {
                "assignment_expression",
                "augmented_assignment_expression",
                "for_in_statement",
            }:
                target = node.child_by_field_name("left")
            elif node.type in {"update_expression", "unary_expression"}:
                target = node.child_by_field_name("argument")
                if node.type == "unary_expression" and not any(
                    child.type == "delete" for child in node.children
                ):
                    target = None
            else:
                target = None
            if target is not None:
                self._write(target, self.scope(node))
            if node.type == "call_expression":
                callee = node.child_by_field_name("function")
                if (
                    callee is not None
                    and self.projection.name(callee) == "eval"
                    and not self.lookup("eval", self.scope(node))[0]
                ):
                    self.scope(node).execution().dynamic = True
