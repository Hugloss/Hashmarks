from __future__ import annotations

import ast
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.python_ast_cache import read_python_ast

from .python_exports import (
    AllExportStatus,
    python_export_binding,
    python_reexport_targets,
    static_all_exports,
)

if TYPE_CHECKING:
    from .engine import CodeMap


@dataclass
class _OwnerWalk:
    """Request-local re-export traversal with one ambiguity owner."""

    resolver: ImportResolutionMixin
    leaves: set[str] = field(default_factory=set)
    visited: set[tuple[str, str]] = field(default_factory=set)
    unresolved: bool = False

    def _binding_targets(
        self, facade_path: str, exported_name: str
    ) -> list[str] | None:
        symbols = self.resolver._session_symbols_for_path(facade_path)
        has_local_symbol = any(
            str(symbol.get("name") or "") == exported_name for symbol in symbols
        )
        kind, binding_targets = self.resolver._python_export_binding(
            facade_path, exported_name
        )
        if kind == "local":
            self.leaves.add(facade_path)
            return None
        targets = (
            binding_targets
            if kind in {"reexport", "ambiguous"}
            else self.resolver._python_reexport_targets(facade_path, exported_name)
        )
        if kind == "star" and (
            not binding_targets
            or any(
                self.resolver._python_star_export_authority(
                    facade_path, target, exported_name
                )
                is not True
                for target in binding_targets
            )
        ):
            self.unresolved = True
            targets = []
        if kind == "ambiguous" or (has_local_symbol and kind in {"unknown", "star"}):
            self.unresolved = True
        return targets

    def _edge_targets(self, facade_path: str, exported_name: str) -> list[str]:
        # Compact edges from Python nested scopes cannot prove a re-export.
        return [
            str(edge.get("target") or "")
            for edge in self.resolver.store.edges_from(facade_path)
            if str(edge.get("kind") or "") == "import"
            and str(edge.get("target_short") or "") == exported_name
            and str(edge.get("target") or "")
        ][:16]

    def _follow_target(self, facade_path: str, target: str, depth: int) -> bool:
        nested_name = target.lstrip(".").rsplit(".", 1)[-1]
        owners = self.resolver._resolve_import_paths(facade_path, target)[:20]
        if len(owners) > 1:
            self.unresolved = True
        progress = False
        for owner in owners:
            if owner == facade_path:
                continue
            progress = True
            symbols = self.resolver._session_symbols_for_path(owner)
            if any(str(symbol.get("name") or "") == nested_name for symbol in symbols):
                self.leaves.add(owner)
            else:
                self.visit(owner, nested_name, depth + 1)
        return progress

    def visit(self, facade_path: str, exported_name: str, depth: int) -> None:
        key = (facade_path, exported_name)
        if key in self.visited:
            self.unresolved = True
            return
        self.visited.add(key)
        targets = self._binding_targets(facade_path, exported_name)
        if targets is None:
            return
        if not targets and not facade_path.endswith((".py", ".pyi")):
            targets = self._edge_targets(facade_path, exported_name)
        if not targets or depth >= 8:
            self.unresolved = True
            return
        progress = [
            self._follow_target(facade_path, target, depth) for target in targets
        ]
        if not any(progress):
            self.unresolved = True


