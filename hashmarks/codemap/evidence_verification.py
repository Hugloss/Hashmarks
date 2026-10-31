from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias, cast

from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.python_ast_cache import read_python_ast

from .decision_session import ReadScope, ReadScopeOwner, decision_scoped
from .model import EvidenceVisibility
from .query_primitives import _TASK_STOPWORDS, _query_terms
from .repository_domains import RepositoryDomain, classify_repository_path
from .repository_observation import evidence_identity
from .task_evidence_contract import read_task_candidate
from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS
from .verification_explanation import VerificationExplanationMixin
from .verification_file_reads import VerificationFileReadsMixin
from .verification_membership import VerificationMembershipMixin
from .verification_ownership import VerificationOwnershipMixin
from .verification_plan import VerificationPlanMixin
from .verification_reference_syntax import (
    MAX_KEYWORD_IDENTIFIER_CHARS,
)
from .verification_reference_syntax import (
    VerificationReferenceIndex as _VerificationReferenceIndex,
)
from .verification_reference_syntax import (
    verification_reference_index as _verification_reference_index,
)
from .verification_relevance_model import (
    VerificationRequest,
    verification_without_edit_owner,
)

_LIMIT = VERIFICATION_RELEVANCE_DEFAULTS.limit
_CANDIDATES = VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit
VerificationKeywordObservations: TypeAlias = dict[
    tuple[ReadScope, str, tuple[str, ...]], dict[str, object]
]
if TYPE_CHECKING:
    from .decision_session import DecisionScope
    from .evidence_correlation import RepositoryCorrelation
    from .import_resolution import RepositoryImports
    from .query_router import NormalizedTaskQuery
    from .task_evidence_types import (
        VerificationRelevance,
    )


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
    file_read_references: dict[str, list[dict[str, object]]] = field(
        default_factory=dict
    )
    search_bound_reasons: set[str] = field(default_factory=set)
    reference_indexes: dict[str, _VerificationReferenceIndex | None] = field(
        default_factory=dict
    )
    # One observation only; copied endpoints replay the cached uncertainty too.
    import_owner_evidence: dict[tuple[str, str], tuple[frozenset[str], bool]] = field(
        default_factory=dict
    )
    unresolved_reference_identity_paths: set[str] = field(default_factory=set)
    unresolved_verifier_identity_paths: set[str] = field(default_factory=set)
    qualified_attribute_refs: dict[str, set[str]] = field(default_factory=dict)
    lexical_test_paths: tuple[str, ...] | None = None
    module_test_paths: tuple[str, ...] | None = None

    def record_unresolved_reference(self, path: str) -> None:
        """Keep caller uncertainty separate from uncertainty in verifier identity."""
        self.unresolved_reference_identity_paths.add(path)
        if RepositoryDomain.TEST in classify_repository_path(path):
            self.unresolved_verifier_identity_paths.add(path)

    @property
    def verifier_identity_ambiguous(self) -> bool:
        return bool(
            self.unresolved_import_identity_paths
            or self.unresolved_verifier_identity_paths
        )


