"""Qualify supplied membership against existing repository correlation evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from ._version import __version__
from .codemap.evidence_correlation_replay import validate_correlation_packet
from .codemap.repository_observation import evidence_identity
from .freshness import FRESHNESS_STATES
from .generation_domain import is_valid_generation
from .producer_identity import native_producer_implementation_identity
from .verification_collection import (
    COLLECTION_REPORT_SCHEMA,
    MAX_MEMBERSHIP_OBSERVATION_BYTES,
    MEMBERSHIP_OBSERVATION_SCHEMA,
    CollectionReport,
    collection_bundle,
    collection_inputs,
    collection_membership,
    normalize_collection_report,
    portable_value,
)

if TYPE_CHECKING:
    from .consumer_conformance import NativeConsumerValidation

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _rows(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return [_mapping(row, label) for row in value]


def _repository(correlation: Mapping[str, object]) -> dict[str, object]:
    evidence = _mapping(correlation.get("repository_evidence"), "repository evidence")
    repository = _mapping(evidence.get("repository"), "repository")
    if set(repository) != {
        "repository_identity",
        "source_identity",
        "codemap_generation",
        "identity_generation",
        "freshness",
    }:
        raise ValueError("repository provenance fields mismatch")
    for name in ("repository_identity", "source_identity"):
        if not isinstance(repository[name], str) or not str(repository[name]).strip():
            raise ValueError(f"{name} must be nonblank")
    if not is_valid_generation(repository["codemap_generation"]):
        raise ValueError("invalid CodeMap generation")
    identity_generation = repository["identity_generation"]
    if identity_generation is not None and not is_valid_generation(identity_generation):
        raise ValueError("invalid Identity generation")
    if repository["freshness"] not in FRESHNESS_STATES:
        raise ValueError("invalid repository freshness")
    return dict(repository)


def _correlated_anchors(
    report: CollectionReport, correlation: Mapping[str, object]
) -> list[Mapping[str, object]]:
    validate_correlation_packet(correlation, label="membership source correlation")
    if correlation.get("path_mappings") != [] or correlation.get(
        "definition_options"
    ) != {"include_relationships": False, "relationship_limit_per_path": None}:
        raise ValueError(
            "membership correlation must bind exact repository-relative members"
        )
    bundles = _rows(correlation.get("bundles"), "correlation bundles")
    if len(bundles) != 1:
        raise ValueError("membership correlation requires exactly one report bundle")
    bundle = bundles[0]
    expected = collection_bundle(report)
    for name in (
        "bundle_id",
        "producer",
        "provenance",
        "scope",
        "completeness",
        "truncation",
    ):
        if bundle.get(name) != expected[name]:
            raise ValueError(f"collection report/correlation {name} mismatch")
    _claim_authority(bundle)
    anchors = _rows(bundle.get("anchors"), "correlation anchors")
    claimed = _rows(expected["anchors"], "expected anchors")
    expected_claims = {
        str(row["anchor_id"]): {
            key: value for key, value in row.items() if key != "anchor_id"
        }
        for row in claimed
    }
    actual_claims = {str(row.get("anchor_id")): row.get("claims") for row in anchors}
    if len(actual_claims) != len(anchors) or actual_claims != expected_claims:
        raise ValueError("collection report/correlation source claims mismatch")
    return anchors


def _claim_authority(bundle: Mapping[str, object]) -> None:
    fixed = {
        "producer_authority": "caller-claimed",
        "provenance_authority": "caller-claimed",
        "repository_freshness_authority": "independent",
    }
    if any(bundle.get(key) != value for key, value in fixed.items()):
        raise ValueError("collection producer claims must remain caller-claimed")


def _qualified_equivalence(
    anchor: Mapping[str, object],
    bindings: Mapping[str, Mapping[str, object]],
    sources: Mapping[str, Mapping[str, object]],
) -> str:
    binding = bindings.get(str(anchor.get("repository_evidence_binding_id")), {})
    rows = _rows(binding.get("evidence"), "member evidence")
    resolution = _mapping(anchor.get("resolution"), "member resolution")
    if len(rows) != 1 or rows[0].get("state") != "known-present":
        return "unknown"
    if resolution.get("state") != "resolved-unique":
        return "unknown"
    source = sources.get(str(rows[0].get("path")), {})
    if source.get("state") != "known-present" or source.get("member_revision") != rows[
        0
    ].get("member_revision"):
        return "unknown"
    equivalence = _mapping(anchor.get("source_equivalence"), "source equivalence")
    return str(equivalence["state"])


def _source_equivalence(
    report: CollectionReport,
    correlation: Mapping[str, object],
    sources: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    anchors = _correlated_anchors(report, correlation)
    evidence = _mapping(correlation["repository_evidence"], "repository evidence")
    bindings = {
        str(row["binding_id"]): row for row in _rows(evidence["bindings"], "bindings")
    }
    states = [_qualified_equivalence(anchor, bindings, sources) for anchor in anchors]
    state = "unknown"
    if "mismatch" in states:
        state = "mismatch"
    elif states and all(value == "proven" for value in states):
        state = "proven"
    return {
        "state": state,
        "scope": "explicit-nominated-inputs",
        "input_count": len(collection_inputs(report)),
    }


def _source_members(
    report: CollectionReport, value: object
) -> dict[str, Mapping[str, object]]:
    rows = _rows(value, "source members")
    expected = {str(row["path"]) for row in collection_inputs(report)}
    indexed: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if set(row) - {
            "path",
            "state",
            "member_revision",
            "evidence_visibility",
            "index_state",
            "reason",
        }:
            raise ValueError("source member fields mismatch")
        path = row.get("path")
        if not isinstance(path, str) or path not in expected or path in indexed:
            raise ValueError("source member path set mismatch")
        if row.get("state") not in {
            "known-present",
            "known-absent",
            "unknown",
            "unsupported",
        }:
            raise ValueError("invalid source member state")
        _source_member_revision(row)
        indexed[path] = row
    if set(indexed) != expected:
        raise ValueError("source member coverage must match the nominated inputs")
    return indexed


def _source_member_revision(row: Mapping[str, object]) -> None:
    revision = row.get("member_revision")
    if revision is not None and (
        not isinstance(revision, str) or not _HEX64.fullmatch(revision)
    ):
        raise ValueError("invalid observed source member revision")
    if row.get("state") == "known-present":
        if (
            revision is None
            or row.get("evidence_visibility") != "source"
            or row.get("index_state") not in {"indexed", "unindexed"}
        ):
            raise ValueError("present source member requires a byte-observed revision")


def _producer(value: Mapping[str, object] | None) -> dict[str, object]:
    if value is None:
        return {
            "name": "hashmarks",
            "version": __version__,
            "implementation_identity": native_producer_implementation_identity(),
        }
    if (
        set(value) != {"name", "version", "implementation_identity"}
        or value.get("name") != "hashmarks"
    ):
        raise ValueError("invalid membership observation producer")
    version, identity = value["version"], value["implementation_identity"]
    if not isinstance(version, str) or not version.strip():
        raise ValueError("invalid Hashmarks version")
    if not isinstance(identity, str) or not _SHA256.fullmatch(identity):
        raise ValueError("invalid Hashmarks producer implementation identity")
    return dict(value)


def membership_observation(
    report: CollectionReport,
    correlation: Mapping[str, object],
    source_members: object,
    *,
    producer: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Compose source correspondence without assigning native collection authority."""
    sources = _source_members(report, source_members)
    payload: dict[str, object] = {
        "schema": MEMBERSHIP_OBSERVATION_SCHEMA,
        "producer": _producer(producer),
        "report": report,
        "report_identity": evidence_identity(COLLECTION_REPORT_SCHEMA, report),
        "membership": collection_membership(report),
        "repository": _repository(correlation),
        "source_members": [dict(sources[path]) for path in sorted(sources)],
        "source_equivalence": _source_equivalence(report, correlation, sources),
        "correlation": dict(correlation),
        "membership_authority": "caller-claimed",
        "collection_completeness_authority": "caller-claimed",
        "repository_absence": "not-inferred",
        "storage": "request-scoped-not-persisted",
        "authority": "repository-intelligence-only",
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
        "execution_effect": "none",
    }
    payload["observation_identity"] = evidence_identity(
        MEMBERSHIP_OBSERVATION_SCHEMA, payload
    )
    detached = portable_value(
        payload,
        label="membership observation",
        max_bytes=MAX_MEMBERSHIP_OBSERVATION_BYTES,
    )
    return dict(_mapping(detached, "membership observation"))


