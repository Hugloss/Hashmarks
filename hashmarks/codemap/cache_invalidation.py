"""Static cache invalidation ownership evidence.

This module parses repository Python only. It never imports repository modules,
executes invalidators, clears cache state, or grants runtime mutation authority.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Iterable, Mapping

_INVALIDATION_METHODS = {"cache_clear", "clear", "invalidate", "invalidate_all"}


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return None


def _resolve_relative_module(current_package: str | None, module: str | None, level: int) -> str | None:
    if level == 0:
        return module
    if not current_package:
        return None
    parts = current_package.split(".") if current_package else []
    # level=1 means current package, level=2 means its parent, etc.
    up = level - 1
    if up > len(parts):
        return None
    base = parts[: len(parts) - up] if up else parts
    if module:
        base.extend(module.split("."))
    return ".".join(base) if base else None


@dataclass(frozen=True)
class CacheInvalidator:
    path: str
    line: int
    invalidator: str
    method: str
    target_module: str
    target_owner: str
    confidence: str

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "invalidator": self.invalidator,
            "method": self.method,
            "target_module": self.target_module,
            "target_owner": self.target_owner,
            "confidence": self.confidence,
            "reason": (
                f"{self.invalidator} calls {self.method} on cache owner "
                f"{self.target_module}.{self.target_owner} using repository-visible import/alias evidence."
            ),
        }


class _Visitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        path: str,
        current_module: str | None,
        current_package: str | None,
        owner_keys: set[tuple[str, str]],
    ) -> None:
        self.path = path
        self.current_module = current_module
        self.current_package = current_package
        self.owner_keys = owner_keys
        self.symbol_imports: dict[str, tuple[str, str]] = {}
        self.module_imports: dict[str, str] = {}
        self.scope_aliases: list[dict[str, str]] = [{}]
        self.scope_shadowed: list[set[str]] = [set()]
        self.stack: list[str] = []
        self.findings: list[CacheInvalidator] = []

    @property
    def current_owner(self) -> str:
        return ".".join(self.stack) if self.stack else "<module>"

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = _resolve_relative_module(self.current_package, node.module, int(node.level or 0))
        if module:
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                self.symbol_imports[local] = (module, alias.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.asname:
                self.module_imports[alias.asname] = alias.name
            else:
                # `import pkg.state` binds `pkg`, but the fully qualified source
                # spelling remains valid as a static target prefix.
                self.module_imports[alias.name] = alias.name
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                if isinstance(node.value, ast.Name):
                    self.scope_aliases[-1][target.id] = node.value.id
                    self.scope_shadowed[-1].discard(target.id)
                else:
                    self.scope_aliases[-1].pop(target.id, None)
                    self.scope_shadowed[-1].add(target.id)
        self.generic_visit(node)

    @staticmethod
    def _argument_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        args = node.args
        values = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        names = {arg.arg for arg in values}
        if args.vararg:
            names.add(args.vararg.arg)
        if args.kwarg:
            names.add(args.kwarg.arg)
        return names

    def _visit_callable(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.stack.append(node.name)
        self.scope_aliases.append({})
        self.scope_shadowed.append(self._argument_names(node))
        self.generic_visit(node)
        self.scope_shadowed.pop()
        self.scope_aliases.pop()
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_callable(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_callable(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.scope_aliases.append({})
        self.scope_shadowed.append(set())
        self.generic_visit(node)
        self.scope_shadowed.pop()
        self.scope_aliases.pop()
        self.stack.pop()

    def _resolve_name_alias(self, name: str) -> str | None:
        seen: set[str] = set()
        current = name
        # Inner local scopes can shadow module names. Module-scope assignments
        # define repository names, so they do not by themselves suppress a
        # proven current-module cache owner.
        for aliases, shadowed in list(zip(self.scope_aliases, self.scope_shadowed))[:0:-1]:
            while current in aliases and current not in seen:
                seen.add(current)
                current = aliases[current]
            if current in shadowed:
                return None
        module_aliases = self.scope_aliases[0]
        while current in module_aliases and current not in seen:
            seen.add(current)
            current = module_aliases[current]
        return current

    def _resolve_root_alias(self, name: str) -> str | None:
        return self._resolve_name_alias(name)

    def _name_target(self,node:ast.Name)->tuple[str,str,str]|None:
        name=self._resolve_name_alias(node.id)
        if name is None:
            return None
        imported=self.symbol_imports.get(name)
        if imported and imported in self.owner_keys:
            return imported[0],imported[1],"qualified-symbol-import"
        if self.current_module and (self.current_module,name) in self.owner_keys:
            return self.current_module,name,"local-owner"
        return None

    def _qualified_target(self,node:ast.AST)->tuple[str,str,str]|None:
        dotted=_dotted(node)
        if not dotted or "." not in dotted:
            return None
        parts=dotted.split(".")
        resolved_root=self._resolve_root_alias(parts[0])
        if resolved_root is None:
            return None
        parts[0]=resolved_root
        prefix,owner=".".join(parts).rsplit(".",1)
        module=self.module_imports.get(prefix,prefix if prefix in self.module_imports.values() else None)
        if module and (module,owner) in self.owner_keys:
            return module,owner,"qualified-module-import"
        return None

    def _target(self,node:ast.AST)->tuple[str,str,str]|None:
        return self._name_target(node) if isinstance(node,ast.Name) else self._qualified_target(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr in _INVALIDATION_METHODS:
            target = self._target(node.func.value)
            if target:
                module, owner, confidence = target
                self.findings.append(CacheInvalidator(
                    path=self.path,
                    line=int(getattr(node, "lineno", 0) or 0),
                    invalidator=self.current_owner,
                    method=node.func.attr,
                    target_module=module,
                    target_owner=owner,
                    confidence=confidence,
                ))
        self.generic_visit(node)


def analyze_python_cache_invalidators(
    *,
    path: str,
    source: str,
    current_module: str | None,
    current_package: str | None,
    cache_owners: Iterable[Mapping[str, object]],
    tree: ast.Module | None = None,
) -> tuple[CacheInvalidator, ...]:
    if tree is None:
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            return ()
    owner_keys = {
        (str(owner["module"]), str(owner["owner"]))
        for owner in cache_owners
        if owner.get("module") and owner.get("owner")
    }
    visitor = _Visitor(
        path=path,
        current_module=current_module,
        current_package=current_package,
        owner_keys=owner_keys,
    )
    visitor.visit(tree)
    # Stable unique evidence: repeated syntactic visitation should not create
    # duplicate authority edges.
    unique: dict[tuple[object, ...], CacheInvalidator] = {}
    for item in visitor.findings:
        key = (item.path, item.line, item.invalidator, item.method, item.target_module, item.target_owner)
        unique[key] = item
    return tuple(unique[key] for key in sorted(unique))
