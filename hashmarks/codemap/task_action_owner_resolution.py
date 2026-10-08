from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .model import EvidenceVisibility
from .query_primitives import _TASK_STOPWORDS, _query_terms
from .repository_domains import RepositoryDomain
from .task_action_types import (
    _TaskActionExactIdentifierEvidence,
    _TaskActionOwnerCandidateState,
    _TaskActionOwnerResolutionRequest,
    _TaskActionOwnerResolutionState,
)

if TYPE_CHECKING:
    from .engine import CodeMap


class TaskActionOwnerResolutionMixin:
    @staticmethod
    def _task_action_class_is_method_scope(
        task: str, candidate: dict[str, object] | None
    ) -> bool:
        """A named class scopes a method request; it is not that method's owner."""
        if candidate is None or re.search(r"\bmethod\b", task, re.I) is None:
            return False
        name = str(candidate.get("name") or "")
        signature = str(candidate.get("signature") or "")
        return bool(
            name
            and signature.startswith("class ")
            and re.search(rf"\b{re.escape(name)}\b", task)
        )

    def _task_action_literal_task_paths(
        self,
        task: str,
        failed: set[str],
    ) -> tuple[str, ...]:
        """Resolve explicitly named current repository paths without lexical retrieval."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        paths: list[str] = []
        for raw in task.split():
            token = raw.strip("`'\"()[]{}<>,:;").replace("\\", "/")
            token = token.partition("::")[0]
            try:
                path = normalize_relative_path(token, allow_root=False)
            except ValueError:
                continue
            if path in failed:
                continue
            row = self._session_file_row(path)
            if row is None:
                continue
            visibility = EvidenceVisibility(
                str(row.get("evidence_visibility") or EvidenceVisibility.DENY.value)
            )
            if visibility is EvidenceVisibility.DENY:
                continue
            if not self._indexed_path_current(path):
                continue
            paths.append(path)
        return tuple(dict.fromkeys(paths))

    def _task_action_exact_owner_basis(
        self,
        task: str,
        candidate: dict[str, object],
    ) -> str:
        """Describe the strongest explicit repository identity behind one owner."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        qualified_terms = tuple(
            term
            for term in self._task_action_exact_identifier_terms(task)
            if "." in term
        )
        path = str(candidate.get("path") or "")
        if candidate.get("qualified_import_owner_projection"):
            return "exact-import-owner"
        if qualified_terms and self._task_action_qualified_identifier_matches_symbol(
            path, candidate, qualified_terms
        ):
            return "qualified-symbol"
        if candidate.get("plain_identifier_index_projection"):
            return "unique-exact-symbol"
        return "exact-symbol"

    def _task_action_literal_owner(
        self,
        request: _TaskActionOwnerResolutionRequest,
        edit: dict[str, object] | None,
    ) -> tuple[dict[str, object] | None, str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        literal_task_paths = self._task_action_literal_task_paths(
            request.task, request.context.failed
        )
        literal_task_path = (
            literal_task_paths[0] if len(literal_task_paths) == 1 else ""
        )
        if not literal_task_path:
            return edit, ""
        literal_row = next(
            (
                row
                for row in request.context.rows
                if str(row.get("path") or "") == literal_task_path
            ),
            None,
        )
        if literal_row is None:
            literal_row = self._task_action_projected_owner_row(
                literal_task_path,
                {"depth": 0},
                request.context.rows,
                request.limit,
            )
        return literal_row, literal_task_path

    def _task_action_exact_owner(
        self,
        request: _TaskActionOwnerResolutionRequest,
        edit: dict[str, object] | None,
        literal_task_path: str,
        blocked: bool,
    ) -> tuple[
        _TaskActionExactIdentifierEvidence,
        dict[str, object] | None,
        str | None,
    ]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        evidence = _TaskActionExactIdentifierEvidence([], None, ())
        owner_basis = "literal-path" if literal_task_path else None
        if not blocked:
            evidence = self._task_action_exact_identifier_edit_candidates(
                request.task, request.context.rows, request.context.failed
            )
            exact_identifier_edits = [
                row
                for row in evidence.candidates
                if not self._task_action_class_is_method_scope(request.task, row)
            ]
            if self._task_action_class_is_method_scope(request.task, edit):
                edit = None
            if literal_task_path:
                exact_identifier_edits = [
                    row
                    for row in exact_identifier_edits
                    if str(row.get("path") or "") == literal_task_path
                ]
            evidence = _TaskActionExactIdentifierEvidence(
                exact_identifier_edits,
                evidence.search_complete,
                evidence.bound_reasons,
            )
            if len(exact_identifier_edits) == 1:
                edit = exact_identifier_edits[0]
                if not literal_task_path and evidence.search_complete is True:
                    owner_basis = self._task_action_exact_owner_basis(
                        request.task, exact_identifier_edits[0]
                    )
        return evidence, edit, owner_basis

    @staticmethod
    def _task_action_behavioral_terms(task: str) -> set[str]:
        return {
            term
            for term in _query_terms(task)
            if len(term) >= 4 and term not in _TASK_STOPWORDS
        }

    @staticmethod
    def _task_action_is_test_shaped_source(
        row: dict[str, object],
        failed: set[str],
    ) -> bool:
        path = str(row.get("path") or "")
        domains = set(map(str, row.get("domains") or ()))
        return bool(
            path
            and path not in failed
            and RepositoryDomain.TEST.value in domains
            and RepositoryDomain.SOURCE.value in domains
        )

    def _task_action_behavioral_reference_candidate(
        self,
        row: dict[str, object],
        task_terms: set[str],
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        best: tuple[int, dict[str, object]] | None = None
        path = str(row.get("path") or "")
        for symbol in self._session_symbols_for_path(path):
            name = str(symbol.get("name") or "")
            symbol_terms = set(
                _query_terms(
                    " ".join(
                        str(symbol.get(key) or "")
                        for key in ("name", "qualname", "signature")
                    )
                )
            )
            anchors = task_terms.intersection(symbol_terms)
            if not name or len(anchors) < 2:
                continue
            projected = self._task_action_reference_backed_source_projection(
                row,
                {name},
            )
            if projected is None:
                continue
            candidate = {
                **projected,
                "name": symbol.get("name"),
                "qualname": symbol.get("qualname"),
                "signature": symbol.get("signature"),
                "start_line": symbol.get("start_line"),
                "end_line": symbol.get("end_line"),
                "behavioral_reference_owner_projection": True,
            }
            score = len(anchors)
            if best is None or score > best[0]:
                best = (score, candidate)
        return None if best is None else best[1]

    def _task_action_reference_backed_behavioral_owner(
        self,
        request: _TaskActionOwnerResolutionRequest,
    ) -> dict[str, object] | None:
        """Promote one test-shaped source only with task-local production-use proof."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        task_terms = self._task_action_behavioral_terms(request.task)
        if not task_terms:
            return None
        rows = getattr(
            request.context,
            "canonical_rows",
            tuple(request.context.rows),
        )
        candidates: list[dict[str, object]] = []
        for row in rows:
            if not self._task_action_is_test_shaped_source(row, request.context.failed):
                continue
            candidate = self._task_action_behavioral_reference_candidate(
                row,
                task_terms,
            )
            if candidate is not None:
                candidates.append(candidate)
        by_path = {
            str(candidate.get("path") or ""): candidate for candidate in candidates
        }
        return next(iter(by_path.values())) if len(by_path) == 1 else None

    @staticmethod
    def _task_action_owner_state(
        candidate: _TaskActionOwnerCandidateState,
        structural_starts: dict[str, object] | None = None,
    ) -> _TaskActionOwnerResolutionState:
        return _TaskActionOwnerResolutionState(
            edit=candidate.edit,
            basis=candidate.basis,
            structural_owner=candidate.structural_owner,
            exact_identifier_paths=candidate.exact_identifier_paths,
            exact_identifier_search_complete=candidate.exact_identifier_search_complete,
            exact_identifier_search_bound_reasons=(
                candidate.exact_identifier_search_bound_reasons
            ),
            structural_starts=structural_starts
            or {
                "scope": "returned-canonical-hits-plus-selected-start",
                "status": "not-evaluated",
                "retrieval_completeness": "unknown",
                "limit_reached": False,
                "candidates": [],
                "candidate_count": 0,
                "observed_owners": [],
                "observation_complete": False,
            },
        )

    def _task_action_structural_owner_start(
        self,
        request: _TaskActionOwnerResolutionRequest,
        candidate: _TaskActionOwnerCandidateState,
        resolved_by_path: dict[str, dict[str, object] | None],
        matched_rows: list[dict[str, object]],
    ) -> str | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        test_candidate = self._task_action_specific_test_candidate(
            getattr(request.context, "canonical_rows", tuple(request.context.rows)),
            request.discrimination,
        )
        source_rows = [
            row
            for row in matched_rows
            if "edit" in row.get("roles", []) or "related" in row.get("roles", [])
        ]
        source_candidate = max(
            source_rows,
            key=lambda row: (
                resolved_by_path.get(str(row.get("path") or "")) is not None,
                len(
                    (resolved_by_path.get(str(row.get("path") or "")) or {}).get(
                        "corroboration"
                    )
                    or []
                ),
                self._task_action_specificity(row, request.discrimination),
                -int(row.get("canonical_rank") or 10_000),
            ),
            default=None,
        )
        task_specific = test_candidate or source_candidate
        task_local_island = self._task_action_local_island(
            request.task, request.context.hits, request.limit
        )
        verify = request.surface.verify
        verify_path = (
            str(verify.get("path"))
            if isinstance(verify, dict) and verify.get("path")
            else ""
        )
        owner_start = (
            verify_path
            if task_local_island and verify_path
            else str(task_specific.get("path"))
            if isinstance(task_specific, dict) and task_specific.get("path")
            else None
        )
        go_entry = self._task_action_go_entry(
            verify_path,
            getattr(request.context, "canonical_rows", tuple(request.context.rows)),
            request.discrimination,
            task_local_island,
        )
        if go_entry is not None:
            return str(go_entry["path"])
        if owner_start is not None:
            return owner_start
        if isinstance(candidate.edit, dict) and candidate.edit.get("path"):
            return verify_path or str(candidate.edit["path"])
        return verify_path or None

    def _task_action_observe_structural_start(
        self,
        request: _TaskActionOwnerResolutionRequest,
        row: dict[str, object],
        terms: list[str],
        origin: str,
    ) -> tuple[dict[str, object], dict[str, object] | None]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        path = str(row.get("path") or "")
        entry: dict[str, object] = {
            "start_path": path,
            "roles": list(row.get("roles") or []),
            "canonical_rank": row.get("canonical_rank"),
            "anchor_terms": terms,
            "origin": origin,
            "observed_owner": None,
            "owner_path": [],
            "graph_completeness": "unknown",
            "graph_bound_reasons": [],
            "status": "unresolved",
        }
        if not self._indexed_path_current(path):
            entry["status"] = "stale"
            return entry, None
        graph = self.ownership_relation_graph(request.task, path, max_depth=3)
        resolved = self._structural_owner_from_graph(graph, path)
        owner = str((resolved or {}).get("path") or "")
        current = bool(owner and self._indexed_path_current(owner))
        entry["graph_completeness"] = graph["completeness"]
        entry["graph_bound_reasons"] = list(graph.get("search_bound_reasons") or [])
        entry["owner_path"] = list(graph.get("owner_path") or [])
        if owner and current and owner not in request.context.failed:
            entry["observed_owner"] = owner
            entry["status"] = (
                "observed-owner"
                if graph["completeness"] == "complete"
                else "graph-incomplete"
            )
            return entry, resolved
        entry["status"] = (
            "stale"
            if owner and not current
            else (
                "graph-incomplete"
                if graph["completeness"] != "complete"
                else "no-selected-owner"
            )
        )
        return entry, None

    def _task_action_observe_structural_starts(
        self,
        request: _TaskActionOwnerResolutionRequest,
        candidate: _TaskActionOwnerCandidateState,
    ) -> tuple[str | None, dict[str, dict[str, object] | None], dict[str, object]]:
        """Observe each nominated start once before selecting an owner candidate."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        canonical_rows = getattr(
            request.context, "canonical_rows", tuple(request.context.rows)
        )
        nominated = self._task_action_structural_start_rows(
            request.task, canonical_rows, request.discrimination
        )
        resolved_by_path: dict[str, dict[str, object] | None] = {}
        entries: dict[str, dict[str, object]] = {}
        for row, terms in nominated:
            path = str(row.get("path") or "")
            if path and path not in entries:
                entries[path], resolved_by_path[path] = (
                    self._task_action_observe_structural_start(
                        request, row, terms, "task-term"
                    )
                )
        owner_start = self._task_action_structural_owner_start(
            request, candidate, resolved_by_path, [row for row, _ in nominated]
        )
        if owner_start and owner_start not in entries:
            selected_row = next(
                (
                    row
                    for row in canonical_rows
                    if str(row.get("path") or "") == owner_start
                ),
                {"path": owner_start, "roles": [], "canonical_rank": None},
            )
            entries[owner_start], resolved_by_path[owner_start] = (
                self._task_action_observe_structural_start(
                    request, selected_row, [], "selected-start"
                )
            )
        candidates = sorted(
            entries.values(),
            key=lambda row: (
                int(row.get("canonical_rank") or request.limit + 1),
                str(row["start_path"]),
            ),
        )
        owners = sorted(
            {
                str(row["observed_owner"])
                for row in candidates
                if row.get("observed_owner")
            }
        )
        for row in candidates:
            if (
                row["status"] == "no-selected-owner"
                and row["start_path"] in owners
                and "edit" in row["roles"]
                and row["graph_completeness"] == "complete"
            ):
                row["status"] = "self-owner"
                row["observed_owner"] = row["start_path"]
        return (
            owner_start,
            resolved_by_path,
            {
                "scope": "returned-canonical-hits-plus-selected-start",
                "status": "observed",
                "retrieval_completeness": "unknown",
                "limit_reached": len(request.context.hits) >= request.limit,
                "candidates": candidates,
                "candidate_count": len(candidates),
                "observed_owners": owners,
                "observation_complete": bool(candidates)
                and all(
                    row["status"]
                    in {
                        "observed-owner",
                        "self-owner",
                        "no-selected-owner",
                    }
                    for row in candidates
                ),
            },
        )

    def _task_action_structural_owner(
        self,
        request: _TaskActionOwnerResolutionRequest,
        candidate: _TaskActionOwnerCandidateState,
    ) -> _TaskActionOwnerResolutionState:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        owner_start, resolved_by_path, structural_starts = (
            self._task_action_observe_structural_starts(request, candidate)
        )
        if not owner_start:
            return self._task_action_owner_state(
                candidate, structural_starts=structural_starts
            )
        resolved = resolved_by_path.get(owner_start)
        if (
            resolved is None
            or str(resolved.get("path") or "") in request.context.failed
        ):
            return self._task_action_owner_state(
                candidate, structural_starts=structural_starts
            )
        owner_path = str(resolved["path"])
        if len(candidate.exact_identifier_paths) > 1:
            discriminated_exact_path = (
                self._task_action_structural_exact_identifier_owner(
                    resolved, candidate.exact_identifier_edits
                )
            )
            if discriminated_exact_path is None:
                candidate.basis = None
                return self._task_action_owner_state(
                    candidate, structural_starts=structural_starts
                )
            candidate.exact_identifier_paths = (discriminated_exact_path,)
            candidate.basis = "exact-import-owner"
        exact_owner_rows = [
            row
            for row in candidate.exact_identifier_edits
            if str(row.get("path") or "") == owner_path
        ]
        candidate.edit = (
            exact_owner_rows[0]
            if len(exact_owner_rows) == 1
            else self._task_action_projected_owner_row(
                owner_path, resolved, request.context.rows, request.limit
            )
        )
        candidate.structural_owner = self._task_action_structural_owner_evidence(
            resolved, owner_path
        )
        if candidate.basis is None:
            candidate.basis = "structural-owner"
        return self._task_action_owner_state(
            candidate, structural_starts=structural_starts
        )

    def _task_action_resolve_owner(
        self, request: _TaskActionOwnerResolutionRequest
    ) -> _TaskActionOwnerResolutionState:
        """Resolve ownership once, preferring stronger repository identity evidence."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        structural_owner = request.surface.literal_reference_owner
        owner_basis = (
            "literal-reference-owner" if structural_owner is not None else None
        )
        edit = request.surface.edit
        edit, literal_task_path = self._task_action_literal_owner(request, edit)
        blocked = any(
            (
                structural_owner is not None,
                request.surface.localized_config_edit,
                request.surface.explicit_config_surface_request,
                request.surface.explicit_edit_surface_selected,
            )
        )
        exact_identifier_evidence, edit, exact_basis = self._task_action_exact_owner(
            request, edit, literal_task_path, blocked
        )
        exact_identifier_edits = exact_identifier_evidence.candidates
        owner_basis = exact_basis or owner_basis
        behavioral_owner = (
            self._task_action_reference_backed_behavioral_owner(request)
            if not exact_identifier_edits
            and not literal_task_path
            and structural_owner is None
            else None
        )
        edit = behavioral_owner or edit
        owner_basis = (
            "reference-backed-behavioral-owner"
            if behavioral_owner is not None
            else owner_basis
        )
        exact_identifier_paths = tuple(
            sorted(
                {
                    str(row.get("path") or "")
                    for row in exact_identifier_edits
                    if row.get("path")
                }
            )
        )
        candidate = _TaskActionOwnerCandidateState(
            edit=edit,
            basis=owner_basis,
            structural_owner=structural_owner,
            exact_identifier_edits=exact_identifier_edits,
            exact_identifier_paths=exact_identifier_paths,
            exact_identifier_search_complete=exact_identifier_evidence.search_complete,
            exact_identifier_search_bound_reasons=exact_identifier_evidence.bound_reasons,
            literal_task_path=literal_task_path,
        )
        selected_edit_path = str(edit.get("path") or "") if edit else ""
        literal_owner = bool(
            literal_task_path and selected_edit_path == literal_task_path
        )
        if literal_owner or behavioral_owner is not None:
            candidate.basis = "literal-path" if literal_owner else candidate.basis
            return self._task_action_owner_state(candidate)
        if exact_identifier_evidence.search_complete is False:
            candidate.basis = None
            return self._task_action_owner_state(candidate)
        if len(exact_identifier_edits) == 1:
            return self._task_action_owner_state(candidate)
        if blocked:
            return self._task_action_owner_state(candidate)
        return self._task_action_structural_owner(request, candidate)
