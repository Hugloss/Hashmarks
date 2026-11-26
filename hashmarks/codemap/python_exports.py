from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from functools import cached_property, lru_cache
from types import MappingProxyType
from typing import TYPE_CHECKING

from .model import symbol_occurrence_parts

if TYPE_CHECKING:
    from hashmarks.python_ast_cache import PythonAstSnapshot


def static_string_names(value: ast.expr | None) -> list[str] | None:
    """Return a static string collection, or None when runtime evaluation is needed."""
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return None
    names: list[str] = []
    for item in value.elts:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            return None
        names.append(item.value)
    return names


def python_reexport_targets(tree: ast.Module, exported_name: str) -> list[str]:
    """Return at most sixteen distinct top-level import targets in source order."""
    targets: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        _, candidates = _import_from_binding(node, exported_name)
        for target in candidates:
            if target not in targets:
                targets.append(target)
            if len(targets) >= 16:
                return targets
    return targets


@dataclass(frozen=True, slots=True)
class PythonExportBinding:
    kind: str
    targets: tuple[str, ...] = ()
    declaration: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None = None
    module_import: ast.alias | None = None
    replaces_assignment: bool = False

    @property
    def unwrapped_declaration(self) -> bool:
        return self.declaration is not None and not self.declaration.decorator_list

    def declaration_rows(
        self, name: str, rows: Sequence[dict[str, object]]
    ) -> list[dict[str, object]]:
        if self.declaration is None:
            return []
        return [
            row
            for row in rows
            if row.get("parent") is None
            and row.get("name") == name
            and (
                not self.replaces_assignment
                or row.get("start_line") == self.declaration.lineno
            )
        ]


@dataclass(frozen=True)
class PythonExportBindings:
    """Read-only binding syntax within one already parsed file snapshot."""

    body: tuple[ast.stmt, ...]
    writes: Mapping[ast.stmt, frozenset[str]]

    def binding(
        self, name: str, *, before_line: int | None = None
    ) -> PythonExportBinding:
        observed = _export_binding(
            self.body, name, self.writes, before_line=before_line
        )
        if observed.module_import is not None and any(
            observed.module_import.name == module
            or observed.module_import.name.startswith(module + ".")
            for module in self._mutated_modules
        ):
            # Keep the import spelling as provenance, without using this receiver
            # to prove an exact callable after an authored attribute write.
            return PythonExportBinding(observed.kind, observed.targets)
        return observed

    @cached_property
    def _mutated_modules(self) -> frozenset[str]:
        roots: set[str] = set()
        for statement in self.body:
            for node in ast.walk(statement):
                if isinstance(node, ast.Attribute) and isinstance(
                    node.ctx, (ast.Store, ast.Del)
                ):
                    target = node.value
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"setattr", "delattr"}
                    and node.args
                ):
                    target = node.args[0]
                else:
                    continue
                while isinstance(target, ast.Attribute):
                    target = target.value
                if isinstance(target, ast.Name):
                    roots.add(target.id)
        return frozenset(
            target
            for root in roots
            if (binding := _export_binding(self.body, root, self.writes)).kind
            == "module"
            for target in binding.targets
        )


@lru_cache(maxsize=256)
def python_export_bindings(
    absolute_path: str,
    source_identity: tuple[int, int, int, int, int],
    tree: ast.Module,
) -> PythonExportBindings:
    """Index one stable, read-only AST; callers retain freshness/visibility authority.

    Path, full parser-snapshot identity and the actual tree bind this disposable
    acceleration. Source-only APIs remain uncached and observe their input tree.
    """
    return PythonExportBindings(
        tuple(tree.body),
        MappingProxyType(
            {
                statement: frozenset(
                    _binding_writes(statement, annotation_targets_bind=False)
                )
                for statement in tree.body
            }
        ),
    )


