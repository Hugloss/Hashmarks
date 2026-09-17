"Bounded static concurrency/read-modify-write risk nomination."

from __future__ import annotations

import ast
from dataclasses import dataclass

_READ_NAMES = {
    "get",
    "read",
    "fetch",
    "select",
    "generation",
    "load",
    "read_text",
    "fetchone",
}
_WRITE_NAMES = {
    "set",
    "write",
    "update",
    "insert",
    "save",
    "commit",
    "execute",
    "bump",
    "write_text",
}
_GUARD_NAMES = ("lock", "transaction", "begin", "atomic", "compare_and_swap", "cas")
_SCOPED_STATE_CONSTRUCTORS = {"ContextVar", "RunVar"}


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def _family(name: str) -> str:
    return name.rsplit(".", 1)[0] if "." in name else ""


@dataclass(frozen=True)
class Risk:
    path: str
    function: str
    line: int
    read_call: str
    write_call: str
    guarded: bool
    confidence: str

    def as_dict(self):
        return {
            "path": self.path,
            "function": self.function,
            "line": self.line,
            "read_call": self.read_call,
            "write_call": self.write_call,
            "guarded": self.guarded,
            "confidence": self.confidence,
            "code": "python-read-modify-write-without-visible-guard"
            if not self.guarded
            else "python-read-modify-write-visible-guard",
            "reason": (
                "A function reads and later writes through the same lexical owner without a visible lock/transaction guard."
                if not self.guarded
                else "A read/write sequence exists, but a visible lock/transaction guard is present."
            ),
            "recommendation": (
                "Verify atomicity at the durable owner; use a transaction/CAS/owner lock when concurrent callers are possible."
                if not self.guarded
                else "Retain the visible guard and verify that it serializes every caller that can reach the durable owner."
            ),
        }


@dataclass(frozen=True)
class _Event:
    line: int
    call: str
    leaf: str
    owner: str
    guards: frozenset[str]
    branches: tuple[tuple[int, object], ...]


class _CallCollector(ast.NodeVisitor):
    """Collect calls in one lexical statement without entering nested callables."""

    def __init__(self, os_aliases: frozenset[str]) -> None:
        self.os_aliases = os_aliases
        self.calls: list[tuple[int, str, str, str]] = []

    def _owner(self, node: ast.Call, name: str, leaf: str) -> str:
        family = _family(name)
        if family in self.os_aliases and leaf in {"read", "write"} and node.args:
            descriptor = _name(node.args[0])
            if descriptor:
                return descriptor
        return family

    def visit_Call(self, node: ast.Call) -> None:
        name = _name(node.func)
        leaf = name.lower().rsplit(".", 1)[-1]
        self.calls.append(
            (int(getattr(node, "lineno", 1)), name, leaf, self._owner(node, name, leaf))
        )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return


def _compatible_branches(
    left: tuple[tuple[int, object], ...], right: tuple[tuple[int, object], ...]
) -> bool:
    l = dict(left)
    r = dict(right)
    return all(l[key] == r[key] for key in l.keys() & r.keys())


def _target_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for item in node.elts:
            names.update(_target_names(item))
        return names
    return set()


def _fresh_local_value(node: ast.AST | None) -> bool:
    return isinstance(
        node,
        (
            ast.Dict,
            ast.List,
            ast.Set,
            ast.ListComp,
            ast.SetComp,
            ast.DictComp,
        ),
    ) or (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"dict", "list", "set"}
    )


class _LocalAssignmentCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.assignments: dict[str, list[bool]] = {}

    def _record(self, target: ast.AST, value: ast.AST | None) -> None:
        for name in _target_names(target):
            self.assignments.setdefault(name, []).append(_fresh_local_value(value))

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._record(target, node.value)
        self.generic_visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._record(node.target, node.value)
        if node.value is not None:
            self.generic_visit(node.value)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._record(node.target, node.value)
        self.generic_visit(node.value)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return


