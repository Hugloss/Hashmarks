from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks._version import __version__
from hashmarks.paths import normalize_relative_path
from hashmarks.producer_identity import native_producer_implementation_identity
from hashmarks.python_ast_cache import read_python_ast

from .model import EvidenceVisibility

if TYPE_CHECKING:
    from .engine import CodeMap

STRUCTURAL_LOCALITY_SCHEMA = "hashmarks.structural-locality.v1"
STRUCTURAL_LOCALITY_DELTA_SCHEMA = "hashmarks.structural-locality-delta.v1"


@dataclass(frozen=True)
class _SelfClsCallTarget:
    receiver: str
    method: str
    class_qualname: str
    source_method: str


def _identity(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _symbol_id(row: Mapping[str, object]) -> str:
    return f"{row['path']}::{row['qualname']}"


def _union_line_count(rows: Sequence[Mapping[str, object]]) -> int:
    by_path: dict[str, list[tuple[int, int]]] = {}
    for row in rows:
        lines = row.get("lines")
        if (
            not isinstance(lines, Sequence)
            or isinstance(lines, (str, bytes, bytearray))
            or len(lines) != 2
        ):
            continue
        by_path.setdefault(str(row["path"]), []).append(
            (int(lines[0]), int(lines[1]))
        )
    total = 0
    for spans in by_path.values():
        current_start: int | None = None
        current_end: int | None = None
        for start, end in sorted(spans):
            if current_start is None:
                current_start, current_end = start, end
                continue
            assert current_end is not None
            if start <= current_end + 1:
                current_end = max(current_end, end)
                continue
            total += current_end - current_start + 1
            current_start, current_end = start, end
        if current_start is not None and current_end is not None:
            total += current_end - current_start + 1
    return total


def _body_without_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return body


def _is_call_value(node: ast.AST | None) -> bool:
    if isinstance(node, ast.Call):
        return True
    return isinstance(node, ast.Await) and isinstance(node.value, ast.Call)


def _forwarding_only_python_symbol(
    path: Path, *, start_line: int, name: str
) -> tuple[bool | None, str]:
    try:
        tree = read_python_ast(path, errors="replace").tree
    except (OSError, SyntaxError, ValueError):
        return None, "python-ast-unavailable"
    candidates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and int(getattr(node, "lineno", -1)) == start_line
        and node.name == name
    ]
    if len(candidates) != 1:
        return None, "python-symbol-node-ambiguous"
    body = _body_without_docstring(candidates[0])
    if len(body) != 1:
        return False, "python-ast"
    statement = body[0]
    if isinstance(statement, ast.Return):
        return _is_call_value(statement.value), "python-ast"
    if isinstance(statement, ast.Expr):
        return _is_call_value(statement.value), "python-ast"
    return False, "python-ast"


def _freshness(stale: object) -> str:
    if stale is False:
        return "current"
    if stale is True:
        return "stale"
    return "unknown"


def _python_node_binds_name(node: ast.AST, name: str) -> bool:
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return node.id == name
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return any(
            (alias.asname or alias.name.rsplit(".", 1)[-1]) == name
            for alias in node.names
        )
    return False


def _binding_result(
    rows: Sequence[dict[str, object]],
    fallback: Sequence[dict[str, object]],
    *,
    unresolved: bool,
) -> tuple[dict[str, object] | None, list[str], bool]:
    if len(rows) == 1:
        return rows[0], [_symbol_id(rows[0])], False
    return None, sorted(_symbol_id(row) for row in rows or fallback), unresolved