def _export_binding(
    body: Sequence[ast.stmt],
    name: str,
    writes: Mapping[ast.stmt, frozenset[str]] | None = None,
    *,
    before_line: int | None = None,
) -> PythonExportBinding:
    bindings: list[PythonExportBinding] = []
    for node in body:
        binding = _statement_export_binding(
            node, name, None if writes is None else writes.get(node)
        )
        if binding is not None:
            # Module code and definition headers can run before the module's
            # final binding exists. The call index has line precision only.
            if (
                before_line is not None
                and (node.end_lineno or node.lineno) >= before_line
            ):
                return PythonExportBinding("ambiguous", binding.targets)
            bindings.append(binding)
    reexports = [row for row in bindings if row.kind in {"reexport", "star", "module"}]
    if len(reexports) > 1:
        targets = tuple(dict.fromkeys(t for row in reexports for t in row.targets))
        return PythonExportBinding("ambiguous", targets)
    if not bindings:
        return PythonExportBinding("unknown")
    last = bindings[-1]
    if last.declaration is not None and len(bindings) > 1:
        previous = bindings[-2]
        # An unconditional data assignment ended the earlier declaration's
        # binding. The following declaration has an exact source occurrence.
        if previous.kind == "local" and previous.declaration is None:
            return replace(last, replaces_assignment=True)
    return last


def python_export_binding(
    tree: ast.Module, exported_name: str
) -> tuple[str, list[str]]:
    """Preserve ordered binding qualification under the canonical syntax owner."""
    binding = _export_binding(tree.body, exported_name)
    return binding.kind, list(binding.targets)


def python_export_is_declaration(tree: ast.Module, exported_name: str) -> bool:
    return _export_binding(tree.body, exported_name).declaration is not None


