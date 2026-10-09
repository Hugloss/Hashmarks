"""Request-local external diagnostic observations and collection-qualified deltas.

The external producer owns acquisition, document synchronization and execution.
This owner preserves claims and compares supplied endpoints without a history store.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass

from hashmarks.operation_contract import operation_schema
from hashmarks.paths import normalize_relative_path

from .diagnostic_path_delta import _canonical_path, diagnostic_path_deltas
from .diagnostic_provenance import (
    COLLECTION_STATES,
    _revision_scope,
    diagnostic_member_claims,
    member_claim_delta,
    member_collection_states,
)
from .diagnostic_source_revision import (
    EXTERNAL_DIAGNOSTIC_OBSERVATION_SCHEMA,
    diagnostic_identity,
    diagnostic_revision_delta,
    normalize_source_revision_claims,
)
from .source_line_correspondence import diagnostic_line_correspondence

DIAGNOSTIC_DELTA_SCHEMA = operation_schema("evidence_comparison", "diagnostics")


@dataclass(frozen=True, slots=True)
class RepositoryGenerationBinding:
    repository_identity: str
    codemap_generation: int


def external_diagnostic_observation(  # noqa: PLR0913 - additive producer fields
    *,
    producer: str,
    binding: RepositoryGenerationBinding,
    diagnostics: Sequence[Mapping[str, object]],
    outcome: str,
    environment_identity: str | None = None,
    scope_paths: Sequence[str] = (),
    collection_state: str | None = None,
    source_revisions: Mapping[str, str] | None = None,
    source_provenance: Mapping[str, Mapping[str, object]] | None = None,
    collection_by_path: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Normalize externally produced diagnostics without executing the tool."""
    allowed_outcomes = {
        "pass",
        "fail",
        "not-run",
        "blocked-environment",
        "blocked-supply",
        "blocked-permission",
        "invalid-baseline",
        "stale",
    }
    if outcome not in allowed_outcomes:
        raise ValueError("unsupported external observation outcome")
    if collection_state is not None and collection_state not in COLLECTION_STATES:
        raise ValueError("unsupported diagnostic collection state")
    revisions = normalize_source_revision_claims(source_revisions, scope_paths)
    member_claims = diagnostic_member_claims(
        {
            "scope_paths": scope_paths,
            "source_revisions": revisions,
            **(
                {"source_provenance": source_provenance}
                if source_provenance is not None
                else {}
            ),
            **(
                {"collection_by_path": collection_by_path}
                if collection_by_path is not None
                else {}
            ),
        }
    )
    rows = []
    for raw in diagnostics:
        row = dict(raw)
        row["identity"] = diagnostic_identity(row)
        rows.append(row)
    rows.sort(key=lambda row: str(row["identity"]))
    return {
        "schema": EXTERNAL_DIAGNOSTIC_OBSERVATION_SCHEMA,
        "producer": producer,
        "repository_identity": binding.repository_identity,
        "codemap_generation": int(binding.codemap_generation),
        "environment_identity": environment_identity,
        "scope_paths": sorted(_revision_scope(scope_paths)),
        **({"source_revisions": revisions} if revisions is not None else {}),
        **member_claims,
        "outcome": outcome,
        "diagnostics": rows,
        "diagnostic_count": len(rows),
        "collection": (
            {"state": collection_state, "authority": "producer-claimed"}
            if collection_state is not None
            else None
        ),
        "authority": "observation-only",
        "execution_effect": "none",
    }


