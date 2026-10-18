from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks._version import __version__
from hashmarks.operation_contract import (
    operation_response,
    operation_schema,
    validate_operation_response,
)
from hashmarks.paths import normalize_relative_path
from hashmarks.producer_identity import native_producer_implementation_identity
from hashmarks.python_ast_cache import read_python_ast

from .decision_session import ReadScopeOwner, decision_scoped
from .model import EvidenceVisibility
from .ownership.filesystem_lifecycle import locality_lifecycle
from .python_exports import (
    python_class_member_binding,
    python_class_node,
    python_function_body_binds,
    python_function_scope_binds,
)
from .repository_domains import is_test_path
from .structural_locality_model import (
    LOCALITY_SCHEMA,
    LocalityNode,
    LocalityNodeFacts,
    locality_coordinate,
    locality_identity,
)
from .structural_search import AstGrepSearchProvider

if TYPE_CHECKING:
    from .decision_session import DecisionScope
    from .evidence_graph import RepositoryRelationships
    from .import_resolution import RepositoryImports
    from .native_evidence import RepositoryNativeEvidence
    from .repository_source import RepositorySource

STRUCTURAL_LOCALITY_SCHEMA = LOCALITY_SCHEMA
_LOCALITY_SYMBOL_CANDIDATE_LIMIT = 64


@dataclass(frozen=True)
class _SelfClsCallTarget:
    receiver: str
    method: str
    class_qualname: str
    source_method: str


@dataclass(frozen=True)
class _NamedSymbolCandidateEvidence:
    rows: list[dict[str, object]]
    complete: bool


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
        by_path.setdefault(str(row["path"]), []).append((int(lines[0]), int(lines[1])))
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


def _body_without_docstring(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.stmt]:
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


def _binding_result(
    rows: Sequence[dict[str, object]],
    fallback: Sequence[dict[str, object]],
    *,
    unresolved: bool,
) -> tuple[dict[str, object] | None, list[str], bool]:
    if len(rows) == 1:
        return rows[0], [_symbol_id(rows[0])], False
    return None, sorted(_symbol_id(row) for row in rows or fallback), unresolved


