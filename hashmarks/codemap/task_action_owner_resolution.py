from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .model import EvidenceVisibility
from .task_action_types import _TaskActionOwnerResolutionState

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
            if "::" in token:
                token = token.split("::", 1)[0]
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

    def _task_action_resolve_owner(
        self,
        *,
        task: str,
        hits: Sequence[object],
        rows: list[dict[str, object]],
        failed: set[str],
        edit: dict[str, object] | None,
        verify: dict[str, object] | None,
        discrimination: object,
        verification_anchor_tokens: object,
        literal_reference_owner: dict[str, object] | None,
        localized_config_edit: bool,
        explicit_config_surface_request: bool,
        explicit_edit_surface_selected: bool,
        limit: int,
    ) -> _TaskActionOwnerResolutionState:
        """Resolve ownership once, preferring stronger repository identity evidence."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        structural_owner = literal_reference_owner
        owner_basis = (
            "literal-reference-owner" if literal_reference_owner is not None else None
        )
        edit, archive_live_owner_ambiguity = (
            self._task_action_archive_live_owner_choice(
                edit, rows, failed, discrimination, verification_anchor_tokens
            )
        )

        literal_task_paths = self._task_action_literal_task_paths(task, failed)
        literal_task_path = (
            literal_task_paths[0] if len(literal_task_paths) == 1 else ""
        )
        if literal_task_path:
            literal_row = next(
                (
                    row
                    for row in rows
                    if str(row.get("path") or "") == literal_task_path
                ),
                None,
            )
            if literal_row is None:
                literal_row = self._task_action_projected_owner_row(
                    literal_task_path,
                    {"depth": 0},
                    rows,
                    limit,
                )
            edit = literal_row
            owner_basis = "literal-path"

        exact_identifier_edits: list[dict[str, object]] = []
        if (
            structural_owner is None
            and not localized_config_edit
            and not explicit_config_surface_request
            and not explicit_edit_surface_selected
        ):
            exact_identifier_edits = self._task_action_exact_identifier_edit_candidates(
                task, rows, failed
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
                        task, exact_identifier_edits[0]
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
        selected_edit_path = (
            str(edit.get("path") or "") if isinstance(edit, dict) else ""
        )
        literal_edit_path = bool(
            literal_task_path and selected_edit_path == literal_task_path
        )
        if literal_edit_path:
            owner_basis = "literal-path"

        # Exact path/symbol authority terminates resolution. A weaker structural
        # walk is not allowed to displace it and therefore needs no repair guard.
        if literal_edit_path or len(exact_identifier_edits) == 1:
            return _TaskActionOwnerResolutionState(
                edit=edit,
                basis=owner_basis,
                structural_owner=structural_owner,
                structural_owner_origin=None,
                archive_live_owner_ambiguity=archive_live_owner_ambiguity,
                exact_identifier_paths=exact_identifier_paths,
            )

        should_resolve = (
            structural_owner is None
            and not localized_config_edit
            and not explicit_config_surface_request
            and not explicit_edit_surface_selected
        )
        if not should_resolve:
            return _TaskActionOwnerResolutionState(
                edit=edit,
                basis=owner_basis,
                structural_owner=structural_owner,
                structural_owner_origin=None,
                archive_live_owner_ambiguity=archive_live_owner_ambiguity,
                exact_identifier_paths=exact_identifier_paths,
            )

        task_specific = self._task_action_specific_entry_candidate(
            task, rows, discrimination
        )
        task_local_island = self._task_action_local_island(task, hits, limit)
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
            verify_path, rows, discrimination, task_local_island
        )
        if go_entry is not None:
            owner_start = str(go_entry["path"])
        if owner_start is None:
            owner_start = verify_path or None
        if owner_start is None and isinstance(edit, dict) and edit.get("path"):
            owner_start = str(edit["path"])
        if not owner_start:
            return _TaskActionOwnerResolutionState(
                edit=edit,
                basis=owner_basis,
                structural_owner=structural_owner,
                structural_owner_origin=None,
                archive_live_owner_ambiguity=archive_live_owner_ambiguity,
                exact_identifier_paths=exact_identifier_paths,
            )

        resolved = self._structural_owner_candidate(owner_start, max_depth=3, task=task)
        if resolved is None or str(resolved.get("path") or "") in failed:
            return _TaskActionOwnerResolutionState(
                edit=edit,
                basis=owner_basis,
                structural_owner=structural_owner,
                structural_owner_origin=None,
                archive_live_owner_ambiguity=archive_live_owner_ambiguity,
                exact_identifier_paths=exact_identifier_paths,
            )

        owner_path = str(resolved["path"])
        if len(exact_identifier_paths) > 1:
            discriminated_exact_path = (
                self._task_action_structural_exact_identifier_owner(
                    resolved, exact_identifier_edits
                )
            )
            if discriminated_exact_path is None:
                return _TaskActionOwnerResolutionState(
                    edit=edit,
                    basis=None,
                    structural_owner=structural_owner,
                    structural_owner_origin=None,
                    archive_live_owner_ambiguity=archive_live_owner_ambiguity,
                    exact_identifier_paths=exact_identifier_paths,
                )
            exact_identifier_paths = (discriminated_exact_path,)
            owner_basis = "exact-import-owner"

        archive_owner = self._task_action_is_archive_path(owner_path)
        live_current_edit = self._task_action_live_current_edit(
            edit, discrimination, verification_anchor_tokens
        )
        if not (archive_owner and live_current_edit):
            exact_owner_rows = [
                row
                for row in exact_identifier_edits
                if str(row.get("path") or "") == owner_path
            ]
            exact_owner_edit = (
                exact_owner_rows[0] if len(exact_owner_rows) == 1 else None
            )
            edit = (
                exact_owner_edit
                if exact_owner_edit is not None
                else self._task_action_projected_owner_row(
                    owner_path, resolved, rows, limit
                )
            )
            structural_owner = self._task_action_structural_owner_evidence(
                resolved, owner_path
            )
            if owner_basis is None:
                owner_basis = "structural-owner"

        return _TaskActionOwnerResolutionState(
            edit=edit,
            basis=owner_basis,
            structural_owner=structural_owner,
            structural_owner_origin={
                "path": owner_start,
                "resolved": resolved,
            }
            if structural_owner is not None
            else None,
            archive_live_owner_ambiguity=archive_live_owner_ambiguity,
            exact_identifier_paths=exact_identifier_paths,
        )
