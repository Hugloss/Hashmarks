"""Bounded path-locality projection over existing diagnostic endpoint deltas.

A producer's diagnostic path and a caller-reported edit path are two
independent observations. Their intersection does not establish causality,
complete change scope, diagnostic resolution, or verification authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hashmarks.paths import normalize_relative_path

DIAGNOSTIC_PATH_LOCALITY_SCHEMA = "hashmarks.diagnostic-path-locality.v1"
_MAX_REPORTED_CHANGED_PATHS = 256


def indexed_diagnostic_rows(
    packet: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    """Reuse canonical delta's existing row-indexing semantics."""
    rows = packet.get("diagnostics")
    if not isinstance(rows, list):
        return {}
    return {
        str(row["identity"]): row
        for row in rows
        if isinstance(row, Mapping) and row.get("identity")
    }


def normalize_reported_changed_paths(changed_paths: Sequence[str]) -> list[str]:
    if (
        isinstance(changed_paths, (str, bytes))
        or not isinstance(changed_paths, Sequence)
        or len(changed_paths) > _MAX_REPORTED_CHANGED_PATHS
    ):
        raise ValueError("changed_paths must be a sequence of at most 256 members")
    paths: set[str] = set()
    for path in changed_paths:
        if not isinstance(path, str):
            raise ValueError("changed_paths must contain strings")
        paths.add(normalize_relative_path(path, allow_root=False))
    return sorted(paths)


def _diagnostic_path(path: object) -> str | None:
    if not isinstance(path, str):
        return None
    try:
        return normalize_relative_path(path, allow_root=False)
    except ValueError:
        return None


def _locality_rows(
    *,
    change_kind: str,
    diagnostics: Sequence[Mapping[str, object]],
    changed: set[str],
    qualified_ids: set[str],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for diagnostic in diagnostics:
        identity = str(diagnostic["identity"])
        path = _diagnostic_path(diagnostic.get("path"))
        if not changed or path is None:
            locality = "unknown"
        elif path in changed:
            locality = "on-reported-changed-path"
        else:
            locality = "outside-reported-changed-paths"
        result.append(
            {
                "diagnostic_identity": identity,
                "change_kind": change_kind,
                "path": path,
                "locality": locality,
                "collection_qualification": (
                    "qualified" if identity in qualified_ids else "unqualified"
                ),
                "basis": "caller-reported-changed-paths-and-external-diagnostic-path",
                "causality": "not-asserted",
            }
        )
    return result


def diagnostic_path_locality(
    *,
    added: Sequence[Mapping[str, object]],
    removed: Sequence[Mapping[str, object]],
    changed_paths: Sequence[str],
    qualification: Mapping[str, object],
) -> dict[str, object]:
    """Partition changed diagnostic facts without inferring cross-file effects.

    The existing diagnostic delta owns fact identities, additions/removals,
    and collection qualification. This projection references those same
    identities without altering or independently validating their authority.
    """
    normalized = normalize_reported_changed_paths(changed_paths)
    changed = set(normalized)
    qualified_added = set(qualification["qualified_added_identities"])
    qualified_removed = set(qualification["qualified_removed_identities"])
    rows = [
        *_locality_rows(
            change_kind="added",
            diagnostics=added,
            changed=changed,
            qualified_ids=qualified_added,
        ),
        *_locality_rows(
            change_kind="removed",
            diagnostics=removed,
            changed=changed,
            qualified_ids=qualified_removed,
        ),
    ]
    return {
        "schema": DIAGNOSTIC_PATH_LOCALITY_SCHEMA,
        "changed_paths": normalized,
        "change_scope": "caller-reported" if normalized else "unreported-or-empty",
        "change_set_completeness": "unknown",
        "rows": rows,
        "counts": {
            kind: {
                state: sum(
                    row["change_kind"] == kind and row["locality"] == state
                    for row in rows
                )
                for state in (
                    "on-reported-changed-path",
                    "outside-reported-changed-paths",
                    "unknown",
                )
            }
            for kind in ("added", "removed")
        },
        "basis": "external-diagnostic-identity-and-caller-reported-paths",
        "causality": "not-asserted",
        "authority": "descriptive-path-locality-only",
        "execution_effect": "none",
    }
