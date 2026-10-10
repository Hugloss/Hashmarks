"""SCIP translation into the direct producer relationship observation contract."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

from .diagnostic_provenance import COLLECTION_STATES, diagnostic_member_claims
from .diagnostic_source_revision import normalize_source_revision_claims
from .semantic_relationship_model import (
    CLAIM_LIMIT,
    ProducerRelationshipObservation,
    bounded_token,
    content_identity,
    direct_claim,
    portable_copy,
)
from .semantic_relationship_source import RelationshipSourceResolver

if TYPE_CHECKING:
    from .engine import CodeMap
    from .scip_adapter import ScipOccurrence


def scip_import_provenance(value: object, scope: Sequence[str]) -> dict[str, Any]:
    if value is None:
        return {
            "configuration_identity": None,
            "collection_state": "unknown",
            "capabilities": None,
            "source_revisions": {},
            "source_provenance": {},
        }
    manifest = portable_copy(value)
    fields = {
        "configuration_identity",
        "collection_state",
        "capabilities",
        "source_revisions",
        "source_provenance",
    }
    if not isinstance(manifest, Mapping) or set(manifest) - fields:
        raise ValueError("unsupported SCIP provenance manifest fields")
    configuration = manifest.get("configuration_identity")
    if configuration is not None:
        bounded_token(configuration, "configuration_identity")
    state = manifest.get("collection_state", "unknown")
    if state not in COLLECTION_STATES:
        raise ValueError("unsupported SCIP collection state")
    capabilities = manifest.get("capabilities")
    if capabilities is not None and not isinstance(capabilities, Mapping):
        raise ValueError("SCIP capabilities must be an object")
    revisions = (
        normalize_source_revision_claims(manifest.get("source_revisions"), scope) or {}
    )
    claims = diagnostic_member_claims(
        {**manifest, "source_revisions": revisions, "scope_paths": scope}
    )
    return {
        "configuration_identity": configuration,
        "collection_state": state,
        "capabilities": capabilities,
        "source_revisions": revisions,
        "source_provenance": claims.get("source_provenance") or {},
    }


def scip_occurrence_payload(
    occurrence: ScipOccurrence,
    observed_revision: str | None,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    metadata = occurrence.document_metadata or {}
    revision = provenance["source_revisions"].get(occurrence.path)
    representation = "member-bytes" if revision is not None else "utf8-document-text"
    return {
        "relationships": [
            {"kind": row.kind, "target_symbol": row.target_symbol}
            for row in occurrence.relationships
        ],
        "source_revision_observation": observed_revision,
        "source_revision_authority": "codemap-observed-at-scip-import",
        "producer_claimed_source_revision": revision
        or metadata.get("producer_text_revision"),
        "producer_source_revision_state": "producer-claimed"
        if revision or metadata.get("producer_text_revision")
        else "not-captured-by-scip-adapter",
        "revision_kind": representation,
        "text_encoding": metadata.get("text_encoding", "unknown"),
        "source_provenance": provenance["source_provenance"].get(occurrence.path),
        "locator": occurrence.locator,
        "relationship_only": occurrence.relationship_only,
        "declaration": occurrence.declaration_metadata,
        **(
            {"occurrence_roles": occurrence.occurrence_roles}
            if occurrence.occurrence_roles is not None
            else {}
        ),
    }


def _payload(row: Mapping[str, Any]) -> dict[str, Any]:
    value = json.loads(row["relationships_json"])
    return {"relationships": value} if isinstance(value, list) else dict(value)


def _snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "revision": payload.get("producer_claimed_source_revision"),
        "revision_kind": payload.get("revision_kind", "member-bytes"),
        "text_encoding": payload.get("text_encoding", "utf-8"),
        "provenance": payload.get("source_provenance"),
        "observed_at_import": payload.get("source_revision_observation"),
    }


def _symbol_key(producer: str, symbol: str, path: str) -> dict[str, Any]:
    return {
        "namespace": producer,
        "symbol": symbol,
        **({"document": path} if symbol.startswith("local ") else {}),
    }


def _source_endpoint(
    row: Mapping[str, Any],
    payload: Mapping[str, Any],
    resolver: RelationshipSourceResolver,
) -> dict[str, Any]:
    path = row["path"]
    locator = payload.get("locator")
    resolution = resolver.candidates(
        path, locator, _snapshot(payload), name=row["display_name"]
    )
    return {
        "key": _symbol_key(row["producer"], row["symbol"], path),
        "locator": None if locator is None else {**locator, "path": path},
        "definition_observed": not payload.get("relationship_only", False),
        "declaration": payload.get("declaration"),
        "provider_display_name": row["display_name"],
        "resolution": resolution,
        "source_binding": resolver.binding(path, _snapshot(payload)),
    }


def _target_endpoint(
    producer: str, symbol: str, source_path: str, resolver: RelationshipSourceResolver
) -> dict[str, Any]:
    rows = resolver.codemap.store.native_definitions_for_symbol(
        symbol,
        producer=producer,
        document_path=source_path if symbol.startswith("local ") else None,
    )
    candidates = []
    for row in rows[:64]:
        if resolver.admitted(row["path"]):
            candidates.append(_source_endpoint(row, _payload(row), resolver))
    mapped = [
        item
        for candidate in candidates
        for item in candidate["resolution"]["candidates"]
    ]
    state = (
        "incomplete-candidate-search"
        if len(rows) > 64
        else "unique-candidate"
        if len(candidates) == 1
        and candidates[0]["resolution"]["state"] == "unique-candidate"
        else "ambiguous-candidates"
        if len(candidates) > 1 or len(mapped) > 1
        else "unresolved"
    )
    return {
        "key": _symbol_key(producer, symbol, source_path),
        "resolution": {
            "state": state,
            "candidates": candidates,
            "truncated": len(rows) > 64,
            "negative_evidence_admissible": False,
        },
    }


def _claim_rows(
    codemap: CodeMap,
    target: Mapping[str, Any],
    producer: str,
    metadata: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    direct = [
        row
        for row in codemap.store.native_definitions_for_path(
            str(target["path"]),
            name=str(target["name"]),
            line=int(target["start_line"]),
            producer=producer,
        )
        if row["producer"] == producer
    ]
    subjects = [str(row["symbol"]) for row in direct]
    incoming = codemap.store.native_relationships_mentioning(
        subjects, producer=producer, document_path=str(target["path"])
    )
    unlocated = [
        row
        for row in metadata.get("unlocated_relationship_claims", [])
        if (row["path"] == target["path"] and row["display_name"] == target["name"])
        or any(
            item["target_symbol"] in subjects for item in _payload(row)["relationships"]
        )
    ]
    direct_keys = {(row["path"], row["symbol"], row["line"]) for row in direct}
    selected = list(
        {
            (row["path"], row["symbol"], row["line"]): row
            for row in [*direct, *incoming, *unlocated]
        }.values()
    )
    scoped = []
    for row in selected:
        payload = _payload(row)
        direct_source = (row["path"], row["symbol"], row["line"]) in direct_keys or (
            row["path"] == target["path"] and row["display_name"] == target["name"]
        )
        if not direct_source:
            payload["relationships"] = [
                item
                for item in payload["relationships"]
                if item["target_symbol"] in subjects
                and (
                    not item["target_symbol"].startswith("local ")
                    or row["path"] == target["path"]
                )
            ]
        scoped.append({**row, "relationships_json": json.dumps(payload)})
    return scoped, len(incoming) >= CLAIM_LIMIT + 1 or len(direct) >= CLAIM_LIMIT + 1


def _producer_observation(
    codemap: CodeMap,
    target: Mapping[str, Any],
    producer: str,
    resolver: RelationshipSourceResolver,
) -> dict[str, Any]:
    metadata = cast(
        "dict[str, Any]", codemap._evidence_snapshot("scip", producer) or {}
    )
    fresh, reason = codemap._evidence_fresh("scip", producer)
    provenance = metadata.get("relationship_provenance", {})
    observation = ProducerRelationshipObservation(
        producer=producer,
        configuration_identity=provenance.get("configuration_identity"),
        scope={
            "subject": f"{target['path']}::{target['qualname']}",
            "selection": "explicit-claims-mentioning-subject",
            "direction": "producer-asserted-source-to-target",
        },
        capability={
            "declared": provenance.get("capabilities"),
            "authority": "producer-claimed",
            "unobserved_kinds_meaning": "unknown-not-unsupported",
        },
        collection_state=provenance.get("collection_state", "unknown"),
        capture_identity=metadata.get("relationship_capture_identity")
        or content_identity(metadata),
        freshness="current" if fresh else "stale",
    )
    rows, search_truncated = _claim_rows(codemap, target, producer, metadata)
    observation.accounting = {
        "selected_definitions": len(rows),
        "denied_or_unadmitted": metadata.get("relationship_import_excluded", 0),
        "omitted_claims": 0,
        "unlocated_import_omitted": metadata.get("unlocated_relationship_omitted", 0),
    }
    observation.truncated = (
        search_truncated
        or len(rows) >= CLAIM_LIMIT + 1
        or bool(metadata.get("unlocated_relationship_omitted"))
    )
    targets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows[:CLAIM_LIMIT]:
        _append_claims(row, observation, resolver, targets)
    observation.capability["freshness_reason"] = reason
    observation.source_bindings = list(
        {
            content_identity(binding): binding
            for binding in [
                *(
                    resolver.binding(row["path"], _snapshot(_payload(row)))
                    for row in rows[:CLAIM_LIMIT]
                    if resolver.admitted(row["path"])
                ),
                *(
                    candidate["source_binding"]
                    for claim in observation.claims
                    for candidate in claim["target"]["resolution"]["candidates"]
                ),
            ]
        }.values()
    )
    return observation.packet()


def _append_claims(
    row: Mapping[str, Any],
    observation: ProducerRelationshipObservation,
    resolver: RelationshipSourceResolver,
    targets: dict[tuple[str, str], dict[str, Any]],
) -> None:
    if not resolver.admitted(row["path"]):
        observation.accounting["denied_or_unadmitted"] += 1
        return
    payload = _payload(row)
    source = _source_endpoint(row, payload, resolver)
    observation.truncated |= bool(row.get("relationships_truncated"))
    for item in payload["relationships"]:
        if len(observation.claims) >= CLAIM_LIMIT:
            observation.truncated = True
            observation.accounting["omitted_claims"] += 1
            continue
        key = (
            row["path"] if item["target_symbol"].startswith("local ") else "",
            item["target_symbol"],
        )
        if key not in targets:
            targets[key] = _target_endpoint(
                row["producer"], item["target_symbol"], row["path"], resolver
            )
        observation.claims.append(
            direct_claim(
                row["producer"],
                item["kind"],
                source,
                targets[key],
                {"format": "scip", "direction": "producer-asserted-source-to-target"},
            )
        )


def scip_relationship_observations(
    codemap: CodeMap, target: Mapping[str, Any], resolver: RelationshipSourceResolver
) -> list[dict[str, Any]]:
    producers = sorted(
        {
            str(row["producer"])
            for row in codemap._native_evidence_status()
            if row["kind"] == "scip"
        }
    )
    return [
        _producer_observation(codemap, target, producer, resolver)
        for producer in producers
    ]
