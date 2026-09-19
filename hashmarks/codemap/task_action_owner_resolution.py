from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .engine import CodeMap


class TaskActionOwnerResolutionMixin:
    def _task_action_resolve_structural_owner(
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
    ) -> dict[str, object]:
        """Resolve the active implementation owner from existing repository evidence."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        structural_owner = literal_reference_owner
        edit, archive_live_owner_ambiguity = (
            self._task_action_archive_live_owner_choice(
                edit, rows, failed, discrimination, verification_anchor_tokens
            )
        )
        edit_path = str(edit.get("path") or "") if isinstance(edit, dict) else ""
        task_path_tokens = {
            token.strip("`'\"()[]{}<>,:;").replace("\\", "/") for token in task.split()
        }
        literal_task_paths = tuple(
            dict.fromkeys(
                str(row.get("path") or "")
                for row in rows
                if row.get("path") and str(row.get("path") or "") in task_path_tokens
            )
        )
        literal_task_path = (
            literal_task_paths[0] if len(literal_task_paths) == 1 else ""
        )
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
        exact_identifier_surface_selected = bool(
            len(exact_identifier_edits) == 1
            and str(exact_identifier_edits[0].get("signature") or "")
            .lstrip()
            .startswith(("def ", "async def "))
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
        exact_identifier_displacement_guard = False
        should_resolve = (
            structural_owner is None
            and not localized_config_edit
            and not explicit_config_surface_request
            and not explicit_edit_surface_selected
            and not literal_edit_path
        )
        if not should_resolve:
            return {
                "edit": edit,
                "structural_owner": structural_owner,
                "structural_owner_origin": None,
                "archive_live_owner_ambiguity": archive_live_owner_ambiguity,
                "exact_identifier_paths": exact_identifier_paths,
                "exact_identifier_displacement_guard": exact_identifier_displacement_guard,
                "exact_identifier_surface_selected": exact_identifier_surface_selected,
            }

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
            return {
                "edit": edit,
                "structural_owner": structural_owner,
                "structural_owner_origin": None,
                "archive_live_owner_ambiguity": archive_live_owner_ambiguity,
                "exact_identifier_paths": exact_identifier_paths,
                "exact_identifier_displacement_guard": exact_identifier_displacement_guard,
                "exact_identifier_surface_selected": exact_identifier_surface_selected,
            }

        resolved = self._structural_owner_candidate(owner_start, max_depth=3, task=task)
        if resolved is None or str(resolved.get("path") or "") in failed:
            return {
                "edit": edit,
                "structural_owner": structural_owner,
                "structural_owner_origin": None,
                "archive_live_owner_ambiguity": archive_live_owner_ambiguity,
                "exact_identifier_paths": exact_identifier_paths,
                "exact_identifier_displacement_guard": exact_identifier_displacement_guard,
                "exact_identifier_surface_selected": exact_identifier_surface_selected,
            }
        owner_path = str(resolved["path"])
        if len(exact_identifier_paths) > 1:
            discriminated_exact_path = (
                self._task_action_structural_exact_identifier_owner(
                    resolved, exact_identifier_edits
                )
            )
            if discriminated_exact_path is None:
                return {
                    "edit": edit,
                    "structural_owner": structural_owner,
                    "structural_owner_origin": None,
                    "archive_live_owner_ambiguity": archive_live_owner_ambiguity,
                    "exact_identifier_paths": exact_identifier_paths,
                    "exact_identifier_displacement_guard": exact_identifier_displacement_guard,
                    "exact_identifier_surface_selected": exact_identifier_surface_selected,
                }
            exact_identifier_paths = (discriminated_exact_path,)
        exact_identifier_path = (
            exact_identifier_paths[0] if len(exact_identifier_paths) == 1 else None
        )
        exact_identifier_displacement_guard = bool(
            exact_identifier_path and owner_path != exact_identifier_path
        )
        archive_owner = self._task_action_is_archive_path(owner_path)
        live_current_edit = self._task_action_live_current_edit(
            edit, discrimination, verification_anchor_tokens
        )
        if not exact_identifier_displacement_guard and not (
            archive_owner and live_current_edit
        ):
            edit = self._task_action_projected_owner_row(
                owner_path, resolved, rows, limit
            )
            structural_owner = self._task_action_structural_owner_evidence(
                resolved, owner_path
            )
        return {
            "edit": edit,
            "structural_owner": structural_owner,
            "structural_owner_origin": {
                "path": owner_start,
                "resolved": resolved,
            }
            if structural_owner is not None
            else None,
            "archive_live_owner_ambiguity": archive_live_owner_ambiguity,
            "exact_identifier_paths": exact_identifier_paths,
            "exact_identifier_displacement_guard": exact_identifier_displacement_guard,
            "exact_identifier_surface_selected": exact_identifier_surface_selected,
        }

