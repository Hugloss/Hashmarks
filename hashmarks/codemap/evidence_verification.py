from __future__ import annotations

import ast
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.native_vitest import local_vitest
from hashmarks.paths import normalize_relative_path
from hashmarks.python_ast_cache import read_python_ast
from hashmarks.verification_selection import (
    VerificationSelectionEnvelopeState,
    downstream_consumption_contract,
    verification_membership_from_selection,
    verification_selection_envelope,
)

from .model import EvidenceVisibility
from .query_primitives import _TASK_STOPWORDS, _query_terms
from .repository_domains import RepositoryDomain, classify_repository_path
from .repository_index_store import git_base_identity

if TYPE_CHECKING:
    from .engine import CodeMap


@dataclass(frozen=True)
class _VerificationSelectionState:
    generation: int
    identity_generation: int | None
    stale: bool
    verify: Mapping[str, object] | None
    action: Mapping[str, object]
    verification_digest: str


@dataclass
class _VerificationRelevanceState:
    current_path: str
    edit_path: str
    generic_parts: set[str]
    edit_parts: set[str]
    task_terms: set[str]
    canonical_rank: dict[str, int]
    candidate_paths: set[str]
    refs_by_path: dict[str, set[str]]
    indirect_refs_by_path: dict[str, set[str]]
    indirect_via_paths: dict[str, set[str]]
    source_ref_paths: set[str]
    unresolved_import_identity_paths: set[str]


@dataclass(frozen=True)
class _VerificationReferenceIndex:
    bindings: tuple[tuple[str, str, str | None], ...]
    reachable_names: frozenset[str]
    reachable_attributes: frozenset[str]


class _VerificationReferenceIndexVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.guard: str | None = None
        self.bindings: list[tuple[str, str, str | None]] = []
        self.reachable_names: set[str] = set()
        self.reachable_attributes: set[str] = set()

    @staticmethod
    def _guard_kind(test: ast.expr) -> str | None:
        if isinstance(test, ast.Constant) and test.value is False:
            return "statically-dead"
        if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
            return "type-checking-only"
        if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
            return "type-checking-only"
        return None

    def visit_If(self, node: ast.If) -> None:
        previous = self.guard
        self.guard = previous or self._guard_kind(node.test)
        for child in node.body:
            self.visit(child)
        self.guard = previous
        for child in node.orelse:
            self.visit(child)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.bindings.extend(
            (alias.name, alias.asname or alias.name, self.guard) for alias in node.names
        )

    def visit_Name(self, node: ast.Name) -> None:
        if self.guard is None and isinstance(node.ctx, ast.Load):
            self.reachable_names.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if self.guard is None and isinstance(node.ctx, ast.Load):
            self.reachable_attributes.add(node.attr)
        self.generic_visit(node)


@lru_cache(maxsize=4096)
def _verification_reference_index(
    absolute_path: str,
    identity: tuple[int, int, int, int, int],
    tree: ast.Module,
) -> _VerificationReferenceIndex:
    """Project one already freshness-bound AST snapshot into reference evidence.

    ``tree`` is part of the process-local cache key so a new snapshot can never
    reuse a projection from an older source identity.  The caller obtains the
    snapshot through ``read_python_ast``; do not re-read the same file here.
    """
    visitor = _VerificationReferenceIndexVisitor()
    visitor.visit(tree)
    return _VerificationReferenceIndex(
        bindings=tuple(visitor.bindings),
        reachable_names=frozenset(visitor.reachable_names),
        reachable_attributes=frozenset(visitor.reachable_attributes),
    )