def _possible_diagnostic_relocations(
    before: Mapping[str, object],
    after: Mapping[str, object],
    removed: Sequence[Mapping[str, object]],
    added: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Non-authoritative candidates; never suppress added/removed evidence."""
    if before.get("repository_identity") != after.get(
        "repository_identity"
    ) or before.get("producer") != after.get("producer"):
        return []

    def facts(row: Mapping[str, object]) -> tuple[object, ...]:
        return tuple(
            row.get(field) for field in ("tool", "rule", "path", "symbol", "message")
        )

    old: dict[tuple[object, ...], list[Mapping[str, object]]] = {}
    new: dict[tuple[object, ...], list[Mapping[str, object]]] = {}
    for row in removed:
        old.setdefault(facts(row), []).append(row)
    for row in added:
        new.setdefault(facts(row), []).append(row)
    possible: list[dict[str, object]] = []
    for key in sorted(old, key=repr):
        before_rows = old[key]
        after_rows = new.get(key, [])
        if len(before_rows) != 1 or len(after_rows) != 1:
            continue
        prior, subsequent = before_rows[0], after_rows[0]
        if (
            prior.get("line") is None
            or subsequent.get("line") is None
            or (prior.get("line"), prior.get("column"))
            == (subsequent.get("line"), subsequent.get("column"))
        ):
            continue
        possible.append(
            {
                "before_identity": prior["identity"],
                "after_identity": subsequent["identity"],
                "before_line": prior["line"],
                "after_line": subsequent["line"],
                "path": prior.get("path"),
                "basis": "unique-equal-nonlocational-diagnostic-fields",
                "state": "possible",
                "identity_authority": False,
            }
        )
    return possible


def _diagnostic_claim_qualification(
    before: Mapping[str, object],
    after: Mapping[str, object],
    added: Sequence[Mapping[str, object]],
    removed: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Qualify diagnostic absence using declared external collection coverage.

    Raw identity additions/removals are retained; this only marks which
    claims can be drawn from producer-claimed collection completeness.
    """
    prior = before.get("collection")
    current = after.get("collection")
    prior_state = prior.get("state") if isinstance(prior, Mapping) else None
    current_state = current.get("state") if isinstance(current, Mapping) else None
    prior_scope = before.get("scope_paths")
    current_scope = after.get("scope_paths")
    before_paths = set(prior_scope) if isinstance(prior_scope, list) else set()
    after_paths = set(current_scope) if isinstance(current_scope, list) else set()
    collections_before = member_collection_states(before)
    collections_after = member_collection_states(after)
    contexts = (
        diagnostic_member_claims(before).get("source_provenance"),
        diagnostic_member_claims(after).get("source_provenance"),
    )
    same_context = all(
        (
            before.get("producer"),
            before.get("producer") == after.get("producer"),
            before.get("repository_identity"),
            before.get("repository_identity") == after.get("repository_identity"),
            before.get("environment_identity"),
            before.get("environment_identity") == after.get("environment_identity"),
            before.get("outcome") in {"pass", "fail"},
            after.get("outcome") in {"pass", "fail"},
        )
    )
    qualified_added = sorted(
        str(row["identity"])
        for row in added
        if same_context
        and _member_claim_context(contexts, _canonical_path(row.get("path")))
        and collections_before.get(_canonical_path(row.get("path")) or "")
        == "fresh-complete"
        and collections_after.get(_canonical_path(row.get("path")) or "")
        in {"fresh-complete", "fresh-partial"}
        and _canonical_path(row.get("path")) in before_paths & after_paths
    )
    qualified_removed = sorted(
        str(row["identity"])
        for row in removed
        if same_context
        and _member_claim_context(contexts, _canonical_path(row.get("path")))
        and collections_before.get(_canonical_path(row.get("path")) or "")
        in {"fresh-complete", "fresh-partial"}
        and collections_after.get(_canonical_path(row.get("path")) or "")
        == "fresh-complete"
        and _canonical_path(row.get("path")) in before_paths & after_paths
    )
    return {
        "schema": "hashmarks.diagnostic-delta-qualification.v1",
        "basis": "producer-claimed-collection-and-explicit-path-scope",
        "shared_context": same_context,
        "collection_before": prior_state or "unknown",
        "collection_after": current_state or "unknown",
        "qualified_added_identities": qualified_added,
        "qualified_removed_identities": qualified_removed,
        "unqualified_added_identities": sorted(
            {str(row["identity"]) for row in added} - set(qualified_added)
        ),
        "unqualified_removed_identities": sorted(
            {str(row["identity"]) for row in removed} - set(qualified_removed)
        ),
        "identity_authority": False,
        "execution_effect": "none",
    }


def _member_claim_context(contexts: tuple[object, object], path: object) -> bool:
    prior, later = contexts
    old = prior.get(path) if isinstance(prior, Mapping) else None
    new = later.get(path) if isinstance(later, Mapping) else None
    if old is None and new is None:
        return True
    if not isinstance(old, Mapping) or not isinstance(new, Mapping):
        return False
    return (
        old["binding_basis"] != "unknown"
        and new["binding_basis"] != "unknown"
        and all(
            old[field] == new[field]
            for field in ("producer_session", "document_lifetime")
        )
    )


def diagnostic_endpoint_claims(packet: Mapping[str, object]) -> dict[str, object]:
    scope = sorted(_revision_scope(packet.get("scope_paths", ())))
    revisions = normalize_source_revision_claims(packet.get("source_revisions"), scope)
    return {
        "scope_paths": scope,
        **({"source_revisions": revisions} if "source_revisions" in packet else {}),
        **diagnostic_member_claims(packet),
    }


def validated_diagnostic_endpoint(
    packet: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    if packet.get("schema") != EXTERNAL_DIAGNOSTIC_OBSERVATION_SCHEMA:
        raise ValueError("expected external diagnostic observation schema")
    diagnostic_endpoint_claims(packet)
    rows = packet.get("diagnostics")
    if not isinstance(rows, list) or packet.get("diagnostic_count") != len(rows):
        raise ValueError("diagnostic_count must account for all diagnostic rows")
    indexed: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("identity") != diagnostic_identity(
            row
        ):
            raise ValueError("diagnostic identity mismatch")
        indexed[str(row["identity"])] = row
    return indexed


def diagnostic_observation_delta(  # noqa: PLR0913 - explicit optional endpoint evidence
    before: Mapping[str, object],
    after: Mapping[str, object],
    *,
    changed_paths: Sequence[str] = (),
    before_source: Mapping[str, object] | None = None,
    after_source: Mapping[str, object] | None = None,
    change_set_complete: bool = False,
    relationship_evidence: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Compare diagnostic identities; counts alone are never delta authority."""

    before = {**before, **diagnostic_endpoint_claims(before)}
    after = {**after, **diagnostic_endpoint_claims(after)}
    old = validated_diagnostic_endpoint(before)
    new = validated_diagnostic_endpoint(after)
    old_ids = set(old)
    new_ids = set(new)
    added_ids = sorted(new_ids - old_ids)
    removed_ids = sorted(old_ids - new_ids)
    scope = _revision_scope(changed_paths)
    added = [deepcopy(new[identity]) for identity in added_ids]
    removed = [deepcopy(old[identity]) for identity in removed_ids]
    added_in_changed_scope = [
        row for row in added if _canonical_path(row.get("path")) in scope
    ]
    possible_relocations = _possible_diagnostic_relocations(
        before, after, removed, added
    )
    if (before_source is None) != (after_source is None):
        raise ValueError("source correspondence requires both endpoint observations")
    source_correspondence = (
        diagnostic_line_correspondence(
            candidates=possible_relocations,
            before_diagnostic=before,
            after_diagnostic=after,
            before_source=before_source,
            after_source=after_source,
        )
        if before_source is not None and after_source is not None
        else None
    )

    return {
        "schema": DIAGNOSTIC_DELTA_SCHEMA,
        "producer": after.get("producer"),
        "producer_context": {
            endpoint: {
                field: packet.get(field)
                for field in ("producer", "environment_identity")
            }
            for endpoint, packet in (("before", before), ("after", after))
        },
        "source_revisions": diagnostic_revision_delta(before, after),
        "scope_paths": {"before": before["scope_paths"], "after": after["scope_paths"]},
        "source_provenance": member_claim_delta(
            before, after, field="source_provenance"
        ),
        "collection_by_path": member_claim_delta(
            before, after, field="collection_by_path"
        ),
        "change_set": {
            "paths": sorted(scope),
            "completeness": "caller-claimed-complete"
            if change_set_complete
            else "unknown",
            "authority": "caller-claimed",
        },
        **(
            {"relationship_evidence": deepcopy(relationship_evidence)}
            if relationship_evidence is not None
            else {}
        ),
        "repository": {
            "before": before.get("repository_identity"),
            "after": after.get("repository_identity"),
            "changed": before.get("repository_identity")
            != after.get("repository_identity"),
        },
        "generation": {
            "before": before.get("codemap_generation"),
            "after": after.get("codemap_generation"),
        },
        "outcome": {
            "before": before.get("outcome"),
            "after": after.get("outcome"),
        },
        "collection": {
            "before": before.get("collection"),
            "after": after.get("collection"),
        },
        "diagnostics": {
            "before_count": len(old),
            "after_count": len(new),
            "added": added,
            "removed": removed,
            "unchanged_count": len(old_ids & new_ids),
            "added_in_changed_scope": added_in_changed_scope,
            "possible_relocations": possible_relocations,
            "source_correspondence": source_correspondence,
            "qualification": _diagnostic_claim_qualification(
                before, after, added, removed
            ),
            "path_deltas": diagnostic_path_deltas(
                before,
                after,
                (old, new),
                changed_paths=changed_paths,
                change_set_complete=change_set_complete,
                relationship_evidence=relationship_evidence,
            ),
        },
        "authority": "observation-only",
        "execution_effect": "none",
    }


def _delta_claim_axes(
    payload: Mapping[str, object], endpoint: str
) -> dict[str, object]:
    claims: dict[str, object] = {}
    for field in ("source_revisions", "source_provenance", "collection_by_path"):
        axis = payload.get(field)
        if (
            not isinstance(axis, Mapping)
            or axis.get("claim_authority") != "producer-claimed"
        ):
            raise ValueError(f"diagnostic delta {field} must preserve claim authority")
        if type(axis.get("changed")) is not bool or axis["changed"] != (
            axis.get("before") != axis.get("after")
        ):
            raise ValueError(
                f"diagnostic delta {field} change flag contradicts endpoints"
            )
        claims[field] = axis.get(endpoint)
    return claims


def _delta_endpoint_claims(
    payload: Mapping[str, object], endpoint: str
) -> dict[str, object]:
    scope = payload.get("scope_paths")
    if not isinstance(scope, Mapping):
        raise ValueError("diagnostic delta scope_paths must retain both endpoints")
    packet: dict[str, object] = {"scope_paths": scope.get(endpoint)}
    context = payload.get("producer_context")
    if not isinstance(context, Mapping) or not isinstance(
        context.get(endpoint), Mapping
    ):
        raise ValueError(
            "diagnostic producer_context must retain both endpoint contexts"
        )
    packet.update(context[endpoint])
    if set(context[endpoint]) != {"producer", "environment_identity"}:
        raise ValueError("diagnostic producer_context has unsupported fields")
    packet.update(_delta_claim_axes(payload, endpoint))
    for field, key in (
        ("collection", "collection"),
        ("outcome", "outcome"),
        ("repository", "repository_identity"),
        ("generation", "codemap_generation"),
    ):
        axis = payload.get(field)
        if not isinstance(axis, Mapping):
            raise ValueError(f"diagnostic delta {field} must retain both endpoints")
        packet[key] = axis.get(endpoint)
    return {**packet, **diagnostic_endpoint_claims(packet)}


def _path_identity_index(
    rows: Sequence[Mapping[str, object]], field: str
) -> dict[str, Mapping[str, object]]:
    indexed: dict[str, Mapping[str, object]] = {}
    for row in rows:
        ids = row.get(field)
        if not isinstance(ids, list) or any(
            not isinstance(identity, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", identity) is None
            for identity in ids
        ):
            raise ValueError("path delta identities must be SHA-256 identity lists")
        if ids != sorted(set(ids)) or any(identity in indexed for identity in ids):
            raise ValueError("path delta identities must be unique and sorted")
        for identity in ids:
            indexed[identity] = {"path": row.get("path"), "identity": identity}
    return indexed


def _validate_delta_conservation(
    value: Mapping[str, object],
    old: Mapping[str, Mapping[str, object]],
    new: Mapping[str, Mapping[str, object]],
) -> None:
    expected_counts = {
        "before_count": len(old),
        "after_count": len(new),
        "unchanged_count": len(set(old) & set(new)),
    }
    if any(
        type(value.get(field)) is not int or value[field] != count
        for field, count in expected_counts.items()
    ):
        raise ValueError("diagnostic delta counts contradict path membership")
    for field, endpoint, expected in (
        ("added", new, set(new) - set(old)),
        ("removed", old, set(old) - set(new)),
    ):
        rows = value.get(field)
        if not isinstance(rows, list) or any(
            not isinstance(row, Mapping)
            or row.get("identity") != diagnostic_identity(row)
            for row in rows
        ):
            raise ValueError(
                "diagnostic delta identities do not match raw diagnostic facts"
            )
        if len(rows) != len(expected) or {row["identity"] for row in rows} != expected:
            raise ValueError("diagnostic delta does not conserve raw identity changes")
        for row in rows:
            raw_path = row.get("path")
            try:
                path = (
                    normalize_relative_path(raw_path, allow_root=False)
                    if isinstance(raw_path, str)
                    else None
                )
            except ValueError:
                path = None
            if endpoint[str(row["identity"])]["path"] != path:
                raise ValueError(
                    "diagnostic delta path contradicts raw diagnostic facts"
                )


def validated_diagnostic_delta(payload: Mapping[str, object]) -> dict[str, object]:
    """Re-prove the optional per-path projection against its retained raw facts."""
    value = payload.get("diagnostics")
    if not isinstance(value, Mapping) or "path_deltas" not in value:
        return {}
    rows = value["path_deltas"]
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("diagnostic path_deltas must be a list of objects")
    before, after = (
        _delta_endpoint_claims(payload, "before"),
        _delta_endpoint_claims(payload, "after"),
    )
    old, new = (
        _path_identity_index(rows, "before_identities"),
        _path_identity_index(rows, "after_identities"),
    )
    _validate_delta_conservation(value, old, new)
    expected_qualification = _diagnostic_claim_qualification(
        before, after, value["added"], value["removed"]
    )
    if value.get("qualification") != expected_qualification:
        raise ValueError(
            "diagnostic qualification contradicts retained endpoint claims"
        )
    change_set = payload.get("change_set")
    if (
        not isinstance(change_set, Mapping)
        or change_set.get("authority") != "caller-claimed"
        or change_set.get("completeness") not in ("unknown", "caller-claimed-complete")
    ):
        raise ValueError(
            "diagnostic change_set must preserve caller-claimed completeness"
        )
    changed = sorted(_revision_scope(change_set.get("paths")))
    relationships = payload.get("relationship_evidence")
    if relationships is not None and not isinstance(relationships, Mapping):
        raise ValueError("diagnostic relationship_evidence must be an object")
    expected = diagnostic_path_deltas(
        before,
        after,
        (old, new),
        changed_paths=changed,
        change_set_complete=change_set["completeness"] == "caller-claimed-complete",
        relationship_evidence=relationships,
    )
    if rows != expected:
        raise ValueError("diagnostic path deltas contradict retained endpoint evidence")
    return {
        "diagnostic_path_deltas": deepcopy(rows),
        "diagnostic_change_set": deepcopy(change_set),
        "diagnostic_scope_paths": deepcopy(payload["scope_paths"]),
        **{
            field: deepcopy(payload[field])
            for field in ("source_revisions", "source_provenance", "collection_by_path")
        },
    }
