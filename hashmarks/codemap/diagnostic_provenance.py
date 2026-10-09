"""Bounded producer-owned source provenance and per-member collection claims."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy

from hashmarks.paths import normalize_relative_path

COLLECTION_STATES = frozenset(
    {
        "fresh-complete",
        "fresh-partial",
        "timed-out",
        "unavailable",
        "source-mismatch",
        "unknown",
    }
)
_PROVENANCE_FIELDS = frozenset(
    {
        "producer_session",
        "document_lifetime",
        "document_version",
        "source_kind",
        "binding_basis",
    }
)


def _revision_scope(scope_paths: object) -> set[str]:
    """Resolve the explicit scope admitted for producer revision claims."""
    if (
        not isinstance(scope_paths, Sequence)
        or isinstance(scope_paths, (str, bytes))
        or any(not isinstance(path, str) for path in scope_paths)
    ):
        raise ValueError("scope_paths must be a sequence of strings")
    return {normalize_relative_path(path, allow_root=False) for path in scope_paths}


def _scoped_claims(
    value: object, scope_paths: object, *, field: str
) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or len(value) > 32:
        raise ValueError(f"{field} must be a mapping of at most 32 members")
    scope = _revision_scope(scope_paths)
    result: dict[str, object] = {}
    for raw, claim in value.items():
        if not isinstance(raw, str):
            raise ValueError(f"{field} paths must be strings")
        path = normalize_relative_path(raw, allow_root=False)
        if path not in scope or path in result:
            raise ValueError(
                f"{field} contains out-of-scope or duplicate normalized paths"
            )
        result[path] = claim
    return dict(sorted(result.items()))


def _provenance_claim(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _PROVENANCE_FIELDS:
        raise ValueError(
            "source_provenance requires the five declared provenance fields"
        )
    for field in ("producer_session", "document_lifetime"):
        token = value[field]
        if not isinstance(token, str) or not token or len(token) > 256:
            raise ValueError(
                f"source_provenance {field} must be a nonempty bounded string"
            )
    version = value["document_version"]
    if version is not None and (
        type(version) is not int or not -(2**31) <= version < 2**31
    ):
        raise ValueError(
            "source_provenance document_version must be an LSP integer or null"
        )
    if value["source_kind"] not in ("buffer", "disk"):
        raise ValueError("source_provenance source_kind must be buffer or disk")
    if value["binding_basis"] not in (
        "reported-version",
        "synchronized-request",
        "producer-snapshot",
        "unknown",
    ):
        raise ValueError("source_provenance binding_basis is unsupported")
    if value["binding_basis"] == "reported-version" and version is None:
        raise ValueError("reported-version binding requires document_version")
    return deepcopy(dict(value))


def normalize_source_provenance(
    value: object, scope_paths: object
) -> dict[str, dict[str, object]] | None:
    claims = _scoped_claims(value, scope_paths, field="source_provenance")
    return (
        None
        if claims is None
        else {path: _provenance_claim(claim) for path, claim in claims.items()}
    )


def normalize_collection_by_path(
    value: object, scope_paths: object
) -> dict[str, str] | None:
    claims = _scoped_claims(value, scope_paths, field="collection_by_path")
    if claims is None:
        return None
    result: dict[str, str] = {}
    for path, state in claims.items():
        if not isinstance(state, str) or state not in COLLECTION_STATES:
            raise ValueError("collection_by_path has an unsupported collection state")
        result[path] = state
    return result


def diagnostic_member_claims(packet: Mapping[str, object]) -> dict[str, object]:
    scope = packet.get("scope_paths", ())
    provenance = normalize_source_provenance(packet.get("source_provenance"), scope)
    collections = normalize_collection_by_path(packet.get("collection_by_path"), scope)
    revisions = packet.get("source_revisions")
    revision_paths = (
        {
            normalize_relative_path(key, allow_root=False)
            for key in revisions
            if isinstance(key, str)
        }
        if isinstance(revisions, Mapping)
        else set()
    )
    for path, claim in (provenance or {}).items():
        has_revision = path in revision_paths
        if has_revision != (claim["binding_basis"] != "unknown"):
            raise ValueError(
                "source_provenance binding basis contradicts source_revisions"
            )
    return {
        **({"source_provenance": provenance} if "source_provenance" in packet else {}),
        **(
            {"collection_by_path": collections}
            if "collection_by_path" in packet
            else {}
        ),
    }


def member_claim_delta(
    before: Mapping[str, object], after: Mapping[str, object], *, field: str
) -> dict[str, object]:
    prior = diagnostic_member_claims(before).get(field)
    later = diagnostic_member_claims(after).get(field)
    return {
        "before": prior,
        "after": later,
        "changed": prior != later,
        "claim_authority": "producer-claimed",
    }


def member_collection_states(packet: Mapping[str, object]) -> dict[str, str]:
    scope = _revision_scope(packet.get("scope_paths", ()))
    claims = normalize_collection_by_path(
        packet.get("collection_by_path"), scope_paths=tuple(scope)
    )
    if claims is not None:
        return {path: claims.get(path, "unknown") for path in scope}
    collection = packet.get("collection")
    state = collection.get("state") if isinstance(collection, Mapping) else None
    state = (
        state if isinstance(state, str) and state in COLLECTION_STATES else "unknown"
    )
    return dict.fromkeys(scope, state)