class VerificationMixin:
    """Repository-owned verification relevance, ownership, plan, and selection semantics."""

    @staticmethod
    def _verification_without_edit_owner(current_path: str) -> dict[str, object]:
        selected = None
        if current_path:
            selected = {
                "path": current_path,
                "selection_reason": "canonical-verification-without-edit-owner",
                "reference_symbols": [],
                "namespace_overlap": 0,
                "task_anchor_terms": [],
                "test_symbol": None,
            }
        return {
            "schema": "hashmarks.verification-relevance.v1",
            "selected": selected,
            "candidates": [selected] if selected else [],
            "selection_reason": "no-edit-owner",
            "selection_changed": False,
            "authority": "bounded-index-evidence-not-verification-execution",
            "secret_knowledge_used": False,
        }

    @staticmethod
    def _verification_generic_parts() -> set[str]:
        return {
            "src",
            "source",
            "lib",
            "app",
            "apps",
            "pkg",
            "packages",
            "test",
            "tests",
            "spec",
            "specs",
            "check",
            "checks",
            "unit",
            "integration",
            "e2e",
            "regression",
            "frontend",
            "backend",
            "python",
            "javascript",
            "typescript",
        }

    def _verification_state(
        self,
        task: str,
        edit_path: str,
        current_path: str,
        rows: Sequence[Mapping[str, object]],
    ) -> _VerificationRelevanceState:
        generic_parts = self._verification_generic_parts()
        edit_parts = {
            part.casefold()
            for part in Path(edit_path).parent.parts
            if part.casefold() not in generic_parts
        }
        task_terms = {
            term
            for term in _query_terms(task)
            if len(term) >= 3 and term not in _TASK_STOPWORDS
        }
        canonical_rank, candidate_paths = self._verification_candidate_seeds(
            rows, current_path
        )
        return _VerificationRelevanceState(
            current_path=current_path,
            edit_path=edit_path,
            generic_parts=generic_parts,
            edit_parts=edit_parts,
            task_terms=task_terms,
            canonical_rank=canonical_rank,
            candidate_paths=candidate_paths,
            refs_by_path={},
            indirect_refs_by_path={},
            indirect_via_paths={},
            source_ref_paths=set(),
            unresolved_import_identity_paths=set(),
        )

    @staticmethod
    def _verification_candidate_seeds(
        rows: Sequence[Mapping[str, object]],
        current_path: str,
    ) -> tuple[dict[str, int], set[str]]:
        canonical_rank: dict[str, int] = {}
        candidate_paths: set[str] = set()
        for row in rows:
            path = str(row.get("path") or "")
            if not path:
                continue
            rank = int(row.get("canonical_rank") or 10_000)
            canonical_rank[path] = min(rank, canonical_rank.get(path, rank))
            if RepositoryDomain.TEST in set(classify_repository_path(path)):
                candidate_paths.add(path)
        if current_path:
            candidate_paths.add(current_path)
        return canonical_rank, candidate_paths

    def _verification_edit_symbols(
        self,
        edit_path: str,
        edit: Mapping[str, object] | None,
    ) -> list[str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        selected_symbols: list[str] = []
        if isinstance(edit, Mapping):
            self._append_verification_symbol_names(selected_symbols, edit)
        if selected_symbols:
            return selected_symbols

        file_symbols: list[str] = []
        for symbol in self._session_symbols_for_path(edit_path)[:32]:
            self._append_verification_symbol_names(file_symbols, symbol)
        return file_symbols

    @staticmethod
    def _append_verification_symbol_names(
        symbol_names: list[str],
        row: Mapping[str, object],
    ) -> None:
        for key in ("name", "qualname"):
            value = str(row.get(key) or "")
            if value and value not in symbol_names:
                symbol_names.append(value)

    @staticmethod
    def _verification_ref_visible(ref: Mapping[str, object]) -> bool:
        try:
            visibility = EvidenceVisibility(
                str(ref.get("evidence_visibility") or EvidenceVisibility.DENY.value)
            )
        except ValueError:
            return False
        return visibility is not EvidenceVisibility.DENY

    def _verification_preload_import_resolution(
        self,
        direct_symbol_refs: Mapping[str, Sequence[Mapping[str, object]]],
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        import_refs = [
            ref
            for refs in direct_symbol_refs.values()
            for ref in refs
            if str(ref.get("kind") or "") == "import"
        ]
        import_source_paths = {
            str(ref.get("path") or "")
            for ref in import_refs
            if str(ref.get("path") or "")
        }
        self._session_file_rows(import_source_paths)
        module_prefetch: set[str] = set()
        for ref in import_refs:
            ref_path = str(ref.get("path") or "")
            target = str(ref.get("target") or "")
            if not ref_path or not target:
                continue
            ref_row = self._session_file_row(ref_path)
            if ref_row is not None and str(ref_row.get("language") or "") == "python":
                module_prefetch.update(
                    self._python_import_module_candidates(ref_path, target)
                )
        self._session_preload_module_paths(module_prefetch)

    def _verification_relative_import_paths(
        self,
        ref_path: str,
        target: str,
    ) -> set[str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not ref_path.endswith(".py") or not target.startswith("."):
            return set()
        leading = len(target) - len(target.lstrip("."))
        suffix = target[leading:]
        source_parts = list(Path(ref_path).with_suffix("").parts[:-1])
        keep = max(0, len(source_parts) - max(0, leading - 1))
        absolute_target = ".".join(source_parts[:keep] + ([suffix] if suffix else []))
        return (
            self._resolve_import_paths(ref_path, absolute_target)
            if absolute_target
            else set()
        )

    def _verification_resolved_import_paths(
        self, state: _VerificationRelevanceState, ref_path: str, target: str
    ) -> set[str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        resolved_paths, unresolved_identity = self._resolve_import_owner_evidence(
            ref_path, target
        )
        if unresolved_identity and RepositoryDomain.TEST in set(
            classify_repository_path(ref_path)
        ):
            state.unresolved_import_identity_paths.add(ref_path)
        if not resolved_paths:
            resolved_paths = self._verification_relative_import_paths(ref_path, target)
        return set(resolved_paths)

    def _verification_exact_import_paths(
        self,
        state: _VerificationRelevanceState,
        symbol_refs: Sequence[Mapping[str, object]],
    ) -> tuple[set[str], bool]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        exact_import_paths: set[str] = set()
        import_resolution_available = False
        for ref in symbol_refs:
            if str(ref.get("kind") or "") != "import":
                continue
            ref_path = str(ref.get("path") or "")
            target = str(ref.get("target") or "")
            if not ref_path or not target:
                continue
            resolved_paths = self._verification_resolved_import_paths(
                state, ref_path, target
            )
            if resolved_paths:
                import_resolution_available = True
            if state.edit_path in resolved_paths:
                exact_import_paths.add(ref_path)
        return exact_import_paths, import_resolution_available

    def _verification_collect_direct_symbol_refs(
        self,
        state: _VerificationRelevanceState,
        symbol: str,
        symbol_refs: Sequence[Mapping[str, object]],
    ) -> None:
        short = symbol.rsplit(".", 1)[-1]
        exact_import_paths, resolution_available = (
            self._verification_exact_import_paths(state, symbol_refs)
        )
        for ref in symbol_refs:
            path = str(ref.get("path") or "")
            if not path or not self._verification_ref_visible(ref):
                continue
            short_match = str(ref.get("target_short") or "") == short
            exact_reference = (
                path in exact_import_paths if resolution_available else short_match
            )
            if not short_match or not exact_reference:
                if RepositoryDomain.TEST in set(classify_repository_path(path)):
                    state.candidate_paths.add(path)
                continue
            domains = set(classify_repository_path(path))
            if RepositoryDomain.TEST in domains:
                state.candidate_paths.add(path)
                state.refs_by_path.setdefault(path, set()).add(short)
            elif RepositoryDomain.SOURCE in domains:
                state.source_ref_paths.add(path)

    def _verification_collect_direct_references(
        self,
        state: _VerificationRelevanceState,
        symbol_names: Sequence[str],
    ) -> None:
        # Explicit scale bound: 16 edit symbols × 1024 reverse refs.
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        direct_symbol_refs = self._session_refs_many(
            symbol_names[:16], limit_per_target=1024
        )

        # A repository-wide same-short-name prefix can hide the qualified
        # reference to the current edit once more than 1,024 unrelated refs sort
        # ahead of it.  Supplement the prefix with owner-targeted candidates,
        # then keep the same total per-symbol safety bound.  These rows are still
        # candidates: qualified import resolution below remains authoritative.
        edit_row = self._session_file_row(state.edit_path)
        edit_module = "" if edit_row is None else str(edit_row.get("module_name") or "")
        if edit_module:
            for symbol in symbol_names[:16]:
                short = symbol.rsplit(".", 1)[-1]
                suffix = f"{edit_module}.{short}"
                targeted = self.store.refs_matching_target_suffix(
                    short, suffix, limit=1024
                )
                existing = list(direct_symbol_refs.get(symbol, ()))
                merged: list[Mapping[str, object]] = []
                seen: set[tuple[str, int, str, str]] = set()
                for ref in [*targeted, *existing]:
                    key = (
                        str(ref.get("path") or ""),
                        int(ref.get("line") or 0),
                        str(ref.get("kind") or ""),
                        str(ref.get("target") or ""),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(ref)
                    if len(merged) >= 1024:
                        break
                direct_symbol_refs[symbol] = merged
        self._verification_preload_import_resolution(direct_symbol_refs)
        for symbol in symbol_names[:16]:
            self._verification_collect_direct_symbol_refs(
                state, symbol, list(direct_symbol_refs.get(symbol, ()))
            )

    def _verification_via_symbols(
        self,
        source_ref_paths: set[str],
    ) -> list[tuple[str, str, str]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        via_paths = sorted(source_ref_paths)[:64]
        via_symbols = self.store.symbols_for_paths_many(via_paths, limit_per_path=16)
        result: list[tuple[str, str, str]] = []
        for via_path in via_paths:
            for via_symbol in via_symbols.get(via_path, ()):
                for key in ("name", "qualname"):
                    symbol = str(via_symbol.get(key) or "")
                    if symbol:
                        result.append((via_path, symbol, symbol.rsplit(".", 1)[-1]))
        return result

    def _verification_collect_indirect_references(
        self,
        state: _VerificationRelevanceState,
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        via_symbol_sources = self._verification_via_symbols(state.source_ref_paths)
        indirect_ref_sets = self._session_refs_many(
            [symbol for _via_path, symbol, _short in via_symbol_sources],
            limit_per_target=256,
        )
        for via_path, symbol, short in via_symbol_sources:
            self._verification_collect_indirect_symbol_refs(
                state, via_path, short, indirect_ref_sets.get(symbol, ())
            )

    def _verification_collect_indirect_symbol_refs(
        self,
        state: _VerificationRelevanceState,
        via_path: str,
        short: str,
        refs: Sequence[Mapping[str, object]],
    ) -> None:
        for ref in refs:
            path = str(ref.get("path") or "")
            if not path or RepositoryDomain.TEST not in set(
                classify_repository_path(path)
            ):
                continue
            if not self._verification_ref_visible(ref):
                continue
            state.candidate_paths.add(path)
            if str(ref.get("target_short") or "") == short:
                state.indirect_refs_by_path.setdefault(path, set()).add(short)
                state.indirect_via_paths.setdefault(path, set()).add(via_path)

    @staticmethod
    def _verification_relevance_test_symbol(
        test_symbols: Sequence[Mapping[str, object]],
        task_terms: set[str],
    ) -> str | None:
        scored: list[tuple[int, str]] = []
        for symbol in test_symbols:
            name = str(symbol.get("name") or "")
            if not name.startswith("test_"):
                continue
            terms = set(_query_terms(name)) | set(
                _query_terms(str(symbol.get("qualname") or ""))
            )
            scored.append((len(task_terms.intersection(terms)), name))
        if not scored:
            return None
        scored.sort(key=lambda item: (-item[0], item[1]))
        if len(scored) > 1 and scored[0][0] <= scored[1][0]:
            return None
        return scored[0][1] if scored[0][0] > 0 or len(scored) == 1 else None

    @staticmethod
    def _verification_index_strength(
        index: _VerificationReferenceIndex, symbols: Sequence[str]
    ) -> dict[str, object]:
        symbol_set = set(symbols)
        bindings = [
            (bound_name, guard)
            for imported_name, bound_name, guard in index.bindings
            if imported_name in symbol_set
        ]
        if not bindings:
            attribute_use = bool(symbol_set.intersection(index.reachable_attributes))
            if attribute_use:
                return {
                    "syntactic_reference": True,
                    "reachable_import": True,
                    "reachable_symbol_use": True,
                    "reference_strength": "reachable-symbol-use",
                }
            return {"syntactic_reference": True, "reference_strength": "syntactic"}
        live_names = {name for name, guard in bindings if guard is None}
        guards = {guard for _name, guard in bindings if guard is not None}
        symbol_use = bool(
            live_names.intersection(index.reachable_names)
            or symbol_set.intersection(index.reachable_attributes)
        )
        if symbol_use:
            strength = "reachable-symbol-use"
        elif live_names:
            strength = "reachable-import"
        elif "type-checking-only" in guards:
            strength = "type-checking-only"
        else:
            strength = "statically-dead"
        return {
            "syntactic_reference": True,
            "reachable_import": bool(live_names),
            "reachable_symbol_use": symbol_use,
            "reference_strength": strength,
        }

    def _verification_reference_strength(
        self, path: str, symbols: Sequence[str]
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not path.endswith(".py") or not symbols:
            strength = "syntactic" if symbols else "none"
            return {
                "syntactic_reference": bool(symbols),
                "reference_strength": strength,
            }
        try:
            snapshot = read_python_ast(self.workspace / path)
            index = _verification_reference_index(
                os.path.abspath(os.fspath(self.workspace / path)),
                snapshot.identity,
                snapshot.tree,
            )
        except (OSError, SyntaxError):
            return {"syntactic_reference": True, "reference_strength": "syntactic"}
        return self._verification_index_strength(index, symbols)

    def _verification_candidate_row(
        self,
        state: _VerificationRelevanceState,
        path: str,
        test_symbols: Sequence[Mapping[str, object]],
        *,
        pytest_declared: bool | None = None,
    ) -> dict[str, object]:
        path_parts = {
            part.casefold()
            for part in Path(path).parent.parts
            if part.casefold() not in state.generic_parts
        }
        namespace_overlap = sorted(state.edit_parts.intersection(path_parts))
        evidence_terms = set(_query_terms(path.replace("/", " ")))
        for symbol in test_symbols:
            evidence_terms.update(_query_terms(str(symbol.get("name") or "")))
            evidence_terms.update(_query_terms(str(symbol.get("qualname") or "")))
        anchor_terms = sorted(state.task_terms.intersection(evidence_terms))
        test_symbol = self._verification_relevance_test_symbol(
            test_symbols, state.task_terms
        )
        direct_symbols = sorted(state.refs_by_path.get(path, set()))
        indirect_symbols = sorted(state.indirect_refs_by_path.get(path, set()))
        reference = self._verification_reference_strength(path, direct_symbols)
        direct_reference = reference.get("reference_strength") == "reachable-symbol-use"
        return {
            "path": path,
            **reference,
            "direct_reference": direct_reference,
            "indirect_reference": bool(indirect_symbols),
            "reference_symbols": direct_symbols,
            "indirect_reference_symbols": indirect_symbols,
            "indirect_via_paths": sorted(state.indirect_via_paths.get(path, set())),
            "namespace_overlap": len(namespace_overlap),
            "namespace_terms": namespace_overlap,
            "task_anchor_count": len(anchor_terms),
            "task_anchor_terms": anchor_terms,
            "canonical_rank": state.canonical_rank.get(path),
            "test_symbol": test_symbol,
            "runner_available": bool(
                self._python_verification_plan(
                    path, test_symbol, None, pytest_declared=pytest_declared
                ).get("available")
                if Path(path).suffix.lower() == ".py" and pytest_declared is not None
                else self.verification_plan(path, symbol=test_symbol).get("available")
            ),
        }

    def _verification_candidates(
        self,
        state: _VerificationRelevanceState,
    ) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        paths = sorted(state.candidate_paths)
        candidate_symbols = self.store.symbols_for_paths_many(paths, limit_per_path=64)
        result: list[dict[str, object]] = []
        pytest_declared = (
            self._pytest_declared()
            if any(Path(path).suffix.lower() == ".py" for path in paths)
            else None
        )
        for path in paths:
            if RepositoryDomain.TEST not in set(classify_repository_path(path)):
                continue
            result.append(
                self._verification_candidate_row(
                    state,
                    path,
                    candidate_symbols.get(path, ()),
                    pytest_declared=pytest_declared,
                )
            )
        result.sort(key=self._verification_candidate_score, reverse=True)
        return result

    @staticmethod
    def _verification_candidate_score(
        row: Mapping[str, object],
    ) -> tuple[int, int, int, int, str]:
        rank = row.get("canonical_rank")
        reference_strength = 0
        if bool(row.get("direct_reference")):
            reference_strength = 2
        elif bool(row.get("indirect_reference")):
            reference_strength = 1
        canonical = int(rank) if isinstance(rank, int) else 10_000
        return (
            reference_strength,
            int(row.get("namespace_overlap") or 0),
            int(row.get("task_anchor_count") or 0),
            -canonical,
            str(row.get("path") or ""),
        )

    @classmethod
    def _verification_select_candidate(
        cls,
        candidates: Sequence[dict[str, object]],
        current_path: str,
    ) -> tuple[dict[str, object] | None, str]:
        selected = next(
            (row for row in candidates if str(row.get("path") or "") == current_path),
            None,
        )
        reason = "canonical-verification"
        if not candidates:
            return selected, reason
        best = candidates[0]
        reference_candidates = [
            row for row in candidates if cls._verification_candidate_score(row)[0] > 0
        ]
        unique_reference = len(reference_candidates) == 1 and (
            selected is None or cls._verification_candidate_score(selected)[0] == 0
        )
        if cls._verification_best_can_replace(
            best, selected, unique_reference, current_path
        ):
            reason = (
                "unique-exact-reference-plus-namespace-locality"
                if bool(best.get("direct_reference"))
                else "unique-bounded-indirect-reference-plus-namespace-locality"
            )
            return best, reason
        if selected is None:
            return best, "best-bounded-verification-evidence"
        return selected, reason

    @classmethod
    def _verification_best_can_replace(
        cls,
        best: Mapping[str, object],
        selected: Mapping[str, object] | None,
        unique_reference: bool,
        current_path: str,
    ) -> bool:
        best_score = cls._verification_candidate_score(best)
        if best_score[0] <= 0:
            return False
        if int(best.get("namespace_overlap") or 0) <= 0 and not unique_reference:
            return False
        if selected is None or str(best.get("path") or "") == current_path:
            return True
        return (
            best_score[:2] > cls._verification_candidate_score(selected)[:2]
            or unique_reference
        )

    @staticmethod
    def _verification_relevance_result(
        state: _VerificationRelevanceState,
        candidates: Sequence[dict[str, object]],
        selected_row: Mapping[str, object] | None,
        selection_reason: str,
        limit: int,
    ) -> dict[str, object]:
        selected = (
            None
            if selected_row is None
            else {**selected_row, "selection_reason": selection_reason}
        )
        identity_ambiguous = bool(state.unresolved_import_identity_paths) and not bool(
            state.refs_by_path
        )
        return {
            "schema": "hashmarks.verification-relevance.v1",
            "selected": selected,
            "candidates": list(candidates[:limit]),
            "candidate_count": len(candidates),
            "selection_reason": selection_reason
            if selected is not None
            else "no-verification-candidate",
            "selection_changed": bool(
                selected is not None
                and state.current_path
                and str(selected.get("path")) != state.current_path
            ),
            "current_canonical_verify": state.current_path or None,
            "qualified_identity_ambiguous": identity_ambiguous,
            "unresolved_import_identity_paths": (
                sorted(state.unresolved_import_identity_paths)[:limit]
                if identity_ambiguous
                else []
            ),
            "bounds": {
                "returned_candidates": limit,
                "reverse_refs_per_symbol": 1024,
                "edit_symbols": 16,
                "indirect_source_paths": 64,
                "indirect_symbols_per_source": 16,
                "indirect_reverse_refs_per_symbol": 256,
            },
            "authority": "bounded-index-evidence-not-verification-execution",
            "secret_knowledge_used": False,
        }

    def _verification_relevance(
        self,
        task: str,
        *,
        edit: Mapping[str, object] | None,
        current_verify: Mapping[str, object] | None,
        rows: Sequence[Mapping[str, object]],
        limit: int = 8,
    ) -> dict[str, object]:
        """Rank bounded verification surfaces around an already-selected edit owner."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        limit = min(int(limit), 16)
        current_path = (
            str(current_verify.get("path") or "")
            if isinstance(current_verify, Mapping)
            else ""
        )
        edit_path = str(edit.get("path") or "") if isinstance(edit, Mapping) else ""
        if not edit_path:
            return self._verification_without_edit_owner(current_path)

        state = self._verification_state(task, edit_path, current_path, rows)
        symbol_names = self._verification_edit_symbols(edit_path, edit)
        self._verification_collect_direct_references(state, symbol_names)
        self._verification_collect_indirect_references(state)
        candidates = self._verification_candidates(state)
        selected, reason = self._verification_select_candidate(candidates, current_path)
        return self._verification_relevance_result(
            state, candidates, selected, reason, limit
        )

    def verification_relevance(
        self,
        task: str,
        *,
        limit: int = 20,
        candidate_limit: int = 8,
    ) -> dict[str, object]:
        """Return the task's bounded verification relevance evidence."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        action = self.task_action_map(task, limit=limit)
        relevance = action.get("verification_relevance")
        if not isinstance(relevance, dict):
            raise RuntimeError("task action map did not produce verification relevance")
        if candidate_limit < 1:
            raise ValueError("candidate_limit must be >= 1")
        result = dict(relevance)
        candidates = relevance.get("candidates")
        if isinstance(candidates, list):
            result["candidates"] = candidates[: min(int(candidate_limit), 16)]
        return result

    @staticmethod
    def _verification_edit_paths(action: dict[str, object]) -> list[str]:
        edit = action.get("edit")
        if not isinstance(edit, dict):
            return []
        path = edit.get("path")
        return [str(path)] if isinstance(path, str) else []

    @staticmethod
    def _authority_rows(
        authority: dict[str, object] | None,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        if not isinstance(authority, dict):
            return [], []
        nodes = authority.get("nodes")
        edges = authority.get("edges")
        node_rows = (
            [row for row in nodes if isinstance(row, dict)]
            if isinstance(nodes, list)
            else []
        )
        edge_rows = (
            [row for row in edges if isinstance(row, dict)]
            if isinstance(edges, list)
            else []
        )
        return node_rows, edge_rows

    @staticmethod
    def _authority_node_ids(path: str, nodes: list[dict[str, object]]) -> set[str]:
        file_id = f"file:{path}"
        return {
            str(row["id"])
            for row in nodes
            if isinstance(row.get("id"), str)
            and (row.get("path") == path or row.get("id") == file_id)
        }

    @staticmethod
    def _authority_relations(
        path: str, edges: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        file_id = f"file:{path}"
        return [
            dict(row)
            for row in edges
            if row.get("source") == file_id or row.get("target") == file_id
        ]

    @staticmethod
    def _relation_node_ids(relations: list[dict[str, object]]) -> set[str]:
        ids: set[str] = set()
        for row in relations:
            for value in (row.get("source"), row.get("target")):
                if isinstance(value, str):
                    ids.add(value)
        return ids

    @classmethod
    def _authority_entry(
        cls,
        path: str,
        nodes: list[dict[str, object]],
        edges: list[dict[str, object]],
        ownership_resolution: object,
    ) -> dict[str, object]:
        relations = cls._authority_relations(path, edges)
        node_ids = cls._authority_node_ids(path, nodes) | cls._relation_node_ids(
            relations
        )
        entry: dict[str, object] = {
            "path": path,
            "authority_node_ids": sorted(node_ids),
            "authority_relations": sorted(
                relations,
                key=lambda row: (
                    str(row.get("source") or ""),
                    str(row.get("target") or ""),
                    str(row.get("relation") or ""),
                ),
            ),
        }
        if (
            isinstance(ownership_resolution, dict)
            and ownership_resolution.get("path") == path
        ):
            entry["ownership_resolution"] = dict(ownership_resolution)
        return entry

    def _edit_authorities(
        self,
        edit_paths: list[str],
        authority: dict[str, object] | None,
        ownership_resolution: object,
    ) -> list[dict[str, object]]:
        nodes, edges = self._authority_rows(authority)
        return [
            self._authority_entry(path, nodes, edges, ownership_resolution)
            for path in edit_paths
        ]

    @staticmethod
    def _coverage_for_candidate(
        item: dict[str, object], edit_paths: list[str]
    ) -> tuple[list[str], str | None]:
        if not edit_paths:
            return [], None
        if bool(item.get("direct_reference")):
            return list(edit_paths), "direct-reference"
        if bool(item.get("indirect_reference")):
            return list(edit_paths), "bounded-indirect-reference"
        return [], None

    def _verification_owner_row(
        self, item: dict[str, object], edit_paths: list[str]
    ) -> dict[str, object] | None:
        path = item.get("path")
        if not isinstance(path, str):
            return None
        coverage, evidence = self._coverage_for_candidate(item, edit_paths)
        return {
            "path": path,
            "score": item.get("score"),
            "reason": item.get("reason"),
            "plan": self.verification_plan(
                path, symbol=item.get("name"), qualname=item.get("qualname")
            ),
            "covers_edit_candidates": coverage,
            "coverage_evidence": evidence,
        }

    def _verification_owner_rows(
        self, relevance: dict[str, object], edit_paths: list[str]
    ) -> tuple[list[dict[str, object]], int]:
        candidates = relevance.get("candidates")
        if not isinstance(candidates, list):
            return [], 0
        rows = [
            row
            for item in candidates
            if isinstance(item, dict)
            and (row := self._verification_owner_row(item, edit_paths)) is not None
        ]
        links = sum(len(row.get("covers_edit_candidates", [])) for row in rows)
        return rows, links

    @staticmethod
    def _linked_edit_paths(verifiers: list[dict[str, object]]) -> set[str]:
        return {
            covered
            for verifier in verifiers
            for covered in verifier.get("covers_edit_candidates", [])
            if isinstance(covered, str)
        }

    def verification_ownership_graph(
        self, task: str, *, limit: int = 20, candidate_limit: int = 8
    ) -> dict[str, object]:
        """Expose verification owners and their evidence-backed edit-authority links."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        relevance = self.verification_relevance(
            task, limit=limit, candidate_limit=candidate_limit
        )
        action = self.task_action_map(task, limit=limit)
        edit_paths = sorted(set(self._verification_edit_paths(action)))
        authority = self.repository_ownership_graph(edit_paths) if edit_paths else None
        edit_authorities = self._edit_authorities(
            edit_paths, authority, action.get("ownership_resolution")
        )
        verifiers, verification_links = self._verification_owner_rows(
            relevance, edit_paths
        )
        linked_paths = self._linked_edit_paths(verifiers)
        selected = relevance.get("selected")
        generation, identity_generation, stale = self._generation_status()
        return {
            "schema": "hashmarks.verification-ownership.v2",
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "task": task,
            "edit_candidates": edit_paths,
            "edit_authorities": edit_authorities,
            "verification_owners": verifiers,
            "summary": {
                "edit_candidates": len(edit_paths),
                "edit_authorities": len(edit_authorities),
                "verification_owners": len(verifiers),
                "verification_links": verification_links,
                "unlinked_edit_candidates": len(set(edit_paths) - linked_paths),
                "unowned": not bool(verifiers),
                "ambiguous": len(verifiers) > 1 and not bool(selected),
            },
            "boundary": "verification/authority repository evidence only; Hashmarks does not execute or certify verification",
        }

    def _pytest_declared(self) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        pyproject = self.workspace / "pyproject.toml"
        if not pyproject.is_file():
            return False
        try:
            return "[tool.pytest." in pyproject.read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            return False

    @staticmethod
    def _verification_test_symbol(
        symbol: str | None, qualname: str | None
    ) -> str | None:
        if isinstance(symbol, str) and symbol.startswith("test_"):
            return symbol
        if not isinstance(qualname, str):
            return None
        root_symbol = qualname.split(".", 1)[0]
        return root_symbol if root_symbol.startswith("test_") else None

    def _python_verification_plan(
        self,
        rel: str,
        symbol: str | None,
        qualname: str | None,
        *,
        pytest_declared: bool | None = None,
    ) -> dict[str, object]:
        if pytest_declared is None:
            pytest_declared = self._pytest_declared()
        test_symbol = self._verification_test_symbol(symbol, qualname)
        target_arg = f"{rel}::{test_symbol}" if test_symbol else rel
        return {
            "schema": "hashmarks.verification-plan.v1",
            "path": rel,
            "available": True,
            "runner": "pytest",
            "argv": ["python", "-m", "pytest", "-q", target_arg],
            "working_directory": ".",
            "confidence": "high" if pytest_declared else "medium",
            "evidence": "pyproject-pytest-config"
            if pytest_declared
            else "python-test-domain",
            "scope": "test-node" if test_symbol else "test-file",
            "test_symbol": test_symbol,
        }

    def _go_verification_plan(self, rel: str, target: Path) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if (
            not target.name.endswith("_test.go")
            or not (self.workspace / "go.mod").is_file()
        ):
            return None
        package = target.parent.as_posix()
        package_arg = "." if package == "." else f"./{package}"
        return {
            "schema": "hashmarks.verification-plan.v1",
            "path": rel,
            "available": True,
            "runner": "go-test",
            "argv": ["go", "test", package_arg],
            "working_directory": ".",
            "confidence": "high",
            "evidence": "go-mod-plus-test-file",
        }

    @staticmethod
    def _vitest_runner(workspace: Path) -> str | None:
        vitest = local_vitest(workspace)
        if vitest is None:
            return None
        try:
            return vitest.relative_to(workspace).as_posix()
        except ValueError:
            return str(vitest)

    def _javascript_verification_plan(
        self, rel: str, target: Path
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        runner = self._vitest_runner(self.workspace)
        if runner is not None:
            return {
                "schema": "hashmarks.verification-plan.v1",
                "path": rel,
                "available": True,
                "runner": "vitest",
                "argv": [runner, "run", rel],
                "working_directory": ".",
                "confidence": "high",
                "evidence": "local-vitest-plus-test-file",
                "scope": "test-file",
            }
        if target.suffix.lower() not in {".js", ".mjs", ".cjs"}:
            return None
        try:
            source = (self.workspace / rel).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            source = ""
        if "node:test" not in source and "node:test/" not in source:
            return None
        return {
            "schema": "hashmarks.verification-plan.v1",
            "path": rel,
            "available": True,
            "runner": "node-test",
            "argv": ["node", "--test", rel],
            "working_directory": ".",
            "confidence": "high",
            "evidence": "node-test-import-plus-test-file",
            "scope": "test-file",
        }

    def _typescript_verification_plan(
        self, rel: str, target: Path
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if target.suffix.lower() not in {".ts", ".tsx", ".mts", ".cts"}:
            return None
        if not (self.workspace / "tsconfig.json").is_file():
            return None
        return {
            "schema": "hashmarks.verification-plan.v1",
            "path": rel,
            "available": True,
            "runner": "typescript-compiler",
            "argv": ["tsc", "--noEmit", "-p", "tsconfig.json"],
            "working_directory": ".",
            "confidence": "medium",
            "evidence": "tsconfig-plus-typescript-test-file",
            "scope": "typescript-project",
        }

    def _polyglot_verification_plan(self, rel: str, target: Path) -> dict[str, object]:
        plan = self._go_verification_plan(rel, target)
        if plan is not None:
            return plan
        js_exts = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
        if target.suffix.lower() in js_exts:
            plan = self._javascript_verification_plan(rel, target)
            if plan is not None:
                return plan
            plan = self._typescript_verification_plan(rel, target)
            if plan is not None:
                return plan
        return {
            "schema": "hashmarks.verification-plan.v1",
            "path": rel,
            "available": False,
            "reason": "unsupported-test-runner",
        }

    def verification_plan(
        self, path: str, *, symbol: str | None = None, qualname: str | None = None
    ) -> dict[str, object]:
        """Derive a bounded argv for a known verification surface."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rel = normalize_relative_path(path, allow_root=False)
        if not self._path_admitted_for_analysis(rel):
            return {
                "schema": "hashmarks.verification-plan.v1",
                "path": rel,
                "available": False,
                "reason": "path-outside-analysis-scope",
            }
        target = Path(rel)
        domains = set(classify_repository_path(rel))
        if RepositoryDomain.TEST not in domains:
            return {
                "schema": "hashmarks.verification-plan.v1",
                "path": rel,
                "available": False,
                "reason": "path-is-not-test-domain",
            }
        if target.suffix.lower() == ".py":
            return self._python_verification_plan(rel, symbol, qualname)
        return self._polyglot_verification_plan(rel, target)

    @staticmethod
    def _packet_digest(domain: str, payload: object) -> str:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(domain.encode("utf-8") + b"\0" + encoded).hexdigest()

    def _repository_packet_identity(self) -> str:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        generation = self.store.generation()
        cached = self._decision_repository_identity_cache
        if (
            self._decision_session_depth > 0
            and cached is not None
            and cached[0] == generation
        ):
            return cached[1]
        base = git_base_identity(self.workspace)
        if base:
            identity = f"git-tree:{base}"
        else:
            path_digest = hashlib.sha256(os.fsencode(str(self.workspace))).hexdigest()
            identity = f"workspace:{path_digest}"
        if self._decision_session_depth > 0:
            self._decision_repository_identity_cache = (generation, identity)
        return identity

    def _source_packet_identity(
        self,
        *,
        generation: int,
        identity_generation: int | None,
        stale: bool | None,
    ) -> str:
        digest = self._packet_digest(
            "hashmarks.source-identity.v1",
            {
                "repository_identity": self._repository_packet_identity(),
                "codemap_generation": generation,
                "identity_generation": identity_generation,
                "stale": stale is not False,
            },
        )
        return f"sha256:{digest}"

    def _decision_evidence_receipt(
        self,
        task: str,
        action: dict[str, object],
        verification: Mapping[str, object],
    ) -> dict[str, object]:
        """Return one compact identity for the repository-owned decision evidence.

        The receipt is intentionally independent of worker projection size.  A
        full decision packet, action brief, and task-evidence packet generated from
        the same repository generation and action evidence therefore carry the
        same identity even when their visible context budgets differ.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        generation, identity_generation, stale = self._generation_status()

        def anchor(value: object) -> dict[str, object] | None:
            if not isinstance(value, Mapping) or not value.get("path"):
                return None
            row: dict[str, object] = {"path": str(value["path"])}
            for key in ("name", "qualname", "verification_test_symbol"):
                if value.get(key) is not None:
                    row[key] = str(value[key])
            return row

        ownership = (
            action.get("ownership_resolution")
            if isinstance(action.get("ownership_resolution"), Mapping)
            else {}
        )
        owner_path = (
            ownership.get("owner_path")
            if isinstance(ownership.get("owner_path"), list)
            else []
        )
        normalized_owner_path = [
            {
                "from": str(edge.get("from") or ""),
                "to": str(edge.get("to") or ""),
                "relation": str(edge.get("relation") or ""),
            }
            for edge in owner_path
            if isinstance(edge, Mapping)
        ]
        ambiguity = (
            action.get("ambiguity")
            if isinstance(action.get("ambiguity"), Mapping)
            else {}
        )
        payload: dict[str, object] = {
            "schema": "hashmarks.decision-evidence.v1",
            "repository_identity": self._repository_packet_identity(),
            "codemap_generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "task_identity": self._packet_digest("hashmarks.task.v1", {"task": task}),
            "edit": anchor(action.get("edit")),
            "verify": anchor(action.get("verify")),
            "contract": anchor(action.get("contract")),
            "ownership": {
                "selected": str(ownership.get("selected") or ""),
                "via": str(ownership.get("via") or ""),
                "owner_path": normalized_owner_path,
            },
            "ambiguity": {
                "ambiguous": bool(ambiguity.get("ambiguous")),
                "reason": str(ambiguity.get("reason") or ""),
            },
            "verification_plan_digest": self._packet_digest(
                "hashmarks.verification-plan.v1", verification
            ),
        }
        evidence_identity = self._packet_digest(
            "hashmarks.decision-evidence.v1", payload
        )
        return {
            "schema": "hashmarks.decision-evidence-receipt.v1",
            "evidence_identity": evidence_identity,
            "repository_identity": payload["repository_identity"],
            "task_identity": payload["task_identity"],
            "codemap_generation": generation,
            "stale": stale,
        }

    def _verification_selection_evidence_hashes(
        self,
        action: Mapping[str, object],
        verification_digest: str,
    ) -> dict[str, str]:
        return {
            "verification_plan": f"sha256:{verification_digest}",
            "verification_relevance": "sha256:"
            + self._packet_digest(
                "hashmarks.verification-relevance.v1",
                action.get("verification_relevance"),
            ),
            "ownership": "sha256:"
            + self._packet_digest(
                "hashmarks.ownership-resolution.v1",
                action.get("ownership_resolution"),
            ),
        }

    def _verification_selection_artifacts(
        self,
        state: _VerificationSelectionState,
    ) -> tuple[dict[str, object] | None, str, dict[str, object] | None]:
        membership = verification_membership_from_selection(state.verify)
        source_identity = self._source_packet_identity(
            generation=state.generation,
            identity_generation=state.identity_generation,
            stale=state.stale,
        )
        if membership is None:
            return None, source_identity, None
        owner_evidence = (
            state.action.get("ownership_resolution")
            if isinstance(state.action.get("ownership_resolution"), Mapping)
            else None
        )
        envelope = verification_selection_envelope(
            VerificationSelectionEnvelopeState(
                repository_identity=self._repository_packet_identity(),
                source_identity=source_identity,
                codemap_generation=state.generation,
                identity_generation=state.identity_generation,
                stale=state.stale,
                membership=membership,
                owner_evidence=owner_evidence,
                evidence_hashes=self._verification_selection_evidence_hashes(
                    state.action,
                    state.verification_digest,
                ),
            )
        )
        return membership, source_identity, envelope

    @staticmethod
    def _verification_selection_identity_fields(
        membership: Mapping[str, object] | None,
        source_identity: str,
        envelope: Mapping[str, object] | None,
    ) -> dict[str, object]:
        return {
            "source_identity": source_identity,
            "verification_membership_identity": (
                membership.get("membership_identity")
                if membership is not None
                else None
            ),
            "verification_selection_envelope_identity": (
                envelope.get("envelope_identity") if envelope is not None else None
            ),
            "verification_selection_producer_implementation_identity": (
                envelope.get("producer", {}).get("implementation_identity")
                if isinstance(envelope, Mapping)
                else None
            ),
        }

    def _task_decision_verification_plan(
        self,
        verify: Mapping[str, object] | None,
    ) -> dict[str, object]:
        if verify is None:
            return {
                "schema": "hashmarks.verification-plan.v1",
                "available": False,
                "reason": "no-verification-surface",
            }
        test_symbol = verify.get("verification_test_symbol")
        symbol = (
            str(test_symbol)
            if test_symbol is not None
            else str(verify.get("name"))
            if verify.get("name") is not None
            else None
        )
        qualname = (
            str(verify.get("qualname")) if verify.get("qualname") is not None else None
        )
        return self.verification_plan(
            str(verify["path"]),
            symbol=symbol,
            qualname=qualname,
        )

    @staticmethod
    def _downstream_verification_contract(
        selection_envelope: Mapping[str, object] | None,
    ) -> dict[str, object] | None:
        if selection_envelope is None:
            return None
        return downstream_consumption_contract(selection_envelope)