def _validated_observation(value: object) -> dict[str, object]:
    raw = _mapping(
        portable_value(
            value,
            label="membership observation",
            max_bytes=MAX_MEMBERSHIP_OBSERVATION_BYTES,
        ),
        "membership observation",
    )
    if raw.get("schema") != MEMBERSHIP_OBSERVATION_SCHEMA:
        raise ValueError("unsupported verification membership observation schema")
    retained_identity = evidence_identity(
        MEMBERSHIP_OBSERVATION_SCHEMA,
        {key: item for key, item in raw.items() if key != "observation_identity"},
    )
    if raw.get("observation_identity") != retained_identity:
        raise ValueError("verification membership observation identity mismatch")
    report = normalize_collection_report(raw.get("report"))
    rebuilt = membership_observation(
        report,
        _mapping(raw.get("correlation"), "correlation"),
        raw.get("source_members"),
        producer=_mapping(raw.get("producer"), "producer"),
    )
    if dict(raw) != rebuilt:
        raise ValueError(
            "verification membership observation contract or identity mismatch"
        )
    return rebuilt


def _normalized_observation(value: Mapping[str, object]) -> dict[str, object]:
    repository = _mapping(value["repository"], "repository")
    membership = value["membership"]
    selected = membership if isinstance(membership, Mapping) else {}
    return {
        "producer": value["producer"],
        **repository,
        "source_equivalence": value["source_equivalence"],
        "members": selected.get("members"),
        "membership_identity": selected.get("membership_identity"),
        "report_identity": value["report_identity"],
        "observation_identity": value["observation_identity"],
        "membership_authority": value["membership_authority"],
        "collection_completeness_authority": value["collection_completeness_authority"],
        "report": value["report"],
    }


