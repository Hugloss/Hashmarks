"""Bounded Python source-reference flow, using caller-owned call resolution.

No code is imported or executed. Equal source references do not prove equal
filesystem objects, feasible execution, exclusive ownership, or protection.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from .filesystem_lifecycle_contract import (
    DEFAULT_BOUNDS,
    IdentityComparison,
    LifecycleBounds,
)
from .filesystem_lifecycle_contract import lifecycle_identity as _reference_identity

CHECKS = frozenset(
    {
        "os.stat",
        "os.lstat",
        "os.fstat",
        "os.path.exists",
        "os.path.isdir",
        "os.path.isfile",
        "os.path.samefile",
    }
)
USES = frozenset({"os.rmdir", "os.unlink", "os.remove", "os.rename", "os.replace"})
MUTATIONS = frozenset({"os.mkdir", "os.makedirs", "os.symlink", "os.link"})
PATH_CHECKS = frozenset({"stat", "lstat", "exists", "is_dir", "is_file", "samefile"})
PATH_USES = frozenset({"rmdir", "unlink", "rename", "replace"})


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else ""
    return ""


@dataclass(frozen=True)
class Value:
    reference: str
    kind: str = "reference"
    literal: str | None = None


@dataclass(frozen=True)
class FunctionSource:
    path: str
    qualname: str
    revision: str
    node: ast.FunctionDef | ast.AsyncFunctionDef


@dataclass
class Flow:
    values: dict[str, Value] = field(default_factory=dict)
    checks: list[dict[str, object]] = field(default_factory=list)
    guards: list[dict[str, object]] = field(default_factory=list)
    trace: list[dict[str, object]] = field(default_factory=list)
    predicates: list[IdentityComparison] = field(default_factory=list)
    returned: Value | None = None
    stopped: bool = False

    def fork(self) -> Flow:
        return replace(
            self,
            values=dict(self.values),
            checks=list(self.checks),
            guards=list(self.guards),
            trace=list(self.trace),
            predicates=list(self.predicates),
        )


ResolveFunction = Callable[[FunctionSource, ast.Call], FunctionSource | None]
ResolveAPI = Callable[[str, str], str | None]


class _LocalBindings(ast.NodeVisitor):
    def __init__(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.names = {
            arg.arg
            for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
        }
        self.visit(node.args)
        for statement in node.body:
            self.visit(statement)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_arg(self, node: ast.arg) -> None:
        self.names.add(node.arg)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.names.add(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)

    def visit_Import(self, node: ast.Import) -> None:
        self.names.update(
            alias.asname or alias.name.split(".")[0] for alias in node.names
        )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.names.update(alias.asname or alias.name for alias in node.names)


class _StatementCalls(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        return

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return


class FilesystemSourceAnalyzer:
    def __init__(
        self,
        resolve: ResolveFunction,
        api: ResolveAPI,
        bounds: LifecycleBounds = DEFAULT_BOUNDS,
    ) -> None:
        self.resolve = resolve
        self.api = api
        self.bounds = bounds
        self.operations: list[dict[str, object]] = []
        self.observations: list[dict[str, object]] = []
        self.unresolved: list[dict[str, object]] = []
        self._active: list[tuple[str, str]] = []
        self._visited: set[tuple[str, str]] = set()
        self._calls: dict[tuple[str, str], int] = {}
        self._locals: dict[tuple[str, str], set[str]] = {}
        # Immutable syntax summaries belong to this request's AST snapshot.
        # Flow-dependent values, checks and call results are never cached here.
        self._nonlocals: dict[ast.AST, bool] = {}
        self._unsupported_syntax: dict[
            ast.AST, tuple[frozenset[str], tuple[ast.Call, ...]]
        ] = {}

    def analyze(self, source: FunctionSource) -> None:
        self._visited = set()
        self._calls = {}
        flow = Flow()
        for arg in (
            *source.node.args.posonlyargs,
            *source.node.args.args,
            *source.node.args.kwonlyargs,
        ):
            flow.values[arg.arg] = Value(f"{source.path}::{source.qualname}:{arg.arg}")
        self._function(source, flow)

    def issue(self, source: FunctionSource, node: ast.AST, reason: str) -> None:
        row = {
            "path": source.path,
            "symbol": source.qualname,
            "line": getattr(node, "lineno", 1),
            "reason": reason,
        }
        if row not in self.unresolved:
            self.unresolved.append(row)

    def _function(self, source: FunctionSource, flow: Flow) -> list[Flow]:
        key = (source.path, source.qualname)
        if key in self._active or len(self._active) > self.bounds.max_depth:
            self.issue(source, source.node, "cyclic-or-depth-bounded-call")
            return []
        if len(self._visited) >= self.bounds.symbols_per_anchor:
            self.issue(source, source.node, "symbol-limit")
            return []
        self._visited.add(key)
        self._active.append(key)
        self._calls.setdefault(key, 0)
        if key not in self._locals:
            self._locals[key] = _LocalBindings(source.node).names
        try:
            return self._block(source, source.node.body, [flow])
        finally:
            self._active.pop()

    def _block(
        self, source: FunctionSource, body: list[ast.stmt], flows: list[Flow]
    ) -> list[Flow]:
        for statement in body:
            following = []
            for flow in flows:
                following.extend(
                    [flow] if flow.stopped else self._statement(source, statement, flow)
                )
            flows = following[: self.bounds.symbols_per_anchor]
            if len(following) > len(flows):
                self.issue(source, statement, "control-flow-limit")
        return flows

    def _statement(
        self, source: FunctionSource, node: ast.stmt, flow: Flow
    ) -> list[Flow]:
        if isinstance(node, ast.If):
            self._value(source, node.test, flow)
            return self._block(source, node.body, [flow.fork()]) + self._block(
                source, node.orelse, [flow.fork()]
            )
        if isinstance(node, (ast.With, ast.AsyncWith)):
            return self._with(source, node, flow)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            self._assign(source, node, flow)
        elif isinstance(node, (ast.Expr, ast.Return, ast.Raise, ast.Assert)):
            self._expression_statement(source, node, flow)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            self._import(source, node, flow)
        elif not isinstance(node, (ast.Pass, ast.FunctionDef, ast.ClassDef)):
            self._unsupported(source, node, flow)
        return [flow]

    def _expression_statement(
        self, source: FunctionSource, node: ast.stmt, flow: Flow
    ) -> None:
        expression = getattr(node, "value", None)
        if isinstance(node, ast.Assert):
            expression = node.test
        if isinstance(expression, ast.expr):
            value = self._value(source, expression, flow)
            if isinstance(node, ast.Return):
                flow.returned = value
        if isinstance(node, (ast.Return, ast.Raise)):
            flow.stopped = True

    def _with(
        self, source: FunctionSource, node: ast.With | ast.AsyncWith, flow: Flow
    ) -> list[Flow]:
        if isinstance(node, ast.AsyncWith):
            self.issue(source, node, "async-interleaving-unresolved")
        count = len(flow.guards)
        for item in node.items:
            self._value(source, item.context_expr, flow)
            flow.guards.append(
                {
                    "path": source.path,
                    "line": node.lineno,
                    "expression": ast.unparse(item.context_expr),
                    "property": "lexical-context-only",
                }
            )
            if item.optional_vars is not None:
                self._bind(item.optional_vars, None, flow)
        flows = self._block(source, node.body, [flow])
        for result in flows:
            result.guards = result.guards[:count]
        return flows

    def _assign(
        self,
        source: FunctionSource,
        node: ast.Assign | ast.AnnAssign | ast.AugAssign,
        flow: Flow,
    ) -> None:
        value = (
            self._value(source, node.value, flow) if node.value is not None else None
        )
        if isinstance(node, ast.AugAssign):
            value = None
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            self._bind(target, value, flow)

    @staticmethod
    def _bind(target: ast.AST, value: Value | None, flow: Flow) -> None:
        if isinstance(target, ast.Attribute):
            root = dotted(target).split(".")[0]
            if root:
                flow.values[root] = Value("modified-attribute", "unresolved")
            return
        for name in ast.walk(target):
            if isinstance(name, ast.Name):
                if value is None or not isinstance(target, ast.Name):
                    flow.values.pop(name.id, None)
                else:
                    flow.values[name.id] = value

    def _unsupported(self, source: FunctionSource, node: ast.AST, flow: Flow) -> None:
        self.issue(source, node, "unsupported-control-flow-or-binding")
        # No check/use relation may cross an unsupported statement.
        flow.checks.clear()
        if node not in self._unsupported_syntax:
            assigned = frozenset(
                child.id
                for child in ast.walk(node)
                if isinstance(child, ast.Name)
                and isinstance(child.ctx, (ast.Store, ast.Del))
            )
            calls = _StatementCalls()
            if isinstance(node, (ast.Try, ast.For, ast.While, ast.AsyncFor, ast.Match)):
                calls.visit(node)
            self._unsupported_syntax[node] = (assigned, tuple(calls.calls))
        assigned, statement_calls = self._unsupported_syntax[node]
        for name in assigned:
            flow.values.pop(name, None)
        for call in statement_calls[: self.bounds.calls_per_symbol]:
            isolated = flow.fork()
            isolated.checks.clear()
            self._call(source, call, isolated)

    def _import(
        self, source: FunctionSource, node: ast.Import | ast.ImportFrom, flow: Flow
    ) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            if isinstance(node, ast.Import):
                target = alias.name if alias.asname else alias.name.split(".")[0]
            else:
                target = f"{node.module}.{alias.name}"
            if target.startswith(("os", "pathlib")) and not getattr(node, "level", 0):
                qualified = self.api(source.path, "@" + target)
                if qualified:
                    flow.values[name] = Value(qualified, "api")

    def _value(
        self, source: FunctionSource, node: ast.expr, flow: Flow
    ) -> Value | None:
        if isinstance(node, ast.Name):
            return flow.values.get(node.id)
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
            literal = (
                node.value.decode("utf-8", errors="replace")
                if isinstance(node.value, bytes)
                else node.value
            )
            return Value(f"literal:{node.value!r}", literal=literal)
        if isinstance(node, ast.Call):
            return self._call(source, node, flow)
        if isinstance(node, ast.Compare):
            self._comparison(source, node, flow)
            return None
        if isinstance(node, ast.Attribute):
            base = self._value(source, node.value, flow)
            if base is not None and base.kind == "metadata":
                return Value(f"{base.reference}.{node.attr}", "metadata-field")
        self._nested_values(source, node, flow)
        return None

    def _comparison(
        self, source: FunctionSource, node: ast.Compare, flow: Flow
    ) -> None:
        values = []
        for expression in (node.left, *node.comparators):
            terms = (
                expression.elts
                if isinstance(expression, (ast.Tuple, ast.List))
                else [expression]
            )
            values.extend(self._value(source, term, flow) for term in terms)
        fields = [
            value.reference
            for value in values
            if value is not None
            and value.kind == "metadata-field"
            and value.reference.rsplit(".", 1)[-1] in {"st_dev", "st_ino"}
        ]
        if fields:
            flow.predicates.append(
                {
                    "path": source.path,
                    "symbol": source.qualname,
                    "lines": [node.lineno, node.end_lineno or node.lineno],
                    "member_revision": source.revision,
                    "kind": "check",
                    "api": "python.metadata-comparison",
                    "fields": fields,
                    "operators": [type(op).__name__ for op in node.ops],
                    "qualification": "source-syntax-only",
                }
            )

    def _nested_values(self, source: FunctionSource, node: ast.AST, flow: Flow) -> None:
        # Conditional expressions and short-circuit operators cannot be flattened
        # into a fabricated unconditional check/use sequence.
        if isinstance(
            node,
            (
                ast.BoolOp,
                ast.IfExp,
                ast.Lambda,
                ast.Await,
                ast.ListComp,
                ast.SetComp,
                ast.DictComp,
                ast.GeneratorExp,
            ),
        ):
            self._unsupported(source, node, flow)
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._value(source, child, flow)

    def _api_name(
        self, source: FunctionSource, node: ast.AST, flow: Flow
    ) -> str | None:
        name = dotted(node)
        root, _, suffix = name.partition(".")
        value = flow.values.get(root)
        if value is not None:
            return (
                value.reference + ("." + suffix if suffix else "")
                if value.kind == "api"
                else None
            )
        if root in self._locals[(source.path, source.qualname)]:
            return None
        return self.api(source.path, name) if name else None

    def _call(self, source: FunctionSource, node: ast.Call, flow: Flow) -> Value | None:
        key = (source.path, source.qualname)
        self._calls[key] += 1
        if self._calls[key] > self.bounds.calls_per_symbol:
            self._unsupported(source, node, flow)
            self.issue(source, node, "call-limit")
            return None
        if any(isinstance(arg, ast.Starred) for arg in node.args) or any(
            kw.arg is None for kw in node.keywords
        ):
            self._unsupported(source, node, flow)
            self.issue(source, node, "variadic-operands-unresolved")
            return None
        receiver = (
            self._value(source, node.func.value, flow)
            if isinstance(node.func, ast.Attribute)
            else None
        )
        args = [self._value(source, arg, flow) for arg in node.args]
        keywords = {kw.arg: self._value(source, kw.value, flow) for kw in node.keywords}
        if dotted(node.func) in {"setattr", "delattr"} and node.args:
            root = dotted(node.args[0]).split(".")[0]
            if root:
                flow.values[root] = Value("modified-attribute", "unresolved")
        api = self._api_name(source, node.func, flow)
        if api in {"pathlib.Path", "pathlib.PosixPath", "pathlib.WindowsPath"}:
            return Value(self._result_reference(source, node, flow), "path")
        if api in CHECKS | USES | MUTATIONS:
            return self._operation(source, node, flow, (api, args, keywords))
        if receiver is not None and receiver.kind == "path":
            return self._path_call(source, node, flow, (receiver, args, keywords))
        return self._delegate(source, node, flow, (args, keywords))

    def _path_call(
        self,
        source: FunctionSource,
        node: ast.Call,
        flow: Flow,
        operands: tuple[Value, list[Value | None], dict[str | None, Value | None]],
    ) -> Value | None:
        receiver, args, keywords = operands
        method = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if method in PATH_CHECKS | PATH_USES:
            return self._operation(
                source,
                node,
                flow,
                (f"pathlib.Path.{method}", [receiver, *args], keywords),
            )
        self.issue(source, node, "unsupported-path-method")
        return None

    def _operation(
        self,
        source: FunctionSource,
        node: ast.Call,
        flow: Flow,
        operands: tuple[str, list[Value | None], dict[str | None, Value | None]],
    ) -> Value | None:
        api, args, keywords = operands
        is_check = api in CHECKS or api.rsplit(".", 1)[-1] in PATH_CHECKS
        is_use = api in USES or api.rsplit(".", 1)[-1] in PATH_USES
        kind = "check" if is_check else "use" if is_use else "mutation"
        operand = args[0] if args else keywords.get("path") or keywords.get("src")
        if api in {"os.link", "os.symlink"}:
            operand = args[1] if len(args) > 1 else keywords.get("dst")
        row = self._operation_record(source, node, kind, api)
        if api in {"os.link", "os.symlink"}:
            row["operand_role"] = "destination"
        row.update(
            self._operand_record(
                operand,
                keywords.get("dir_fd") or keywords.get("src_dir_fd"),
                "dir_fd" in keywords or "src_dir_fd" in keywords,
            )
        )
        row["guards"] = list(flow.guards)
        row["call_chain"] = list(flow.trace)
        self.operations.append(row)
        if operand is None:
            self.issue(source, node, "operand-identity-unresolved")
        elif is_check:
            flow.checks.append(row)
        elif is_use:
            self._relate(row, flow)
        self._secondary_operand(row, args, keywords, flow)
        if is_check and operand is not None:
            return Value(operand.reference, "metadata")
        return None

    @staticmethod
    def _operation_record(
        source: FunctionSource, node: ast.Call, kind: str, api: str
    ) -> dict[str, object]:
        return {
            "path": source.path,
            "symbol": source.qualname,
            "lines": [node.lineno, node.end_lineno or node.lineno],
            "column": node.col_offset,
            "member_revision": source.revision,
            "kind": kind,
            "api": api,
            "operand_role": "source",
            "selection_kind": "descriptor"
            if api == "os.fstat"
            else "path-or-descriptor"
            if api == "os.stat"
            else "name-or-path",
        }

    @staticmethod
    def _operand_record(
        operand: Value | None, parent: Value | None, supplied: bool = False
    ) -> dict[str, object]:
        if operand is not None and operand.kind not in {"reference", "path"}:
            operand = None
        anchoring = "supplied-unresolved" if supplied else "not-supplied"
        if parent is not None:
            anchoring = "conditional-relative-path"
            if operand is not None and operand.literal is not None:
                anchoring = (
                    "ignored-absolute-path"
                    if operand.literal.startswith("/")
                    else "relative-path"
                )
        return {
            "reference": operand.reference if operand else None,
            "dir_fd_reference": parent.reference if parent else None,
            "dir_fd_supplied": supplied,
            "parent_binding": anchoring,
            "descriptor_lifetime": "unverified",
        }

    def _secondary_operand(
        self,
        row: dict[str, object],
        args: list[Value | None],
        keywords: dict[str | None, Value | None],
        flow: Flow,
    ) -> None:
        if row["api"] in {"os.path.samefile", "pathlib.Path.samefile"}:
            if len(args) > 1:
                other = {
                    **row,
                    "operand_role": "comparison-other",
                    **self._operand_record(args[1], None),
                }
                self.operations.append(other)
                flow.checks.append(other)
            return
        if row["api"] not in {
            "os.rename",
            "os.replace",
            "pathlib.Path.rename",
            "pathlib.Path.replace",
        }:
            return
        target = (
            args[1] if len(args) > 1 else keywords.get("dst") or keywords.get("target")
        )
        destination = {
            **row,
            "operand_role": "destination",
            **self._operand_record(
                target, keywords.get("dst_dir_fd"), "dst_dir_fd" in keywords
            ),
        }
        self.operations.append(destination)
        if target is not None:
            self._relate(destination, flow)

    def _relate(self, use: dict[str, object], flow: Flow) -> None:
        for check in flow.checks:
            if not check["reference"] or check["reference"] != use["reference"]:
                continue
            namespace = "unverified"
            if check["dir_fd_reference"] == use["dir_fd_reference"] and (
                use["dir_fd_reference"] is not None
                or not (check["dir_fd_supplied"] or use["dir_fd_supplied"])
            ):
                namespace = (
                    "same-source-dir-fd-reference"
                    if use["dir_fd_reference"]
                    else "implicit-runtime-namespace"
                )
            self.observations.append(
                {
                    "check": check,
                    "use": use,
                    "relationship": "same-source-reference",
                    "namespace_binding": namespace,
                    "runtime_identity": "unverified",
                    "identity_comparisons": [
                        row
                        for row in flow.predicates
                        if any(
                            str(term).rsplit(".", 1)[0] == check["reference"]
                            for term in row["fields"]
                        )
                    ],
                    "observed": "A check and subsequent operation select through the same source reference.",
                    "potential_failure": "If namespace mutation is possible between operations, name selection may identify a different object.",
                    "unverified": [
                        "exclusive-namespace-ownership",
                        "runtime-protection",
                        "execution-feasibility",
                    ],
                }
            )

    def _delegate(
        self,
        source: FunctionSource,
        node: ast.Call,
        flow: Flow,
        operands: tuple[list[Value | None], dict[str | None, Value | None]],
    ) -> Value | None:
        target = self.resolve(source, node)
        if target is None:
            self.issue(source, node, "call-target-unresolved-or-external")
            if source.node not in self._nonlocals:
                self._nonlocals[source.node] = any(
                    isinstance(child, ast.Nonlocal) for child in ast.walk(source.node)
                )
            if self._nonlocals[source.node]:
                flow.checks.clear()
                self.issue(source, node, "closure-rebinding-unresolved")
            return Value(self._result_reference(source, node, flow))
        if isinstance(target.node, ast.AsyncFunctionDef) or target.node.decorator_list:
            self.issue(source, node, "async-or-decorated-callee-unresolved")
            return None
        if isinstance(node.func, ast.Attribute) and dotted(node.func.value) in {
            "self",
            "cls",
        }:
            operands = (
                [self._value(source, node.func.value, flow), *operands[0]],
                operands[1],
            )
        child = self._bound_call(target, operands)
        if child is None:
            self.issue(source, node, "argument-forwarding-unresolved")
            return None
        child.checks = list(flow.checks)
        child.guards = list(flow.guards)
        child.predicates = list(flow.predicates)
        child.trace = [
            *flow.trace,
            {
                "path": source.path,
                "symbol": source.qualname,
                "line": node.lineno,
                "column": node.col_offset,
                "target": f"{target.path}::{target.qualname}",
            },
        ]
        results = self._function(target, child)
        continuing = [
            item for item in results if item.returned is not None or not item.stopped
        ]
        if len(continuing) != 1:
            self.issue(source, node, "callee-exit-flow-unresolved")
            return None
        flow.checks = continuing[0].checks
        flow.predicates = continuing[0].predicates
        return continuing[0].returned

    @staticmethod
    def _result_reference(source: FunctionSource, node: ast.Call, flow: Flow) -> str:
        return _reference_identity(
            {
                "kind": "source-call-value",
                "path": source.path,
                "symbol": source.qualname,
                "line": node.lineno,
                "column": node.col_offset,
                "call_chain": flow.trace,
            }
        )

    @staticmethod
    def _bound_call(
        target: FunctionSource,
        operands: tuple[list[Value | None], dict[str | None, Value | None]],
    ) -> Flow | None:
        args, keywords = operands
        parameters = [*target.node.args.posonlyargs, *target.node.args.args]
        if target.node.args.vararg or target.node.args.kwarg or None in keywords:
            return None
        if len(args) > len(parameters):
            return None
        names = {p.arg for p in (*parameters, *target.node.args.kwonlyargs)}
        forbidden = {
            p.arg for p in (*target.node.args.posonlyargs, *parameters[: len(args)])
        }
        if set(keywords) - names or set(keywords) & forbidden:
            return None
        required = parameters[: len(parameters) - len(target.node.args.defaults)]
        if any(p.arg not in keywords for p in required[len(args) :]):
            return None
        if any(
            default is None and p.arg not in keywords
            for p, default in zip(
                target.node.args.kwonlyargs, target.node.args.kw_defaults, strict=True
            )
        ):
            return None
        values = {
            parameter.arg: value
            for parameter, value in zip(parameters, args, strict=False)
            if value is not None
        }
        for parameter in (*parameters[len(args) :], *target.node.args.kwonlyargs):
            value = keywords.get(parameter.arg)
            if value is not None:
                values[parameter.arg] = value
        return Flow(values=values)