def _binding_children(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        body = set(node.body)
        return [child for child in ast.iter_child_nodes(node) if child not in body]
    if isinstance(node, ast.Lambda):
        return [node.args]
    if isinstance(node, ast.comprehension):
        return [node.iter, *node.ifs]
    return list(ast.iter_child_nodes(node))


def _binding_nodes(node: ast.AST) -> Iterator[ast.AST]:
    yield node
    for child in _binding_children(node):
        yield from _binding_nodes(child)


def _class_global_names(node: ast.ClassDef) -> frozenset[str]:
    return frozenset(
        name
        for statement in node.body
        for child in _binding_nodes(statement)
        if isinstance(child, ast.Global)
        for name in child.names
    )


def _class_global_writes(node: ast.ClassDef) -> Iterator[str]:
    names = _class_global_names(node)
    for statement in node.body:
        yield from _binding_writes(statement, names, annotation_targets_bind=False)


def _node_binding_writes(node: ast.AST) -> Iterator[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        yield node.name
    if isinstance(node, ast.Name):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            yield node.id
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        yield from (alias.asname or alias.name.split(".")[0] for alias in node.names)
    if isinstance(
        node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar, ast.MatchMapping)
    ):
        bound_name = getattr(node, "name", getattr(node, "rest", None))
        if isinstance(bound_name, str):
            yield bound_name


def _binding_writes(
    node: ast.AST,
    names: frozenset[str] | None = None,
    *,
    include_class_globals: bool = True,
    annotation_targets_bind: bool = True,
) -> Iterator[str]:
    # Nested bodies are local; definition headers and walrus expressions can
    # still bind the containing scope. Comprehension iteration targets are local.
    if isinstance(node, ast.ClassDef) and include_class_globals:
        # Class construction executes its body now. Explicit global writes
        # escape that namespace, including writes by immediately nested classes.
        yield from _class_global_writes(node)
    yield from (
        name for name in _node_binding_writes(node) if names is None or name in names
    )
    for child in _binding_write_children(node, annotation_targets_bind):
        yield from _binding_writes(
            child,
            names,
            include_class_globals=include_class_globals,
            annotation_targets_bind=annotation_targets_bind,
        )


def _binding_write_children(
    node: ast.AST, annotation_targets_bind: bool
) -> list[ast.AST]:
    # Module/class annotation-only targets do not assign a name. Preserve
    # possible expression effects without assuming runtime annotation timing.
    children = _binding_children(node)
    if (
        isinstance(node, ast.AnnAssign)
        and node.value is None
        and isinstance(node.target, ast.Name)
        and not annotation_targets_bind
    ):
        children.remove(node.target)
    return children


def _writes_name(
    node: ast.AST, name: str, *, annotation_targets_bind: bool = True
) -> bool:
    return any(
        bound == name
        for bound in _binding_writes(
            node, annotation_targets_bind=annotation_targets_bind
        )
    )


def _arguments_bind(arguments: ast.arguments, name: str) -> bool:
    positional = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    positional.extend(
        arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None
    )
    return any(argument.arg == name for argument in positional)


def _call_uses_name(node: ast.Call, name: str) -> bool:
    target = node.func
    while isinstance(target, ast.Attribute):
        target = target.value
    return isinstance(target, ast.Name) and target.id == name


def _comprehension_body(
    node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
) -> Iterator[ast.expr]:
    yield from (generator.iter for generator in node.generators[1:])
    yield from (
        condition for generator in node.generators for condition in generator.ifs
    )
    if isinstance(node, ast.DictComp):
        yield node.key
        yield node.value
    else:
        yield node.elt


def _expression_bound_call(
    node: ast.AST, name: str, line: int, bound: bool = False
) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        # Headers execute before their declaration publishes its binding. The
        # final file binding therefore cannot qualify a self-named header call.
        # Decorators may precede the declaration's own lineno.
        return any(
            _expression_bound_call(child, name, line, bound or node.name == name)
            for child in _binding_children(node)
        )
    start = getattr(node, "lineno", None)
    if start is not None and not start <= line <= (
        getattr(node, "end_lineno", None) or start
    ):
        return False
    if (
        isinstance(node, ast.Call)
        and bound
        and node.lineno == line
        and _call_uses_name(node, name)
    ):
        return True
    if isinstance(node, ast.Lambda):
        defaults = [
            *node.args.defaults,
            *(value for value in node.args.kw_defaults if value is not None),
        ]
        return any(
            _expression_bound_call(value, name, line, bound) for value in defaults
        ) or _expression_bound_call(
            node.body,
            name,
            line,
            bound or _arguments_bind(node.args, name) or _writes_name(node.body, name),
        )
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        local = bound or any(
            _writes_name(generator.target, name) for generator in node.generators
        )
        return _expression_bound_call(
            node.generators[0].iter, name, line, bound
        ) or any(
            _expression_bound_call(value, name, line, local)
            for value in _comprehension_body(node)
        )
    return any(
        _expression_bound_call(child, name, line, bound)
        for child in _binding_children(node)
    )


def python_expression_call_binds(
    snapshot: PythonAstSnapshot, source: str, name: str, line: int
) -> bool:
    """Observe call-site shadowing without leaking expression locals into their parent.

    The compact call index has line coordinates only. A same-line collision
    therefore preserves uncertainty for every call with that receiver spelling.
    """
    body = snapshot.tree.body
    if source:
        functions = python_source_functions(
            snapshot.function_definitions_by_qualname, source
        )
        if len(functions) != 1:
            return True
        body = functions[0].body
    return any(_expression_bound_call(statement, name, line) for statement in body)


def python_source_functions(
    definitions: Mapping[str, tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]],
    source: str,
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]:
    """Match a lexical source occurrence only; a bare callee keeps its ambiguity."""
    qualname, line = symbol_occurrence_parts(source)
    functions = definitions.get(qualname, ())
    if line is not None:
        # A Python def cannot share a physical start line with another def.
        return tuple(function for function in functions if str(function.lineno) == line)
    return functions


