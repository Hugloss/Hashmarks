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
    MAX_BINDING_DETAILS,
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


def _qualification(reasons: tuple[str, ...], conditions: tuple[str, ...]) -> str:
    return "unknown" if reasons else "conditional" if conditions else "qualified"


def _supporting_nodes(
    *nodes: StructuralNode,
) -> tuple[tuple[StructuralNode, ...], bool]:
    support = {node_key(node): node for node in nodes}
    return (
        tuple(support.values())[:MAX_BINDING_SUPPORTING_RANGES],
        len(support) > MAX_BINDING_SUPPORTING_RANGES,
    )


@dataclass(frozen=True)
class _SymbolicPath:
    """Authored parameter paths retain source identity, never runtime values."""

    parameter: Binding
    properties: tuple[str, ...] = ()
    support: tuple[StructuralNode, ...] = ()
    conditions: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def proof(
        self, *nodes: StructuralNode, conditions: tuple[str, ...] = ()
    ) -> _SymbolicPath:
        support, bounded = _supporting_nodes(*self.support, *nodes)
        return replace(
            self,
            support=support,
            conditions=tuple(sorted(set((*self.conditions, *conditions)))),
            reasons=tuple(
                sorted(
                    set(
                        (
                            *self.reasons,
                            *(("supporting-evidence-bound",) if bounded else ()),
                        )
                    )
                )
            ),
        )

    def unknown(self, reason: str) -> _SymbolicPath:
        return replace(self, reasons=tuple(sorted(set((*self.reasons, reason)))))

    def key(self) -> tuple[str, ...]:
        return (
            "parameter",
            str(self.parameter.node.start_byte),
            str(self.parameter.node.end_byte),
            *self.properties,
        )

    def record(self) -> dict[str, object]:
        return {
            "root": {
                "kind": "parameter",
                "name": self.parameter.name,
                "range": syntax_range(self.parameter.node),
                "scope": self.parameter.scope.record(),
            },
            "properties": list(self.properties),
            "qualification": _qualification(self.reasons, self.conditions),
            "conditions": list(self.conditions),
            "reasons": list(self.reasons),
            "supporting_ranges": [syntax_range(node) for node in self.support],
            "runtime_identity": "not-established",
        }