def _fresh_local_owners(node: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
    collector = _LocalAssignmentCollector()
    for stmt in node.body:
        collector.visit(stmt)
    parameters = {
        arg.arg
        for arg in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
    }
    if node.args.vararg is not None:
        parameters.add(node.args.vararg.arg)
    if node.args.kwarg is not None:
        parameters.add(node.args.kwarg.arg)
    return frozenset(
        name
        for name, values in collector.assignments.items()
        if name not in parameters and values and all(values)
    )


def _scoped_state_owners(tree: ast.Module) -> frozenset[str]:
    owners: set[str] = set()
    for node in tree.body:
        target: ast.AST | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if target is None or not isinstance(value, ast.Call):
            continue
        constructor = (
            value.func.value if isinstance(value.func, ast.Subscript) else value.func
        )
        if _name(constructor).rsplit(".", 1)[-1] in _SCOPED_STATE_CONSTRUCTORS:
            owners.update(_target_names(target))
    return frozenset(owners)


class V(ast.NodeVisitor):
    def __init__(
        self,
        path,
        os_aliases: frozenset[str] = frozenset({"os"}),
        scoped_state_owners: frozenset[str] = frozenset(),
    ):
        self.path = path
        self.os_aliases = os_aliases
        self.scoped_state_owners = scoped_state_owners
        self.r = []

    def _guard_owner(self, expr: ast.AST) -> str:
        target = expr.func if isinstance(expr, ast.Call) else expr
        name = _name(target)
        leaf = name.lower().rsplit(".", 1)[-1]
        if not any(g in leaf for g in _GUARD_NAMES):
            return ""
        return _family(name) or name.split(".", 1)[0]

    def _events_from_node(
        self,
        node: ast.AST,
        guards: frozenset[str],
        branches: tuple[tuple[int, object], ...],
    ) -> list[_Event]:
        c = _CallCollector(self.os_aliases)
        c.visit(node)
        return [
            _Event(line, n, leaf, owner, guards, branches)
            for line, n, leaf, owner in c.calls
        ]

    def _scan_with(self, stmt, guards, branches):
        events = []
        for item in stmt.items:
            events.extend(self._events_from_node(item.context_expr, guards, branches))
        inner = set(guards)
        for item in stmt.items:
            owner = self._guard_owner(item.context_expr)
            if owner:
                inner.add(owner)
        events.extend(self._scan_block(stmt.body, frozenset(inner), branches))
        return events

    def _scan_if(self, stmt, guards, branches):
        branch_id = id(stmt)
        return [
            *self._events_from_node(stmt.test, guards, branches),
            *self._scan_block(stmt.body, guards, branches + ((branch_id, 0),)),
            *self._scan_block(stmt.orelse, guards, branches + ((branch_id, 1),)),
        ]

    def _scan_loop(self, stmt, guards, branches):
        probe = stmt.iter if isinstance(stmt, (ast.For, ast.AsyncFor)) else stmt.test
        return [
            *self._events_from_node(probe, guards, branches),
            *self._scan_block(stmt.body, guards, branches),
            *self._scan_block(stmt.orelse, guards, branches),
        ]

    def _scan_try(self, stmt, guards, branches):
        events = self._scan_block(stmt.body, guards, branches)
        for handler in stmt.handlers:
            events.extend(self._scan_block(handler.body, guards, branches))
        events.extend(self._scan_block(stmt.orelse, guards, branches))
        events.extend(self._scan_block(stmt.finalbody, guards, branches))
        return events

    def _scan_match(self, stmt, guards, branches):
        events = self._events_from_node(stmt.subject, guards, branches)
        match_id = id(stmt)
        for index, case in enumerate(stmt.cases):
            events.extend(
                self._scan_block(case.body, guards, branches + ((match_id, index),))
            )
        return events

    def _scan_statement(self, stmt, guards, branches):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            events = []
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            events = self._scan_with(stmt, guards, branches)
        elif isinstance(stmt, ast.If):
            events = self._scan_if(stmt, guards, branches)
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            events = self._scan_loop(stmt, guards, branches)
        elif isinstance(stmt, ast.Try):
            events = self._scan_try(stmt, guards, branches)
        elif isinstance(stmt, ast.Match):
            events = self._scan_match(stmt, guards, branches)
        else:
            events = self._events_from_node(stmt, guards, branches)
        return events

    def _scan_block(
        self,
        body: list[ast.stmt],
        guards: frozenset[str] = frozenset(),
        branches: tuple[tuple[int, object], ...] = (),
    ) -> list[_Event]:
        events = []
        for stmt in body:
            events.extend(self._scan_statement(stmt, guards, branches))
        events.sort(key=lambda x: x.line)
        return events

    @staticmethod
    def _first_compatible_write(calls, start, owner):
        read = calls[start]
        for write in calls[start + 1 :]:
            if write.leaf not in _WRITE_NAMES or write.owner != owner:
                continue
            if _compatible_branches(read.branches, write.branches):
                return write
        return None

    def _risk_for_read(self, node, calls, index, fresh_local_owners: frozenset[str]):
        read = calls[index]
        if read.leaf not in _READ_NAMES:
            return None
        owner = read.owner
        if (
            not owner
            or owner in self.scoped_state_owners
            or owner in fresh_local_owners
        ):
            return None
        write = self._first_compatible_write(calls, index, owner)
        if write is None:
            return None
        guarded = owner in read.guards and owner in write.guards
        return Risk(
            self.path,
            node.name,
            read.line,
            read.call,
            write.call,
            guarded,
            "high" if guarded else "medium",
        )

    def _fn(self, node):
        calls = self._scan_block(node.body)
        fresh_local_owners = _fresh_local_owners(node)
        for index in range(len(calls)):
            risk = self._risk_for_read(node, calls, index, fresh_local_owners)
            if risk is not None:
                self.r.append(risk)
                return

    def visit_FunctionDef(self, node):
        self._fn(node)
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.visit(stmt)

    def visit_AsyncFunctionDef(self, node):
        self._fn(node)
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.visit(stmt)


def _os_aliases(tree: ast.Module) -> frozenset[str]:
    aliases = {"os"}
    for node in tree.body:
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            if alias.name == "os":
                aliases.add(alias.asname or "os")
    return frozenset(aliases)


def analyze_python_concurrency_risk(
    *, path: str, source: str, tree: ast.Module | None = None
):
    if tree is None:
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            return ()
    v = V(path, _os_aliases(tree), _scoped_state_owners(tree))
    v.visit(tree)
    return tuple(v.r)