def validate_membership_observation(
    value: object,
    *,
    expected_producer_implementation_identity: str | None = None,
    require_fresh: bool = False,
) -> NativeConsumerValidation:
    """Validate retained observation integrity; do not perform a live repository read."""
    reasons: list[str] = []
    normalized: dict[str, object] | None = None
    producer_identity: object = None
    try:
        observed = _validated_observation(value)
        producer_identity = _mapping(observed["producer"], "producer")[
            "implementation_identity"
        ]
        normalized = _normalized_observation(observed)
        if require_fresh and (
            normalized["freshness"] != "current"
            or _mapping(normalized["source_equivalence"], "source equivalence")["state"]
            != "proven"
        ):
            reasons.append("fresh-source-evidence-required")
    except (ValueError, TypeError, KeyError) as exc:
        reasons.append(f"invalid-membership-observation:{exc}")
    if (
        expected_producer_implementation_identity is not None
        and producer_identity != expected_producer_implementation_identity
    ):
        reasons.append("producer-implementation-identity-not-expected")
    return {
        "schema": "hashmarks.consumer-conformance.v1",
        "valid": not reasons,
        "reasons": reasons,
        "producer_implementation_identity": producer_identity,
        "identity_semantics": "opaque-hashmarks-issued",
        "normalized": normalized if not reasons else None,
        "authority": "repository-intelligence-only",
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
    }
