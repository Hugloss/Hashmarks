"""Pure replay of retained dependency/verifier composition.

Content integrity and correspondence are not producer authentication or live
source freshness. Consumers obtain current observations separately.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from hashmarks.codemap.dependency_resolution_correlation import _ownership_summary
from hashmarks.codemap.dependency_resolution_evidence import (
    DependencyResolutionEvidenceMixin,
)
from hashmarks.codemap.dependency_resolution_query import (
    MAX_QUERIES,
    dependency_queries,
)
from hashmarks.codemap.dependency_verification import (
    MAX_CHAINS,
    packet_identity,
    path_requests,
    verification_chains,
    verification_request,
)
from hashmarks.codemap.repository_observation import evidence_identity
from hashmarks.operation_contract import operation_schema
from hashmarks.verification_nomination_validation import (
    validate_verification_nomination,
)
from hashmarks.verification_selection import (
    verification_member,
    verification_membership,
)

_FIELDS = frozenset(
    {
        "schema",
        "request",
        "observation_identity",
        "consumer_packet",
        "path_requests",
        "path_queries",
        "verification_packets",
        "chains",
        "completeness",
        "negative_evidence_admissible",
        "authority",
        "producer_authority",
        "execution_authority",
        "result_authority",
        "certification_authority",
        "storage",
        "evidence_identity",
    }
)
_REQUEST_FIELDS = frozenset(
    {
        "source_paths",
        "node_ids",
        "context",
        "max_dependency_depth",
        "consumer_limit",
        "verification_limit",
        "dependency_pairs",
    }
)


def _record(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _records(value: object, label: str, maximum: int) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{label} must be a bounded list")
    return [_record(row, label) for row in value]


def _target_members(
    targets: Sequence[Mapping[str, object]],
    relationships: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    members = []
    for target in targets:
        path = target.get("path")
        nomination = _record(target.get("nomination"), "verification nomination")
        if not validate_verification_nomination(nomination)["valid"]:
            raise ValueError("invalid verifier nomination")
        if not any(row.get("target") == path for row in relationships):
            raise ValueError("verifier lacks a source relationship")
        member = verification_member(str(path)) if nomination["available"] else None
        if target.get("member") != member:
            raise ValueError("verifier member differs from nomination")
        nominated = (
            _record(nomination["verification_target"], "verification target")
            if nomination["available"]
            else {"path": nomination["path"]}
        )
        if nominated.get("path") != path:
            raise ValueError("verifier path differs from nomination")
        if member is not None:
            members.append(member)
    return members


def _changed_packet(
    value: Mapping[str, object], source: str, binding: object, limit: int
) -> None:
    payload = {key: item for key, item in value.items() if key != "evidence_identity"}
    if (
        value.get("schema") != operation_schema("changed_set_verification")
        or value.get("changed_paths") != [source]
        or evidence_identity(str(value.get("schema")), payload)
        != value.get("evidence_identity")
    ):
        raise ValueError("changed verification identity or source mismatch")
    repository = _record(value.get("repository"), "verification repository")
    endpoint = _record(binding, "dependency repository binding")
    if any(
        repository.get(key) != endpoint.get(key)
        for key in ("repository_identity", "codemap_generation")
    ):
        raise ValueError("verification repository differs from dependency observation")
    changes = _records(value.get("changes"), "verification changes", 1)
    if len(changes) != 1 or changes[0].get("path") != source:
        raise ValueError("verification changes differ from source")
    targets = _records(value.get("targets"), "verification targets", limit)
    relationships = _records(
        changes[0].get("relationships"), "verification relationships", 1000
    )
    members = _target_members(targets, relationships)
    expected = verification_membership(members) if members else None
    if value.get("membership") != expected:
        raise ValueError("verification membership differs from returned nominations")


def _consumers(
    packet: Mapping[str, object],
    request: Mapping[str, object],
    observation: Mapping[str, object],
) -> list[str]:
    if (
        packet.get("schema") != operation_schema("dependency_consumers")
        or packet.get("observation_identity") != observation["observation_identity"]
        or packet.get("repository_binding") != observation["repository_binding"]
        or packet.get("selected_node_ids") != request["node_ids"]
    ):
        raise ValueError("dependency consumer packet binding mismatch")
    scope = _record(packet.get("source_scope"), "dependency source scope")
    if scope.get("paths") != request["source_paths"]:
        raise ValueError("dependency source scope differs from request")
    ledger = _records(scope.get("members"), "source members", 64)
    members = {str(row["path"]): row for row in ledger}
    if sorted(members) != request["source_paths"] or len(members) != len(ledger):
        raise ValueError("dependency source members differ from request")
    sources: set[str] = set()
    for row in _records(
        packet.get("consumers"),
        "dependency consumers",
        cast("int", request["consumer_limit"]),
    ):
        if row.get("source_member") != members.get(str(row.get("source_path"))):
            raise ValueError("consumer source revision differs from source scope")
        _consumer_ownership(row, observation)
        if row.get("distribution_state") == "resolved-unique":
            nodes = cast("list[str]", row.get("distribution_nodes"))
            if not set(nodes) <= set(cast("list[str]", request["node_ids"])):
                raise ValueError("unique consumer owner is outside selected node scope")
            sources.add(str(row["source_path"]))
    return sorted(sources)


def _consumer_ownership(
    row: Mapping[str, object], observation: Mapping[str, object]
) -> None:
    matches = _records(row.get("matched_modules"), "module ownership", 4096)
    if any(
        match not in cast("list[dict[str, object]]", observation["module_ownership"])
        for match in matches
    ):
        raise ValueError(
            "consumer ownership differs from qualified dependency observation"
        )
    summary = _ownership_summary(matches)
    if any(row.get(key) != item for key, item in summary.items()):
        raise ValueError("consumer ownership projection differs from producer rows")


def _request(
    packet: Mapping[str, object], observation: Mapping[str, object]
) -> dict[str, object]:
    request = _record(packet["request"], "dependency verification request")
    if (
        set(request) != _REQUEST_FIELDS
        or any(
            type(request[key]) is not int
            for key in ("max_dependency_depth", "consumer_limit")
        )
        or verification_request(
            observation,
            source_paths=cast("Sequence[str]", request["source_paths"]),
            node_ids=cast("Sequence[str]", request["node_ids"]),
            context=cast("str | None", request["context"]),
            verification_limit=cast("int", request["verification_limit"]),
            dependency_pairs=cast(
                "Sequence[Mapping[str, str]]", request["dependency_pairs"]
            ),
        )
        != request
    ):
        raise ValueError("dependency verification request mismatch")
    return request


def _verification_packets(
    packet: Mapping[str, object],
    consumers: Mapping[str, object],
    request: Mapping[str, object],
    observation: Mapping[str, object],
) -> list[dict[str, object]]:
    sources = _consumers(consumers, request, observation)
    verifications = _records(packet["verification_packets"], "verification packets", 64)
    if len(verifications) != len(sources):
        raise ValueError("verification sources differ from dependency consumers")
    for source, verification in zip(sources, verifications, strict=True):
        _changed_packet(
            verification,
            source,
            observation["repository_binding"],
            cast("int", request["verification_limit"]),
        )
        change = cast("list[dict[str, object]]", verification["changes"])[0]
        member = _record(change["source"], "changed source")["member"]
        for consumer in cast("list[dict[str, object]]", consumers["consumers"]):
            if (
                consumer["source_path"] == source
                and consumer["source_member"] != member
            ):
                raise ValueError(
                    "consumer and verifier observe different source revisions"
                )
    return verifications


def _chain_indices(packet: Mapping[str, object]) -> None:
    for chain in _records(
        packet["chains"], "dependency verification chains", MAX_CHAINS
    ):
        if any(
            type(chain[key]) is not int
            for key in ("consumer_index", "verification_index", "target_index")
        ):
            raise ValueError("dependency verification chain indices must be integers")
        if chain["query_index"] is not None and type(chain["query_index"]) is not int:
            raise ValueError(
                "dependency verification query index must be an integer or null"
            )
        indices = chain["relationship_indices"]
        if not isinstance(indices, list) or any(
            type(index) is not int for index in indices
        ):
            raise ValueError(
                "dependency verifier relationship indices must be integers"
            )


def _validate(value: object, observation: Mapping[str, object]) -> str:
    DependencyResolutionEvidenceMixin._require_qualified_dependency_observation_v3(
        observation
    )
    packet = _record(value, "dependency verification")
    if set(packet) != _FIELDS or packet["schema"] != operation_schema(
        "dependency_verification"
    ):
        raise ValueError("dependency verification fields or schema mismatch")
    payload = {key: item for key, item in packet.items() if key != "evidence_identity"}
    identity = packet_identity(payload)
    if (
        identity != packet["evidence_identity"]
        or packet["observation_identity"] != observation["observation_identity"]
    ):
        raise ValueError("dependency verification identity mismatch")
    request = _request(packet, observation)
    consumers = _record(packet["consumer_packet"], "dependency consumer packet")
    verifications = _verification_packets(packet, consumers, request, observation)
    requests = path_requests(request)
    queries = [
        dependency_queries(observation, requests[offset : offset + MAX_QUERIES])
        for offset in range(0, len(requests), MAX_QUERIES)
    ]
    if packet["path_requests"] != requests or packet["path_queries"] != queries:
        raise ValueError("dependency paths differ from qualified observation")
    _chain_indices(packet)
    if packet["chains"] != verification_chains(
        consumers,
        verifications,
        requests,
        queries,
        cast("str | None", request["context"]),
    ):
        raise ValueError("dependency verifier chains differ from producer evidence")
    constants = {
        "completeness": "incomplete",
        "negative_evidence_admissible": False,
        "authority": "repository-evidence-only",
        "producer_authority": "caller-claimed",
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
        "storage": "request-scoped-not-persisted",
    }
    if (
        any(packet[key] != expected for key, expected in constants.items())
        or packet["negative_evidence_admissible"] is not False
    ):
        raise ValueError("dependency verification authority mismatch")
    return identity


def validate_dependency_verification(
    value: object, observation: Mapping[str, object]
) -> dict[str, object]:
    """Replay retained composition, without reading source or authenticating it."""
    identity = None
    reasons: list[str] = []
    try:
        identity = _validate(value, observation)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        reasons.append(str(exc))
    return {
        "valid": not reasons,
        "reasons": reasons,
        "evidence_identity": identity if not reasons else None,
        "authority": "content-integrity-and-correspondence-only",
        "repository_binding": "not-reobserved",
        "producer_authenticity": "not-checked",
        "execution_authority": "external",
    }