class RepositoryVerification(
    VerificationMembershipMixin,
    VerificationPlanMixin,
    VerificationOwnershipMixin,
    VerificationExplanationMixin,
    VerificationFileReadsMixin,
    ReadScopeOwner,
):
    """Own source-qualified test relevance for supplied owner/candidate facts."""

    def __init__(
        self,
        imports: RepositoryImports,
        *,
        correlation: RepositoryCorrelation | None = None,
    ) -> None:
        self.source = source = imports.source
        self.imports = imports
        self.store = source.store
        self.files = source.files
        self.workspace = source.workspace
        if correlation is None:
            from .evidence_correlation import RepositoryCorrelation
            from .repository_evidence_bindings import RepositoryBindings

            correlation = RepositoryCorrelation(RepositoryBindings(source))
        if correlation.source is not source:
            raise ValueError(
                "verification and correlation must share their source owner"
            )
        self._collection_correlation = correlation

    @property
    def reads(self) -> DecisionScope:
        return self.source.reads

    def relationship_evidence(
        self,
        *,
        source: str,
        target: str,
        classification: str,
        relation_kind: str,
        provenance: str,
    ) -> dict[str, object]:
        """Describe an objective repository relationship without consumer policy."""
        if classification not in {"direct", "related", "unknown"}:
            raise ValueError("unsupported verification relationship classification")
        if not relation_kind.strip():
            raise ValueError("verification relationship kind must be nonblank")
        payload = {
            "source": source,
            "target": target,
            "classification": classification,
            "relation_kind": relation_kind,
            "provenance": provenance,
        }
        return {
            **payload,
            "evidence_identity": evidence_identity(
                "hashmarks.verification-relationship.v1", payload
            ),
            "authority": "repository-relationship-only",
            "execution_effect": "none",
        }

    def bounded_relevance(
        self, relevance: VerificationRelevance, candidate_limit: int
    ) -> VerificationRelevance:
        if candidate_limit < 1:
            raise ValueError("candidate_limit must be >= 1")
        result = relevance.copy()
        candidates = relevance.get("candidates")
        selected = relevance.get("selected")
        if isinstance(candidates, list):
            result["candidates"] = [
                read_task_candidate(row)
                for row in self._verification_bounded_candidates(
                    candidates,
                    selected if isinstance(selected, Mapping) else None,
                    min(int(candidate_limit), 16),
                )
            ]
        return result

    """Repository-owned verification relevance, ownership, plan, and selection semantics."""

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
        query: NormalizedTaskQuery,
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
        # Use the shared identifier vocabulary: two-letter components such as
        # ``db`` in ``db_type`` are evidence, just as they are in task retrieval.
        task_terms = {term for term in query.terms if term not in _TASK_STOPWORDS}
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
            search_bound_reasons=set(),
            reference_indexes={},
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
            rank = int(cast("int | str", row.get("canonical_rank") or 10_000))
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
    ) -> tuple[list[str], bool]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        selected_symbols: list[str] = []
        if isinstance(edit, Mapping):
            self._append_verification_symbol_names(selected_symbols, edit)
        if selected_symbols:
            return selected_symbols, True

        symbol_rows = self.reads.symbols_for_path(edit_path)
        # A file-level target has no selected declaration. Seed its bounded
        # reference search from module-level, ordinary identifiers before
        # private/nested implementation helpers. This is candidate ordering,
        # never proof of exports, call reachability or test sufficiency.
        symbol_rows = sorted(
            symbol_rows,
            key=lambda row: (
                "." in str(row.get("qualname") or ""),
                str(row.get("name") or "").startswith("_"),
                int(cast("int", row.get("start_line") or 0)),
                str(row.get("qualname") or ""),
            ),
        )
        file_symbols: list[str] = []
        for symbol in symbol_rows[:32]:
            self._append_verification_symbol_names(file_symbols, symbol)
        return file_symbols, len(symbol_rows) <= 32

    @staticmethod
    def _append_verification_symbol_names(
        symbol_names: list[str],
        row: Mapping[str, object],
    ) -> None:
        # refs_many already reads by short name. Retain the selected declaration's
        # scope while qualifying those candidates instead of deciding it again.
        value = str(row.get("qualname") or row.get("name") or "")
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
            self = cast("RepositoryVerification", self)
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
        self.reads.file_rows(import_source_paths)
        module_prefetch: set[str] = set()
        for ref in import_refs:
            ref_path = str(ref.get("path") or "")
            target = str(ref.get("target") or "")
            if not ref_path or not target:
                continue
            ref_row = self.reads.file_row(ref_path)
            if ref_row is not None and str(ref_row.get("language") or "") == "python":
                module_prefetch.update(
                    self.imports._python_import_module_candidates(ref_path, target)
                )
        self.reads.preload_module_paths(module_prefetch)

    def _verification_relative_import_paths(
        self,
        ref_path: str,
        target: str,
    ) -> set[str]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        if not ref_path.endswith(".py") or not target.startswith("."):
            return set()
        leading = len(target) - len(target.lstrip("."))
        suffix = target[leading:]
        source_parts = list(Path(ref_path).with_suffix("").parts[:-1])
        keep = max(0, len(source_parts) - max(0, leading - 1))
        absolute_target = ".".join(source_parts[:keep] + ([suffix] if suffix else []))
        return (
            set(self.imports._resolve_import_paths(ref_path, absolute_target))
            if absolute_target
            else set()
        )

    def _verification_resolved_import_paths(
        self, state: _VerificationRelevanceState, ref_path: str, target: str
    ) -> set[str]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        key = (ref_path, target)
        observed = state.import_owner_evidence.get(key)
        if observed is None:
            paths, unresolved = self.imports._resolve_import_owner_evidence(
                ref_path, target
            )
            if not paths and not unresolved:
                paths = sorted(
                    self._verification_relative_import_paths(ref_path, target)
                )
            observed = (frozenset() if unresolved else frozenset(paths), unresolved)
            state.import_owner_evidence[key] = observed
        resolved_paths, unresolved_identity = observed
        if unresolved_identity and RepositoryDomain.TEST in set(
            classify_repository_path(ref_path)
        ):
            state.unresolved_import_identity_paths.add(ref_path)
        if unresolved_identity:
            # The resolver's facade path is an observed import location, not
            # proof of the underlying exported symbol's owner.
            return set()
        return set(resolved_paths)

    def _verification_exact_import_paths(
        self,
        state: _VerificationRelevanceState,
        symbol_refs: Sequence[Mapping[str, object]],
    ) -> tuple[set[str], bool]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
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
            if resolved_paths or ref_path in state.unresolved_import_identity_paths:
                import_resolution_available = True
            if state.edit_path in resolved_paths:
                exact_import_paths.add(ref_path)
                index = self._verification_reference_index_for_path(state, ref_path)
                if (
                    RepositoryDomain.TEST in classify_repository_path(ref_path)
                    and index is not None
                    and (
                        index.star_import
                        or any(
                            imported == target and bound in index.bound_names
                            for imported, bound, _guard in index.module_bindings
                        )
                    )
                ):
                    state.record_unresolved_reference(ref_path)
        return exact_import_paths, import_resolution_available

    def _verification_reference_index_for_path(
        self,
        state: _VerificationRelevanceState | None,
        path: str,
    ) -> _VerificationReferenceIndex | None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        if state is not None and path in state.reference_indexes:
            return state.reference_indexes[path]
        try:
            snapshot = read_python_ast(self.workspace / path)
            index = _verification_reference_index(
                os.path.abspath(os.fspath(self.workspace / path)),
                snapshot.identity,
                snapshot.tree,
            )
        except (OSError, SyntaxError):
            index = None
        if state is not None:
            state.reference_indexes[path] = index
        return index

    def _verification_task_keyword_syntax(
        self,
        state: _VerificationRelevanceState,
        path: str,
        observations: VerificationKeywordObservations | None = None,
    ) -> dict[str, object]:
        """Observe multiword task matches in named call arguments, without binding."""
        if (
            not path.endswith(".py")
            or self.files.decide(path).evidence_visibility
            is not EvidenceVisibility.SOURCE
        ):
            return {}
        self.source.ensure_current(path)
        key = (
            (self.reads.scope, path, tuple(sorted(state.task_terms)))
            if self.reads.scope is not None
            else None
        )
        if observations is not None and key is not None and key in observations:
            return observations[key]
        member = self.reads.file_row(path)
        index = self._verification_reference_index_for_path(state, path)
        if member is None or index is None:
            return {}
        matches = []
        for name, line, end_line in index.keyword_arguments:
            terms = sorted(state.task_terms.intersection(_query_terms(name)))
            if len(terms) >= 2:
                matches.append(
                    {
                        "name": name,
                        "line": line,
                        "end_line": end_line,
                        "matched_task_terms": terms,
                    }
                )
        self.source.ensure_current(path)
        result: dict[str, object] = (
            {
                "task_keyword_syntax": {
                    "basis": "named-call-keyword-syntax-and-task-terms",
                    "source_revision": member["file_digest"],
                    "matches": matches[:16],
                    "observed_keywords": len(matches),
                    "omitted_keywords": max(0, len(matches) - 16),
                    "returned_bound": 16,
                    "identifier_chars_bound": MAX_KEYWORD_IDENTIFIER_CHARS,
                    "scope": "named keywords outside statically dead/type-only branches",
                    "runtime_binding": "not-established",
                    "verification_selection_authority": False,
                    "negative_evidence_admissible": False,
                }
            }
            if matches
            else {}
        )
        if observations is not None and key is not None:
            observations[key] = result
        return result

    def _verification_module_alias_reference_owner_match(
        self,
        state: _VerificationRelevanceState,
        ref_path: str,
        target: str,
        symbol: str,
    ) -> bool | None:
        self = cast("RepositoryVerification", self)
        index = (
            self._verification_reference_index_for_path(state, ref_path)
            if ref_path.endswith(".py") and "." in target
            else None
        )
        binding = None if index is None else index.imported_attribute(target)
        if binding is None:
            return None
        imported, suffix = binding
        module = (
            self.imports._python_relative_module_candidate(ref_path, imported)
            if imported.startswith(".")
            else imported
        )
        if suffix != symbol or not self.reads.module_paths(module):
            return None
        owners = self._verification_resolved_import_paths(
            state, ref_path, imported + "." + suffix
        )
        return state.edit_path in owners if owners else None

    def _verification_member_reference_owner_match(
        self,
        state: _VerificationRelevanceState,
        ref_path: str,
        target: str,
        symbol: str,
    ) -> bool | None:
        """Qualify an explicit imported member; instance receivers stay unknown."""
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        index = self._verification_reference_index_for_path(state, ref_path)
        binding = None if index is None else index.imported_attribute(target)
        if binding is None:
            return None
        imported, suffix = binding
        qualified = imported + "." + suffix
        if imported.startswith("."):
            qualified = self.imports._python_relative_module_candidate(
                ref_path, qualified
            )
        owners = self._verification_resolved_import_paths(state, ref_path, imported)
        if not owners:
            return None
        if state.edit_path not in owners:
            return False
        row = self.reads.file_row(state.edit_path)
        module = str(row.get("module_name") or "") if row is not None else ""
        return True if module and qualified == module + "." + symbol else None

    def _verification_reference_owner_match(
        self,
        state: _VerificationRelevanceState,
        symbol: str,
        ref: Mapping[str, object],
        imports: tuple[set[str], bool],
    ) -> bool:
        path, target = str(ref.get("path") or ""), str(ref.get("target") or "")
        if str(ref.get("target_short") or "") != symbol.rsplit(".", 1)[-1]:
            return False
        if "." in symbol and path.endswith(".py"):
            member = self._verification_member_reference_owner_match(
                state, path, target, symbol
            )
            if member is None:
                state.record_unresolved_reference(path)
            return member is True
        alias_owner = self._verification_module_alias_reference_owner_match(
            state, path, target, symbol
        )
        if path.endswith(".py") and "." in target and str(ref.get("kind")) != "import":
            if alias_owner is None:
                state.record_unresolved_reference(path)
            return alias_owner is True
        exact_import_paths, resolution_available = imports
        if path.endswith(".py") and not resolution_available:
            state.record_unresolved_reference(path)
            return False
        return (
            alias_owner
            if alias_owner is not None
            else path in exact_import_paths
            if resolution_available
            else True
        )

    def _verification_collect_direct_symbol_refs(
        self,
        state: _VerificationRelevanceState,
        symbol: str,
        symbol_refs: Sequence[Mapping[str, object]],
    ) -> None:
        short = symbol.rsplit(".", 1)[-1]
        imports = self._verification_exact_import_paths(state, symbol_refs)
        for ref in symbol_refs:
            path = str(ref.get("path") or "")
            if not path or not self._verification_ref_visible(ref):
                continue
            exact_reference = self._verification_reference_owner_match(
                state, symbol, ref, imports
            )
            exact_reference = exact_reference and (
                path not in state.unresolved_import_identity_paths
            )
            if (
                exact_reference
                and "." in str(ref.get("target") or "")
                and str(ref.get("kind")) != "import"
            ):
                state.qualified_attribute_refs.setdefault(path, set()).add(short)
            domains = set(classify_repository_path(path))
            if RepositoryDomain.TEST in domains:
                state.candidate_paths.add(path)
                if exact_reference:
                    state.refs_by_path.setdefault(path, set()).add(short)
            elif RepositoryDomain.SOURCE in domains and exact_reference:
                state.source_ref_paths.add(path)

    @staticmethod
    def _verification_ref_identity(
        ref: Mapping[str, object],
    ) -> tuple[str, int, str, str]:
        return (
            str(ref.get("path") or ""),
            int(cast("int | str", ref.get("line") or 0)),
            str(ref.get("kind") or ""),
            str(ref.get("target") or ""),
        )

    def _verification_bounded_direct_refs(
        self,
        state: _VerificationRelevanceState,
        selected_symbols: Sequence[str],
    ) -> dict[str, list[Mapping[str, object]]]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        raw = self.reads.refs_many(
            selected_symbols,
            limit_per_target=1025,
            preferred_paths=self._verification_test_paths(state)[:4096],
        )
        local_paths = self._verification_module_test_paths(state)
        local = (
            self.store.refs_many_for_paths(
                selected_symbols, local_paths, limit_per_target=1025
            )
            if local_paths
            else {}
        )
        bounded: dict[str, list[Mapping[str, object]]] = {}
        for symbol in selected_symbols:
            refs: list[Mapping[str, object]] = list(raw.get(symbol, ()))
            if len(refs) > 1024:
                state.search_bound_reasons.add("direct-reverse-ref-limit")
            scoped = list(local.get(symbol, ()))
            if len(scoped) > 1024:
                state.search_bound_reasons.add("module-test-reverse-ref-limit")
            merged = {
                self._verification_ref_identity(ref): ref for ref in [*scoped, *refs]
            }
            if len(merged) > 1024:
                state.search_bound_reasons.add("merged-direct-ref-limit")
            bounded[symbol] = list(merged.values())[:1024]
        return bounded

    def _verification_targeted_direct_refs(
        self,
        state: _VerificationRelevanceState,
        symbol: str,
        edit_module: str,
        existing: Sequence[Mapping[str, object]],
    ) -> list[Mapping[str, object]]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        short = symbol.rsplit(".", 1)[-1]
        suffix = f"{edit_module}.{short}"
        raw_targeted = list(
            self.store.refs_matching_target_suffix(short, suffix, limit=1025)
        )
        if len(raw_targeted) > 1024:
            state.search_bound_reasons.add("targeted-reverse-ref-limit")
        merged: list[Mapping[str, object]] = []
        seen: set[tuple[str, int, str, str]] = set()
        test_paths = set(self._verification_test_paths(state))
        local_paths = set(self._verification_module_test_paths(state))
        ordered = sorted(
            [*raw_targeted[:1024], *existing],
            key=lambda row: (
                str(row.get("path") or "") not in local_paths,
                str(row.get("path") or "") not in test_paths,
            ),
        )
        for ref in ordered:
            key = self._verification_ref_identity(ref)
            if key in seen:
                continue
            seen.add(key)
            merged.append(ref)
            if len(merged) > 1024:
                state.search_bound_reasons.add("merged-direct-ref-limit")
                break
        return merged[:1024]

    def _verification_collect_direct_references(
        self,
        state: _VerificationRelevanceState,
        symbol_names: Sequence[str],
    ) -> None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        selected_symbols = list(symbol_names[:16])
        if len(symbol_names) > 16:
            state.search_bound_reasons.add("edit-symbol-limit")
        direct_symbol_refs = self._verification_bounded_direct_refs(
            state, selected_symbols
        )
        # Probe owner-targeted evidence before semantic qualification.
        edit_row = self.reads.file_row(state.edit_path)
        edit_module = "" if edit_row is None else str(edit_row.get("module_name") or "")
        if edit_module:
            for symbol in selected_symbols:
                direct_symbol_refs[symbol] = self._verification_targeted_direct_refs(
                    state, symbol, edit_module, direct_symbol_refs.get(symbol, ())
                )
        self._verification_preload_import_resolution(direct_symbol_refs)
        for symbol in selected_symbols:
            self._verification_collect_direct_symbol_refs(
                state, symbol, list(direct_symbol_refs.get(symbol, ()))
            )

    def _verification_via_symbols(
        self,
        state: _VerificationRelevanceState,
    ) -> list[tuple[str, str, str]]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        source_ref_paths = sorted(state.source_ref_paths)
        if len(source_ref_paths) > 64:
            state.search_bound_reasons.add("indirect-source-path-limit")
        via_paths = source_ref_paths[:64]
        via_symbols = self.store.symbols_for_paths_many(via_paths, limit_per_path=17)
        result: list[tuple[str, str, str]] = []
        for via_path in via_paths:
            symbol_rows = list(via_symbols.get(via_path, ()))
            if len(symbol_rows) > 16:
                state.search_bound_reasons.add("indirect-symbol-limit")
            for via_symbol in symbol_rows[:16]:
                symbol = str(via_symbol.get("qualname") or via_symbol.get("name") or "")
                if symbol:
                    result.append((via_path, symbol, symbol.rsplit(".", 1)[-1]))
        return result

    def _verification_collect_indirect_references(
        self,
        state: _VerificationRelevanceState,
    ) -> None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        via_symbol_sources = self._verification_via_symbols(state)
        indirect_ref_sets = self.reads.refs_many(
            [symbol for _via_path, symbol, _short in via_symbol_sources],
            limit_per_target=257,
        )
        test_ref_sets = self._verification_test_ref_supplements(
            state, indirect_ref_sets
        )
        self._verification_preload_import_resolution(indirect_ref_sets)
        self._verification_preload_import_resolution(test_ref_sets)
        for via_path, symbol, _short in via_symbol_sources:
            refs = list(indirect_ref_sets.get(symbol, ()))
            if len(refs) > 256:
                state.search_bound_reasons.add("indirect-reverse-ref-limit")
            self._verification_collect_indirect_symbol_refs(
                state, via_path, symbol, refs[:256]
            )
            if symbol in test_ref_sets:
                self._verification_collect_indirect_symbol_refs(
                    state, via_path, symbol, test_ref_sets[symbol]
                )

    def _verification_test_ref_supplements(
        self,
        state: _VerificationRelevanceState,
        refs: Mapping[str, Sequence[Mapping[str, object]]],
    ) -> dict[str, list[dict[str, object]]]:
        """Nominate bounded test-scope candidates without bypassing import proof."""
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        bounded_symbols = [symbol for symbol, rows in refs.items() if len(rows) > 256]
        if not bounded_symbols:
            return {}
        test_paths = sorted(
            path
            for path in self.store.paths()
            if RepositoryDomain.TEST in classify_repository_path(path)
        )
        if len(test_paths) > 4096:
            state.search_bound_reasons.add("indirect-test-path-limit")
        results = self.store.refs_many_for_paths(
            bounded_symbols, test_paths[:4096], limit_per_target=1024
        )
        # A saturated scoped read cannot prove that every row was observed.
        if any(len(rows) >= 1024 for rows in results.values()):
            state.search_bound_reasons.add("indirect-test-reverse-ref-limit")
        return results

    def _verification_collect_indirect_symbol_refs(
        self,
        state: _VerificationRelevanceState,
        via_path: str,
        symbol: str,
        refs: Sequence[Mapping[str, object]],
    ) -> None:
        # The second reference has the same import/alias identity obligations
        # as the first. A same-named definition in another module is a scout
        # candidate, not evidence of a relationship through this source file.
        # Share this observation's identity/cache bookkeeping, while keeping
        # the temporary endpoint's collected links separate from the edit owner.
        endpoint = replace(
            state,
            edit_path=via_path,
            candidate_paths=set(),
            refs_by_path={},
            source_ref_paths=set(),
            qualified_attribute_refs={},
        )
        self._verification_collect_direct_symbol_refs(endpoint, symbol, refs)
        state.candidate_paths.update(endpoint.candidate_paths)
        for path, symbols in endpoint.refs_by_path.items():
            state.indirect_refs_by_path.setdefault(path, set()).update(symbols)
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
        index: _VerificationReferenceIndex,
        symbols: Sequence[str],
        *,
        attribute_use: bool = False,
    ) -> dict[str, object]:
        symbol_set = set(symbols)
        bindings = [
            (bound_name, guard)
            for imported_name, bound_name, guard in index.bindings
            if imported_name in symbol_set
        ]
        if not bindings:
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
            (
                not index.star_import
                and (live_names - index.bound_names).intersection(index.reachable_names)
            )
            or attribute_use
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
        self,
        path: str,
        symbols: Sequence[str],
        *,
        state: _VerificationRelevanceState | None = None,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        if not path.endswith(".py") or not symbols:
            strength = "syntactic" if symbols else "none"
            return {
                "syntactic_reference": bool(symbols),
                "reference_strength": strength,
            }
        index = self._verification_reference_index_for_path(state, path)
        if index is None:
            return {"syntactic_reference": True, "reference_strength": "syntactic"}
        attribute_use = state is not None and bool(
            set(symbols).intersection(state.qualified_attribute_refs.get(path, set()))
        )
        return self._verification_index_strength(
            index, symbols, attribute_use=attribute_use
        )

    def _verification_candidate_row(
        self,
        state: _VerificationRelevanceState,
        path: str,
        test_symbols: Sequence[Mapping[str, object]],
        *,
        pytest_declared: bool | None = None,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
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
        reference = self._verification_reference_strength(
            path, direct_symbols, state=state
        )
        if not direct_symbols and path in state.unresolved_reference_identity_paths:
            reference = {
                "syntactic_reference": True,
                "reference_strength": "unresolved-reference-identity",
            }
        file_reads = state.file_read_references.get(path)
        if file_reads:
            reference = {
                "syntactic_reference": True,
                "reference_strength": "literal-file-read",
                "file_read_evidence": file_reads,
            }
        direct_reference = reference.get("reference_strength") in {
            "reachable-symbol-use",
            "literal-file-read",
        }
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
                else self.plan(path, symbol=test_symbol).get("available")
            ),
        }

    def _verification_candidates(
        self,
        state: _VerificationRelevanceState,
    ) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        paths = sorted(state.candidate_paths)
        # Observe each selected module before bounding the reply. A source-order
        # prefix can hide the relevant test or manufacture a unique best symbol.
        self.reads.preload_symbols(paths)
        candidate_symbols = {path: self.reads.symbols_for_path(path) for path in paths}
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

    def _verification_lexical_candidates(
        self, state: _VerificationRelevanceState
    ) -> list[dict[str, object]]:
        """Expose bounded test scouts without granting reference/selection authority."""
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        rows = self._verification_test_lexical_rows(state)
        if len(rows) > 64:
            state.search_bound_reasons.add("lexical-verification-candidate-limit")
        paths = {
            str(row["path"])
            for row in rows[:64]
            if self._verification_ref_visible(row)
            and RepositoryDomain.TEST in classify_repository_path(str(row["path"]))
        } - state.candidate_paths
        # Only newly exposed paths need symbol/runner reads. Existing candidate
        # observations and qualified references stay owned by the original state.
        scouts = replace(state, candidate_paths=paths)
        return [
            {**row, "candidate_origin": "bounded-task-lexical-only"}
            for row in self._verification_candidates(scouts)
        ]

    def _verification_task_matches(
        self, state: _VerificationRelevanceState
    ) -> dict[str, object]:
        """Keep lexical test observations separate from owner-bound references.

        These are indexed term matches, including when there is no admitted edit
        owner. They cannot choose verification or establish a test relationship.
        """
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        rows = self._verification_test_lexical_rows(state)
        matches = [
            {
                "path": str(row["path"]),
                "matched_term_count": row["matches"],
                "evidence_visibility": row.get("evidence_visibility"),
            }
            for row in rows[:64]
            if self._verification_ref_visible(row)
            and RepositoryDomain.TEST in classify_repository_path(str(row["path"]))
        ]
        return {
            "basis": "indexed-task-term-matches",
            "index_generation": self.store.generation(),
            "source_binding": "indexed-not-source-revalidated",
            "matches": matches[:16],
            "observed_in_search": len(matches),
            "omitted_from_projection": max(0, len(matches) - 16),
            "search_truncated": len(rows) > 64,
            "bounds": {"lexical_files": 64, "returned_test_paths": 16},
            "edit_relationship": "unestablished",
            "verification_selection_authority": False,
            "negative_evidence_admissible": False,
        }

    def _verification_test_paths(
        self, state: _VerificationRelevanceState
    ) -> tuple[str, ...]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        if state.lexical_test_paths is None:
            state.lexical_test_paths = tuple(
                sorted(
                    path
                    for path in self.store.paths()
                    if RepositoryDomain.TEST in classify_repository_path(path)
                )
            )
        return state.lexical_test_paths

    def _verification_module_test_paths(
        self, state: _VerificationRelevanceState
    ) -> tuple[str, ...]:
        """Nominate module-filename matches; import/source proof still qualifies refs."""
        if state.module_test_paths is None:
            stem = Path(state.edit_path).stem
            names = {f"test_{stem}", f"{stem}_test"}
            paths = tuple(
                path
                for path in self._verification_test_paths(state)
                if Path(path).stem in names
                and self.files.decide(path).evidence_visibility
                is EvidenceVisibility.SOURCE
            )
            if len(paths) > 64:
                state.search_bound_reasons.add("module-test-path-limit")
            state.module_test_paths = paths[:64]
        return state.module_test_paths

    def _verification_test_lexical_rows(
        self, state: _VerificationRelevanceState
    ) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        return self.reads.lexical_file_candidates(
            sorted(state.task_terms),
            limit=65,
            paths=self._verification_test_paths(state),
        )

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
            int(cast("int | str", row.get("namespace_overlap") or 0)),
            int(cast("int | str", row.get("task_anchor_count") or 0)),
            -canonical,
            str(row.get("path") or ""),
        )

    @classmethod
    def _verification_select_candidate(
        cls,
        candidates: Sequence[dict[str, object]],
        current_path: str,
        *,
        uniqueness_admissible: bool = True,
    ) -> tuple[dict[str, object] | None, str]:
        selected = next(
            (row for row in candidates if str(row.get("path") or "") == current_path),
            None,
        )
        reason = "canonical-verification"
        if not candidates:
            return selected, reason
        best = candidates[0]
        direct_reference_candidates = [
            row for row in candidates if bool(row.get("direct_reference"))
        ]
        if direct_reference_candidates:
            unique_reference = (
                uniqueness_admissible
                and len(direct_reference_candidates) == 1
                and (selected is None or not bool(selected.get("direct_reference")))
            )
        else:
            indirect_reference_candidates = [
                row for row in candidates if bool(row.get("indirect_reference"))
            ]
            selected_has_reference = bool(
                isinstance(selected, Mapping)
                and (
                    selected.get("direct_reference")
                    or selected.get("indirect_reference")
                )
            )
            unique_reference = (
                uniqueness_admissible
                and len(indirect_reference_candidates) == 1
                and not selected_has_reference
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
        if cls._verification_locality_can_replace(best, selected):
            return best, "stronger-namespace-task-locality"
        return selected, reason

    @staticmethod
    def _verification_locality_can_replace(
        best: Mapping[str, object], selected: Mapping[str, object]
    ) -> bool:
        if any(
            bool(row.get("direct_reference") or row.get("indirect_reference"))
            for row in (best, selected)
        ):
            return False
        best_namespace = int(cast("int | str", best.get("namespace_overlap") or 0))
        selected_namespace = int(
            cast("int | str", selected.get("namespace_overlap") or 0)
        )
        best_anchors = int(cast("int | str", best.get("task_anchor_count") or 0))
        selected_anchors = int(
            cast("int | str", selected.get("task_anchor_count") or 0)
        )
        return (
            bool(best.get("runner_available"))
            and best_namespace > selected_namespace
            and best_anchors > selected_anchors
        )

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
        if (
            int(cast("int | str", best.get("namespace_overlap") or 0)) <= 0
            and not unique_reference
        ):
            return False
        if selected is None or str(best.get("path") or "") == current_path:
            return True
        selected_has_reference = bool(
            selected.get("direct_reference") or selected.get("indirect_reference")
        )
        best_is_indirect_only = bool(
            best.get("indirect_reference") and not best.get("direct_reference")
        )
        if best_is_indirect_only and selected_has_reference:
            return False
        return (
            best_score[:2] > cls._verification_candidate_score(selected)[:2]
            or unique_reference
        )

    @staticmethod
    def _verification_disclosure_order(
        candidates: Sequence[dict[str, object]],
        *,
        task_candidates: Sequence[dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        """Retain task retrieval alongside reference discovery in bounded replies.

        A module-wide reverse-reference search can fill every returned slot with
        smoke tests and hide an already retrieved behavior-specific test. Merge
        the two existing orders for disclosure only; selection and reference
        qualification have already finished and are not re-decided here.
        """
        task_order = (
            list(task_candidates)
            if task_candidates is not None
            else sorted(
                (
                    row
                    for row in candidates
                    if isinstance(row.get("canonical_rank"), int)
                ),
                key=lambda row: cast("int", row["canonical_rank"]),
            )
        )
        ordered: dict[str, dict[str, object]] = {}
        for index, row in enumerate(candidates):
            ordered.setdefault(str(row["path"]), row)
            if index < len(task_order):
                task_row = task_order[index]
                ordered.setdefault(str(task_row["path"]), task_row)
        return list(ordered.values())

    @staticmethod
    def _verification_bounded_candidates(
        candidates: Sequence[Mapping[str, object]],
        selected: Mapping[str, object] | None,
        limit: int,
    ) -> list[dict[str, object]]:
        bounded = [dict(row) for row in candidates[:limit]]
        selected_path = (
            str(selected.get("path") or "") if isinstance(selected, Mapping) else ""
        )
        if not selected_path or any(
            str(row.get("path") or "") == selected_path for row in bounded
        ):
            return bounded
        selected_row = next(
            (
                dict(row)
                for row in candidates
                if str(row.get("path") or "") == selected_path
            ),
            None,
        )
        if selected_row is None and isinstance(selected, Mapping):
            selected_row = {
                key: value
                for key, value in selected.items()
                if key != "selection_reason"
            }
        if selected_row is None:
            return bounded
        if len(bounded) >= limit:
            bounded[-1] = selected_row
        else:
            bounded.append(selected_row)
        return bounded

    @staticmethod
    def _verification_relevance_result(
        state: _VerificationRelevanceState,
        candidates: Sequence[dict[str, object]],
        selected_row: Mapping[str, object] | None,
        selection_reason: str,
        limit: int,
    ) -> VerificationRelevance:
        selected = (
            None
            if selected_row is None
            else read_task_candidate(
                {**selected_row, "selection_reason": selection_reason}
            )
        )
        identity_ambiguous = bool(
            state.unresolved_import_identity_paths
            or state.unresolved_reference_identity_paths
        )
        search_complete = not state.search_bound_reasons
        if selected is not None:
            projected_reason = selection_reason
        elif not search_complete:
            projected_reason = "verification-candidate-search-bounded"
        elif identity_ambiguous:
            projected_reason = "verification-candidate-identity-ambiguous"
        else:
            projected_reason = "no-verification-candidate"
        return {
            "schema": operation_schema("verification_relevance"),
            "selected": selected,
            "candidates": [
                read_task_candidate(row)
                for row in RepositoryVerification._verification_bounded_candidates(
                    candidates, selected_row, limit
                )
            ],
            "candidate_count": len(candidates),
            "selection_reason": projected_reason,
            "completeness": "complete" if search_complete else "incomplete",
            "truncation": "complete" if search_complete else "truncated",
            "negative_evidence_admissible": search_complete and not identity_ambiguous,
            "search_bound_reasons": sorted(state.search_bound_reasons),
            "selection_changed": bool(
                selected is not None
                and state.current_path
                and str(selected.get("path")) != state.current_path
            ),
            "current_canonical_verify": state.current_path or None,
            "qualified_identity_ambiguous": identity_ambiguous,
            "verifier_identity_ambiguous": state.verifier_identity_ambiguous,
            "unresolved_import_identity_paths": (
                sorted(state.unresolved_import_identity_paths)[:limit]
                if identity_ambiguous
                else []
            ),
            "unresolved_reference_identity_paths": sorted(
                state.unresolved_reference_identity_paths
            )[:limit],
            "unresolved_reference_identity_omitted_paths": max(
                0, len(state.unresolved_reference_identity_paths) - limit
            ),
            "bounds": {
                "returned_candidates": limit,
                "reverse_refs_per_symbol": 1024,
                "module_test_paths": 64,
                "module_test_reverse_refs_per_symbol": 1024,
                "edit_symbols": 16,
                "indirect_source_paths": 64,
                "indirect_symbols_per_source": 16,
                "indirect_reverse_refs_per_symbol": 256,
                "indirect_test_paths": 4096,
                "indirect_test_reverse_refs_per_symbol": 1024,
                **(
                    {
                        "literal_reader_paths": VERIFICATION_RELEVANCE_DEFAULTS.literal_file_reader_paths,
                        "literal_read_sites_per_reader": VERIFICATION_RELEVANCE_DEFAULTS.literal_file_read_sites,
                    }
                    if "literal-file-reader-syntax-scope" in state.search_bound_reasons
                    else {}
                ),
            },
            "authority": "bounded-index-evidence-not-verification-execution",
            "secret_knowledge_used": False,
        }

    @operation_response("verification_relevance")
    @decision_scoped
    def for_owner(
        self, request: VerificationRequest, *, limit: int = _CANDIDATES
    ) -> VerificationRelevance:
        if self.reads.scope is not request.scope:
            raise RuntimeError("verification request belongs to a different read scope")
        if request.owner_state == "unresolved" and request.edit is not None:
            raise ValueError("unresolved ownership cannot supply an admitted edit")
        task = request.query.text
        edit, current_verify, rows = request.edit, request.current_verify, request.rows
        if limit < 1:
            raise ValueError("limit must be >= 1")
        limit = min(int(limit), 16)
        current_path = (
            str(current_verify.get("path") or "")
            if isinstance(current_verify, Mapping)
            else ""
        )
        edit_path = str(edit.get("path") or "") if isinstance(edit, Mapping) else ""
        state = self._verification_state(request.query, edit_path, current_path, rows)
        task_matches = self._verification_task_matches(state)
        if not edit_path:
            return {
                **verification_without_edit_owner(current_path),
                "task_matches": task_matches,
            }

        self._verification_collect_file_reads(state)
        symbol_names, symbol_scope_complete = self._verification_edit_symbols(
            edit_path, edit
        )
        if not symbol_scope_complete:
            state.search_bound_reasons.add("edit-file-symbol-limit")
        self._verification_collect_direct_references(state, symbol_names)
        self._verification_collect_indirect_references(state)
        candidates = self._verification_candidates(state)
        identity_ambiguous = bool(
            state.unresolved_import_identity_paths
            or state.unresolved_reference_identity_paths
        )
        selected, reason = self._verification_select_candidate(
            candidates,
            current_path,
            uniqueness_admissible=not state.search_bound_reasons
            and not identity_ambiguous,
        )
        # Projection can reveal useful weak candidates without changing the
        # already selected verification surface or any exact reference claim.
        candidates.extend(self._verification_lexical_candidates(state))
        candidates.sort(key=self._verification_candidate_score, reverse=True)
        candidates = self._verification_disclosure_order(candidates)
        return {
            **self._verification_relevance_result(
                state, candidates, selected, reason, limit
            ),
            "task_matches": task_matches,
        }