@dataclass(frozen=True)
class _Value:
    target: dict[str, object] | None = None
    literal: str | None = None
    support: tuple[StructuralNode, ...] = ()
    conditions: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    symbolic: _SymbolicPath | None = None

    @property
    def qualification(self) -> str:
        return _qualification(self.reasons, self.conditions)

    def proof(self, *nodes: StructuralNode, conditions: tuple[str, ...] = ()) -> _Value:
        support, bounded = _supporting_nodes(*self.support, *nodes)
        symbolic = (
            self.symbolic.proof(*nodes, conditions=conditions)
            if self.symbolic is not None
            else None
        )
        if bounded:
            return replace(
                self,
                target=None,
                literal=None,
                support=support,
                symbolic=symbolic,
                reasons=tuple(
                    sorted(set((*self.reasons, "supporting-evidence-bound")))
                ),
            )
        return replace(
            self,
            support=support,
            symbolic=symbolic,
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


def _value_key(value: _Value) -> tuple[str, ...] | None:
    if value.target is not None:
        return _target_key(value.target)
    if value.symbolic is not None and not value.symbolic.reasons:
        return value.symbolic.key()
    return None


class _Resolver:
    def __init__(self, inventory: BindingInventory) -> None:
        self.inventory = inventory
        self.projection = inventory.projection
        self.property_writes: set[tuple[str, ...]] = set()
        for node, scope in inventory.property_writes:
            context = _Context(scope, node.start_byte, check_properties=False)
            prefix = self._write_prefix(node, context)
            if prefix is not None:
                self.property_writes.add(prefix)

    def _write_prefix(
        self, node: StructuralNode, context: _Context
    ) -> tuple[str, ...] | None:
        current: StructuralNode | None = node
        for _ in range(MAX_BINDING_EXPRESSION_DEPTH + 1):
            if current is None:
                return None
            value = self.resolve(current, context)
            key = _value_key(value)
            if key is not None:
                return key
            if set(value.reasons).intersection(
                {
                    "alias-cycle-or-depth-bound",
                    "expression-unavailable-or-depth-bound",
                    "supporting-evidence-bound",
                }
            ):
                raise BindingObservationBound("property-write-depth-bound")
            current = (
                self._wrapped_child(current)
                if current.type in _WRAPPED_EXPRESSIONS
                else current.child_by_field_name("object")
            )
        raise BindingObservationBound("property-write-depth-bound")

    def _qualified_property(self, value: _Value, context: _Context) -> _Value:
        key = _value_key(value)
        if context.check_properties and key is not None:
            if any(
                key[:length] in self.property_writes
                for length in range(1, len(key) + 1)
            ):
                return replace(
                    _unknown("source-property-reassigned", *value.support),
                    symbolic=value.symbolic.unknown("source-property-reassigned")
                    if value.symbolic is not None
                    else None,
                )
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
            value = _unknown(reason, binding.node, *binding.writes)
            if reason == "parameter-value-unknown":
                value = replace(
                    value, symbolic=_SymbolicPath(binding, support=(binding.node,))
                )
            return value
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
        self,
        base: _Value,
        key: _Value,
        node: StructuralNode,
        context: _Context,
        *,
        write_address: bool = False,
    ) -> _Value:
        if base.symbolic is not None:
            return self._append_symbolic(
                base, key, node, context, write_address=write_address
            )
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
        value = value.proof(*key.support, node, conditions=key.conditions)
        return value if write_address else self._qualified_property(value, context)

    def _append_symbolic(
        self,
        base: _Value,
        key: _Value,
        node: StructuralNode,
        context: _Context,
        *,
        write_address: bool,
    ) -> _Value:
        assert base.symbolic is not None
        symbolic = base.symbolic
        if key.reasons or key.literal is None:
            symbolic = symbolic.unknown("symbolic-property-key-unqualified")
        elif len(symbolic.properties) >= MAX_ALIAS_DEPTH:
            symbolic = symbolic.unknown("property-depth-bound")
        else:
            symbolic = replace(symbolic, properties=(*symbolic.properties, key.literal))
        value = replace(base, symbolic=symbolic).proof(
            *key.support, node, conditions=key.conditions
        )
        return value if write_address else self._qualified_property(value, context)

    def _member(
        self, node: StructuralNode, context: _Context, *, write_address: bool = False
    ) -> _Value:
        base = self.resolve(node.child_by_field_name("object"), context.nested())
        key_node = node.child_by_field_name(
            "index" if node.type == "subscript_expression" else "property"
        )
        key = (
            self.resolve(key_node, context.nested())
            if node.type == "subscript_expression"
            else self._property_name(key_node, context)
        )
        value = self._append(base, key, node, context, write_address=write_address)
        return value.proof(
            conditions=("optional-access",) if self.projection.optional(node) else ()
        )

    def write_address(self, node: StructuralNode, context: _Context) -> _Value:
        """Observe the destination without reading its previous property value."""
        return self._member(node, context, write_address=True)

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
        self.parents = {
            node_key(visit.node): visit.parent for visit in inventory.visits
        }
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
            "symbolic_reference": value.symbolic.record() if value.symbolic else None,
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
        row = self._row(kind, node, binding.scope, value, binding=binding)
        row["declaration_kind"] = self._declaration_kind(binding)
        if binding.kind == "import" and binding.import_target is not None:
            row["import_syntax"] = {
                "module": binding.import_target["module"],
                "name": binding.import_target["name"],
                "level": binding.import_target["level"],
                "local_name": binding.name,
            }
        self.rows.append(row)
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
    def _declaration_kind(binding: Binding) -> str:
        if binding.kind in {"function", "parameter", "import"}:
            return binding.kind
        if binding.declaration.type in {
            "class_declaration",
            "abstract_class_declaration",
            "class",
        }:
            return "class"
        return (
            "variable"
            if binding.kind in {"const", "let", "var"}
            else binding.declaration.type
        )

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
        row = self._row("call-site", node, scope, value)
        entries = self._argument_nodes(node)
        row.update(self._call_arguments(entries, scope))
        self.rows.append(row)
        if callee is not None and node.type == "call_expression":
            self._module_call(visit, callee, value, entries)
            self._helper(node, callee, value)

    @staticmethod
    def _argument_nodes(node: StructuralNode) -> list[StructuralNode]:
        arguments = node.child_by_field_name("arguments")
        return (
            []
            if arguments is None
            else [
                child for child in arguments.named_children if child.type != "comment"
            ]
        )

    def _call_arguments(
        self, entries: list[StructuralNode], scope: LexicalScope
    ) -> dict[str, object]:
        records: list[dict[str, object]] = []
        for index, argument in enumerate(entries[:MAX_BINDING_DETAILS]):
            value = self.resolver.resolve(
                argument, _Context(scope, argument.start_byte)
            )
            record = self._row("positional", argument, scope, value)
            record.update(
                kind="spread" if argument.type == "spread_element" else "positional",
                index=index,
                name=None,
            )
            records.append(record)
        clipped = len(entries) > len(records)
        return {
            "arguments": records,
            "argument_count": len(entries),
            "arguments_completeness": "incomplete" if clipped else "complete",
            "arguments_truncation": "truncated" if clipped else "not-truncated",
        }

    @staticmethod
    def _is_require(value: _Value) -> bool:
        return (
            value.target is not None
            and value.target["kind"] == "lexical-global"
            and value.target["name"] == "require"
            and not value.target["properties"]
            and not value.reasons
        )

    def _module_call(
        self,
        visit: SyntaxVisit,
        callee: StructuralNode,
        callee_value: _Value,
        arguments: list[StructuralNode],
    ) -> None:
        dynamic = callee.type == "import"
        require = self._is_require(callee_value)
        if not dynamic and not require and self.projection.name(callee) != "require":
            return
        scope = self.inventory.scope(visit.node)
        argument = arguments[0] if arguments else None
        value = self.resolver.resolve(argument, _Context(scope, visit.node.start_byte))
        if not dynamic and not require:
            value = _unknown("module-loader-callee-unqualified", callee)
        elif not arguments or arguments[0].type == "spread_element":
            value = _unknown("module-source-argument-unqualified", visit.node)
        elif value.literal is None:
            value = _unknown("module-specifier-unqualified", *value.support)
        value = value.proof(
            callee, conditions=() if dynamic else callee_value.conditions
        )
        row = self._row("module-declaration", visit.node, scope, value)
        row.update(
            declaration_kind="import-call" if dynamic else "require-call",
            module_specifier=value.literal,
            source=self.projection.expression(argument),
            type_only=visit.context != "value-syntax",
            module_resolution="not-performed",
        )
        self.rows.append(row)

    def _module_declaration(self, visit: SyntaxVisit) -> None:
        syntax = self.projection.fact(visit)
        if syntax is None:
            return
        source = visit.node.child_by_field_name("source")
        scope = self.inventory.scope(visit.node)
        value = self.resolver.resolve(source, _Context(scope, visit.node.start_byte))
        row = self._row("module-declaration", visit.node, scope, value)
        row.update(
            declaration_kind=syntax["declaration_kind"],
            module_specifier=value.literal,
            source=syntax["source"],
            type_only=syntax["type_only"],
            module_resolution="not-performed",
        )
        self.rows.append(row)

    def _parent_owner(
        self, node: StructuralNode, kinds: frozenset[str]
    ) -> StructuralNode | None:
        current = self.parents.get(node_key(node))
        for _ in range(MAX_BINDING_EXPRESSION_DEPTH + 1):
            if current is None or current.type in kinds:
                return current
            current = self.parents.get(node_key(current))
        return None

    @staticmethod
    def _write_syntax(owner: StructuralNode) -> dict[str, object]:
        kinds = {
            "assignment_expression": "assignment",
            "augmented_assignment_expression": "assignment",
            "update_expression": "update",
            "unary_expression": "delete",
            "for_in_statement": "iteration",
        }
        operator = owner.child_by_field_name("operator")
        token = (
            operator.type
            if operator is not None
            else next(
                (
                    child.type
                    for child in owner.children
                    if child.type in {"=", "delete", "in", "of"}
                ),
                None,
            )
        )
        return {
            "write_kind": kinds[owner.type],
            "operator": token,
            "reads_previous_value": owner.type
            in {"augmented_assignment_expression", "update_expression"},
        }

    def _property_writes(self) -> None:
        kinds = frozenset(
            {
                "assignment_expression",
                "augmented_assignment_expression",
                "update_expression",
                "unary_expression",
                "for_in_statement",
            }
        )
        for node, scope in self.inventory.property_writes:
            owner = self._parent_owner(node, kinds)
            value = self.resolver.write_address(node, _Context(scope, node.start_byte))
            if owner is None:
                value = _unknown("property-write-syntax-unqualified", node)
            row = self._row("property-write", owner or node, scope, value)
            row["destination"] = self.projection.expression(node)
            row.update(self._write_parts(node, scope))
            row["context"] = (
                "delete"
                if owner is not None and owner.type == "unary_expression"
                else "store"
            )
            if owner is not None:
                row.update(self._write_syntax(owner))
                row["value"] = self.projection.expression(
                    owner.child_by_field_name("right")
                )
            self.rows.append(row)

    def _write_parts(
        self, node: StructuralNode, scope: LexicalScope
    ) -> dict[str, object]:
        computed = node.type == "subscript_expression"
        receiver = node.child_by_field_name("object")
        key_node = node.child_by_field_name("index" if computed else "property")
        key = (
            self.resolver.resolve(key_node, _Context(scope, node.start_byte)).literal
            if computed
            else self.projection.name(key_node)
        )
        return {
            "access_kind": "subscript" if computed else "attribute",
            "property": key,
            "receiver": None
            if receiver is None
            else self._row(
                "receiver",
                receiver,
                scope,
                self.resolver.resolve(receiver, _Context(scope, node.start_byte)),
            ),
        }

    def _parameter_type(self, node: StructuralNode) -> dict[str, object]:
        annotation = node.child_by_field_name("type")
        children = (
            []
            if annotation is None
            else [
                child for child in annotation.named_children if child.type != "comment"
            ]
        )
        native = children[0] if len(children) == 1 else None
        predefined = (
            native is not None
            and native.type == "predefined_type"
            and len(native.children) == 1
        )
        return {
            "kind": "predefined" if predefined else "unqualified",
            "name": native.children[0].type
            if native is not None and predefined
            else None,
            "range": syntax_range(annotation) if annotation is not None else None,
            "expression": self.projection.expression(native),
            "qualification": "qualified" if predefined else "unknown",
            "conditions": [],
            "reasons": [] if predefined else ["type-resolution-not-performed"],
        }

    def _signature_parameter(
        self, node: StructuralNode, index: int
    ) -> dict[str, object]:
        pattern = node.child_by_field_name("pattern")
        rest = pattern is not None and pattern.type == "rest_pattern"
        name = (
            next(iter(pattern.named_children), None)
            if rest and pattern is not None
            else pattern
        )
        return {
            "index": index,
            "name": self.projection.name(name),
            "range": syntax_range(node),
            "expression": self.projection.expression(pattern),
            "optional": node.type == "optional_parameter",
            "rest": rest,
            "type": self._parameter_type(node),
        }

    def _callable_signature(self, visit: SyntaxVisit) -> None:
        node = visit.node
        container = self._signature_container(node)
        name = self.projection.name(node.child_by_field_name("name"))
        parameters = node.child_by_field_name("parameters")
        entries = (
            []
            if parameters is None
            else [
                child for child in parameters.named_children if child.type != "comment"
            ]
        )
        projected = [
            self._signature_parameter(child, index)
            for index, child in enumerate(entries[:MAX_BINDING_DETAILS])
        ]
        clipped = len(entries) > len(projected)
        value = self._signature_value(container, name, projected, clipped)
        row = self._row("callable-signature", node, self.inventory.scope(node), value)
        row.update(
            name=name,
            declaration_kind="method-signature",
            container=None
            if container is None
            else {
                "kind": "interface"
                if container.type == "interface_declaration"
                else "class",
                "name": self.projection.name(container.child_by_field_name("name")),
                "range": syntax_range(container),
            },
            syntax_context=visit.context,
            parameters=projected,
            parameter_count=len(entries),
            parameters_completeness="incomplete" if clipped else "complete",
            parameters_truncation="truncated" if clipped else "not-truncated",
        )
        self.rows.append(row)

    def _signature_container(self, node: StructuralNode) -> StructuralNode | None:
        body = self.parents.get(node_key(node))
        if body is None or body.type not in {"interface_body", "class_body"}:
            return None
        container = self.parents.get(node_key(body))
        return (
            container
            if container is not None
            and container.type
            in {
                "interface_declaration",
                "class_declaration",
                "abstract_class_declaration",
                "class",
            }
            else None
        )

    def _signature_value(
        self,
        container: StructuralNode | None,
        name: str | None,
        parameters: list[dict[str, object]],
        clipped: bool,
    ) -> _Value:
        if (
            container is None
            or self.projection.name(container.child_by_field_name("name")) is None
        ):
            return _unknown("callable-container-unqualified")
        if name is None:
            return _unknown("callable-name-unqualified")
        if clipped:
            return _unknown("callable-parameter-projection-bound", container)
        if any(
            cast("dict[str, object]", row["type"])["qualification"] != "qualified"
            for row in parameters
        ):
            return _unknown("callable-parameter-type-unqualified", container)
        return _Value(support=(container,))

    def collect(self) -> list[dict[str, object]]:
        for binding in self.inventory.bindings:
            self._binding_row(binding)
        self._property_writes()
        for visit in self.inventory.visits:
            self._visit(visit)
        return sorted(self.rows, key=_row_key)

    def _visit(self, visit: SyntaxVisit) -> None:
        if visit.node.type in {"import_statement", "export_statement"}:
            self._module_declaration(visit)
        elif visit.node.type in {"method_signature", "abstract_method_signature"}:
            self._callable_signature(visit)
        if visit.context != "value-syntax":
            self._type_module_call(visit)
            return
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

    def _type_module_call(self, visit: SyntaxVisit) -> None:
        if visit.node.type != "call_expression":
            return
        callee = visit.node.child_by_field_name("function")
        if callee is not None and callee.type == "import":
            self._module_call(
                visit,
                callee,
                _unknown("type-syntax-value-not-resolved", callee),
                self._argument_nodes(visit.node),
            )

    def _literal_row(self, visit: SyntaxVisit) -> None:
        node = visit.node
        scope = self.inventory.scope(node)
        value = self.resolver.resolve(node, _Context(scope, node.start_byte))
        self.rows.append(self._row("literal-expression", node, scope, value))


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