class RepositoryStructure(ReadScopeOwner):
    """Own bounded structural searches and exact source/call locality evidence."""

    def __init__(
        self,
        source: RepositorySource,
        imports: RepositoryImports,
        native: RepositoryNativeEvidence,
        relationships: RepositoryRelationships,
        *,
        search_provider: AstGrepSearchProvider | None = None,
    ) -> None:
        if any(
            owner.reads is not source.reads
            for owner in (imports, native, relationships)
        ):
            raise ValueError("Structural inputs must share one repository read scope")
        self.source = source
        self.imports = imports
        self.native = native
        self.relationships = relationships
        self.files = source.files
        self.index = source.index
        self.store = source.store
        self.workspace = source.workspace
        self.search_provider = (
            AstGrepSearchProvider(self.workspace)
            if search_provider is None
            else search_provider
        )

    @property
    def reads(self) -> DecisionScope:
        return self.source.reads

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
        if "::" not in target:
            raise ValueError(
                "structural locality requires an exact path::qualname target"
            )
        raw_path, qualname = target.split("::", 1)
        path = normalize_relative_path(
            raw_path.strip().replace("\\", "/"), allow_root=False
        )
        qualname = qualname.strip()
        if not qualname:
            raise ValueError("target path and qualname must be non-empty")
        self.source.ensure_current(path)
        row = self.store.symbol_at(path, qualname)
        if row is None:
            raise KeyError(f"symbol not found: {target}")
        if (
            EvidenceVisibility(str(row["evidence_visibility"]))
            is EvidenceVisibility.DENY
        ):
            raise PermissionError(
                f"symbol exists but repository evidence is denied: {target}"
            )
        return dict(row)

    def _visible_named_symbol_candidates(
        self, name: str
    ) -> _NamedSymbolCandidateEvidence:
        probe = self.store.visible_symbol_candidates(
            name, limit=_LOCALITY_SYMBOL_CANDIDATE_LIMIT + 1
        )
        return _NamedSymbolCandidateEvidence(
            rows=[dict(row) for row in probe[:_LOCALITY_SYMBOL_CANDIDATE_LIMIT]],
            complete=len(probe) <= _LOCALITY_SYMBOL_CANDIDATE_LIMIT,
        )

    def _qualified_path_symbols(self, path: str) -> list[dict[str, object]]:
        """Observe the complete admitted file scope before binding a declaration."""
        decision = self.source.files.decide(path)
        if (
            not decision.index
            or decision.evidence_visibility is not EvidenceVisibility.SOURCE
        ):
            return []
        self.source.ensure_current(path)
        return self.reads.symbols_for_path(path)

    def _python_function_locally_binds(self, path: str, source: str, name: str) -> bool:
        if not path.endswith(".py") or not source or not name:
            return False
        try:
            snapshot = read_python_ast(self.workspace / path, errors="replace")
        except (OSError, SyntaxError, UnicodeError, ValueError):
            return True
        return python_function_scope_binds(
            snapshot.function_definitions_by_qualname, source, name
        )

    def _python_plain_call_binding(
        self,
        *,
        source_path: str,
        source_qualname: str,
        short: str,
        evidence: _NamedSymbolCandidateEvidence,
    ) -> tuple[dict[str, object] | None, list[str], bool]:
        candidates = evidence.rows
        candidate_ids = sorted(_symbol_id(row) for row in candidates)
        if self._python_function_locally_binds(source_path, source_qualname, short):
            return None, candidate_ids, False
        kind, targets = self.imports._python_export_binding(source_path, short)
        if kind in {"ambiguous", "star"} or (kind == "local" and not evidence.complete):
            return None, candidate_ids, True
        if kind == "local":
            declared = self.imports._python_export_is_declaration(source_path, short)
            local = [
                row
                for row in candidates
                if declared and str(row.get("path") or "") == source_path
            ]
            return _binding_result(
                local, candidates, unresolved=not declared or len(local) > 1
            )
        if kind == "reexport" and len(targets) == 1:
            symbols, unresolved = self.imports._resolve_import_symbol_evidence(
                source_path, targets[0]
            )
            if unresolved:
                return None, candidate_ids, True
            owned = [
                row
                for path, qualname in symbols
                for row in self._qualified_path_symbols(path)
                if str(row.get("qualname") or "") == qualname
            ]
            return _binding_result(owned, candidates, unresolved=bool(symbols))
        return None, candidate_ids, False

    def _python_class_node(self, path: str, qualname: str) -> ast.ClassDef | None:
        if not path.endswith(".py") or not qualname:
            return None
        try:
            tree = read_python_ast(self.workspace / path, errors="replace").tree
        except (OSError, SyntaxError, UnicodeError, ValueError):
            return None
        return python_class_node(tree, qualname)

    def _python_class_bases(
        self, path: str, qualname: str
    ) -> tuple[list[tuple[str, str]], bool]:
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
            kind, targets = self.imports._python_export_binding(path, base.id)
            if kind != "reexport" or len(targets) != 1:
                unresolved = True
                continue
            owners, import_unresolved = self.imports._resolve_import_owner_evidence(
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
        seen: frozenset[tuple[str, str]] = frozenset(),
    ) -> tuple[dict[str, object] | None, bool]:
        key = (path, class_qualname)
        if key in seen:
            return None, True
        direct, unresolved = self._python_direct_method_owners(
            path, class_qualname, method, self._qualified_path_symbols(path)
        )
        if unresolved:
            return None, True
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
                seen=seen | {key},
            )
            ambiguous = ambiguous or base_ambiguous
            if owner is not None:
                owners[_symbol_id(owner)] = owner
        if ambiguous or len(owners) > 1:
            return None, True
        owner = next(iter(owners.values())) if owners else None
        return owner, False

    def _python_direct_method_owners(
        self,
        path: str,
        class_qualname: str,
        method: str,
        candidates: Sequence[dict[str, object]],
    ) -> tuple[list[dict[str, object]], bool]:
        class_node = self._python_class_node(path, class_qualname)
        if class_node is None:
            return [], True
        kind, declaration = python_class_member_binding(class_node, method)
        if declaration is None:
            return [], kind != "unknown"
        owners = [
            row
            for row in candidates
            if str(row.get("path") or "") == path
            and str(row.get("qualname") or "") == f"{class_qualname}.{method}"
            and locality_coordinate(row["start_line"])
            <= declaration.lineno
            <= locality_coordinate(row["end_line"])
        ]
        return owners, not owners

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
    def _python_receiver_method(
        class_node: ast.ClassDef, target: _SelfClsCallTarget
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        methods = [
            node
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == target.source_method
        ]
        if len(methods) != 1:
            return None
        source_node = methods[0]
        positional = [*source_node.args.posonlyargs, *source_node.args.args]
        if not positional or positional[0].arg != target.receiver:
            return None
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
            return source_node if "classmethod" in decorators else None
        return source_node if not {"classmethod", "staticmethod"} & decorators else None

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
        source_node = (
            self._python_receiver_method(class_node, call_target)
            if class_node
            else None
        )
        if source_node is None:
            return None
        candidate_ids = sorted(_symbol_id(row) for row in candidates)
        if python_function_body_binds(source_node, call_target.receiver):
            return None, candidate_ids, True

        owner, unresolved = self._python_method_owner(
            path=source_path,
            class_qualname=call_target.class_qualname,
            method=call_target.method,
        )
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
    ) -> tuple[dict[str, object] | None, list[str], bool, bool]:
        self_cls_binding = self._python_self_cls_call_binding(
            source_path=source_path,
            source_qualname=source_qualname,
            target=target,
            candidates=candidates,
        )
        if self_cls_binding is not None:
            resolved, ids, unresolved = self_cls_binding
            return resolved, ids, unresolved, True
        return self._python_repository_qualified_call_binding(
            source_path=source_path,
            source_qualname=source_qualname,
            target=target,
            candidates=candidates,
        )

    def _python_local_qualified_call_binding(
        self,
        source_path: str,
        target: str,
        root: str,
        candidates: list[dict[str, object]],
    ) -> tuple[dict[str, object] | None, list[str], bool, bool]:
        candidate_ids = sorted(_symbol_id(row) for row in candidates)
        if self._python_class_node(source_path, root) is None:
            return None, candidate_ids, True, True
        class_name, method = target.rsplit(".", 1)
        qualified, _unresolved = self._python_direct_method_owners(
            source_path, class_name, method, self._qualified_path_symbols(source_path)
        )
        if len(qualified) == 1:
            return qualified[0], [_symbol_id(qualified[0])], False, True
        resolved, ids, unresolved = _binding_result(
            qualified, candidates, unresolved=True
        )
        return resolved, ids, unresolved, True

    def _python_reexport_qualified_call_binding(
        self,
        source_path: str,
        target: str,
        import_target: str,
        candidates: list[dict[str, object]],
    ) -> tuple[dict[str, object] | None, list[str], bool, bool]:
        candidate_ids = sorted(_symbol_id(row) for row in candidates)
        symbols, unresolved = self.imports._resolve_import_symbol_evidence(
            source_path, import_target
        )
        if unresolved or len(symbols) != 1:
            data_binding = self._python_imported_data_binding(
                source_path, import_target
            )
            return None, candidate_ids, not data_binding, data_binding
        path, class_name = symbols[0]
        if self._python_class_node(path, class_name) is None:
            return None, candidate_ids, True, True
        member = target.split(".", 1)[1]
        qualified_name = f"{class_name}.{member}"
        class_qualname, method = qualified_name.rsplit(".", 1)
        qualified, _unresolved = self._python_direct_method_owners(
            path, class_qualname, method, self._qualified_path_symbols(path)
        )
        resolved, ids, unresolved = _binding_result(
            qualified, candidates, unresolved=True
        )
        return resolved, ids, unresolved, True

    def _python_imported_data_binding(self, path: str, target: str) -> bool:
        """Keep admitted imported data in the existing external/unindexed category."""
        owners, unresolved = self.imports._resolve_import_owner_evidence(path, target)
        if unresolved:
            return False
        name = target.rsplit(".", 1)[-1]
        return any(
            self.imports._python_export_binding(owner, name)[0] == "local"
            and not self.imports._python_export_is_declaration(owner, name)
            for owner in owners
        )

    def _python_repository_qualified_call_binding(
        self,
        *,
        source_path: str,
        source_qualname: str,
        target: str,
        candidates: list[dict[str, object]],
    ) -> tuple[dict[str, object] | None, list[str], bool, bool]:
        candidate_ids = sorted(_symbol_id(row) for row in candidates)
        root = target.split(".", 1)[0]
        if not root or self._python_function_locally_binds(
            source_path, source_qualname, root
        ):
            return None, candidate_ids, False, True
        kind, targets = self.imports._python_export_binding(source_path, root)
        if kind == "local" and self.imports._python_export_is_declaration(
            source_path, root
        ):
            return self._python_local_qualified_call_binding(
                source_path, target, root, candidates
            )
        if kind == "reexport" and len(targets) == 1:
            return self._python_reexport_qualified_call_binding(
                source_path, target, targets[0], candidates
            )
        return None, candidate_ids, kind in {"local", "ambiguous", "star"}, True

    def _resolve_call_target(
        self, edge: Mapping[str, object]
    ) -> tuple[dict[str, object] | None, list[str], bool, bool]:
        target = str(edge.get("target") or "").strip()
        short = target.rsplit(".", 1)[-1]
        if not short:
            return None, [], False, True
        source_path = str(edge.get("path") or "")
        name = (
            self.imports._python_imported_call_name(source_path, short)
            if target == short
            else short
        )
        evidence = self._visible_named_symbol_candidates(name)
        candidates = evidence.rows
        candidate_ids = sorted(_symbol_id(row) for row in candidates)
        source_qualname = str(edge.get("source") or "")
        source_row = self.store.file_row(source_path)
        language = "" if source_row is None else str(source_row["language"] or "")
        if language == "python" and target != short:
            binding = self._python_qualified_call_binding(
                source_path=source_path,
                source_qualname=source_qualname,
                target=target,
                candidates=candidates,
            )
            if binding[0] is not None or evidence.complete:
                return binding
            return None, binding[1], True, False
        if language == "python":
            resolved, ids, unresolved = self._python_plain_call_binding(
                source_path=source_path,
                source_qualname=source_qualname,
                short=short,
                evidence=evidence,
            )
            if resolved is not None:
                return resolved, ids, False, True
            return None, ids, unresolved or not evidence.complete, evidence.complete
        return (
            None,
            candidate_ids,
            bool(candidate_ids) or not evidence.complete,
            evidence.complete,
        )

    def _locality_callers(
        self, row: Mapping[str, object], *, ref_limit: int
    ) -> tuple[list[dict[str, object]], bool, list[dict[str, object]]]:
        target_id = _symbol_id(row)
        raw_refs, reference_bound_complete = (
            self.imports._python_call_reference_candidates(row, ref_limit)
        )
        raw = [ref for ref in raw_refs if str(ref.get("kind") or "") == "call"]
        callers: dict[tuple[str, str], dict[str, object]] = {}
        unresolved: list[dict[str, object]] = []
        for ref in raw:
            (
                resolved,
                candidates,
                repository_unresolved,
                candidate_search_complete,
            ) = self._resolve_call_target(ref)
            if resolved is None or _symbol_id(resolved) != target_id:
                candidate_ids = list(candidates)
                if not candidate_search_complete and target_id not in candidate_ids:
                    candidate_ids.append(target_id)
                    candidate_ids.sort()
                if repository_unresolved and (
                    target_id in candidate_ids or not candidate_search_complete
                ):
                    unresolved.append(
                        {
                            "path": str(ref.get("path") or ""),
                            "source": ref.get("source"),
                            "line": ref.get("line"),
                            "target": ref.get("target"),
                            "candidate_symbol_ids": candidate_ids,
                            "candidate_search": _candidate_search_contract(
                                candidate_search_complete
                            ),
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
                    locality_coordinate(item["line"] or 0),
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
    ) -> LocalityNode:
        path = str(row["path"])
        start = locality_coordinate(row["start_line"])
        end = locality_coordinate(row["end_line"])
        file_row = self.store.file_row(path)
        digest = "" if file_row is None else str(file_row["file_digest"])
        forwarding: bool | None = None
        forwarding_provider = "unsupported-language"
        language = "" if file_row is None else str(file_row["language"])
        if language == "python":
            forwarding, forwarding_provider = _forwarding_only_python_symbol(
                self.workspace / path,
                start_line=start,
                name=str(row["name"]),
            )
        callers, caller_reference_bound_complete, unresolved_callers = (
            self._locality_callers(row, ref_limit=ref_limit)
        )
        source_semantic = {
            "path": path,
            "qualname": str(row["qualname"]),
            "file_digest": digest,
            "lines": [start, end],
        }
        semantic: LocalityNodeFacts = {
            "path": path,
            "qualname": str(row["qualname"]),
            "name": str(row["name"]),
            "kind": str(row["kind"]),
            "signature": str(row["signature"]),
            "lines": [start, end],
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
            "symbol_source_identity": locality_identity(source_semantic),
            "symbol_evidence_identity": locality_identity(semantic),
        }

    def _locality_graph(
        self,
        target_row: Mapping[str, object],
        *,
        max_depth: int,
        call_limit_per_symbol: int,
        ref_limit_per_symbol: int,
    ) -> tuple[
        list[LocalityNode],
        list[dict[str, object]],
        list[dict[str, object]],
        list[dict[str, object]],
    ]:
        queue: list[tuple[dict[str, object], int]] = [(dict(target_row), 0)]
        nodes: dict[str, LocalityNode] = {}
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
                and edge.get("source") == row["qualname"]
            ]
            for edge in outgoing[:call_limit_per_symbol]:
                (
                    resolved,
                    candidates,
                    repository_unresolved,
                    candidate_search_complete,
                ) = self._resolve_call_target(edge)
                record = _locality_edge_record(
                    symbol_id,
                    edge,
                    resolved,
                    candidates,
                    candidate_search_complete=candidate_search_complete,
                )
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

    def locality(  # noqa: PLR0913 - retain traversal bounds alongside explicit observation inputs
        self,
        target: str,
        *,
        max_depth: int = 2,
        call_limit_per_symbol: int = 64,
        ref_limit_per_symbol: int = 256,
        refresh: bool = True,
        result_mode: str = "default",
        supplied_observations: Sequence[Mapping[str, object]] | None = None,
    ) -> dict[str, object]:
        """Return one generation-scoped structural-locality observation."""
        from .lsp_relationship_adapter import normalize_lsp_captures
        from .semantic_relationship_observation import (
            exact_relationship_target,
            semantic_relationship_observation,
        )

        captures = normalize_lsp_captures(supplied_observations)
        if result_mode not in ("default", "relationships"):
            raise ValueError("result_mode must be default or relationships")
        self._validate_locality_bounds(
            max_depth, call_limit_per_symbol, ref_limit_per_symbol
        )
        if refresh:
            self.index.sync()
        with self.reads.session():
            if result_mode == "relationships":
                result = semantic_relationship_observation(
                    self, exact_relationship_target(self, target), captures
                )
            else:
                result = self._structural_locality_impl(
                    target,
                    max_depth=max_depth,
                    call_limit_per_symbol=call_limit_per_symbol,
                    ref_limit_per_symbol=ref_limit_per_symbol,
                    refresh=refresh,
                )
                if captures:
                    result["supplied_relationship_observation"] = (
                        semantic_relationship_observation(
                            self, self._exact_locality_target(target), captures
                        )
                    )
                    result["evidence_identity"] = locality_identity(
                        {
                            key: value
                            for key, value in result.items()
                            if key != "evidence_identity"
                        }
                    )
            return validate_operation_response(
                "structural_locality", result, mode=result_mode
            )

    @staticmethod
    def _scip_relationship_payload(
        row: Mapping[str, object],
    ) -> tuple[list[Mapping[str, object]], str | None]:
        value = json.loads(str(row["relationships_json"]))
        if isinstance(value, list):
            # Old disposable CodeMap state has no import-time source revision.
            return [item for item in value if isinstance(item, Mapping)], None
        if not isinstance(value, Mapping):
            return [], None
        raw = value.get("relationships", [])
        relationships = (
            [item for item in raw if isinstance(item, Mapping)]
            if isinstance(raw, list)
            else []
        )
        revision = value.get("source_revision_observation")
        return relationships, revision if isinstance(revision, str) else None

    def _scip_target_resolution(
        self, producer: str, target_symbol: str, source_path: str
    ) -> dict[str, object]:
        fresh, _reason = self.native._evidence_fresh("scip", producer)
        candidates = self.store.native_definitions_for_symbol(
            target_symbol,
            producer=producer,
            limit=65,
            document_path=source_path if target_symbol.startswith("local ") else None,
        )
        truncated = len(candidates) >= 65
        current = candidates[:64] if fresh else []
        projected: list[dict[str, object]] = []
        mapped: set[str] = set()
        for candidate in current:
            path = str(candidate["path"])
            symbols = [
                row
                for row in self.reads.symbols_for_path(path)
                if str(row["name"]) == str(candidate["display_name"])
                and locality_coordinate(row["start_line"]) == int(candidate["line"])
            ]
            symbol_ids = sorted(_symbol_id(row) for row in symbols)
            mapped.update(symbol_ids)
            _relationships, revision = self._scip_relationship_payload(candidate)
            projected.append(
                {
                    "producer": producer,
                    "scip_symbol": target_symbol,
                    "path": path,
                    "line": int(candidate["line"]),
                    "code_map_symbol_ids": symbol_ids,
                    "source_revision_observation": revision,
                }
            )
        if truncated:
            state = "incomplete-candidate-search"
        elif len(projected) == 1 and len(mapped) == 1:
            state = "unique-candidate"
        elif len(projected) > 1 or len(mapped) > 1:
            state = "ambiguous-candidates"
        else:
            state = "unresolved"
        return {
            "state": state,
            "candidates": projected,
            "candidate_search": {
                "scope": "retained-fresh-definitions-from-same-scip-producer",
                "complete_within_scope": not truncated,
                "truncated": truncated,
                "negative_evidence_admissible": False,
            },
            "negative_evidence_admissible": False,
        }

    def _scip_provider_freshness(
        self, raw_rows: Sequence[Mapping[str, object]]
    ) -> tuple[dict[str, tuple[bool, str | None]], bool]:
        freshness = {
            producer: self.native._evidence_fresh("scip", producer)
            for producer in {str(row["producer"]) for row in raw_rows}
        }
        statuses = [row for row in self.native.status() if row.get("kind") == "scip"]
        for row in statuses[:64]:
            producer = str(row["producer"])
            freshness.setdefault(
                producer,
                (
                    bool(row["fresh"]),
                    None if row["reason"] is None else str(row["reason"]),
                ),
            )
        return freshness, len(statuses) > 64

    def _scip_decoded_relationships(
        self, rows: Sequence[Mapping[str, object]]
    ) -> tuple[
        dict[int, tuple[list[Mapping[str, object]], str | None]],
        dict[str, set[str]],
        list[str],
        bool,
    ]:
        decoded = {id(row): self._scip_relationship_payload(row) for row in rows}
        observed: dict[str, set[str]] = {}
        revisions: set[str] = set()
        truncated = False
        for row in rows:
            producer = str(row["producer"])
            relationships, revision = decoded[id(row)]
            observed.setdefault(producer, set()).update(
                str(item["kind"])
                for item in relationships
                if isinstance(item.get("kind"), str)
            )
            if revision is not None:
                revisions.add(revision)
            truncated = truncated or bool(row["relationships_truncated"])
        return decoded, observed, sorted(revisions), truncated

    def _scip_target_resolutions(
        self,
        rows: Sequence[Mapping[str, object]],
        decoded: Mapping[int, tuple[list[Mapping[str, object]], str | None]],
    ) -> tuple[dict[tuple[str, str], dict[str, object]], bool]:
        by_producer: dict[str, set[str]] = {}
        for row in rows:
            producer = str(row["producer"])
            by_producer.setdefault(producer, set()).update(
                str(item["target_symbol"])
                for item in decoded[id(row)][0]
                if isinstance(item.get("target_symbol"), str)
            )
        projected: dict[tuple[str, str], dict[str, object]] = {}
        truncated = False
        for producer, targets in by_producer.items():
            ordered = sorted(targets)
            for target in ordered[:128]:
                source_path = next(
                    str(row["path"]) for row in rows if str(row["producer"]) == producer
                )
                projected[(producer, target)] = self._scip_target_resolution(
                    producer, target, source_path
                )
            for target in ordered[128:]:
                truncated = True
                projected[(producer, target)] = {
                    "state": "not-searched-budget",
                    "candidates": [],
                    "candidate_search": {
                        "scope": "retained-fresh-definitions-from-same-scip-producer",
                        "complete_within_scope": False,
                        "truncated": True,
                        "negative_evidence_admissible": False,
                    },
                    "negative_evidence_admissible": False,
                }
        return projected, truncated

    @staticmethod
    def _scip_projected_relation_rows(
        rows: Sequence[Mapping[str, object]],
        decoded: Mapping[int, tuple[list[Mapping[str, object]], str | None]],
        target_node: Mapping[str, object],
    ) -> list[dict[str, object]]:
        relations: list[dict[str, object]] = []
        for row in rows:
            producer = str(row["producer"])
            source_revision = decoded[id(row)][1]
            for item in decoded[id(row)][0]:
                target = item.get("target_symbol")
                if not isinstance(target, str):
                    continue
                relations.append(
                    {
                        "producer": producer,
                        "path": row["path"],
                        "line": row["line"],
                        "source_symbol": row["symbol"],
                        "kind": item.get("kind"),
                        "target_symbol": target,
                        "source_identity": target_node["symbol_source_identity"],
                        "source_revision": {
                            "observed_at_import": source_revision,
                            "observed_current": target_node.get("file_digest"),
                            "same_as_current_observation": (
                                source_revision == target_node.get("file_digest")
                                if source_revision is not None
                                else None
                            ),
                            "producer_claimed_revision": None,
                            "producer_claim_state": "not-captured-by-scip-adapter",
                            "binding_state": "unknown",
                        },
                        "target_resolution_ref": {
                            "producer": producer,
                            "target_symbol": target,
                        },
                    }
                )
        return sorted(
            relations,
            key=lambda item: (
                str(item["producer"]),
                str(item["source_symbol"]),
                str(item["kind"]),
                str(item["target_symbol"]),
            ),
        )

    def _scip_compact_discovery(
        self, row: Mapping[str, object]
    ) -> dict[str, object] | None:
        """Summarize observed SCIP flags without relationship graph traversal.

        Used only to describe available evidence for an already-selected exact
        repository symbol. It neither resolves owners nor proves absent edges.
        """
        definitions, definition_truncated = (
            self.native._fresh_native_definitions_for_path(
                str(row["path"]),
                name=str(row["name"]),
                line=locality_coordinate(row["start_line"]),
            )
        )
        if not definitions:
            return None
        decoded, kinds, revisions, relation_truncated = (
            self._scip_decoded_relationships(definitions[:128])
        )
        count = sum(len(decoded[id(item)][0]) for item in definitions[:128])
        file_row = self.reads.file_row(str(row["path"]))
        current_revision = (
            str(file_row["file_digest"])
            if file_row is not None and file_row.get("file_digest")
            else None
        )
        if not revisions or current_revision is None:
            revision_observation = "unknown"
        elif all(revision == current_revision for revision in revisions):
            revision_observation = "same-as-import-observation"
        else:
            revision_observation = "differs-from-import-observation"
        return {
            "authority": "scip-producer-claim-only",
            "subject": f"{row['path']}::{row['qualname']}",
            "observation_state": (
                "direct-claims-observed"
                if count
                else "definition-observed-no-direct-claims"
            ),
            "observed_relationship_count": count,
            "observed_kinds": sorted(set().union(*kinds.values())),
            "producer_bindings": sorted(kinds),
            "truncated": definition_truncated or relation_truncated,
            "completeness": "unknown",
            "source_equivalence": "unknown",
            "repository_revision_observation": revision_observation,
            "negative_evidence_admissible": False,
            "detail_surface": "structural_locality",
            "detail_arguments": {
                "target": f"{row['path']}::{row['qualname']}",
                "result_mode": "relationships",
            },
        }

    def _scip_direct_relationships(
        self,
        target_row: Mapping[str, object],
        target_node: Mapping[str, object],
    ) -> dict[str, object]:
        """Project bounded SCIP claims with revision and coverage provenance."""
        raw_rows = self.store.native_definitions_for_path(
            str(target_row["path"]),
            name=str(target_row["name"]),
            line=locality_coordinate(target_row["start_line"]),
            limit=129,
        )
        source_truncated = len(raw_rows) >= 129
        freshness, provider_status_truncated = self._scip_provider_freshness(raw_rows)
        fresh_rows = [row for row in raw_rows if freshness[str(row["producer"])][0]][
            :128
        ]
        decoded, observed_kinds, revisions, relationship_truncated = (
            self._scip_decoded_relationships(fresh_rows)
        )
        target_resolutions, target_resolution_truncated = self._scip_target_resolutions(
            fresh_rows, decoded
        )
        truncated = source_truncated or relationship_truncated
        relations = self._scip_projected_relation_rows(fresh_rows, decoded, target_node)
        target_resolution_records = [
            {
                "producer": producer,
                "target_symbol": target_symbol,
                **resolution,
            }
            for (producer, target_symbol), resolution in sorted(
                target_resolutions.items()
            )
        ]
        providers = sorted(freshness)
        return {
            "native_semantic_relationships": {
                "authority": "scip-producer-claim-only",
                "scope": "target-definition-start-line-only",
                "producer_bindings": sorted(
                    {str(row["producer"]) for row in fresh_rows}
                ),
                "provider_capabilities": [
                    {
                        "producer": producer,
                        "declared_relationship_capability": None,
                        "declared_capability_state": "not-captured-by-scip-adapter",
                        "adapter_recognized_relationship_kinds": [
                            "definition",
                            "implementation",
                            "reference",
                            "type_definition",
                        ],
                        "observed_relationship_kinds_for_scope": sorted(
                            observed_kinds.get(producer, set())
                        ),
                        "unobserved_kinds_meaning": "unknown-not-unsupported",
                        "freshness": "current" if freshness[producer][0] else "stale",
                        "freshness_reason": freshness[producer][1],
                    }
                    for producer in providers
                ],
                "provider_status_truncated": provider_status_truncated,
                "target_resolution_truncated": target_resolution_truncated,
                "target_resolutions": target_resolution_records,
                "source_revision": {
                    "observed_at_import": revisions,
                    "observed_current": target_node.get("file_digest"),
                    "same_as_current_observation": (
                        all(
                            revision == target_node.get("file_digest")
                            for revision in revisions
                        )
                        if revisions
                        else None
                    ),
                    "producer_claimed_revision": None,
                    "producer_claim_state": "not-captured-by-scip-adapter",
                    "binding_state": "unknown",
                },
                "observation_coverage": {
                    "state": "current-bounded-observation"
                    if fresh_rows
                    else "stale-provider-observation"
                    if any(not value[0] for value in freshness.values())
                    else "provider-observed-target-definition-not-found"
                    if freshness
                    else "no-provider-observation",
                    "definition_scope": ("exact-admitted-path-display-name-start-line"),
                    "definitions_observed": len(fresh_rows),
                    "definition_limit": 128,
                    "relationship_limit_per_definition": 64,
                    "truncated": (
                        truncated
                        or target_resolution_truncated
                        or provider_status_truncated
                    ),
                    "producer_response_completeness": "unknown",
                    "negative_evidence_admissible": False,
                },
                "truncated": truncated,
                "negative_evidence_admissible": False,
                "relationships": relations,
            }
        }

    def _structural_locality_impl(
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
        self.reads.ready()
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
        target_node = next(
            row for row in ordered_nodes if row["symbol_id"] == _symbol_id(target_row)
        )
        verification_paths = self._locality_verification_paths(target_row, target_node)
        dimensions = {
            "symbol_count": len(ordered_nodes),
            "file_count": len({str(row["path"]) for row in ordered_nodes}),
            "max_navigation_depth": max(
                (row["navigation_depth"] for row in ordered_nodes), default=0
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
            "target_exact_caller_count": target_node["exact_caller_count"],
        }
        repository_identity = "sha256:" + self.index._workspace_fingerprint_from_store()
        configuration = {
            "max_depth": max_depth,
            "call_limit_per_symbol": call_limit_per_symbol,
            "ref_limit_per_symbol": ref_limit_per_symbol,
            "verification_max_depth": 3,
            "target_resolution": "exact-path-qualname",
            "call_resolution": "unambiguous-indexed-symbol-only",
            "refresh": refresh,
        }
        freshness_fields = self.reads.freshness_fields()
        freshness_state = (
            "current" if refresh else _freshness(freshness_fields.get("stale"))
        )
        semantic = {
            "schema": STRUCTURAL_LOCALITY_SCHEMA,
            "provider": "hashmarks",
            "provider_version": __version__,
            "provider_implementation_identity": native_producer_implementation_identity(),
            "repository_identity": repository_identity,
            "source_identity": target_node["symbol_source_identity"],
            "measurement_configuration_identity": locality_identity(configuration),
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
                    locality_coordinate(item["line"] or 0),
                    str(item["target_text"]),
                ),
            ),
            "unresolved_calls": sorted(
                unresolved_calls,
                key=lambda item: (
                    str(item.get("source_symbol_id") or ""),
                    locality_coordinate(item.get("line") or 0),
                    str(item.get("target_text") or item.get("reason") or ""),
                ),
            ),
            "external_or_unindexed_calls": sorted(
                external_or_unindexed_calls,
                key=lambda item: (
                    str(item.get("source_symbol_id") or ""),
                    locality_coordinate(item.get("line") or 0),
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
        # Preserve unavailable and stale provider coverage without making it a
        # repository-negative relationship claim.
        semantic.update(self._scip_direct_relationships(target_row, target_node))
        semantic["resource_lifecycle"] = locality_lifecycle(
            self, ordered_nodes, max_depth, call_limit_per_symbol, ref_limit_per_symbol
        )
        return {**semantic, "evidence_identity": locality_identity(semantic)}

    @operation_response("structural")
    @decision_scoped
    def search(
        self, pattern: str, *, language: str | None = None, limit: int = 100
    ) -> dict[str, object]:
        """Syntax-aware search through an optional local ast-grep authority."""
        self.reads.ready()
        raw, warnings = self.search_provider.search(
            self.workspace, pattern, language=language, limit=max(limit * 4, limit)
        )
        matches: list[dict[str, object]] = []
        for row in raw:
            raw_path = row.get("file")
            if not raw_path:
                continue
            try:
                rel = normalize_relative_path(
                    str(raw_path).replace("\\", "/"), allow_root=False
                )
            except ValueError:
                continue
            mapped = self.reads.file_row(rel)
            if mapped is None:
                continue
            visibility = EvidenceVisibility(str(mapped["evidence_visibility"]))
            # ast-grep's match text is implementation content, so outline-only
            # files are intentionally not disclosed by this operation.
            if visibility is not EvidenceVisibility.SOURCE:
                continue
            range_value = row.get("range") if isinstance(row.get("range"), dict) else {}
            start_value = (
                range_value.get("start") if isinstance(range_value, dict) else {}
            )
            end_value = range_value.get("end") if isinstance(range_value, dict) else {}
            matches.append(
                {
                    "path": rel,
                    "text": str(row.get("text") or ""),
                    "language": row.get("language"),
                    "range": [
                        int((start_value or {}).get("line", 0)) + 1,
                        int((end_value or {}).get("line", 0)) + 1,
                    ],
                    "producer": "ast-grep",
                }
            )
            if len(matches) >= limit:
                break
        return {
            "schema": operation_schema("structural"),
            **self.reads.freshness_fields(),
            "pattern": pattern,
            "available": self.search_provider.available,
            "provider": self.search_provider.status().as_dict(),
            "matches": matches,
            "warnings": list(warnings),
        }

    def _locality_verification_paths(
        self, target: Mapping[str, object], node: Mapping[str, object]
    ) -> list[str]:
        """Add qualified indexed test callers to existing bounded impact evidence."""
        affected = cast(
            "Sequence[str]",
            self.relationships.tests(str(target["path"]), max_depth=3).get("tests", []),
        )
        callers = cast("Sequence[Mapping[str, object]]", node["exact_callers"])
        direct = {str(row["path"]) for row in callers if is_test_path(str(row["path"]))}
        return sorted(set(map(str, affected)) | direct)


def _candidate_search_contract(complete: bool) -> dict[str, object]:
    return {
        "completeness": "complete" if complete else "incomplete",
        "truncation": "complete" if complete else "truncated",
        "negative_evidence_admissible": complete,
        "uniqueness_admissible": complete,
    }


def _locality_edge_record(
    source_symbol_id: str,
    edge: Mapping[str, object],
    resolved: Mapping[str, object] | None,
    candidates: list[str],
    *,
    candidate_search_complete: bool,
) -> dict[str, object]:
    return {
        "source_symbol_id": source_symbol_id,
        "path": str(edge.get("path") or ""),
        "line": edge.get("line"),
        "target_text": str(edge.get("target") or ""),
        "confidence": str(edge.get("confidence") or ""),
        "resolved_symbol_id": None if resolved is None else _symbol_id(resolved),
        "candidate_symbol_ids": candidates,
        "candidate_search": _candidate_search_contract(candidate_search_complete),
    }


def _locality_node_sort_key(item: LocalityNode) -> tuple[int, str, int, str]:
    return (
        item["navigation_depth"],
        item["path"],
        item["lines"][0],
        item["qualname"],
    )
