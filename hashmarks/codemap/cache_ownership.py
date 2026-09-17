"""Static process-local cache ownership diagnostics.

Evidence only: this module parses repository Python and never imports, executes,
rewrites, invalidates, or manages cache state.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

_CACHE_FACTORIES = {"lru_cache", "cache", "cached_property"}
_CACHE_NAME_TOKENS = ("cache", "memo", "registry", "singleton", "pool")


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _call_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return None


def _looks_cache_name(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in _CACHE_NAME_TOKENS)


@dataclass(frozen=True)
class CacheOwner:
    path: str
    line: int
    owner: str
    kind: str
    scope: str
    mutable: bool
    invalidation: str
    confidence: str
    import_identity_risk: bool = False

    def as_dict(self) -> dict[str, object]:
        reason = (
            f"{self.owner} owns process-local {self.kind} state at module identity '{self.path}'. "
            f"Invalidation evidence is {self.invalidation}."
        )
        if self.import_identity_risk:
            reason += " This module is also a target of a risky dynamic loader, so duplicate module identity can duplicate this cache."
        recommendation = (
            "Preserve one canonical module/package owner for shared cache state and make invalidation explicit."
            if self.mutable
            else "Keep cache ownership at one canonical module identity; document lifecycle/invalidation when callers depend on reuse."
        )
        return {
            "path": self.path,
            "line": self.line,
            "owner": self.owner,
            "kind": self.kind,
            "scope": self.scope,
            "mutable": self.mutable,
            "invalidation": self.invalidation,
            "confidence": self.confidence,
            "import_identity_risk": self.import_identity_risk,
            "reason": reason,
            "recommendation": recommendation,
        }


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.owners: list[CacheOwner] = []
        self.invalidators: set[str] = set()
        self.aliases: dict[str, str] = {}
        self.stack: list[str] = []

    @property
    def current(self) -> str | None:
        return ".".join(self.stack) if self.stack else None

    def _decorated(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for dec in node.decorator_list:
            raw = dec.func if isinstance(dec, ast.Call) else dec
            name = (_call_name(raw) or "").rsplit(".", 1)[-1]
            if name in _CACHE_FACTORIES:
                self.owners.append(
                    CacheOwner(
                        self.path,
                        int(node.lineno),
                        node.name,
                        f"decorator:{name}",
                        "function",
                        False,
                        "decorator-managed",
                        "high",
                    )
                )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._decorated(node)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._decorated(node)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    @staticmethod
    def _assignment_kind(value: ast.AST) -> str:
        if isinstance(value, (ast.Dict, ast.DictComp)):
            return "module-mapping"
        if isinstance(value, (ast.Set, ast.SetComp)):
            return "module-set"
        if isinstance(value, (ast.List, ast.ListComp)):
            return "module-list"
        return "module-state"

    def _record_module_assignment(self, node: ast.Assign, target: ast.Name) -> None:
        if isinstance(node.value, ast.Name):
            self.aliases[target.id] = node.value.id
        if not _looks_cache_name(target.id):
            return
        self.owners.append(
            CacheOwner(
                self.path,
                int(node.lineno),
                target.id,
                self._assignment_kind(node.value),
                "module",
                True,
                "not-proven",
                "medium",
            )
        )

    def visit_Assign(self, node: ast.Assign) -> None:
        if self.current is None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._record_module_assignment(node, target)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func) or ""
        if name.endswith((".cache_clear", ".clear", ".invalidate", ".invalidate_all")):
            base = name.rsplit(".", 1)[0]
            self.invalidators.add(base.rsplit(".", 1)[-1])
        self.generic_visit(node)


def _ownership_tree(source: str, tree: ast.Module | None) -> ast.Module | None:
    if tree is not None:
        return tree
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError):
        return None


def analyze_python_cache_ownership(
    *,
    path: str,
    source: str,
    import_risk_targets: Iterable[str] = (),
    tree: ast.Module | None = None,
) -> tuple[CacheOwner, ...]:
    tree = _ownership_tree(source, tree)
    if tree is None:
        return ()
    visitor = _Visitor(path)
    visitor.visit(tree)
    risks = set(import_risk_targets)
    out = []
    for owner in visitor.owners:
        invalidation = owner.invalidation
        if owner.owner in visitor.invalidators:
            invalidation = "explicit-local"
        else:
            for invalidated in visitor.invalidators:
                seen: set[str] = set()
                current = invalidated
                while current in visitor.aliases and current not in seen:
                    seen.add(current)
                    current = visitor.aliases[current]
                if current == owner.owner:
                    invalidation = "explicit-local-alias"
                    break
        out.append(
            CacheOwner(
                path=owner.path,
                line=owner.line,
                owner=owner.owner,
                kind=owner.kind,
                scope=owner.scope,
                mutable=owner.mutable,
                invalidation=invalidation,
                confidence=owner.confidence,
                import_identity_risk=path in risks,
            )
        )
    return tuple(out)
