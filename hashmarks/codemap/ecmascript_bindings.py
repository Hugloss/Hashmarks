"""Bounded source-local ECMAScript binding observations from admitted syntax.

Symbolic import/global/property paths describe authored references and aliases.
They do not establish runtime object identity, callable values, reachability or
execution. Parameters never specialize from defaults or observed helper calls.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from .ecmascript_binding_scope import (
    Binding,
    BindingInventory,
    LexicalScope,
    node_key,
)
from .ecmascript_syntax import CALLABLE_SCOPES, SyntaxVisit, syntax_range
from .source_binding_contract import (
    MAX_ALIAS_DEPTH,
    MAX_BINDING_EXPRESSION_DEPTH,
    MAX_BINDING_SUPPORTING_RANGES,
    MAX_HELPER_EDGES,
    MAX_LITERAL_BYTES,
    BindingObservationBound,
)

if TYPE_CHECKING:
    from .providers import StructuralNode, StructuralTree

_WRAPPED_EXPRESSIONS = frozenset(
    {
        "parenthesized_expression",
        "as_expression",
        "satisfies_expression",
        "non_null_expression",
        "type_assertion",
    }
)


@dataclass(frozen=True)
class _Value:
    target: dict[str, object] | None = None
    literal: str | None = None
    support: tuple[StructuralNode, ...] = ()
    conditions: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    @property
    def qualification(self) -> str:
        return (
            "unknown"
            if self.reasons
            else "conditional"
            if self.conditions
            else "qualified"
        )

    def proof(self, *nodes: StructuralNode, conditions: tuple[str, ...] = ()) -> _Value:
        support = {node_key(node): node for node in (*self.support, *nodes)}
        if len(support) > MAX_BINDING_SUPPORTING_RANGES:
            return replace(
                self,
                target=None,
                literal=None,
                support=tuple(support.values())[:MAX_BINDING_SUPPORTING_RANGES],
                reasons=tuple(
                    sorted(set((*self.reasons, "supporting-evidence-bound")))
                ),
            )
        return replace(
            self,
            support=tuple(support.values()),
            conditions=tuple(sorted(set((*self.conditions, *conditions)))),
        )


def _unknown(reason: str, *support: StructuralNode) -> _Value:
    reasons = (reason,)
    if len(support) > MAX_BINDING_SUPPORTING_RANGES:
        reasons += ("supporting-evidence-bound",)
    return _Value(support=support[:MAX_BINDING_SUPPORTING_RANGES], reasons=reasons)


@dataclass(frozen=True)
class _Context:
    scope: LexicalScope
    position: int
    trail: tuple[Binding, ...] = ()
    depth: int = 0
    check_properties: bool = True

    def nested(self) -> _Context:
        return replace(self, depth=self.depth + 1)


@dataclass(frozen=True)
class _HelperCall:
    node: StructuralNode
    callee: StructuralNode
    value: _Value


def _target_key(target: dict[str, object]) -> tuple[str, ...]:
    return (
        str(target["kind"]),
        str(target.get("module", "")),
        str(target.get("name", "")),
        *cast("list[str]", target["properties"]),
    )


class _Resolver:
    def __init__(self, inventory: BindingInventory) -> None:
        self.inventory = inventory
        self.projection = inventory.projection
        self.property_writes: set[tuple[str, ...]] = set()
        for node, scope in inventory.property_writes:
            context = _Context(scope, node.start_byte, check_properties=False)
            prefix = self._write_prefix(node, context)
            if prefix is not None:
                self.property_writes.add(_target_key(prefix))

    def _write_prefix(
        self, node: StructuralNode, context: _Context
    ) -> dict[str, object] | None:
        current: StructuralNode | None = node
        for _ in range(MAX_BINDING_EXPRESSION_DEPTH + 1):
            if current is None:
                return None
            value = self.resolve(current, context)
            if value.target is not None:
                return value.target
            current = (
                self._wrapped_child(current)
                if current.type in _WRAPPED_EXPRESSIONS
                else current.child_by_field_name("object")
            )
        raise BindingObservationBound("property-write-depth-bound")

    def _qualified_property(self, value: _Value, context: _Context) -> _Value:
        if context.check_properties and value.target is not None:
            key = _target_key(value.target)
            if any(
                key[:length] in self.property_writes
                for length in range(1, len(key) + 1)
            ):
                return _unknown("source-property-reassigned", *value.support)
        return value

    def _identifier(self, node: StructuralNode, context: _Context) -> _Value:
        name = self.projection.name(node)
        if name is None:
            return _unknown("identifier-unqualified", node)
        bindings, reason = self.inventory.lookup(name, context.scope)
        if reason is not None:
            return _unknown(reason, node, *(binding.node for binding in bindings))
        if not bindings:
            return _Value(
                target={
                    "kind": "lexical-global",
                    "name": name,
                    "properties": [],
                    "runtime_identity": "not-established",
                },
                support=(node,),
            )
        if len(bindings) != 1:
            return _unknown(
                "competing-bindings", *(binding.node for binding in bindings)
            )
        return self.binding(bindings[0], context).proof(node)

    @staticmethod
    def _declaration(binding: Binding) -> _Value:
        return _Value(
            target={
                "kind": "declaration",
                "name": binding.name,
                "range": syntax_range(binding.declaration),
                "properties": [],
            },
            support=(binding.node, binding.declaration),
        )

    def binding(self, binding: Binding, context: _Context) -> _Value:
        reason = self._binding_reason(binding, context)
        if reason is not None:
            return _unknown(reason, binding.node, *binding.writes)
        if binding.kind == "import":
            return _Value(
                target=binding.import_target,
                support=(binding.declaration, binding.node),
            )
        if binding.kind in {"function", "declaration"}:
            return self._declaration(binding).proof(
                conditions=("captured-binding-initialization-not-observed",)
                if binding.kind == "declaration"
                and binding.scope.execution() is not context.scope.execution()
                else ()
            )
        assert binding.initializer is not None
        nested = _Context(
            binding.scope,
            binding.declaration.start_byte,
            (*context.trail, binding),
            context.depth + 1,
            context.check_properties,
        )
        value = self.resolve(binding.initializer, nested)
        for property_node in binding.properties:
            value = self._append(
                value, self._property_name(property_node, nested), property_node, nested
            )
        conditions = (
            ("captured-binding-initialization-not-observed",)
            if binding.scope.execution() is not context.scope.execution()
            else ()
        )
        return value.proof(binding.node, binding.initializer, conditions=conditions)

    @staticmethod
    def _binding_reason(binding: Binding, context: _Context) -> str | None:
        if binding.reason is not None:
            return binding.reason
        if binding.writes:
            return "binding-reassigned"
        if binding.kind in {"import", "function", "declaration"}:
            return (
                _Resolver._initialization_reason(binding, context)
                if binding.kind == "declaration"
                else None
            )
        if binding in context.trail or len(context.trail) >= MAX_ALIAS_DEPTH:
            return "alias-cycle-or-depth-bound"
        if binding.kind != "const":
            return {
                "parameter": "parameter-value-unknown",
                "catch": "catch-value-unknown",
                "iteration": "iteration-value-unknown",
            }.get(binding.kind, "mutable-or-unsupported-binding")
        return _Resolver._const_reason(binding, context)

    @staticmethod
    def _const_reason(binding: Binding, context: _Context) -> str | None:
        if binding.default is not None:
            return "destructuring-default-not-selected"
        if binding.initializer is None:
            return "initializer-unavailable"
        return _Resolver._initialization_reason(binding, context)

    @staticmethod
    def _initialization_reason(binding: Binding, context: _Context) -> str | None:
        if (
            binding.scope.execution() is context.scope.execution()
            and context.position < binding.declaration.end_byte
        ):
            return "binding-before-initialization"
        return None

    def _property_name(self, node: StructuralNode | None, context: _Context) -> _Value:
        if node is None:
            return _unknown("property-unqualified")
        if node.type == "computed_property_name":
            node = next(iter(node.named_children), None)
            return self.resolve(node, context.nested())
        name = self.projection.name(node)
        if name is not None:
            return _Value(literal=name, support=(node,))
        return self.resolve(node, context.nested())

    def _append(
        self, base: _Value, key: _Value, node: StructuralNode, context: _Context
    ) -> _Value:
        if base.reasons:
            return base
        if key.reasons:
            return key
        if base.target is None or key.literal is None:
            return _unknown("property-value-not-static", node)
        properties = [*cast("list[str]", base.target["properties"]), key.literal]
        if len(properties) > MAX_ALIAS_DEPTH:
            return _unknown("property-depth-bound", node)
        value = replace(base, target={**base.target, "properties": properties})
        return self._qualified_property(
            value.proof(*key.support, node, conditions=key.conditions), context
        )

    def _member(self, node: StructuralNode, context: _Context) -> _Value:
        base = self.resolve(node.child_by_field_name("object"), context.nested())
        key_node = node.child_by_field_name(
            "index" if node.type == "subscript_expression" else "property"
        )
        key = (
            self.resolve(key_node, context.nested())
            if node.type == "subscript_expression"
            else self._property_name(key_node, context)
        )
        value = self._append(base, key, node, context)
        return value.proof(
            conditions=("optional-access",) if self.projection.optional(node) else ()
        )

    def _literal(self, node: StructuralNode) -> _Value:
        literal = self.projection.literal_text(node)
        if literal is None:
            return _unknown("literal-syntax-unqualified", node)
        if len(literal.encode("utf-8")) > MAX_LITERAL_BYTES:
            return _unknown("literal-byte-bound", node)
        return _Value(literal=literal, support=(node,))

    def _binary(self, node: StructuralNode, context: _Context) -> _Value:
        if not any(child.type == "+" for child in node.children):
            return _unknown("unsupported-expression", node)
        left = self.resolve(node.child_by_field_name("left"), context.nested())
        right = self.resolve(node.child_by_field_name("right"), context.nested())
        if left.reasons or right.reasons:
            return left if left.reasons else right
        if left.literal is None or right.literal is None:
            return _unknown("non-string-concatenation", node)
        literal = left.literal + right.literal
        if len(literal.encode("utf-8")) > MAX_LITERAL_BYTES:
            return _unknown("literal-byte-bound", node)
        return _Value(literal=literal).proof(
            *left.support,
            *right.support,
            node,
            conditions=(*left.conditions, *right.conditions),
        )

    @staticmethod
    def _wrapped_child(node: StructuralNode) -> StructuralNode | None:
        children = [child for child in node.named_children if child.type != "comment"]
        if not children:
            return None
        return children[-1] if node.type == "type_assertion" else children[0]

    def _wrapped(self, node: StructuralNode, context: _Context) -> _Value:
        child = self._wrapped_child(node)
        return self.resolve(child, context.nested()).proof(node)

    def resolve(self, node: StructuralNode | None, context: _Context) -> _Value:
        if node is None or context.depth > MAX_BINDING_EXPRESSION_DEPTH:
            return _unknown("expression-unavailable-or-depth-bound")
        if node.type in {"identifier", "shorthand_property_identifier"}:
            return self._identifier(node, context)
        handlers = {"string": self._literal, "template_string": self._literal}
        if node.type in handlers:
            return handlers[node.type](node)
        if node.type in {"member_expression", "subscript_expression"}:
            return self._member(node, context)
        if node.type == "binary_expression":
            return self._binary(node, context)
        return self._other_expression(node, context)

    def _other_expression(self, node: StructuralNode, context: _Context) -> _Value:
        if node.type in _WRAPPED_EXPRESSIONS:
            return self._wrapped(node, context)
        if node.type in CALLABLE_SCOPES:
            return _Value(
                target={
                    "kind": "declaration",
                    "name": self.projection.name(node.child_by_field_name("name")),
                    "range": syntax_range(node),
                    "properties": [],
                },
                support=(node,),
            )
        return _unknown("unsupported-expression", node)


class _Observations:
    def __init__(self, inventory: BindingInventory) -> None:
        self.inventory = inventory
        self.resolver = _Resolver(inventory)
        self.projection = inventory.projection
        self.rows: list[dict[str, object]] = []
        self.helpers = {
            (entry.node.start_byte, entry.node.end_byte): entry
            for entry in inventory.functions.values()
        }

    def _row(
        self,
        kind: str,
        node: StructuralNode,
        scope: LexicalScope,
        value: _Value,
        *,
        binding: Binding | None = None,
    ) -> dict[str, object]:
        return {
            "kind": kind,
            "name": binding.name if binding else self.projection.name(node),
            "range": syntax_range(node),
            "scope": scope.record(),
            "expression": self.projection.expression(node),
            "qualification": value.qualification,
            "target": value.target,
            "literal": value.literal,
            "binding_range": syntax_range(binding.node) if binding else None,
            "supporting_ranges": [syntax_range(item) for item in value.support],
            "conditions": list(value.conditions),
            "reasons": list(value.reasons),
            "runtime_target": "not-established",
        }

    def _binding_row(self, binding: Binding) -> None:
        context = _Context(binding.scope, binding.declaration.end_byte)
        value = self.resolver.binding(binding, context)
        kind = (
            "import-binding"
            if binding.kind == "import"
            else "literal-binding"
            if value.literal is not None
            else "alias-binding"
            if binding.kind == "const"
            else "declaration"
        )
        node = binding.initializer or binding.node
        self.rows.append(self._row(kind, node, binding.scope, value, binding=binding))
        if binding.default is not None:
            default = (
                _unknown(binding.reason, binding.default)
                if binding.reason is not None
                else self.resolver.resolve(binding.default, context)
            ).proof(
                binding.node,
                conditions=(
                    "default-binding-only",
                    "argument-or-property-override-possible",
                ),
            )
            row = self._row(
                "default-binding",
                binding.default,
                binding.scope,
                default,
                binding=binding,
            )
            row["parameter"] = (
                self._parameter(binding) if binding.kind == "parameter" else None
            )
            self.rows.append(row)

    @staticmethod
    def _parameter(binding: Binding) -> dict[str, object]:
        return {
            "name": binding.name,
            "range": syntax_range(binding.node),
            "scope": binding.scope.record(),
        }

    def _reference(self, visit: SyntaxVisit) -> None:
        node = visit.node
        if node_key(node) in self.inventory.definitions:
            return
        if visit.parent is not None and visit.parent.type in {
            "import_specifier",
            "export_specifier",
            "namespace_import",
            "import_clause",
        }:
            return
        scope = self.inventory.scope(node)
        value = self.resolver.resolve(node, _Context(scope, node.start_byte))
        if visit.parent is not None and visit.parent.type.startswith("jsx_"):
            value = _unknown("jsx-name-interpretation-not-performed", node)
        self.rows.append(self._row("reference", node, scope, value))

    def _helper(
        self, node: StructuralNode, callee: StructuralNode, value: _Value
    ) -> None:
        if (
            MAX_HELPER_EDGES < 1
            or value.target is None
            or value.target["kind"] != "declaration"
            or value.target["properties"]
            or value.reasons
        ):
            return
        target = cast("dict[str, int]", value.target["range"])
        info = self.helpers.get((target["start_byte"], target["end_byte"]))
        arguments = node.child_by_field_name("arguments")
        if info is None or arguments is None:
            return
        arguments_list = [
            child for child in arguments.named_children if child.type != "comment"
        ]
        spread = False
        for index, argument in enumerate(arguments_list):
            spread = spread or argument.type == "spread_element"
            parameter = info.parameters[index] if index < len(info.parameters) else None
            self._argument(
                _HelperCall(node, callee, value), argument, parameter, spread
            )

    def _argument(
        self,
        call: _HelperCall,
        argument: StructuralNode,
        parameter: Binding | None,
        spread: bool,
    ) -> None:
        scope = self.inventory.scope(call.node)
        value = self.resolver.resolve(argument, _Context(scope, argument.start_byte))
        if spread or parameter is None:
            value = _unknown("helper-parameter-or-spread-unqualified", argument)
        value = value.proof(
            *call.value.support,
            *(() if parameter is None else (parameter.node,)),
            conditions=(
                *call.value.conditions,
                "observed-direct-call-only",
                "other-callers-not-excluded",
            ),
        )
        row = self._row("argument-binding", argument, scope, value, binding=parameter)
        row["parameter"] = None if parameter is None else self._parameter(parameter)
        row["call"] = {
            "range": syntax_range(call.node),
            "callee_range": syntax_range(call.callee),
        }
        self.rows.append(row)

    def _call(self, visit: SyntaxVisit) -> None:
        node = visit.node
        callee = node.child_by_field_name(
            "constructor" if node.type == "new_expression" else "function"
        )
        scope = self.inventory.scope(node)
        value = self.resolver.resolve(callee, _Context(scope, node.start_byte))
        if self.projection.optional(node):
            value = value.proof(conditions=("optional-call",))
        self.rows.append(self._row("call-site", node, scope, value))
        if callee is not None and node.type == "call_expression":
            self._helper(node, callee, value)

    def collect(self) -> list[dict[str, object]]:
        for binding in self.inventory.bindings:
            self._binding_row(binding)
        for visit in self.inventory.visits:
            if visit.context != "value-syntax":
                continue
            if visit.node.type in {"call_expression", "new_expression"}:
                self._call(visit)
            elif visit.node.type in {
                "identifier",
                "shorthand_property_identifier",
                "member_expression",
                "subscript_expression",
            }:
                self._reference(visit)
            elif visit.node.type in {"string", "template_string", "binary_expression"}:
                self._literal_row(visit)
        return sorted(self.rows, key=_row_key)

    def _literal_row(self, visit: SyntaxVisit) -> None:
        if visit.module is not None:
            return
        node = visit.node
        scope = self.inventory.scope(node)
        value = self.resolver.resolve(node, _Context(scope, node.start_byte))
        self.rows.append(self._row("literal-binding", node, scope, value))


def ecmascript_bindings(
    tree: StructuralTree, raw: bytes, limit: int
) -> tuple[list[dict[str, object]], int]:
    """Qualify the complete source scope before returning a bounded projection."""
    inventory = BindingInventory(tree, raw)
    rows = _Observations(inventory).collect()
    return rows[:limit], len(rows)


def _row_key(row: dict[str, object]) -> tuple[int, int, str]:
    span = cast("dict[str, int]", row["range"])
    return span["start_byte"], span["end_byte"], str(row["kind"])
