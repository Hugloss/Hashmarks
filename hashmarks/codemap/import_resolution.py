from __future__ import annotations

import ast
import posixpath
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.python_ast_cache import read_python_ast

from .python_exports import static_string_names

if TYPE_CHECKING:
    from .engine import CodeMap


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
        targets: list[str] = []
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            prefix = "." * int(node.level) + (node.module or "")
            for alias in node.names:
                exposed = alias.asname or alias.name
                if alias.name == "*":
                    target = f"{prefix}.{exported_name}" if prefix else exported_name
                elif exposed == exported_name:
                    target = f"{prefix}.{alias.name}" if prefix else alias.name
                else:
                    continue
                if target and target not in targets:
                    targets.append(target)
                if len(targets) >= 16:
                    return targets
        return targets

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
        bindings: list[tuple[str, list[str]]] = []
        reexport_count = 0
        for node in tree.body:
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == exported_name
            ):
                bindings.append(("local", []))
                continue
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                if any(
                    isinstance(item, ast.Name) and item.id == exported_name
                    for item in targets
                ):
                    bindings.append(("local", []))
                continue
            if not isinstance(node, ast.ImportFrom):
                continue
            prefix = "." * int(node.level) + (node.module or "")
            direct: list[str] = []
            star = False
            for alias in node.names:
                exposed = alias.asname or alias.name
                if alias.name == "*":
                    star = True
                    candidate = f"{prefix}.{exported_name}" if prefix else exported_name
                    if candidate:
                        direct.append(candidate)
                elif exposed == exported_name:
                    candidate = f"{prefix}.{alias.name}" if prefix else alias.name
                    if candidate:
                        direct.append(candidate)
            if direct:
                reexport_count += 1
                bindings.append(
                    ("star" if star else "reexport", list(dict.fromkeys(direct)))
                )
        if reexport_count > 1:
            targets = [
                target
                for kind, values in bindings
                if kind in {"reexport", "star"}
                for target in values
            ]
            return "ambiguous", list(dict.fromkeys(targets))
        return bindings[-1] if bindings else ("unknown", [])

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
        if len(owners) != 1:
            return None
        owner = owners[0]
        if not owner.endswith((".py", ".pyi")):
            return None
        try:
            tree = read_python_ast(self.workspace / owner).tree
        except (OSError, UnicodeError, SyntaxError, ValueError):
            return None

        all_values: list[str] | None = None
        saw_all = False
        for node in tree.body:
            assigned_value: ast.expr | None = None
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(item, ast.Name) and item.id == "__all__"
                    for item in node.targets
                )
                or isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "__all__"
            ):
                assigned_value = node.value
            if assigned_value is not None:
                saw_all = True
                names = static_string_names(assigned_value)
                if names is None:
                    return None
                all_values = names
                continue

            if (
                isinstance(node, ast.AugAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "__all__"
            ):
                saw_all = True
                if not isinstance(node.op, ast.Add) or all_values is None:
                    return None
                names = static_string_names(node.value)
                if names is None:
                    return None
                all_values.extend(names)
                continue

            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                func = call.func
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "__all__"
                    and func.attr in {"append", "extend"}
                ):
                    saw_all = True
                    if all_values is None or call.keywords or len(call.args) != 1:
                        return None
                    if func.attr == "append":
                        arg = call.args[0]
                        if not isinstance(arg, ast.Constant) or not isinstance(
                            arg.value, str
                        ):
                            return None
                        all_values.append(arg.value)
                    else:
                        names = static_string_names(call.args[0])
                        if names is None:
                            return None
                        all_values.extend(names)
                    continue

            if isinstance(node, ast.Delete) and any(
                isinstance(item, ast.Name) and item.id == "__all__"
                for item in node.targets
            ):
                return None
        if saw_all:
            return exported_name in (all_values or [])
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

        leaves: set[str] = set()
        visited: set[tuple[str, str]] = set()
        unresolved = False

        def walk(facade_path: str, exported_name: str, depth: int) -> None:
            nonlocal unresolved
            key = (facade_path, exported_name)
            if key in visited:
                unresolved = True
                return
            visited.add(key)
            symbols = self._session_symbols_for_path(facade_path)
            has_local_symbol = any(
                str(symbol.get("name") or "") == exported_name for symbol in symbols
            )
            binding_kind, binding_targets = self._python_export_binding(
                facade_path, exported_name
            )
            if binding_kind == "local":
                leaves.add(facade_path)
                return
            if binding_kind in {"reexport", "ambiguous"}:
                nested_targets = binding_targets
            else:
                nested_targets = self._python_reexport_targets(
                    facade_path, exported_name
                )
            if binding_kind == "star":
                authorities = [
                    self._python_star_export_authority(
                        facade_path, target, exported_name
                    )
                    for target in binding_targets
                ]
                if not authorities or any(
                    authority is not True for authority in authorities
                ):
                    unresolved = True
                    nested_targets = []
            if binding_kind == "ambiguous" or (
                has_local_symbol and binding_kind in {"unknown", "star"}
            ):
                unresolved = True
            if not nested_targets and not facade_path.endswith((".py", ".pyi")):
                # Python AST binding evidence is scope-sensitive.  The compact
                # edge store intentionally records imports from nested scopes and
                # conditional blocks as dependency evidence, so using those edges
                # as a re-export fallback can manufacture a false unique owner
                # (for example TYPE_CHECKING, ``if False``, or function-local
                # imports).  For Python facades, absence of a directly provable
                # top-level binding therefore remains unresolved/fail-closed.
                nested_targets = [
                    str(edge.get("target") or "")
                    for edge in self.store.edges_from(facade_path)
                    if str(edge.get("kind") or "") == "import"
                    and str(edge.get("target_short") or "") == exported_name
                    and str(edge.get("target") or "")
                ][:16]
            if not nested_targets:
                unresolved = True
                return
            if depth >= 8:
                unresolved = True
                return
            branch_progress = False
            for nested_target in nested_targets:
                nested_name = nested_target.lstrip(".").rsplit(".", 1)[-1]
                owners = self._resolve_import_paths(facade_path, nested_target)[:20]
                if len(owners) > 1:
                    unresolved = True
                for owner in owners:
                    if owner == facade_path:
                        continue
                    branch_progress = True
                    owner_symbols = self._session_symbols_for_path(owner)
                    if any(
                        str(symbol.get("name") or "") == nested_name
                        for symbol in owner_symbols
                    ):
                        leaves.add(owner)
                    else:
                        walk(owner, nested_name, depth + 1)
            if not branch_progress:
                unresolved = True

        for facade_path in resolved[:20]:
            walk(facade_path, short, 0)
        if len(leaves) > 1:
            unresolved = True
        qualified = sorted(leaves) if len(leaves) == 1 and not unresolved else []
        return list(dict.fromkeys([*resolved, *qualified])), unresolved

    def _resolve_import_owner_paths(self, source_path: str, target: str) -> list[str]:
        """Return bounded concrete import-owner paths without collapsing ambiguity."""
        resolved, _ = self._resolve_import_owner_evidence(source_path, target)
        return resolved

    def _python_import_module_candidates(
        self, source_path: str, target: str
    ) -> tuple[str, ...]:
        """Return exact Python module candidates in resolver fallback order."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        candidate = target.strip()
        if not candidate:
            return ()
        if candidate.startswith("."):
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
                return ()
            candidate = ".".join(source_parts[:keep] + ([suffix] if suffix else []))
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
            for suffix in (
                ".ts",
                ".tsx",
                ".mts",
                ".cts",
                ".js",
                ".jsx",
                ".mjs",
                ".cjs",
            )
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