def python_function_scope_binds(
    definitions: Mapping[str, tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]],
    qualname: str,
    name: str,
) -> bool:
    """Preserve local/closure shadowing before admitting module import identity.

    Unrelated methods and nested bodies cannot rebind this callable's names.
    Duplicate declarations or an unknown callable scope remain unresolved.
    """
    parts = qualname.split(".")
    for depth in range(1, len(parts) + 1):
        functions = python_source_functions(definitions, ".".join(parts[:depth]))
        if not functions and depth < len(parts):
            continue
        if len(functions) != 1:
            return True
        function = functions[0]
        if _arguments_bind(function.args, name) or any(
            _writes_name(statement, name) for statement in function.body
        ):
            return True
    return False


def _module_import_binding(node: ast.Import, name: str) -> PythonExportBinding | None:
    aliases = [
        alias
        for alias in node.names
        if (alias.asname or alias.name.split(".")[0]) == name
    ]
    if not aliases:
        return None
    targets = tuple(alias.name if alias.asname else name for alias in aliases)
    return PythonExportBinding(
        "module", targets, module_import=aliases[0] if len(aliases) == 1 else None
    )


def _statement_export_binding(
    node: ast.stmt, name: str, writes: frozenset[str] | None = None
) -> PythonExportBinding | None:
    if (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == name
    ):
        return PythonExportBinding("local", declaration=node)
    if isinstance(node, ast.ImportFrom):
        kind, targets = _import_from_binding(node, name)
        return PythonExportBinding(kind, tuple(targets)) if targets else None
    if isinstance(node, ast.Import):
        return _module_import_binding(node, name)
    if writes is None:
        writes = frozenset(_binding_writes(node, annotation_targets_bind=False))
    # A compound statement can conditionally import any star-exported name.
    # Its wildcard write does not prove which module supplied this binding.
    if name not in writes and "*" not in writes:
        return None
    if _assignment_binds(node, name):
        return PythonExportBinding("local")
    return PythonExportBinding("ambiguous")


def assignment_name_targets(target: ast.AST) -> Iterator[ast.Name]:
    """Yield lexical names actually assigned, in Python target order."""
    if isinstance(target, ast.Name):
        yield target
    elif isinstance(target, ast.Starred):
        yield from assignment_name_targets(target.value)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for child in target.elts:
            yield from assignment_name_targets(child)


def _assignment_target_binds(target: ast.AST, name: str) -> bool:
    return any(item.id == name for item in assignment_name_targets(target))


def _assignment_binds(node: ast.stmt, name: str) -> bool:
    if isinstance(node, getattr(ast, "TypeAlias", ())):
        target = getattr(node, "name", None)
        return isinstance(target, ast.AST) and _assignment_target_binds(target, name)
    if isinstance(node, ast.Assign):
        return any(_assignment_target_binds(target, name) for target in node.targets)
    if isinstance(node, ast.AugAssign) or (
        isinstance(node, ast.AnnAssign) and node.value is not None
    ):
        return _assignment_target_binds(node.target, name)
    return False


def python_class_export_binding(
    node: ast.ClassDef, name: str, *, before_line: int | None = None
) -> PythonExportBinding:
    if name in _class_global_names(node):
        return PythonExportBinding("ambiguous")
    writes = {
        statement: frozenset(
            _binding_writes(
                statement, include_class_globals=False, annotation_targets_bind=False
            )
        )
        for statement in node.body
    }
    return _export_binding(node.body, name, writes, before_line=before_line)


def python_class_node(
    tree: ast.Module, qualname: str, *, require_unwrapped: bool = False
) -> ast.ClassDef | None:
    """Locate a declaration; a call through its published path must qualify every component."""
    selected: ast.ClassDef | None = None
    for part in qualname.split("."):
        binding = (
            _export_binding(tree.body, part)
            if selected is None
            else python_class_export_binding(selected, part)
        )
        if not isinstance(binding.declaration, ast.ClassDef) or (
            require_unwrapped and not binding.unwrapped_declaration
        ):
            return None
        selected = binding.declaration
    return selected


