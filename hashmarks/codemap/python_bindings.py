"""Qualified, source-local Python bindings from the canonical supplied AST.

Targets describe authored origins and lexical relationships, never runtime
objects or unconditional call targets. Defaults and one-edge helper inputs are
separate conditional observations; neither can resolve a parameter use.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from typing import cast

from .python_binding_scope import (
    FunctionNode,
    PythonBinding,
    PythonScope,
    PythonScopes,
    function_defaults,
    function_parameters,
)
from .source_binding_contract import (
    MAX_ALIAS_DEPTH,
    MAX_BINDING_EXPRESSION_DEPTH,
    MAX_BINDING_SUPPORTING_RANGES,
    MAX_LITERAL_BYTES,
)

_ImportKey = tuple[str, str | None, int, tuple[str, ...]]


@dataclass(frozen=True)
class _Value:
    target: dict[str, object] | None = None
    literal: str | None = None
    binding: ast.AST | None = None
    support: tuple[ast.AST, ...] = ()
    reasons: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    declaration: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None = None

    @property
    def qualification(self) -> str:
        if self.target is None and self.literal is None:
            return "unknown"
        return "conditional" if self.conditions else "qualified"


def _import_target(binding: PythonBinding) -> dict[str, object]:
    alias = cast(ast.alias, binding.node)
    imported = binding.imported
    return {
        "kind": "import",
        "module": (
            imported.module or ""
            if isinstance(imported, ast.ImportFrom)
            else alias.name
            if alias.asname
            else alias.name.split(".")[0]
        ),
        "name": alias.name if isinstance(imported, ast.ImportFrom) else None,
        "level": imported.level if isinstance(imported, ast.ImportFrom) else 0,
        "properties": [],
        "module_resolution": "not-performed",
    }


def _position(node: ast.AST) -> tuple[int, int]:
    return (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))


def _publication_position(binding: PythonBinding) -> tuple[int, int]:
    if binding.kind == "declaration":
        return (
            getattr(binding.node, "end_lineno", 0),
            getattr(binding.node, "end_col_offset", 0),
        )
    return _position(binding.node)


def _immediate_read(binding: PythonBinding, scope: PythonScope) -> bool:
    while scope is not binding.scope:
        if scope.kind == "function" or scope.parent is None:
            return False
        scope = scope.parent
    return True


def _line_offsets(raw: bytes) -> list[int]:
    """Python coordinates use UTF-8 columns and universal physical newlines."""
    offsets = [0]
    for index, byte in enumerate(raw):
        if byte == 10 or (byte == 13 and raw[index + 1 : index + 2] != b"\n"):
            offsets.append(index + 1)
    return offsets


def _import_key(target: dict[str, object] | None) -> _ImportKey | None:
    if target is None or target.get("kind") != "import":
        return None
    name = cast(str | None, target["name"])
    return (
        str(target["module"]),
        None,
        int(cast(int, target["level"])),
        (
            *((name,) if name is not None else ()),
            *cast(list[str], target["properties"]),
        ),
    )


class _PythonBindings:
    def __init__(self, tree: ast.Module, raw: bytes) -> None:
        self.raw = raw
        self.lines = _line_offsets(raw)
        self.syntax = PythonScopes(tree)
        self.rows: list[dict[str, object]] = []
        self._property_mutations: dict[_ImportKey, ast.AST] = {}
        self._observe_property_writes()

    def range(self, node: ast.AST) -> dict[str, int]:
        if isinstance(node, ast.Module):
            return {"start_byte": 0, "end_byte": len(self.raw)}
        start = self.lines[int(getattr(node, "lineno", 1)) - 1]
        end = self.lines[int(getattr(node, "end_lineno", 1)) - 1]
        return {
            "start_byte": start + int(getattr(node, "col_offset", 0)),
            "end_byte": end + int(getattr(node, "end_col_offset", 0)),
        }

    def scope(self, scope: PythonScope) -> dict[str, object]:
        return {"kind": scope.kind, "range": self.range(scope.node), "name": scope.name}

    def expression(self, node: ast.AST) -> dict[str, object]:
        span = self.range(node)
        raw = self.raw[span["start_byte"] : span["end_byte"]]
        return {
            "syntax_type": type(node).__name__,
            "range": span,
            "text": raw[:MAX_LITERAL_BYTES].decode("utf-8", errors="replace"),
            "text_truncated": len(raw) > MAX_LITERAL_BYTES,
        }

    def _declaration_target(self, node: ast.AST, name: str) -> dict[str, object]:
        return {
            "kind": "declaration",
            "name": name,
            "range": self.range(node),
            "properties": [],
        }

    def _unknown(self, reason: str, binding: PythonBinding | None = None) -> _Value:
        return _Value(
            binding=None if binding is None else binding.node,
            reasons=(reason,),
            support=() if binding is None else (binding.node,),
        )

    def _supported(self, value: _Value, *groups: tuple[ast.AST, ...]) -> _Value:
        nodes = tuple(dict.fromkeys(node for group in groups for node in group))
        if len(nodes) > MAX_BINDING_SUPPORTING_RANGES:
            return self._unknown("supporting-range-bound")
        return replace(value, support=nodes)

    def _name(
        self,
        node: ast.Name,
        scope: PythonScope,
        trail: tuple[PythonBinding, ...],
        depth: int = 0,
    ) -> _Value:
        binding = self.syntax.lookup(node.id, scope)
        if binding is None:
            return self._unknown("unresolved-lexical-name")
        if binding.kind == "unknown":
            return self._unknown(binding.reason or "unknown-binding", binding)
        if _immediate_read(binding, scope) and _publication_position(
            binding
        ) > _position(node):
            return self._unknown("read-before-binding", binding)
        return self._bound_value(binding, trail, depth)

    def _bound_value(
        self, binding: PythonBinding, trail: tuple[PythonBinding, ...], depth: int
    ) -> _Value:
        if binding.kind == "parameter":
            return self._unknown("parameter-value-unknown", binding)
        if binding.kind == "import":
            return self._checked_property(
                _Value(
                    target=_import_target(binding),
                    binding=binding.node,
                    support=(binding.node,),
                )
            )
        if binding.kind == "declaration":
            return self._declaration_value(binding)
        if binding in trail:
            return self._unknown("alias-cycle", binding)
        if len(trail) >= MAX_ALIAS_DEPTH:
            return self._unknown("alias-depth-bound", binding)
        value = self.resolve(binding.value, binding.scope, (*trail, binding), depth + 1)
        return self._supported(
            replace(value, binding=binding.node),
            value.support,
            (
                binding.node,
                *((binding.value,) if binding.value is not None else ()),
            ),
        )

    def _declaration_value(self, binding: PythonBinding) -> _Value:
        node = cast(ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, binding.node)
        if node.decorator_list:
            return self._unknown("decorated-declaration", binding)
        return _Value(
            target=self._declaration_target(node, binding.name),
            binding=node,
            support=(node,),
            declaration=node,
        )

    def _property(self, base: _Value, name: str) -> _Value:
        if base.target is None:
            return (
                base
                if base.literal is None
                else self._unknown("literal-property-unresolved")
            )
        if base.target["kind"] == "declaration":
            return self._unknown("declaration-property-unresolved")
        properties = cast(list[str], base.target["properties"])
        target = {**base.target, "properties": [*properties, name]}
        return self._checked_property(replace(base, target=target))

    def _checked_property(self, value: _Value) -> _Value:
        key = _import_key(value.target)
        if key is None:
            return value
        mutation = next(
            (
                self._property_mutations[(*key[:3], key[3][:depth])]
                for depth in range(len(key[3]) + 1)
                if (*key[:3], key[3][:depth]) in self._property_mutations
            ),
            None,
        )
        if mutation is not None:
            return self._supported(
                self._unknown("property-binding-may-be-mutated"),
                value.support,
                (mutation,),
            )
        return value

    def _literal(self, value: str, node: ast.AST) -> _Value:
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            return self._unknown("literal-not-utf8")
        if size > MAX_LITERAL_BYTES:
            return self._unknown("literal-byte-bound")
        return _Value(literal=value, support=(node,))

    def _concatenation(
        self,
        node: ast.BinOp,
        scope: PythonScope,
        trail: tuple[PythonBinding, ...],
        depth: int,
    ) -> _Value:
        if not isinstance(node.op, ast.Add):
            return self._unknown("unsupported-expression")
        left = self.resolve(node.left, scope, trail, depth + 1)
        right = self.resolve(node.right, scope, trail, depth + 1)
        if left.literal is None or right.literal is None:
            return _Value(
                reasons=tuple(
                    dict.fromkeys(
                        (*left.reasons, *right.reasons, "nonliteral-concatenation")
                    )
                )
            )
        value = self._literal(left.literal + right.literal, node)
        return self._supported(
            replace(
                value,
                conditions=tuple(dict.fromkeys((*left.conditions, *right.conditions))),
            ),
            left.support,
            right.support,
            (node,),
        )

    def _getattr(
        self,
        node: ast.Call,
        scope: PythonScope,
        trail: tuple[PythonBinding, ...],
        depth: int,
    ) -> _Value:
        if not (
            isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and self.syntax.lookup("getattr", scope) is None
        ):
            return self._unknown("unsupported-call-expression")
        if len(node.args) != 2 or node.keywords:
            return self._unknown("unsupported-getattr-arguments")
        attribute = self.resolve(node.args[1], scope, trail, depth + 1)
        if attribute.literal is None or not attribute.literal.isidentifier():
            return self._unknown("nonliteral-getattr-attribute")
        base = self.resolve(node.args[0], scope, trail, depth + 1)
        value = self._property(base, attribute.literal)
        return self._supported(
            replace(
                value,
                conditions=(
                    *value.conditions,
                    *attribute.conditions,
                    "unshadowed-builtin-getattr",
                ),
            ),
            value.support,
            attribute.support,
            (node,),
        )

    def resolve(
        self,
        node: ast.AST | None,
        scope: PythonScope,
        trail: tuple[PythonBinding, ...] = (),
        depth: int = 0,
    ) -> _Value:
        if depth >= MAX_BINDING_EXPRESSION_DEPTH:
            return self._unknown("expression-depth-bound")
        return self._resolve_expression(node, scope, trail, depth)

    def _resolve_expression(
        self,
        node: ast.AST | None,
        scope: PythonScope,
        trail: tuple[PythonBinding, ...],
        depth: int,
    ) -> _Value:
        if isinstance(node, ast.Name):
            return self._name(node, scope, trail, depth)
        if isinstance(node, ast.Attribute):
            return self._property(
                self.resolve(node.value, scope, trail, depth + 1), node.attr
            )
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return self._literal(node.value, node)
        if isinstance(node, ast.BinOp):
            return self._concatenation(node, scope, trail, depth)
        if isinstance(node, ast.Call):
            return self._getattr(node, scope, trail, depth)
        return self._unknown("unsupported-expression")

    def _observe_property_writes(self) -> None:
        mutations: dict[_ImportKey, ast.AST] = {}
        for node in self.syntax.nodes:
            key = self._property_write(node)
            if key is not None:
                mutations[key] = node
        self._property_mutations = mutations

    def _property_write(self, node: ast.AST) -> _ImportKey | None:
        if isinstance(node, ast.Attribute) and isinstance(
            node.ctx, (ast.Store, ast.Del)
        ):
            base, name = node.value, node.attr
        elif isinstance(node, ast.Call):
            return self._setattr_write(node)
        else:
            return None
        value = self.resolve(base, self.syntax.owners[node])
        key = _import_key(value.target)
        return None if key is None else (*key[:3], (*key[3], name))

    def _setattr_write(self, node: ast.Call) -> _ImportKey | None:
        if not (
            isinstance(node.func, ast.Name)
            and node.func.id in {"setattr", "delattr"}
            and self.syntax.lookup(node.func.id, self.syntax.owners[node]) is None
            and len(node.args) >= 2
        ):
            return None
        scope = self.syntax.owners[node]
        key = _import_key(self.resolve(node.args[0], scope).target)
        if key is None:
            return None
        name = self.resolve(node.args[1], scope).literal
        return key if name is None else (*key[:3], (*key[3], name))

    def row(
        self, kind: str, node: ast.AST, value: _Value, name: str | None = None
    ) -> dict[str, object]:
        supports = {tuple(self.range(item).values()) for item in value.support}
        conditions = [*value.conditions]
        if node in self.syntax.type_nodes:
            conditions.append("type-syntax")
        return {
            "kind": kind,
            "name": name,
            "range": self.range(node),
            "scope": self.scope(self.syntax.owners[node]),
            "expression": self.expression(node),
            "qualification": (
                "conditional"
                if conditions and value.qualification != "unknown"
                else value.qualification
            ),
            "target": value.target,
            "literal": value.literal,
            "binding_range": None
            if value.binding is None
            else self.range(value.binding),
            "supporting_ranges": [
                {"start_byte": start, "end_byte": end}
                for start, end in sorted(supports)
            ],
            "conditions": conditions,
            "reasons": list(value.reasons),
            "runtime_target": "not-established",
        }

    def _import_rows(self, node: ast.Import | ast.ImportFrom) -> None:
        scope = self.syntax.owners[node]
        for alias in node.names:
            if alias.name == "*":
                self.rows.append(
                    self.row("import-binding", alias, self._unknown("star-import"), "*")
                )
                continue
            name = alias.asname or alias.name.split(".")[0]
            binding = PythonBinding(name, alias, scope, "import", imported=node)
            value = _Value(
                target=_import_target(binding), binding=alias, support=(alias,)
            )
            active = self.syntax.lookup(name, scope)
            if active is None or active.node is not alias or active.reason is not None:
                value = replace(value, conditions=("binding-may-be-overwritten",))
            self.rows.append(self.row("import-binding", alias, value, name))

    def _assignment_rows(self, node: ast.Assign | ast.AnnAssign) -> None:
        if isinstance(node, ast.AnnAssign) and node.value is None:
            return
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            value = self._name(target, self.syntax.owners[target], ())
            row = self.row(
                "literal-binding" if value.literal is not None else "alias-binding",
                target,
                value,
                target.id,
            )
            row["expression"] = (
                None if node.value is None else self.expression(node.value)
            )
            self.rows.append(row)

    def _reference_row(self, node: ast.Name | ast.Attribute) -> None:
        if not isinstance(node.ctx, ast.Load):
            return
        value = self.resolve(node, self.syntax.owners[node])
        name = node.id if isinstance(node, ast.Name) else node.attr
        self.rows.append(self.row("reference", node, value, name))

    def _call_row(self, node: ast.Call) -> None:
        value = self.resolve(node.func, self.syntax.owners[node])
        if value.target is None and value.literal is not None:
            value = self._unknown("literal-call-target")
        row = self.row("call-site", node, value)
        row["expression"] = self.expression(node.func)
        self.rows.append(row)

    def _declaration_row(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ) -> None:
        value = _Value(
            target=self._declaration_target(node, node.name),
            binding=node,
            support=(node,),
        )
        row = self.row("declaration", node, value, node.name)
        row["expression"] = None
        self.rows.append(row)

    def _parameter(self, argument: ast.arg, scope: PythonScope) -> dict[str, object]:
        return {
            "name": argument.arg,
            "range": self.range(argument),
            "scope": self.scope(scope),
        }

    def _function_rows(self, node: FunctionNode, scope: PythonScope) -> None:
        for argument in function_parameters(node):
            value = _Value(
                target=self._declaration_target(argument, argument.arg),
                binding=argument,
            )
            row = self.row("declaration", argument, value, argument.arg)
            row.update(
                scope=self.scope(scope),
                parameter=self._parameter(argument, scope),
                expression=None,
            )
            self.rows.append(row)
        for argument, default in function_defaults(node):
            value = self.resolve(default, scope.defining or self.syntax.root)
            value = replace(value, conditions=(*value.conditions, "default-is-used"))
            row = self.row("default-binding", default, value, argument.arg)
            row.update(
                binding_range=self.range(argument),
                parameter=self._parameter(argument, scope),
            )
            self.rows.append(row)

    def _helper_calls(
        self,
    ) -> dict[ast.FunctionDef | ast.AsyncFunctionDef, list[ast.Call]]:
        calls: dict[ast.FunctionDef | ast.AsyncFunctionDef, list[ast.Call]] = {}
        for node in self.syntax.nodes:
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            value = self.resolve(node.func, self.syntax.owners[node])
            declaration = value.declaration
            if (
                isinstance(declaration, (ast.FunctionDef, ast.AsyncFunctionDef))
                and self.syntax.owners[declaration] is self.syntax.root
                and value.target is not None
            ):
                calls.setdefault(declaration, []).append(node)
        return calls

    def _argument_rows(
        self,
        node: ast.Call,
        function: ast.FunctionDef | ast.AsyncFunctionDef,
        single: bool,
    ) -> None:
        arguments, reason = _supplied_arguments(node, function)
        scope = self.syntax.function_scopes[function]
        for parameter, expression in arguments:
            value = self.resolve(expression, self.syntax.owners[node])
            if reason is not None or not single:
                value = self._unknown(reason or "multiple-helper-call-sites")
            value = replace(
                value,
                conditions=(
                    *value.conditions,
                    "caller-supplied-value",
                    *(("single-observed-local-call",) if single else ()),
                    "external-callers-not-observed",
                ),
            )
            row = self.row("argument-binding", expression or node, value, parameter.arg)
            row.update(
                binding_range=self.range(parameter),
                parameter=self._parameter(parameter, scope),
                call={"range": self.range(node), "callee_range": self.range(node.func)},
            )
            if expression is None:
                row["expression"] = None
            self.rows.append(row)

    def observe(self) -> list[dict[str, object]]:
        for node in self.syntax.nodes:
            self._node_rows(node)
        for function, scope in self.syntax.function_scopes.items():
            self._function_rows(function, scope)
        for function, calls in self._helper_calls().items():
            for call in calls:
                self._argument_rows(call, function, len(calls) == 1)
        return sorted(
            self.rows,
            key=lambda row: (
                cast(dict[str, int], row["range"])["start_byte"],
                str(row["kind"]),
            ),
        )

    def _node_rows(self, node: ast.AST) -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            self._import_rows(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            self._assignment_rows(node)
        elif isinstance(node, (ast.Name, ast.Attribute)):
            self._reference_row(node)
        elif isinstance(node, ast.Call):
            self._call_row(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self._declaration_row(node)


def _supplied_arguments(
    call: ast.Call, function: ast.FunctionDef | ast.AsyncFunctionDef
) -> tuple[list[tuple[ast.arg, ast.expr | None]], str | None]:
    parameters = [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]
    if function.args.vararg is not None or function.args.kwarg is not None:
        return [
            (parameter, None) for parameter in parameters
        ], "variadic-helper-parameters"
    if any(isinstance(arg, ast.Starred) for arg in call.args) or any(
        keyword.arg is None for keyword in call.keywords
    ):
        return [
            (parameter, None) for parameter in parameters
        ], "dynamic-helper-arguments"
    positional = [*function.args.posonlyargs, *function.args.args]
    if len(call.args) > len(positional):
        return [
            (parameter, None) for parameter in parameters
        ], "invalid-helper-arguments"
    provided = {
        parameter.arg: value
        for parameter, value in zip(positional, call.args, strict=False)
    }
    allowed = {
        parameter.arg for parameter in (*function.args.args, *function.args.kwonlyargs)
    }
    keywords = [keyword.arg for keyword in call.keywords]
    if len(keywords) != len(set(keywords)) or any(
        name not in allowed or name in provided for name in keywords
    ):
        return [
            (parameter, None) for parameter in parameters
        ], "invalid-helper-arguments"
    provided.update((str(keyword.arg), keyword.value) for keyword in call.keywords)
    defaults = {parameter.arg for parameter, _value in function_defaults(function)}
    if any(
        parameter.arg not in provided and parameter.arg not in defaults
        for parameter in parameters
    ):
        return [
            (parameter, provided.get(parameter.arg)) for parameter in parameters
        ], "missing-helper-arguments"
    return [
        (parameter, provided[parameter.arg])
        for parameter in parameters
        if parameter.arg in provided
    ], None


def python_bindings(
    tree: ast.Module, raw: bytes, limit: int
) -> tuple[list[dict[str, object]], int]:
    """Qualify the entire bounded syntax scope before projecting result limits."""
    rows = _PythonBindings(tree, raw).observe()
    return rows[:limit], len(rows)