class ImportResolutionMixin:
    """Own repository import/re-export identity resolution for CodeMap evidence."""

    def _python_reexport_targets(
        self, facade_path: str, exported_name: str
    ) -> list[str]:
        """Return bounded Python import targets that expose ``exported_name``.

        This is intentionally syntax-only repository evidence.  It preserves
        ``as`` aliases (which the compact edge store does not encode) and expands
        a star import only for the single name currently being qualified.  Parse
        failures simply contribute no extra authority.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not facade_path.endswith(".py") or not exported_name:
            return []
        try:
            tree = read_python_ast(self.workspace / facade_path).tree
        except (OSError, UnicodeError, SyntaxError, ValueError):
            return []
        return python_reexport_targets(tree, exported_name)

    def _python_export_binding(
        self, facade_path: str, exported_name: str
    ) -> tuple[str, list[str]]:
        """Return conservative top-level binding authority for one exported name.

        Multiple re-export statements remain ambiguous even though Python runtime
        ordering can overwrite a binding: repository ownership must not depend on
        import execution order.  A single direct re-export and a local binding can
        however be ordered exactly when both are unconditional top-level statements.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not facade_path.endswith(".py") or not exported_name:
            return "unknown", []
        try:
            tree = read_python_ast(self.workspace / facade_path).tree
        except (OSError, UnicodeError, SyntaxError, ValueError):
            return "unknown", []
        return python_export_binding(tree, exported_name)

    def _python_star_export_authority(
        self, facade_path: str, target: str, exported_name: str
    ) -> bool | None:
        """Prove whether a star-import target exports one name.

        ``from module import *`` is name-sensitive: a static ``__all__`` is
        authoritative, while absent ``__all__`` exports non-underscore names.
        Dynamic or ambiguous ``__all__`` remains unknown/fail-closed.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not exported_name or exported_name.startswith("_"):
            return False
        module_target = (
            target.rsplit(".", 1)[0]
            if "." in target.lstrip(".")
            else target.rstrip(".")
        )
        owners = self._resolve_import_paths(facade_path, module_target)[:20]
        if len(owners) != 1 or not owners[0].endswith((".py", ".pyi")):
            return None
        owner = owners[0]
        try:
            tree = read_python_ast(self.workspace / owner).tree
        except (OSError, UnicodeError, SyntaxError, ValueError):
            return None

        exports = static_all_exports(tree)
        if exports is AllExportStatus.UNKNOWN:
            return None
        if isinstance(exports, list):
            return exported_name in exports
        symbols = self._session_symbols_for_path(owner)
        return any(str(symbol.get("name") or "") == exported_name for symbol in symbols)

    def _resolve_import_owner_evidence(
        self, source_path: str, target: str
    ) -> tuple[list[str], bool]:
        """Resolve bounded import-owner evidence and report unresolved identity.

        The boolean is true when the qualified re-export frontier is ambiguous,
        cyclic, or continues beyond the explicit eight-hop bound.  Callers that
        make safety decisions must preserve that uncertainty rather than treating
        a facade-only resolution as proof of the underlying owner.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        resolved = list(self._resolve_import_paths(source_path, target))
        short = target.lstrip(".").rsplit(".", 1)[-1]
        if not short or not resolved:
            ambiguous = source_path.endswith(
                (".py", ".pyi")
            ) and self._python_import_identity_ambiguous(source_path, target)
            return resolved, ambiguous

        walk = _OwnerWalk(self)
        for facade_path in resolved[:20]:
            walk.visit(facade_path, short, 0)
        if len(walk.leaves) > 1:
            walk.unresolved = True
        qualified = (
            sorted(walk.leaves) if len(walk.leaves) == 1 and not walk.unresolved else []
        )
        return list(dict.fromkeys([*resolved, *qualified])), walk.unresolved

    def _resolve_import_owner_paths(self, source_path: str, target: str) -> list[str]:
        """Return bounded concrete import-owner paths without collapsing ambiguity."""
        resolved, _ = self._resolve_import_owner_evidence(source_path, target)
        return resolved

    def _python_relative_module_candidate(
        self, source_path: str, candidate: str
    ) -> str:
        """Resolve a relative module against the indexed source package."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        leading = len(candidate) - len(candidate.lstrip("."))
        suffix = candidate[leading:]
        source_row = self._session_file_row(source_path)
        source_module = (
            "" if source_row is None else str(source_row.get("module_name") or "")
        )
        if source_module:
            source_parts = source_module.split(".")
            if Path(source_path).stem != "__init__":
                source_parts = source_parts[:-1]
        else:
            source_parts = list(Path(source_path).with_suffix("").parts[:-1])
        keep = len(source_parts) - max(0, leading - 1)
        if keep < 0:
            return ""
        return ".".join(source_parts[:keep] + ([suffix] if suffix else []))

    def _python_import_module_candidates(
        self, source_path: str, target: str
    ) -> tuple[str, ...]:
        """Return exact Python module candidates in resolver fallback order."""
        candidate = target.strip()
        if candidate.startswith("."):
            candidate = self._python_relative_module_candidate(source_path, candidate)
        if not candidate:
            return ()
        ordered: list[str] = []
        while candidate:
            ordered.append(candidate)
            candidate = candidate.rsplit(".", 1)[0] if "." in candidate else ""
        return tuple(ordered)

    def _resolve_python_import_paths(self, source_path: str, target: str) -> list[str]:
        """Resolve only uniquely owned Python module evidence.

        Multiple repository paths exposing the same qualified import identity are
        ambiguity, not deterministic ownership.  Path ordering may stabilize the
        evidence but must never choose an owner.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        for candidate in self._python_import_module_candidates(source_path, target):
            resolved = self._session_module_paths(candidate)
            if resolved:
                return resolved if len(resolved) == 1 else []
        return []

    def _python_import_identity_ambiguous(self, source_path: str, target: str) -> bool:
        """Report whether the first resolvable Python module identity has >1 owner."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        for candidate in self._python_import_module_candidates(source_path, target):
            resolved = self._session_module_paths(candidate)
            if resolved:
                return len(resolved) > 1
        return False

    def _resolve_js_import_paths(self, source_path: str, target: str) -> list[str]:
        """Resolve exact in-workspace JS/TS relative-import evidence."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not target.startswith("."):
            return []
        base = (Path(source_path).parent / target).as_posix()
        normalized = posixpath.normpath(base)
        if (
            posixpath.isabs(normalized)
            or normalized in {"", ".", ".."}
            or normalized.startswith("../")
        ):
            return []
        if normalized.startswith("./"):
            normalized = normalized[2:]
        candidates = [normalized]
        explicit_suffix = Path(normalized).suffix.lower()
        source_variant_suffixes = {
            ".js": (".ts", ".tsx"),
            ".jsx": (".tsx", ".ts"),
            ".mjs": (".mts", ".ts"),
            ".cjs": (".cts", ".ts"),
        }
        if explicit_suffix in source_variant_suffixes:
            stem = normalized[: -len(explicit_suffix)]
            candidates.extend(
                stem + suffix for suffix in source_variant_suffixes[explicit_suffix]
            )
        candidates.extend(
            normalized + suffix
            for suffix in (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
        )
        candidates.extend(
            normalized.rstrip("/") + suffix
            for suffix in (
                "/index.ts",
                "/index.tsx",
                "/index.mts",
                "/index.cts",
                "/index.js",
                "/index.jsx",
                "/index.mjs",
                "/index.cjs",
            )
        )
        ordered = list(dict.fromkeys(candidates))
        existing = self._session_file_rows(ordered)
        return [candidate for candidate in ordered if candidate in existing]

    def _resolve_go_import_paths(self, target: str) -> list[str]:
        """Resolve Go module/package evidence without broad repository guessing."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        go_mod = self.workspace / "go.mod"
        if not go_mod.is_file():
            return []
        try:
            module_line = next(
                (
                    line.strip()
                    for line in go_mod.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                    if line.strip().startswith("module ")
                ),
                "",
            )
        except OSError:
            return []
        module_name = module_line.removeprefix("module ").strip()
        if not module_name or not (
            target == module_name or target.startswith(module_name + "/")
        ):
            return []
        rel_dir = target[len(module_name) :].lstrip("/")
        prefix = rel_dir.rstrip("/")
        package_paths = self.store.paths_under(prefix) if prefix else self.store.paths()
        candidates = [
            path
            for path in package_paths
            if path.endswith(".go")
            and not path.endswith("_test.go")
            and (
                (not prefix and "/" not in path)
                or (
                    prefix
                    and path.startswith(prefix + "/")
                    and "/" not in path[len(prefix) + 1 :]
                )
            )
        ]
        return sorted(candidates)

    def _resolve_import_paths(self, source_path: str, target: str) -> list[str]:
        """Resolve import evidence by language while preserving exact resolver semantics."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        target = target.strip()
        if not target:
            return []
        source_row = self._session_file_row(source_path)
        language = None if source_row is None else str(source_row["language"])
        if language == "python":
            return self._resolve_python_import_paths(source_path, target)
        if language in {"javascript", "typescript"}:
            return self._resolve_js_import_paths(source_path, target)
        if language == "go":
            return self._resolve_go_import_paths(target)
        return []