def python_class_member_binding(
    node: ast.ClassDef, name: str
) -> tuple[str, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None]:
    """Expose the same ordered binding rule inside one declared class scope."""
    binding = python_class_export_binding(node, name)
    return binding.kind, binding.declaration


def python_function_body_binds(
    node: ast.FunctionDef | ast.AsyncFunctionDef, name: str
) -> bool:
    """Observe writes in the body separately from formal argument bindings."""
    return any(_writes_name(statement, name) for statement in node.body)


def python_import_target(node: ast.ImportFrom, name: str) -> str:
    """One spelling for indexed and qualified relative import evidence."""
    prefix = "." * node.level + (node.module or "")
    return f"{prefix}.{name}" if node.module else f"{prefix}{name}"


def _import_from_binding(
    node: ast.ImportFrom, exported_name: str
) -> tuple[str, list[str]]:
    targets: list[str] = []
    star = False
    for alias in node.names:
        if alias.name == "*":
            star = True
            name = exported_name
        elif (alias.asname or alias.name) == exported_name:
            name = alias.name
        else:
            continue
        target = python_import_target(node, name)
        if target:
            targets.append(target)
    return "star" if star else "reexport", list(dict.fromkeys(targets))


def python_import_alias_targets(tree: ast.Module, name: str) -> list[tuple[str, str]]:
    """Nominate at most seventeen explicit top-level imported alias bindings."""
    rows: list[tuple[str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            if alias.name == name:
                rows.append(
                    (alias.asname or alias.name, python_import_target(node, name))
                )
                if len(rows) == 17:
                    return rows
    return rows


class AllExportStatus(Enum):
    """Distinguish implicit exports from an explicitly unprovable declaration."""

    ABSENT = "absent"
    UNKNOWN = "unknown"


def static_all_exports(tree: ast.Module) -> list[str] | AllExportStatus:
    """Interpret supported top-level ``__all__`` declarations in source order.

    Unknown declarations and deletion are terminal: a later assignment cannot
    restore authority. Only ABSENT permits the caller's implicit-symbol fallback.
    This parser reads syntax only; the caller owns repository identity/freshness.
    """
    exports: list[str] | AllExportStatus = AllExportStatus.ABSENT
    for node in tree.body:
        exports = _all_statement_exports(node, exports)
        if exports is AllExportStatus.UNKNOWN:
            break
    return exports


def _targets_all(targets: list[ast.expr]) -> bool:
    return any(isinstance(item, ast.Name) and item.id == "__all__" for item in targets)


def _other_name_target(target: ast.expr) -> bool:
    """A plain sibling store may unpack names, but must not rebind __all__."""
    if isinstance(target, ast.Name):
        return target.id != "__all__"
    if isinstance(target, ast.Starred):
        return _other_name_target(target.value)
    return isinstance(target, (ast.Tuple, ast.List)) and all(
        _other_name_target(item) for item in target.elts
    )


def _all_assignment(node: ast.stmt) -> ast.expr | None:
    match node:
        case ast.Assign(targets=targets, value=value) if _targets_all(targets):
            # Each target receives the same value, in order. A computed store
            # can mutate that value and nested unpacking can replace __all__.
            if all(
                isinstance(target, ast.Name) or _other_name_target(target)
                for target in targets
            ):
                return value
        case ast.AnnAssign(target=ast.Name(id="__all__"), value=value):
            return value
    return None


def _all_statement_exports(
    node: ast.stmt, exports: list[str] | AllExportStatus
) -> list[str] | AllExportStatus:
    assigned = _all_assignment(node)
    if assigned is not None:
        names = static_string_names(assigned)
        return AllExportStatus.UNKNOWN if names is None else names
    match node:
        case ast.AugAssign(target=ast.Name(id="__all__"), op=op, value=value):
            if not isinstance(op, ast.Add):
                return AllExportStatus.UNKNOWN
            return _extend_all_exports(exports, value)
        case ast.Expr(
            value=ast.Call(
                func=ast.Attribute(value=ast.Name(id="__all__"), attr=method)
            ) as call
        ) if method in {"append", "extend"}:
            return _call_all_exports(exports, call, method)
    if _writes_name(
        node, "__all__", annotation_targets_bind=False
    ) or _mutates_module_all(node):
        return AllExportStatus.UNKNOWN
    return exports


def _may_mutate_all(node: ast.AST) -> bool:
    match node:
        case ast.AugAssign(target=ast.Name(id="__all__")):
            return True
        case ast.Subscript(value=ast.Name(id="__all__"), ctx=ast.Store() | ast.Del()):
            return True
        case ast.Call(func=ast.Attribute(value=ast.Name(id="__all__"), attr=method)):
            # The supported unconditional append/extend cases have already
            # been consumed. Do not execute other methods to derive membership.
            return method not in {"copy", "count", "index"}
    return False


def _all_value_children(node: ast.AST) -> Iterator[ast.AST]:
    discarded: ast.AST | None = None
    if isinstance(node, ast.Expr):
        discarded = node.value
    elif isinstance(node, (ast.If, ast.While, ast.Assert)):
        discarded = node.test
    for child in _binding_children(node):
        if child is discarded:
            # Discarding or truth-testing a generator only constructs its
            # outermost iterable. Stored or passed generators can be consumed.
            while isinstance(child, ast.GeneratorExp):
                child = child.generators[0].iter
        yield child


def _mutates_module_all(node: ast.AST, *, class_local: bool = False) -> bool:
    if not class_local and _may_mutate_all(node):
        return True
    if isinstance(node, ast.ClassDef) and _class_mutates_module_all(node):
        return True
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        # Only the first iterable reads the enclosing class namespace.
        return (
            _mutates_module_all(node.generators[0].iter, class_local=class_local)
            or any(_mutates_module_all(g.target) for g in node.generators)
            or any(_mutates_module_all(expr) for expr in _comprehension_body(node))
        )
    return any(
        _mutates_module_all(child, class_local=class_local)
        for child in _all_value_children(node)
    )


def _class_mutates_module_all(node: ast.ClassDef) -> bool:
    # A fresh class-local container is independent of module membership.
    class_local = False
    for statement in node.body:
        rebinds = _writes_name(statement, "__all__", annotation_targets_bind=False)
        # A simple augmented assignment reads the previous class-local
        # receiver. Its right-hand expression can still affect the module.
        if (
            class_local
            and isinstance(statement, ast.AugAssign)
            and _targets_all([statement.target])
        ):
            expression = statement.value
        else:
            expression = statement
        if _mutates_module_all(expression, class_local=class_local and not rebinds):
            return True
        if rebinds:
            class_local = isinstance(
                _all_assignment(statement), (ast.List, ast.Dict, ast.Set, ast.Tuple)
            )
    return False


def _extend_all_exports(
    exports: list[str] | AllExportStatus, value: ast.expr
) -> list[str] | AllExportStatus:
    names = static_string_names(value)
    if not isinstance(exports, list) or names is None:
        return AllExportStatus.UNKNOWN
    exports.extend(names)
    return exports


def _call_all_exports(
    exports: list[str] | AllExportStatus, call: ast.Call, method: str
) -> list[str] | AllExportStatus:
    if not isinstance(exports, list) or call.keywords or len(call.args) != 1:
        return AllExportStatus.UNKNOWN
    if method == "extend":
        return _extend_all_exports(exports, call.args[0])
    arg = call.args[0]
    if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
        return AllExportStatus.UNKNOWN
    exports.append(arg.value)
    return exports