class StructuralLocalityMixin:
    """Project bounded structural-locality facts without refactor recommendations."""

    @staticmethod
    def _validate_locality_bounds(
        max_depth: int, call_limit_per_symbol: int, ref_limit_per_symbol: int
    ) -> None:
        if max_depth < 0 or max_depth > 8:
            raise ValueError("max_depth must be between 0 and 8")
        if call_limit_per_symbol < 1 or call_limit_per_symbol > 1024:
            raise ValueError("call_limit_per_symbol must be between 1 and 1024")
        if ref_limit_per_symbol < 1 or ref_limit_per_symbol > 1024:
            raise ValueError("ref_limit_per_symbol must be between 1 and 1024")

    def _exact_locality_target(self, target: str) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if "::" not in target:
            raise ValueError(
                "structural locality requires an exact path::qualname target"
            )
        raw_path, qualname = target.split("::", 1)
        path = normalize_relative_path(raw_path.strip().replace("\\", "/"), allow_root=False)
        qualname = qualname.strip()
        if not qualname:
            raise ValueError("target path and qualname must be non-empty")
        self._ensure_path_current(path)
        row = self.store.symbol_at(path, qualname)
        if row is None:
            raise KeyError(f"symbol not found: {target}")
        if EvidenceVisibility(str(row["evidence_visibility"])) is EvidenceVisibility.DENY:
            raise PermissionError(f"symbol exists but repository evidence is denied: {target}")
        return dict(row)

    def _visible_named_symbol_candidates(self, name: str) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return [
            dict(row)
            for row in self.store.symbols_named(name, limit=64)
            if EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        ]

    def _python_function_locally_binds(
        self, path: str, source: str, name: str
    ) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not path.endswith(".py") or not source or not name:
            return False
        try:
            tree = read_python_ast(self.workspace / path, errors="replace").tree
        except (OSError, SyntaxError, UnicodeError, ValueError):
            return True
        function_name = source.rsplit(".", 1)[-1]
        matching = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ]
        if len(matching) != 1:
            return True
        function = matching[0]
        arguments = [
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
            *(() if function.args.vararg is None else (function.args.vararg,)),
            *(() if function.args.kwarg is None else (function.args.kwarg,)),
        ]
        return any(argument.arg == name for argument in arguments) or any(
            _python_node_binds_name(node, name) for node in ast.walk(function)
        )

    def _python_plain_call_binding(
        self,
        *,
        source_path: str,
        source_qualname: str,
        short: str,
        candidates: list[dict[str, object]],
    ) -> tuple[dict[str, object] | None, list[str], bool]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        candidate_ids = sorted(_symbol_id(row) for row in candidates)
        if self._python_function_locally_binds(source_path, source_qualname, short):
            return None, candidate_ids, False
        kind, targets = self._python_export_binding(source_path, short)
        if kind == "local":
            local = [
                row
                for row in candidates
                if str(row.get("path") or "") == source_path
            ]
            return _binding_result(
                local, candidates, unresolved=len(local) > 1
            )
        if kind == "reexport" and len(targets) == 1:
            owners, unresolved = self._resolve_import_owner_evidence(
                source_path, targets[0]
            )
            if unresolved:
                return None, candidate_ids, True
            owner_paths = set(owners)
            owned = [
                row
                for row in candidates
                if str(row.get("path") or "") in owner_paths
            ]
            return _binding_result(
                owned, candidates, unresolved=bool(owners)
            )
        if kind in {"ambiguous", "star"}:
            return None, candidate_ids, True
        return None, candidate_ids, False

    def _python_class_node(self, path: str, qualname: str) -> ast.ClassDef | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not path.endswith(".py") or not qualname:
            return None
        try:
            tree = read_python_ast(self.workspace / path, errors="replace").tree
        except (OSError, SyntaxError, UnicodeError, ValueError):
            return None
        body: Sequence[ast.stmt] = tree.body
        selected: ast.ClassDef | None = None
        for part in qualname.split("."):
            matches = [
                node
                for node in body
                if isinstance(node, ast.ClassDef) and node.name == part
            ]
            if len(matches) != 1:
                return None
            selected = matches[0]
            body = selected.body
        return selected

    def _python_class_bases(
        self, path: str, qualname: str
    ) -> tuple[list[tuple[str, str]], bool]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        node = self._python_class_node(path, qualname)
        if node is None:
            return [], True
        bases: list[tuple[str, str]] = []
        unresolved = False
        for base in node.bases:
            if not isinstance(base, ast.Name):
                unresolved = True
                continue
            if self._python_class_node(path, base.id) is not None:
                bases.append((path, base.id))
                continue
            kind, targets = self._python_export_binding(path, base.id)
            if kind != "reexport" or len(targets) != 1:
                unresolved = True
                continue
            owners, import_unresolved = self._resolve_import_owner_evidence(
                path, targets[0]
            )
            class_name = targets[0].lstrip(".").rsplit(".", 1)[-1]
            matching_paths = sorted(
                {
                    owner
                    for owner in owners
                    if self._python_class_node(owner, class_name) is not None
                }
            )
            if import_unresolved or len(matching_paths) != 1:
                unresolved = True
                continue
            bases.append((matching_paths[0], class_name))
        return list(dict.fromkeys(bases)), unresolved

    def _python_method_owner(
        self,
        *,
        path: str,
        class_qualname: str,
        method: str,
        candidates: list[dict[str, object]],
        seen: frozenset[tuple[str, str]] = frozenset(),
    ) -> tuple[dict[str, object] | None, bool]:
        key = (path, class_qualname)
        if key in seen:
            return None, True
        direct = self._python_direct_method_owners(
            path, class_qualname, method, candidates
        )
        if direct:
            return (direct[0], False) if len(direct) == 1 else (None, True)

        bases, unresolved = self._python_class_bases(path, class_qualname)
        if unresolved:
            return None, True
        owners: dict[str, dict[str, object]] = {}
        ambiguous = False
        for base_path, base_qualname in bases:
            owner, base_ambiguous = self._python_method_owner(
                path=base_path,
                class_qualname=base_qualname,
                method=method,
                candidates=candidates,
                seen=seen | {key},
            )
            ambiguous = ambiguous or base_ambiguous
            if owner is not None:
                owners[_symbol_id(owner)] = owner
        if ambiguous or len(owners) > 1:
            return None, True
        owner = next(iter(owners.values())) if owners else None
        return owner, False

    @staticmethod
    def _python_direct_method_owners(
        path: str,
        class_qualname: str,
        method: str,
        candidates: Sequence[dict[str, object]],
    ) -> list[dict[str, object]]:
        return [
            row
            for row in candidates
            if str(row.get("path") or "") == path
            and str(row.get("qualname") or "") == f"{class_qualname}.{method}"
        ]

    @staticmethod
    def _python_self_cls_target(
        source_qualname: str, target: str
    ) -> _SelfClsCallTarget | None:
        parts = target.split(".")
        if (
            len(parts) != 2
            or parts[0] not in {"self", "cls"}
            or "." not in source_qualname
        ):
            return None
        class_qualname, source_method = source_qualname.rsplit(".", 1)
        return _SelfClsCallTarget(
            receiver=parts[0],
            method=parts[1],
            class_qualname=class_qualname,
            source_method=source_method,
        )

    @staticmethod
    def _python_receiver_matches_method(
        class_node: ast.ClassDef, target: _SelfClsCallTarget
    ) -> bool:
        methods = [
            node
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == target.source_method
        ]
        if len(methods) != 1:
            return False
        source_node = methods[0]
        positional = [*source_node.args.posonlyargs, *source_node.args.args]
        if not positional or positional[0].arg != target.receiver:
            return False
        decorators = {
            (
                decorator.id
                if isinstance(decorator, ast.Name)
                else decorator.attr
                if isinstance(decorator, ast.Attribute)
                else ""
            )
            for decorator in source_node.decorator_list
        }
        if target.receiver == "cls":
            return "classmethod" in decorators
        return not {"classmethod", "staticmethod"} & decorators

    def _python_self_cls_call_binding(
        self,
        *,
        source_path: str,
        source_qualname: str,
        target: str,
        candidates: list[dict[str, object]],
    ) -> tuple[dict[str, object] | None, list[str], bool] | None:
        call_target = self._python_self_cls_target(source_qualname, target)
        if call_target is None:
            return None
        class_node = self._python_class_node(source_path, call_target.class_qualname)
        if class_node is None or not self._python_receiver_matches_method(
            class_node, call_target
        ):
            return None

        owner, unresolved = self._python_method_owner(
            path=source_path,
            class_qualname=call_target.class_qualname,
            method=call_target.method,
            candidates=candidates,
        )
        candidate_ids = sorted(_symbol_id(row) for row in candidates)
        if owner is None:
            return None, candidate_ids, unresolved
        return owner, [_symbol_id(owner)], False

    def _python_qualified_call_binding(
        self,
        *,
        source_path: str,
        source_qualname: str,
        target: str,
        candidates: list[dict[str, object]],
    ) -> tuple[dict[str, object] | None, list[str], bool]:
        self_cls_binding = self._python_self_cls_call_binding(
            source_path=source_path,
            source_qualname=source_qualname,
            target=target,
            candidates=candidates,
        )
        if self_cls_binding is not None:
            return self_cls_binding
        return self._python_repository_qualified_call_binding(
            source_path=source_path,
            source_qualname=source_qualname,
            target=target,
            candidates=candidates,
        )

    def _python_repository_qualified_call_binding(
        self,
        *,
        source_path: str,
        source_qualname: str,
        target: str,
        candidates: list[dict[str, object]],
    ) -> tuple[dict[str, object] | None, list[str], bool]:
        self = cast("CodeMap", self)
        candidate_ids = sorted(_symbol_id(row) for row in candidates)
        root = target.split(".", 1)[0]
        if not root or self._python_function_locally_binds(
            source_path, source_qualname, root
        ):
            return None, candidate_ids, False
        kind, targets = self._python_export_binding(source_path, root)
        if kind == "local":
            qualified = [
                row
                for row in candidates
                if str(row.get("path") or "") == source_path
                and str(row.get("qualname") or "") == target
            ]
            if len(qualified) == 1:
                binding = qualified[0], [_symbol_id(qualified[0])], False
            else:
                root_symbols = [
                    row
                    for row in self._visible_named_symbol_candidates(root)
                    if str(row.get("path") or "") == source_path
                    and str(row.get("qualname") or "") == root
                ]
                binding = _binding_result(
                    qualified, candidates, unresolved=bool(root_symbols)
                )
            return binding
        if kind == "reexport" and len(targets) == 1:
            owners, unresolved = self._resolve_import_owner_evidence(
                source_path, targets[0]
            )
            if unresolved:
                return None, candidate_ids, True
            owner_paths = set(owners)
            imported_name = targets[0].rsplit(".", 1)[-1]
            root_symbols = [
                row
                for row in self._visible_named_symbol_candidates(imported_name)
                if str(row.get("path") or "") in owner_paths
                and str(row.get("qualname") or "") == imported_name
                and str(row.get("kind") or "") == "class"
            ]
            if not root_symbols:
                # Imported data/functions can expose runtime methods such as
                # dict.items().  Without an indexed class namespace there is no
                # repository member authority to make that call ambiguous.
                return None, candidate_ids, False
            member = target.split(".", 1)[1]
            qualified_name = f"{imported_name}.{member}"
            qualified = [
                row
                for row in candidates
                if str(row.get("path") or "") in owner_paths
                and str(row.get("qualname") or "") == qualified_name
            ]
            return _binding_result(qualified, candidates, unresolved=True)
        return None, candidate_ids, kind in {"ambiguous", "star"}

    def _resolve_call_target(
        self, edge: Mapping[str, object]
    ) -> tuple[dict[str, object] | None, list[str], bool]:
        target = str(edge.get("target") or "").strip()
        short = target.rsplit(".", 1)[-1]
        if not short:
            return None, [], False
        candidates = self._visible_named_symbol_candidates(short)
        source_path = str(edge.get("path") or "")
        source_qualname = str(edge.get("source") or "")
        source_row = self.store.file_row(source_path)
        language = "" if source_row is None else str(source_row["language"] or "")
        if language == "python" and target != short:
            return self._python_qualified_call_binding(
                source_path=source_path,
                source_qualname=source_qualname,
                target=target,
                candidates=candidates,
            )
        if language == "python":
            return self._python_plain_call_binding(
                source_path=source_path,
                source_qualname=source_qualname,
                short=short,
                candidates=candidates,
            )
        candidate_ids = sorted(_symbol_id(row) for row in candidates)
        return None, candidate_ids, bool(candidate_ids)

    def _locality_callers(
        self, row: Mapping[str, object], *, ref_limit: int
    ) -> tuple[list[dict[str, object]], bool, list[dict[str, object]]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        name = str(row["name"])
        target_id = _symbol_id(row)
        raw_refs = [dict(ref) for ref in self.store.refs(name, limit=ref_limit)]
        reference_bound_complete = len(raw_refs) < ref_limit
        raw = [
            ref for ref in raw_refs if str(ref.get("kind") or "") == "call"
        ]
        callers: dict[tuple[str, str], dict[str, object]] = {}
        unresolved: list[dict[str, object]] = []
        for ref in raw:
            resolved, candidates, repository_unresolved = self._resolve_call_target(ref)
            if resolved is None or _symbol_id(resolved) != target_id:
                if repository_unresolved and target_id in candidates:
                    unresolved.append(
                        {
                            "path": str(ref.get("path") or ""),
                            "source": ref.get("source"),
                            "line": ref.get("line"),
                            "target": ref.get("target"),
                            "candidate_symbol_ids": candidates,
                        }
                    )
                continue
            key = (str(ref.get("path") or ""), str(ref.get("source") or "<module>"))
            callers[key] = {
                "path": key[0],
                "source": None if key[1] == "<module>" else key[1],
                "line": ref.get("line"),
                "confidence": ref.get("confidence"),
            }
        return (
            [callers[key] for key in sorted(callers)],
            reference_bound_complete,
            sorted(
                unresolved,
                key=lambda item: (
                    str(item["path"]),
                    int(item["line"] or 0),
                    str(item["source"] or ""),
                ),
            ),
        )

    def _locality_node(
        self,
        row: Mapping[str, object],
        *,
        navigation_depth: int,
        ref_limit: int,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        path = str(row["path"])
        file_row = self.store.file_row(path)
        digest = "" if file_row is None else str(file_row["file_digest"])
        forwarding: bool | None = None
        forwarding_provider = "unsupported-language"
        language = "" if file_row is None else str(file_row["language"])
        if language == "python":
            forwarding, forwarding_provider = _forwarding_only_python_symbol(
                self.workspace / path,
                start_line=int(row["start_line"]),
                name=str(row["name"]),
            )
        callers, caller_reference_bound_complete, unresolved_callers = self._locality_callers(
            row, ref_limit=ref_limit
        )
        source_semantic = {
            "path": path,
            "qualname": str(row["qualname"]),
            "file_digest": digest,
            "lines": [int(row["start_line"]), int(row["end_line"])],
        }
        semantic = {
            "path": path,
            "qualname": str(row["qualname"]),
            "name": str(row["name"]),
            "kind": str(row["kind"]),
            "signature": str(row["signature"]),
            "lines": [int(row["start_line"]), int(row["end_line"])],
            "navigation_depth": navigation_depth,
            "file_digest": digest,
            "forwarding_only": forwarding,
            "forwarding_provider": forwarding_provider,
            "exact_callers": callers,
            "exact_caller_count": len(callers),
            "caller_reference_bound_complete": caller_reference_bound_complete,
            "unresolved_caller_candidates": unresolved_callers,
        }
        return {
            "symbol_id": _symbol_id(row),
            **semantic,
            "symbol_source_identity": _identity(source_semantic),
            "symbol_evidence_identity": _identity(semantic),
        }

    def _locality_graph(
        self,
        target_row: Mapping[str, object],
        *,
        max_depth: int,
        call_limit_per_symbol: int,
        ref_limit_per_symbol: int,
    ) -> tuple[
        list[dict[str, object]],
        list[dict[str, object]],
        list[dict[str, object]],
        list[dict[str, object]],
    ]:
        queue: list[tuple[dict[str, object], int]] = [(dict(target_row), 0)]
        nodes: dict[str, dict[str, object]] = {}
        edges: list[dict[str, object]] = []
        unresolved_calls: list[dict[str, object]] = []
        external_calls: list[dict[str, object]] = []
        while queue:
            row, depth = queue.pop(0)
            symbol_id = _symbol_id(row)
            if symbol_id in nodes:
                continue
            nodes[symbol_id] = self._locality_node(
                row, navigation_depth=depth, ref_limit=ref_limit_per_symbol
            )
            if depth >= max_depth:
                continue
            outgoing = [
                dict(edge)
                for edge in self.store.edges_from(
                    str(row["path"]), str(row["qualname"])
                )
                if str(edge.get("kind") or "") == "call"
            ]
            for edge in outgoing[:call_limit_per_symbol]:
                resolved, candidates, repository_unresolved = self._resolve_call_target(edge)
                record = _locality_edge_record(symbol_id, edge, resolved, candidates)
                edges.append(record)
                if resolved is not None:
                    queue.append((resolved, depth + 1))
                elif repository_unresolved:
                    unresolved_calls.append(record)
                else:
                    external_calls.append(record)
            if len(outgoing) > call_limit_per_symbol:
                unresolved_calls.append(
                    {
                        "source_symbol_id": symbol_id,
                        "reason": "call-limit-reached",
                        "limit": call_limit_per_symbol,
                    }
                )
        ordered_nodes = sorted(nodes.values(), key=_locality_node_sort_key)
        return ordered_nodes, edges, unresolved_calls, external_calls

    def structural_locality(
        self,
        target: str,
        *,
        max_depth: int = 2,
        call_limit_per_symbol: int = 64,
        ref_limit_per_symbol: int = 256,
        refresh: bool = True,
    ) -> dict[str, object]:
        """Return bounded structural facts reachable from one exact symbol.

        The projection deliberately does not label a refactor good/bad, propose an
        edit, or infer semantic responsibility. Ambiguous static call targets stay
        unresolved instead of being counted as reuse or ownership.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._validate_locality_bounds(
            max_depth, call_limit_per_symbol, ref_limit_per_symbol
        )
        if refresh:
            self.sync()
        else:
            self._ensure_map_ready()
        target_row = self._exact_locality_target(target)

        (
            ordered_nodes,
            edges,
            unresolved_calls,
            external_or_unindexed_calls,
        ) = self._locality_graph(
            target_row,
            max_depth=max_depth,
            call_limit_per_symbol=call_limit_per_symbol,
            ref_limit_per_symbol=ref_limit_per_symbol,
        )
        files = sorted({str(row["path"]) for row in ordered_nodes})
        verification_paths = sorted(
            {
                str(path)
                for path in self.tests(str(target_row["path"]), max_depth=3).get(
                    "tests", []
                )
            }
        )
        target_node = next(
            row for row in ordered_nodes if row["symbol_id"] == _symbol_id(target_row)
        )
        dimensions = {
            "symbol_count": len(ordered_nodes),
            "file_count": len(files),
            "max_navigation_depth": max(
                (int(row["navigation_depth"]) for row in ordered_nodes), default=0
            ),
            "forwarding_only_symbol_count": sum(
                1 for row in ordered_nodes if row["forwarding_only"] is True
            ),
            "forwarding_unknown_symbol_count": sum(
                1 for row in ordered_nodes if row["forwarding_only"] is None
            ),
            "context_lines": _union_line_count(ordered_nodes),
            "verifier_file_count": len(verification_paths),
            "cross_file_symbol_count": sum(
                1
                for row in ordered_nodes
                if str(row["path"]) != str(target_row["path"])
            ),
            "unresolved_call_count": len(unresolved_calls),
            "external_or_unindexed_call_count": len(external_or_unindexed_calls),
            "target_exact_caller_count": int(target_node["exact_caller_count"]),
        }
        repository_identity = "sha256:" + self._workspace_fingerprint_from_store()
        configuration = {
            "max_depth": max_depth,
            "call_limit_per_symbol": call_limit_per_symbol,
            "ref_limit_per_symbol": ref_limit_per_symbol,
            "verification_max_depth": 3,
            "target_resolution": "exact-path-qualname",
            "call_resolution": "unambiguous-indexed-symbol-only",
            "refresh": refresh,
        }
        freshness_fields = self._query_freshness_fields()
        freshness_state = "current" if refresh else _freshness(freshness_fields.get("stale"))
        semantic = {
            "schema": STRUCTURAL_LOCALITY_SCHEMA,
            "provider": "hashmarks",
            "provider_version": __version__,
            "provider_implementation_identity": native_producer_implementation_identity(),
            "repository_identity": repository_identity,
            "source_identity": target_node["symbol_source_identity"],
            "measurement_configuration_identity": _identity(configuration),
            "target": target,
            "target_symbol_id": _symbol_id(target_row),
            "freshness": {
                **freshness_fields,
                "state": freshness_state,
                "basis": "explicit-sync" if refresh else "observer-status",
            },
            "bounds": configuration,
            "nodes": ordered_nodes,
            "edges": sorted(
                edges,
                key=lambda item: (
                    str(item["source_symbol_id"]),
                    int(item["line"] or 0),
                    str(item["target_text"]),
                ),
            ),
            "unresolved_calls": sorted(
                unresolved_calls,
                key=lambda item: (
                    str(item.get("source_symbol_id") or ""),
                    int(item.get("line") or 0),
                    str(item.get("target_text") or item.get("reason") or ""),
                ),
            ),
            "external_or_unindexed_calls": sorted(
                external_or_unindexed_calls,
                key=lambda item: (
                    str(item.get("source_symbol_id") or ""),
                    int(item.get("line") or 0),
                    str(item.get("target_text") or ""),
                ),
            ),
            "verification_paths": verification_paths,
            "dimensions": dimensions,
            "claims": {
                "refactor_recommendation": False,
                "semantic_responsibility_inferred": False,
                "ambiguous_calls_promoted_to_exact": False,
                "execution_authority": False,
            },
        }
        return {**semantic, "evidence_identity": _identity(semantic)}


def _locality_edge_record(
    source_symbol_id: str,
    edge: Mapping[str, object],
    resolved: Mapping[str, object] | None,
    candidates: list[str],
) -> dict[str, object]:
    return {
        "source_symbol_id": source_symbol_id,
        "path": str(edge.get("path") or ""),
        "line": edge.get("line"),
        "target_text": str(edge.get("target") or ""),
        "confidence": str(edge.get("confidence") or ""),
        "resolved_symbol_id": None if resolved is None else _symbol_id(resolved),
        "candidate_symbol_ids": candidates,
    }


def _locality_node_sort_key(item: Mapping[str, object]) -> tuple[int, str, int, str]:
    lines = item["lines"]
    assert isinstance(lines, Sequence) and not isinstance(lines, (str, bytes, bytearray))
    return (
        int(item["navigation_depth"]),
        str(item["path"]),
        int(lines[0]),
        str(item["qualname"]),
    )


def _packet_identity_valid(packet: Mapping[str, object]) -> bool:
    identity = packet.get("evidence_identity")
    if not isinstance(identity, str) or not identity:
        return False
    semantic = {
        str(key): value for key, value in packet.items() if key != "evidence_identity"
    }
    return identity == _identity(semantic)


def _delta_incomparability_reasons(before: Mapping[str, object], after: Mapping[str, object]) -> list[str]:
    checks = (
        ("before-schema", before.get("schema") == STRUCTURAL_LOCALITY_SCHEMA),
        ("after-schema", after.get("schema") == STRUCTURAL_LOCALITY_SCHEMA),
        ("before-provider", before.get("provider") == "hashmarks"),
        ("after-provider", after.get("provider") == "hashmarks"),
        ("provider-version", before.get("provider_version") == after.get("provider_version")),
        ("provider-implementation", before.get("provider_implementation_identity") == after.get("provider_implementation_identity")),
        ("before-evidence-identity", _packet_identity_valid(before)),
        ("after-evidence-identity", _packet_identity_valid(after)),
        ("target", before.get("target") == after.get("target")),
        ("measurement-configuration", before.get("measurement_configuration_identity") == after.get("measurement_configuration_identity")),
        ("repository-state-not-distinct", before.get("repository_identity") != after.get("repository_identity")),
    )
    issues = [label for label, valid in checks if not valid]
    for label, packet in (("before", before), ("after", after)):
        freshness = packet.get("freshness")
        if not isinstance(freshness, Mapping) or freshness.get("state") != "current":
            issues.append(f"{label}-freshness")
        if not isinstance(packet.get("evidence_identity"), str):
            issues.append(f"{label}-identity")
    return issues


def _delta_nodes(packet: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    rows = packet.get("nodes", [])
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        return {}
    return {str(row.get("symbol_id")): row for row in rows if isinstance(row, Mapping) and row.get("symbol_id")}


def _integer_dimension_delta(before: object, after: object) -> tuple[dict[str, int], bool]:
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return {}, False
    delta: dict[str, int] = {}
    for key in sorted(set(before) & set(after)):
        left, right = before.get(key), after.get(key)
        if isinstance(left, int) and not isinstance(left, bool) and isinstance(right, int) and not isinstance(right, bool):
            delta[str(key)] = right - left
    return delta, True


def _string_set(packet: Mapping[str, object], key: str) -> set[str]:
    values = packet.get(key, [])
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return set()
    return {str(value) for value in values if value}


def structural_locality_delta(before: Mapping[str, object], after: Mapping[str, object]) -> dict[str, object]:
    """Compare two structural-locality packets without interpreting the tradeoff."""
    issues = _delta_incomparability_reasons(before, after)
    before_nodes, after_nodes = _delta_nodes(before), _delta_nodes(after)
    dimension_delta, dimensions_valid = _integer_dimension_delta(before.get("dimensions"), after.get("dimensions"))
    if not dimensions_valid:
        issues.append("dimensions")
    before_verifiers = _string_set(before, "verification_paths")
    after_verifiers = _string_set(after, "verification_paths")
    semantic = {
        "schema": STRUCTURAL_LOCALITY_DELTA_SCHEMA,
        "target": before.get("target"),
        "before_evidence_identity": before.get("evidence_identity"),
        "after_evidence_identity": after.get("evidence_identity"),
        "before_repository_identity": before.get("repository_identity"),
        "after_repository_identity": after.get("repository_identity"),
        "measurement_configuration_identity": before.get("measurement_configuration_identity"),
        "comparable": not issues,
        "incomparability_reasons": sorted(set(issues)),
        "introduced_symbol_ids": sorted(set(after_nodes) - set(before_nodes)),
        "removed_symbol_ids": sorted(set(before_nodes) - set(after_nodes)),
        "dimension_delta": dimension_delta,
        "verification_paths_added": sorted(after_verifiers - before_verifiers),
        "verification_paths_removed": sorted(before_verifiers - after_verifiers),
        "claims": {"architectural_improvement": False, "refactor_recommendation": False, "consumer_policy_applied": False},
    }
    return {**semantic, "evidence_identity": _identity(semantic)}
