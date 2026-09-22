from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .model import EvidenceVisibility
from .task_action_types import (
    _TaskActionOwnerCandidateState,
    _TaskActionOwnerResolutionRequest,
    _TaskActionOwnerResolutionState,
)

if TYPE_CHECKING:
    from .engine import CodeMap


class TaskActionOwnerResolutionMixin:
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
        structural_owner: dict[str, object] | None,
    ) -> tuple[list[dict[str, object]], dict[str, object] | None, str | None]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        exact_identifier_edits: list[dict[str, object]] = []
        blocked = any(
            (
                structural_owner is not None,
                request.surface.localized_config_edit,
                request.surface.explicit_config_surface_request,
                request.surface.explicit_edit_surface_selected,
            )
        )
        owner_basis = "literal-path" if literal_task_path else None
        if not blocked:
            exact_identifier_edits = self._task_action_exact_identifier_edit_candidates(
                request.task, request.context.rows, request.context.failed
            )
            if literal_task_path:
                exact_identifier_edits = [
                    row
                    for row in exact_identifier_edits
                    if str(row.get("path") or "") == literal_task_path
                ]
            if len(exact_identifier_edits) == 1:
                edit = exact_identifier_edits[0]
                if not literal_task_path:
                    owner_basis = self._task_action_exact_owner_basis(
                        request.task, exact_identifier_edits[0]
                    )
        return exact_identifier_edits, edit, owner_basis

    @staticmethod
    def _task_action_owner_state(
        candidate: _TaskActionOwnerCandidateState,
        structural_owner_origin: dict[str, object] | None = None,
    ) -> _TaskActionOwnerResolutionState:
        return _TaskActionOwnerResolutionState(
            edit=candidate.edit,
            basis=candidate.basis,
            structural_owner=candidate.structural_owner,
            structural_owner_origin=structural_owner_origin,
            archive_live_owner_ambiguity=candidate.archive_live_owner_ambiguity,
            exact_identifier_paths=candidate.exact_identifier_paths,
        )

    def _task_action_structural_owner_start(
        self,
        request: _TaskActionOwnerResolutionRequest,
        candidate: _TaskActionOwnerCandidateState,
    ) -> str | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        task_specific = self._task_action_specific_entry_candidate(
            request.task, request.context.rows, request.discrimination
        )
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
            request.context.rows,
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

    def _task_action_structural_owner(
        self,
        request: _TaskActionOwnerResolutionRequest,
        candidate: _TaskActionOwnerCandidateState,
    ) -> _TaskActionOwnerResolutionState:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        owner_start = self._task_action_structural_owner_start(request, candidate)
        if not owner_start:
            return self._task_action_owner_state(candidate)
        resolved = self._structural_owner_candidate(
            owner_start, max_depth=3, task=request.task
        )
        if (
            resolved is None
            or str(resolved.get("path") or "") in request.context.failed
        ):
            return self._task_action_owner_state(candidate)
        owner_path = str(resolved["path"])
        if len(candidate.exact_identifier_paths) > 1:
            discriminated_exact_path = (
                self._task_action_structural_exact_identifier_owner(
                    resolved, candidate.exact_identifier_edits
                )
            )
            if discriminated_exact_path is None:
                candidate.basis = None
                return self._task_action_owner_state(candidate)
            candidate.exact_identifier_paths = (discriminated_exact_path,)
            candidate.basis = "exact-import-owner"
        archive_owner = self._task_action_is_archive_path(owner_path)
        live_current_edit = self._task_action_live_current_edit(
            candidate.edit,
            request.discrimination,
            request.surface.verification_anchor_tokens,
        )
        if not (archive_owner and live_current_edit):
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
        origin: dict[str, object] | None = (
            {"path": owner_start, "resolved": resolved}
            if candidate.structural_owner is not None
            else None
        )
        return self._task_action_owner_state(candidate, origin)

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
        edit, archive_live_owner_ambiguity = (
            self._task_action_archive_live_owner_choice(
                request.surface.edit,
                request.context.rows,
                request.context.failed,
                request.discrimination,
                request.surface.verification_anchor_tokens,
            )
        )
        edit, literal_task_path = self._task_action_literal_owner(request, edit)
        exact_identifier_edits, edit, exact_basis = self._task_action_exact_owner(
            request, edit, literal_task_path, structural_owner
        )
        owner_basis = exact_basis or owner_basis
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
            archive_live_owner_ambiguity=archive_live_owner_ambiguity,
            exact_identifier_edits=exact_identifier_edits,
            exact_identifier_paths=exact_identifier_paths,
            literal_task_path=literal_task_path,
        )
        selected_edit_path = str(edit.get("path") or "") if edit else ""
        if literal_task_path and selected_edit_path == literal_task_path:
            candidate.basis = "literal-path"
            return self._task_action_owner_state(candidate)
        if len(exact_identifier_edits) == 1:
            return self._task_action_owner_state(candidate)
        blocked = any(
            (
                structural_owner is not None,
                request.surface.localized_config_edit,
                request.surface.explicit_config_surface_request,
                request.surface.explicit_edit_surface_selected,
            )
        )
        if blocked:
            return self._task_action_owner_state(candidate)
        return self._task_action_structural_owner(request, candidate)
