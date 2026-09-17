"""Static Python module/import ownership diagnostics.

This module reports repository patterns that can bypass Python's normal
``sys.modules`` ownership and therefore duplicate process-local module state or
caches.  It deliberately does not rewrite imports or execute repository code.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


_DYNAMIC_SPEC = "spec_from_file_location"
_DYNAMIC_MODULE = "module_from_spec"
_DYNAMIC_EXEC = "exec_module"


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _path_call_args(value: ast.Call) -> tuple[ast.AST, ...]:
    name = _call_name(value.func) or ""
    if name.endswith(("joinpath", "os.path.join")):
        return tuple(value.args)
    if name in {"str", "os.fspath"} and value.args:
        return (value.args[0],)
    if name.endswith("Path") and value.args:
        return (value.args[0],)
    return ()


def _literal_path_parts(value: ast.Constant) -> tuple[str, ...]:
    if not isinstance(value.value, str):
        return ()
    raw = value.value.replace("\\", "/").strip("/")
    return tuple(piece for piece in raw.split("/") if piece and piece != ".")


def _bound_path_parts(value: ast.Name, *, bound: dict[str, ast.AST], resolving: set[str], depth: int) -> tuple[str, ...]:
    if value.id not in bound or value.id in resolving:
        return ()
    resolving.add(value.id)
    try:
        return _collect_path_parts(bound[value.id], bound=bound, resolving=resolving, depth=depth + 1)
    finally:
        resolving.remove(value.id)


def _sequence_path_parts(values: tuple[ast.AST, ...] | list[ast.AST], *, bound: dict[str, ast.AST], resolving: set[str], depth: int) -> tuple[str, ...]:
    return tuple(
        part
        for item in values
        for part in _collect_path_parts(item, bound=bound, resolving=resolving, depth=depth + 1)
    )


def _collect_path_parts(value: ast.AST, *, bound: dict[str, ast.AST], resolving: set[str], depth: int) -> tuple[str, ...]:
    if depth > 8:
        result = ()
    elif isinstance(value, ast.Name):
        result = _bound_path_parts(value, bound=bound, resolving=resolving, depth=depth)
    elif isinstance(value, ast.Constant):
        result = _literal_path_parts(value)
    elif isinstance(value, ast.BinOp) and isinstance(value.op, ast.Div):
        result = _sequence_path_parts((value.left, value.right), bound=bound, resolving=resolving, depth=depth)
    elif isinstance(value, (ast.List, ast.Tuple)):
        result = _sequence_path_parts(value.elts, bound=bound, resolving=resolving, depth=depth)
    elif isinstance(value, ast.Call):
        result = _sequence_path_parts(_path_call_args(value), bound=bound, resolving=resolving, depth=depth)
    else:
        result = ()
    return result


def _string_path_parts(
    node: ast.AST, bindings: dict[str, ast.AST] | None = None
) -> tuple[str, ...]:
    """Recover a deterministic repository-path suffix from a path expression."""

    return _collect_path_parts(node, bound=bindings or {}, resolving=set(), depth=0)


def _resolve_target_path(path_expr: ast.AST, repository_paths: set[str], bindings: dict[str, ast.AST] | None = None) -> str | None:
    parts = _string_path_parts(path_expr, bindings)
    if not parts:
        return None
    # Try the complete recovered path first, then progressively shorter
    # suffixes. This handles literal absolute prefixes without guessing their
    # runtime root while still requiring one unique repository-owned target.
    for offset in range(len(parts)):
        suffix = "/".join(parts[offset:])
        if suffix in repository_paths:
            return suffix
        matches = sorted(path for path in repository_paths if path.endswith("/" + suffix))
        if len(matches) == 1:
            return matches[0]
    return None


def _package_parts(path: PurePosixPath, repository_paths: set[str]) -> tuple[str, ...]:
    parent = path.parent
    parts: list[str] = []
    while str(parent) not in {".", ""}:
        if not ({str(parent / "__init__.py"), str(parent / "__init__.pyi")} & repository_paths):
            break
        parts.append(parent.name)
        parent = parent.parent
    return tuple(reversed(parts))


def _importable_module(target_path: str | None, repository_paths: set[str]) -> str | None:
    if not target_path or not target_path.endswith((".py", ".pyi")):
        return None
    path = PurePosixPath(target_path)
    module_parts = [] if path.stem == "__init__" else [path.stem]
    package_parts = _package_parts(path, repository_paths)
    if package_parts:
        return ".".join([*package_parts, *module_parts])
    if path.parent == PurePosixPath(".") and module_parts:
        return module_parts[0]
    return None


def _is_test_path(path: str) -> bool:
    parts = {part.lower() for part in PurePosixPath(path).parts}
    name = PurePosixPath(path).name.lower()
    return bool(parts & {"test", "tests", "testing"}) or name.startswith("test_") or name.endswith("_test.py")


def _is_pluginish(path: str, source: str) -> bool:
    lowered = f"{path}\n{source}".lower()
    return any(token in lowered for token in ("plugin", "extension", "entry_point", "entrypoint"))


def _finding_code_reason(*, mismatch: bool, registered: bool, target_module: str | None, requested_module: str | None) -> tuple[str, str]:
    if mismatch:
        return "python-duplicate-module-identity", (
            f"The loader names repository module '{target_module}' as '{requested_module}'. "
            "The same file can therefore exist under multiple module identities and duplicate module-level state."
        )
    if registered:
        return "python-custom-module-loader", (
            "This file constructs and executes a module object dynamically, but also explicitly "
            "registers module state in sys.modules. Module identity is custom-owned rather than an unregistered cache bypass."
        )
    return "python-dynamic-module-identity-bypass", (
        "spec_from_file_location + module_from_spec + exec_module constructs a fresh module "
        "object outside normal import ownership; repeated loads can duplicate module-level state and defeat process-local caches."
    )


def _finding_recommendation(*, target_module: str | None, requested_module: str | None, mismatch: bool, registered: bool) -> str:
    if target_module and mismatch:
        return f"Use the canonical package identity '{target_module}' or a normal package import; do not load the same repository file under '{requested_module}'."
    if target_module and not registered:
        return f"Prefer the package-aware normal import '{target_module}' when shared module/cache identity is intended. Keep a dynamic loader only when isolation/plugin semantics are explicit."
    return "Document the loader's ownership/isolation contract. Prefer normal package imports when shared module/cache identity is intended."


@dataclass(frozen=True)
class ImportOwnershipFinding:
    path: str
    line: int
    target_path: str | None
    target_module: str | None
    requested_module: str | None
    explicit_sys_modules_registration: bool
    domain: str
    severity: str
    confidence: str

    def as_dict(self) -> dict[str, object]:
        registered = self.explicit_sys_modules_registration
        mismatch = bool(self.target_module and self.requested_module and self.target_module != self.requested_module)
        code, reason = _finding_code_reason(
            mismatch=mismatch,
            registered=registered,
            target_module=self.target_module,
            requested_module=self.requested_module,
        )
        recommendation = _finding_recommendation(
            target_module=self.target_module,
            requested_module=self.requested_module,
            mismatch=mismatch,
            registered=registered,
        )
        return {
            "path": self.path, "line": self.line, "code": code,
            "severity": self.severity, "confidence": self.confidence, "domain": self.domain,
            "calls": [_DYNAMIC_SPEC, _DYNAMIC_MODULE, _DYNAMIC_EXEC],
            "target_path": self.target_path, "target_module": self.target_module,
            "requested_module": self.requested_module, "module_identity_mismatch": mismatch,
            "explicit_sys_modules_registration": registered, "reason": reason,
            "recommendation": recommendation,
        }



def _finding_domain_severity(path: str, source: str, target_path: str | None, registered: bool) -> tuple[str, str, str]:
    test_path = _is_test_path(path)
    pluginish = _is_pluginish(path, source)
    domain = "test" if test_path else ("plugin" if pluginish else "source")
    if registered:
        return domain, "advisory", "high"
    confidence = "high" if target_path else "medium"
    return domain, "advisory" if test_path or pluginish else "warning", confidence


class _DynamicLoaderVisitor(ast.NodeVisitor):
    def __init__(self, path: str, source: str, repository_paths: set[str]) -> None:
        self.path = path
        self.source = source
        self.repository_paths = repository_paths
        self.specs: dict[str, tuple[int, ast.AST, str | None]] = {}
        self.modules: dict[str, str] = {}
        self.path_bindings: dict[str, ast.AST] = {}
        self.exec_modules: list[tuple[int, str | None]] = []
        self.sys_modules_values: set[str] = set()
        self.call_aliases: dict[str, str] = {}
        self.sys_modules_aliases: set[str] = set()

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "importlib.util":
            for alias in node.names:
                if alias.name in {_DYNAMIC_SPEC, _DYNAMIC_MODULE}:
                    self.call_aliases[alias.asname or alias.name] = alias.name
        self.generic_visit(node)

    def _resolved_call(self, node: ast.AST) -> str:
        raw = _call_name(node) or ""
        return self.call_aliases.get(raw, raw)

    @staticmethod
    def _assigned_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names: list[str] = []
        for target in targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
        return tuple(names)

    def _record_spec(self, assigned: tuple[str, ...], node: ast.AST, value: ast.Call) -> None:
        requested = value.args[0].value if isinstance(value.args[0], ast.Constant) and isinstance(value.args[0].value, str) else None
        spec = (int(getattr(value, "lineno", getattr(node, "lineno", 1))), value.args[1], requested)
        self.specs.update(dict.fromkeys(assigned, spec))

    def _record_dynamic_module(self, assigned: tuple[str, ...], value: ast.Call) -> None:
        if value.args and isinstance(value.args[0], ast.Name):
            self.modules.update(dict.fromkeys(assigned, value.args[0].id))

    def _record_assignment(self, node: ast.Assign | ast.AnnAssign, value: ast.AST | None) -> None:
        assigned = self._assigned_names(node)
        if value is not None:
            self.path_bindings.update(dict.fromkeys(assigned, value))
        if not isinstance(value, ast.Call):
            return
        call = self._resolved_call(value.func)
        if call.endswith(_DYNAMIC_SPEC) and len(value.args) >= 2:
            self._record_spec(assigned, node, value)
        elif call.endswith(_DYNAMIC_MODULE):
            self._record_dynamic_module(assigned, value)

    def _is_sys_modules_target(self, target: ast.AST) -> bool:
        if not isinstance(target, ast.Subscript):
            return False
        name = _call_name(target.value) or ""
        return name == "sys.modules" or name.endswith(".sys.modules") or name in self.sys_modules_aliases

    def _record_sys_modules_aliases(self, node: ast.Assign) -> None:
        value_name = _call_name(node.value) or ""
        if value_name != "sys.modules" and value_name not in self.sys_modules_aliases:
            return
        self.sys_modules_aliases.update(target.id for target in node.targets if isinstance(target, ast.Name))

    def _record_sys_modules_value(self, value: ast.AST, targets: list[ast.expr]) -> None:
        if isinstance(value, ast.Name) and any(self._is_sys_modules_target(target) for target in targets):
            self.sys_modules_values.add(value.id)

    def visit_Assign(self, node: ast.Assign) -> None:
        self._record_assignment(node, node.value)
        self._record_sys_modules_aliases(node)
        self._record_sys_modules_value(node.value, node.targets)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._record_assignment(node, node.value)
        if isinstance(node.value, ast.Name) and self._is_sys_modules_target(node.target):
            self.sys_modules_values.add(node.value.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call = self._resolved_call(node.func)
        if call.endswith(_DYNAMIC_EXEC):
            module_name = node.args[0].id if node.args and isinstance(node.args[0], ast.Name) else None
            self.exec_modules.append((int(getattr(node, "lineno", 1)), module_name))
        elif call.endswith("sys.modules.setdefault") and len(node.args) >= 2 and isinstance(node.args[1], ast.Name):
            self.sys_modules_values.add(node.args[1].id)
        self.generic_visit(node)

    def _finding_for(self, module_name: str | None) -> ImportOwnershipFinding | None:
        if module_name is None:
            return None
        spec_name = self.modules.get(module_name)
        spec = self.specs.get(spec_name) if spec_name else None
        if spec is None:
            return None
        spec_line, path_expr, requested_module = spec
        target_path = _resolve_target_path(path_expr, self.repository_paths, self.path_bindings)
        target_module = _importable_module(target_path, self.repository_paths)
        registered = module_name in self.sys_modules_values
        domain, severity, confidence = _finding_domain_severity(
            self.path, self.source, target_path, registered
        )
        return ImportOwnershipFinding(
            path=self.path, line=spec_line, target_path=target_path, target_module=target_module,
            requested_module=requested_module, explicit_sys_modules_registration=registered,
            domain=domain, severity=severity, confidence=confidence,
        )

    def findings(self) -> tuple[ImportOwnershipFinding, ...]:
        out: list[ImportOwnershipFinding] = []
        seen: set[tuple[int, str | None]] = set()
        for _, module_name in self.exec_modules:
            finding = self._finding_for(module_name)
            if finding is None:
                continue
            key = (finding.line, finding.target_path)
            if key in seen:
                continue
            seen.add(key)
            out.append(finding)
        return tuple(out)


def analyze_python_import_ownership(
    *, path: str, source: str, repository_paths: Iterable[str], tree: ast.Module | None = None
) -> tuple[ImportOwnershipFinding, ...]:
    """Return high-signal module-ownership findings without executing code."""

    if tree is None:
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            return ()
    paths = set(repository_paths)
    visitor = _DynamicLoaderVisitor(path, source, paths)
    visitor.visit(tree)
    return visitor.findings()
