from __future__ import annotations

from collections.abc import Mapping

STRUCTURAL_SELECTION_BASIS = "unique-complete-structural-owner"


def _ambiguity_payload(
    action: Mapping[str, object],
) -> Mapping[str, object] | None:
    ambiguity = action.get("ambiguity")
    if not isinstance(ambiguity, Mapping):
        return None
    return ambiguity if bool(ambiguity.get("ambiguous")) else None


def _unique_complete_structural_owner(
    action: Mapping[str, object],
) -> str | None:
    starts = action.get("structural_starts")
    if not isinstance(starts, Mapping):
        return None
    if starts.get("status") != "observed":
        return None
    if starts.get("observation_complete") is not True:
        return None
    observed = starts.get("observed_owners")
    if not isinstance(observed, list):
        return None
    owners = tuple(dict.fromkeys(str(path) for path in observed if str(path)))
    return owners[0] if len(owners) == 1 else None


def _row_for_path(value: object, path: str) -> Mapping[str, object] | None:
    if not isinstance(value, list):
        return None
    return next(
        (
            row
            for row in value
            if isinstance(row, Mapping) and str(row.get("path") or "") == path
        ),
        None,
    )


def _structural_candidate(
    action: Mapping[str, object],
    ambiguity: Mapping[str, object],
) -> Mapping[str, object] | None:
    owner = _unique_complete_structural_owner(action)
    if owner is None:
        return None
    return (
        _row_for_path(ambiguity.get("candidates"), owner)
        or _row_for_path(action.get("canonical"), owner)
        or {"path": owner}
    )


def select_task_evidence_discrimination_candidate(
    action: Mapping[str, object],
) -> tuple[Mapping[str, object], Mapping[str, object], str] | None:
    """Choose a read-only ambiguity discriminator without changing ownership."""
    ambiguity = _ambiguity_payload(action)
    if ambiguity is None:
        return None

    structural = _structural_candidate(action, ambiguity)
    if structural is not None:
        return ambiguity, structural, STRUCTURAL_SELECTION_BASIS
    return None
