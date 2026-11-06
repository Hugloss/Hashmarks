"""Bounded dependency/import/verifier relationships, without execution policy."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from hashmarks.file_store import UnstableFileError
from hashmarks.operation_contract import operation_response, operation_schema

from .decision_session import ReadScopeOwner, decision_scoped, reconcile_decision
from .dependency_consumers import _paths, _selected_nodes
from .dependency_resolution_query import MAX_QUERIES
from .repository_observation import evidence_identity

if TYPE_CHECKING:
    from .repository_dependencies import RepositoryDependencies

MAX_PACKET_BYTES = 8_388_608
MAX_CHAINS = 16_384


def verification_request(
    observation: Mapping[str, object],
    *,
    source_paths: Sequence[str],
    node_ids: Sequence[str],
    context: str | None,
    verification_limit: int,
    dependency_pairs: Sequence[Mapping[str, str]],
) -> dict[str, object]:
    paths = _paths(source_paths)
    selections = _selected_nodes(observation, node_ids, 1000, 1)
    if type(verification_limit) is not int or not 1 <= verification_limit <= 1000:
        raise ValueError("dependency verification limit must be between 1 and 1000")
    if context is not None and (
        not isinstance(context, str)
        or context not in cast("Sequence[str]", observation["contexts"])
    ):
        raise ValueError(
            "dependency verification context must name an observed context"
        )
    if (
        isinstance(dependency_pairs, (str, bytes))
        or not isinstance(dependency_pairs, Sequence)
        or len(dependency_pairs) > 64
    ):
        raise ValueError("dependency verification requires at most 64 dependency pairs")
    pairs: set[tuple[str, str]] = set()
    for pair in dependency_pairs:
        if not isinstance(pair, Mapping) or set(pair) != {
            "source_node_id",
            "target_node_id",
        }:
            raise ValueError(
                "dependency verification pair requires exact source and target node IDs"
            )
        parent, child = pair["source_node_id"], pair["target_node_id"]
        if (
            not isinstance(parent, str)
            or not isinstance(child, str)
            or parent == child
            or parent not in selections.selected
            or child not in selections.selected
        ):
            raise ValueError(
                "dependency verification pair must join distinct selected nodes"
            )
        if (parent, child) in pairs:
            raise ValueError("duplicate dependency verification pair")
        pairs.add((parent, child))
    return {
        "source_paths": paths,
        "node_ids": sorted(selections.selected),
        "context": context,
        "max_dependency_depth": 1,
        "consumer_limit": 1000,
        "verification_limit": verification_limit,
        "dependency_pairs": [
            {"source_node_id": parent, "target_node_id": child}
            for parent, child in sorted(pairs)
        ],
    }


def path_requests(request: Mapping[str, object]) -> list[dict[str, object]]:
    return [
        {
            "operation": "paths",
            "node_id": pair["source_node_id"],
            "target_id": pair["target_node_id"],
            **(
                {"context": request["context"]}
                if request["context"] is not None
                else {}
            ),
            "max_depth": request["max_dependency_depth"],
            "max_results": 64,
            "max_visits": 4096,
        }
        for pair in cast("list[dict[str, str]]", request["dependency_pairs"])
    ]


def _complete_paths(
    requests: Sequence[Mapping[str, object]],
    queries: Sequence[Mapping[str, object]],
) -> dict[str, list[tuple[str, list[str], int | None]]]:
    paths: dict[str, list[tuple[str, list[str], int | None]]] = {}
    results = [
        result
        for batch in queries
        for result in cast("Sequence[Mapping[str, object]]", batch["results"])
    ]
    for index, (request, result) in enumerate(zip(requests, results, strict=True)):
        # A bounded/conditional path result is retained but cannot strengthen the
        # composed relationship. The consumer can widen or refuse its own work.
        if result["completeness"] == "complete" and result["omissions"] == []:
            for path in cast("list[list[str]]", result["result"]):
                paths.setdefault(str(request["node_id"]), []).append(
                    (str(request["target_id"]), path, index)
                )
    return paths


def _relationship_identity(row: Mapping[str, object]) -> bool:
    base = {
        key: row.get(key)
        for key in ("source", "target", "classification", "relation_kind", "provenance")
    }
    identity = evidence_identity("hashmarks.verification-relationship.v1", base)
    if (
        row.get("authority") != "repository-relationship-only"
        or row.get("execution_effect") != "none"
    ):
        return False
    if row.get("relation_kind") == "changed-verifier":
        return row.get("evidence_identity") == identity
    return row.get("relationship_identity") == identity and row.get(
        "evidence_identity"
    ) == evidence_identity(
        "hashmarks.changed-verification-relationship.v1",
        {**row, "evidence_identity": identity},
    )


def _qualified_reference(
    row: Mapping[str, object],
    source: Mapping[str, object],
    nomination: Mapping[str, object],
) -> bool:
    if not _relationship_identity(row) or row.get("source") != source.get("path"):
        return False
    kind = row.get("relation_kind")
    if kind == "changed-verifier":
        return (
            row.get("classification") == "direct"
            and row.get("target") == source.get("path")
            and nomination.get("source_member_revision")
            == source.get("member_revision")
        )
    classes = {"direct-reference": "direct", "bounded-indirect-reference": "related"}
    if (
        not isinstance(kind, str)
        or kind not in classes
        or row.get("classification") != classes[kind]
    ):
        return False
    members = row.get("supporting_source_members")
    if not isinstance(members, list) or not _member_in(members, source):
        return False
    target_member = {
        "path": row["target"],
        "state": "known-present",
        "member_revision": nomination["source_member_revision"],
    }
    return _member_in(members, target_member) and _reference_claim(row, members)


def _reference_claim(row: Mapping[str, object], members: list[object]) -> bool:
    evidence = row.get("reference_evidence")
    if not isinstance(evidence, Mapping) or row.get("provenance") != operation_schema(
        "verification_relevance"
    ):
        return False
    if row["relation_kind"] == "direct-reference":
        return evidence.get("direct_reference") is True
    paths = evidence.get("indirect_via_paths")
    if (
        evidence.get("indirect_reference") is not True
        or not isinstance(paths, list)
        or not paths
    ):
        return False
    present = {
        member.get("path")
        for member in members
        if isinstance(member, Mapping) and member.get("state") == "known-present"
    }
    return all(isinstance(path, str) and path in present for path in paths)


def _member_in(members: list[object], expected: Mapping[str, object]) -> bool:
    return any(
        isinstance(member, Mapping)
        and all(
            member.get(key) == expected.get(key)
            for key in ("path", "state", "member_revision")
        )
        for member in members
    )


def qualified_verifier_targets(packet: Mapping[str, object]) -> dict[int, list[int]]:
    """Preserve only source-qualified positive verifier relationships."""
    if packet.get("freshness") == "stale":
        return {}
    change = cast("list[dict[str, object]]", packet["changes"])[0]
    source = cast(
        "Mapping[str, object]", cast("Mapping[str, object]", change["source"])["member"]
    )
    if source.get("state") != "known-present" or source.get("path") != change["path"]:
        return {}
    relationships = cast("list[dict[str, object]]", change["relationships"])
    targets: dict[int, list[int]] = {}
    for index, target in enumerate(cast("list[dict[str, object]]", packet["targets"])):
        nomination = cast("Mapping[str, object]", target["nomination"])
        if nomination.get("available") is not True:
            continue
        indices = [
            position
            for position, row in enumerate(relationships)
            if row.get("target") == target["path"]
            and _qualified_reference(row, source, nomination)
        ]
        if indices:
            targets[index] = indices
    return targets


def verification_chains(
    consumers: Mapping[str, object],
    verifications: Sequence[Mapping[str, object]],
    requests: Sequence[Mapping[str, object]],
    queries: Sequence[Mapping[str, object]],
    context: str | None,
) -> list[dict[str, object]]:
    """Join only producer-qualified positive paths and exact source nominations."""
    sources = {
        str(cast("list[str]", packet["changed_paths"])[0]): (
            index,
            qualified_verifier_targets(packet),
        )
        for index, packet in enumerate(verifications)
    }
    paths = _complete_paths(requests, queries)
    chains: list[dict[str, object]] = []
    for consumer_index, consumer in enumerate(
        cast("Sequence[Mapping[str, object]]", consumers["consumers"])
    ):
        if consumer["distribution_state"] != "resolved-unique" or (
            context is not None
            and context not in cast("list[str]", consumer["observed_contexts"])
        ):
            continue
        source = str(consumer["source_path"])
        verification_index, targets = sources[source]
        for node in cast("list[str]", consumer["distribution_nodes"]):
            for target_index, relationship_indices in targets.items():
                for selected, path, query_index in [
                    (node, [node], None),
                    *paths.get(node, []),
                ]:
                    chains.append(
                        {
                            "node_id": selected,
                            "consumer_node_id": node,
                            "source_path": source,
                            "consumer_index": consumer_index,
                            "verification_index": verification_index,
                            "target_index": target_index,
                            "dependency_path": path,
                            "query_index": query_index,
                            "relationship_indices": relationship_indices,
                        }
                    )
                    if len(chains) > MAX_CHAINS:
                        raise ValueError(
                            "dependency verification chains exceed bound; reduce scope"
                        )
    return chains


def packet_identity(packet: Mapping[str, object]) -> str:
    try:
        raw = json.dumps(
            {**packet, "evidence_identity": "sha256:" + "0" * 64},
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("dependency verification packet must be bounded JSON") from exc
    if len(raw) > MAX_PACKET_BYTES:
        raise ValueError(
            "dependency verification packet exceeds byte bound; reduce scope"
        )
    return evidence_identity(operation_schema("dependency_verification"), packet)


class DependencyVerificationMixin(ReadScopeOwner):
    @operation_response("dependency_verification")
    @reconcile_decision
    @decision_scoped
    def verification(
        self,
        observation: Mapping[str, object],
        *,
        source_paths: Sequence[str],
        node_ids: Sequence[str],
        context: str | None = None,
        verification_limit: int = 2,
        dependency_pairs: Sequence[Mapping[str, str]] = (),
    ) -> dict[str, object]:
        """Observe selected dependency paths to imported sources and verifiers.

        Direct imports and dependency paths remain distinct. Empty or ambiguous
        observations never prove absence or verification sufficiency.
        """
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        request = verification_request(
            observation,
            source_paths=source_paths,
            node_ids=node_ids,
            context=context,
            verification_limit=verification_limit,
            dependency_pairs=dependency_pairs,
        )
        consumers = self.consumers(
            observation,
            source_paths=cast("list[str]", request["source_paths"]),
            node_ids=cast("list[str]", request["node_ids"]),
            limit=1000,
        )
        requests = path_requests(request)
        queries = [
            self.queries(observation, requests[offset : offset + MAX_QUERIES])
            for offset in range(0, len(requests), MAX_QUERIES)
        ]
        paths = sorted(
            {
                str(row["source_path"])
                for row in cast(
                    "Sequence[Mapping[str, object]]", consumers["consumers"]
                )
                if row["distribution_state"] == "resolved-unique"
            }
        )
        verifications = [
            self._verification.changed_set([path], limit=verification_limit)
            for path in paths
        ]
        # Recheck earlier consumers and all supporting source members after the
        # last composition, inside the same read lifetime and generation.
        for member in cast(
            "Sequence[Mapping[str, object]]",
            cast("Mapping[str, object]", consumers["source_scope"])["members"],
        ):
            current, _ = self.source.member(str(member["path"]))
            if current != member:
                raise UnstableFileError(
                    "dependency consumer source changed during verification"
                )
        for packet in verifications:
            self._verification._changed_recheck(
                cast("list[dict[str, object]]", packet["changes"]),
                cast("list[dict[str, object]]", packet["targets"]),
            )
        self._require_current_dependency_observation_v3(observation)
        result: dict[str, object] = {
            "schema": operation_schema("dependency_verification"),
            "request": request,
            "observation_identity": observation["observation_identity"],
            "consumer_packet": consumers,
            "path_requests": requests,
            "path_queries": queries,
            "verification_packets": verifications,
            "chains": verification_chains(
                consumers, verifications, requests, queries, context
            ),
            "completeness": "incomplete",
            "negative_evidence_admissible": False,
            "authority": "repository-evidence-only",
            "producer_authority": "caller-claimed",
            "execution_authority": "external",
            "result_authority": "external",
            "certification_authority": "external",
            "storage": "request-scoped-not-persisted",
        }
        result["evidence_identity"] = packet_identity(result)
        return result
