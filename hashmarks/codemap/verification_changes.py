"""One bounded, command-free projection of changed-set verification evidence.

The existing verification, source, project and correlation owners interpret
repository facts. This composition never decides verification sufficiency,
native collection, process layout or execution policy.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from hashmarks.freshness import freshness_state
from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.paths import normalize_relative_path
from hashmarks.verification_selection import (
    verification_member,
    verification_membership,
)

from .decision_session import (
    DecisionRefreshRequired,
    ReadScopeOwner,
    decision_scoped,
    reconcile_decision,
)
from .query_router import normalize_task_query
from .repository_observation import evidence_identity
from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS
from .verification_relevance_model import VerificationRequest

if TYPE_CHECKING:
    from .evidence_verification import RepositoryVerification


_MAX_CHANGED_PATHS = 256
_MAX_TARGETS = 1000
_MAX_PACKET_BYTES = 1_048_576
_REFERENCE_FIELDS = (
    "direct_reference",
    "indirect_reference",
    "reference_strength",
    "reference_symbols",
    "indirect_reference_symbols",
    "indirect_via_paths",
    "file_read_evidence",
)


def _changed_paths(paths: Sequence[str], limit: int) -> list[str]:
    if isinstance(paths, (str, bytes)) or not isinstance(paths, Sequence):
        raise ValueError("changed paths must be a sequence of repository paths")
    if len(paths) > _MAX_CHANGED_PATHS:
        raise ValueError(f"changed paths exceeds {_MAX_CHANGED_PATHS} entries")
    if type(limit) is not int or not 1 <= limit <= _MAX_TARGETS:
        raise ValueError(f"limit must be between 1 and {_MAX_TARGETS}")
    if any(not isinstance(path, str) or len(path) > 4096 for path in paths):
        raise ValueError(
            "each changed path must be a string of at most 4096 characters"
        )
    return sorted({normalize_relative_path(path, allow_root=False) for path in paths})


def _records(value: object) -> list[dict[str, object]]:
    return (
        [dict(row) for row in value if isinstance(row, Mapping)]
        if isinstance(value, list)
        else []
    )


def _consumer_scope(
    relevance: Mapping[str, object],
    support: Mapping[str, object],
    context: Mapping[str, object],
    asset: Mapping[str, object] | None,
) -> dict[str, object]:
    candidates = _records(relevance.get("candidates"))
    count = relevance.get("candidate_count")
    omitted = max(0, count - len(candidates)) if type(count) is int else 0
    bounded = relevance.get("completeness") == "incomplete"
    asset_scope = cast("Mapping[str, object]", asset["consumer_scope"]) if asset else {}
    truncated = (
        bounded
        or bool(omitted)
        or support.get("truncated") is True
        or context.get("truncation") == "truncated"
        or asset_scope.get("truncated") is True
    )
    incomplete = (
        truncated
        or support.get("completeness") == "incomplete"
        or context.get("completeness") == "incomplete"
        or asset_scope.get("completeness") == "incomplete"
    )
    return {
        "completeness": "incomplete" if incomplete else "unknown",
        "reference_search_completeness": relevance.get("completeness", "unknown"),
        "support_scope_completeness": support.get("completeness", "unknown"),
        "context_completeness": context.get("completeness", "unknown"),
        "truncated": truncated,
        "omitted_reference_candidates": omitted,
        "qualified_identity_ambiguous": relevance.get(
            "qualified_identity_ambiguous", False
        ),
        "negative_evidence_admissible": False,
        "reasons": [
            "dynamic-verification-consumers-not-exhaustively-observed",
            *cast("list[str]", relevance.get("search_bound_reasons", [])),
            *cast("list[str]", support.get("reasons", [])),
            *cast("list[str]", context.get("reasons", [])),
            *cast("list[str]", asset_scope.get("reasons", [])),
        ],
    }


def _supporting_members(value: object) -> list[dict[str, object]]:
    """Collect only explicit source-observation ledgers, not caller metadata."""
    if not isinstance(value, Mapping):
        return []
    return _records(value.get("supporting_source_members"))


class VerificationChangesMixin:
    """Compose verification observations for caller-selected changed paths."""

    def _changed_relevance(self, path: str, limit: int) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        scope = self.reads.scope
        assert scope is not None
        request = VerificationRequest(
            scope,
            normalize_task_query(path),
            "nominated",
            {"path": path},
            None,
            (),
        )
        relevance = dict(self.for_owner(request, limit=min(limit, 16)))
        # Shared indexed selection preserves stale bindings for its callers.
        # This producer owns reconciliation of the contributors it qualifies.
        for path in cast(
            "list[str]", relevance.get("unresolved_reference_identity_paths", [])
        ):
            self.source.ensure_current(path)
        return relevance

    def _changed_reference_members(
        self, path: str, candidate: Mapping[str, object]
    ) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        via = candidate.get("indirect_via_paths")
        paths = {path, str(candidate["path"])}
        if isinstance(via, list):
            paths.update(str(item) for item in via)
        members = _supporting_members(candidate)
        observed_paths = {str(member["path"]) for member in members}
        for member_path in sorted(paths | observed_paths):
            self.source.ensure_current(member_path)
        for member_path in sorted(paths - observed_paths):
            member, _raw = self.source.member(member_path)
            members.append(member)
        return members

    def _changed_reference(
        self, path: str, candidate: Mapping[str, object]
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        direct, indirect = (
            candidate.get("direct_reference"),
            candidate.get("indirect_reference"),
        )
        if not direct and not indirect:
            return None
        target = str(candidate["path"])
        if self._verification_path_kind(target)["kind"] != "verifier":
            return None
        members = self._changed_reference_members(path, candidate)
        if any(member.get("state") != "known-present" for member in members):
            return None
        relationship = self.relationship_evidence(
            source=path,
            target=target,
            classification="direct" if direct else "related",
            relation_kind="direct-reference"
            if direct
            else "bounded-indirect-reference",
            provenance=operation_schema("verification_relevance"),
        )
        payload = {
            **relationship,
            "relationship_identity": relationship["evidence_identity"],
            "reference_evidence": {
                key: candidate[key] for key in _REFERENCE_FIELDS if key in candidate
            },
            "supporting_source_members": members,
        }
        payload["evidence_identity"] = evidence_identity(
            "hashmarks.changed-verification-relationship.v1", payload
        )
        return payload

    def _changed_relationships(
        self,
        path: str,
        classification: Mapping[str, object],
        relevance: Mapping[str, object],
    ) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        relationships = [
            row
            for candidate in _records(relevance.get("candidates"))
            if (row := self._changed_reference(path, candidate)) is not None
        ]
        if classification["kind"] == "verifier":
            relationships.insert(
                0,
                self.relationship_evidence(
                    source=path,
                    target=path,
                    classification="direct",
                    relation_kind="changed-verifier",
                    provenance=str(classification["evidence_identity"]),
                ),
            )
        return relationships

    def _changed_path_observation(self, path: str, limit: int) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        self.source.ensure_current(path)
        source = self.source.observe(
            path, max_bytes=VERIFICATION_RELEVANCE_DEFAULTS.source_member_bytes
        )
        classification = self._verification_path_kind(path)
        context = self._verification_context(path)
        member = cast("Mapping[str, object]", source["member"])
        relevance = (
            self._changed_relevance(path, limit)
            if member.get("state") == "known-present"
            else {}
        )
        support = self._verification_support_scope(path, limit=limit)
        relationships = self._changed_relationships(path, classification, relevance)
        relationships.extend(_records(support.get("relationships")))
        asset = self._asset_observation(path, source)
        return {
            "path": path,
            "source": source,
            "classification": classification,
            "context": context,
            "relevance": relevance or None,
            "explanation": self.explain_relevance(path, relevance)
            if relevance
            else None,
            "support_scope": support,
            "relationships": relationships,
            "asset": asset,
            "consumer_scope": _consumer_scope(relevance, support, context, asset),
        }

    def _changed_target(self, path: str) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        nomination = self.nomination(path)
        # A whole changed file never narrows to a guessed individual test node.
        # Native parameterized membership belongs to an explicit collector report.
        return {
            "path": path,
            "member": verification_member(path) if nomination["available"] else None,
            "nomination": nomination,
            "context": self._verification_context(path),
        }

    @staticmethod
    def _changed_targets(changes: Sequence[Mapping[str, object]]) -> list[str]:
        return sorted(
            {
                str(relationship["target"])
                for change in changes
                for relationship in _records(change.get("relationships"))
            }
        )

    @staticmethod
    def _changed_member_ledger(
        changes: Sequence[Mapping[str, object]], targets: Sequence[Mapping[str, object]]
    ) -> list[dict[str, object]]:
        members: list[dict[str, object]] = []
        for change in changes:
            source = cast("Mapping[str, object]", change["source"])
            members.append(dict(cast("Mapping[str, object]", source["member"])))
            for key in ("classification", "context", "support_scope", "asset"):
                members.extend(_supporting_members(change.get(key)))
            for relationship in _records(change.get("relationships")):
                members.extend(_supporting_members(relationship))
        for target in targets:
            for key in ("nomination", "context"):
                members.extend(_supporting_members(target.get(key)))
        return members

    def _changed_recheck(
        self,
        changes: Sequence[Mapping[str, object]],
        targets: Sequence[Mapping[str, object]],
    ) -> None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        observed: dict[str, dict[str, object]] = {}
        for claimed in self._changed_member_ledger(changes, targets):
            path = str(claimed["path"])
            if claimed.get("state") not in {"known-present", "known-absent"}:
                continue
            if path not in observed:
                self.source.ensure_current(path)
                observed[path], _raw = self.source.member(path)
            if (
                self._nomination_member_correspondence(claimed, observed[path])
                != "matched"
            ):
                raise DecisionRefreshRequired(path)

    def _changed_repository(self) -> tuple[dict[str, object], str]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        generation, identity_generation, stale = self.reads.generation_status()
        return {
            "repository_identity": self.reads.repository_identity(),
            "source_identity": self.source.packet_identity(
                generation=generation,
                identity_generation=identity_generation,
                stale=stale,
            ),
            "codemap_generation": generation,
            "identity_generation": identity_generation,
        }, freshness_state(stale)

    @staticmethod
    def _changed_packet(
        paths: list[str],
        changes: list[dict[str, object]],
        targets: list[dict[str, object]],
        *,
        limit: int,
        target_count: int,
    ) -> dict[str, object]:
        members = [
            cast("Mapping[str, object]", row["member"])
            for row in targets
            if row["member"] is not None
        ]
        scopes = [
            cast("Mapping[str, object]", row["consumer_scope"]) for row in changes
        ]
        truncated = target_count > len(targets) or any(
            scope["truncated"] for scope in scopes
        )
        incomplete = truncated or any(
            scope["completeness"] == "incomplete" for scope in scopes
        )
        return {
            "schema": operation_schema("changed_set_verification"),
            "changed_paths": paths,
            "changes": changes,
            "targets": targets,
            "membership": verification_membership(members) if members else None,
            "membership_scope": "returned-source-qualified-logical-targets",
            "native_collection": "external-observation-required",
            "completeness": "incomplete" if incomplete else "unknown",
            "truncated": truncated,
            "negative_evidence_admissible": False,
            "bounds": {
                "changed_paths": _MAX_CHANGED_PATHS,
                "returned_targets": limit,
                "observed_target_count": target_count,
                "omitted_targets": target_count - len(targets),
                "reference_candidates_per_path": min(limit, 16),
                "packet_max_bytes": _MAX_PACKET_BYTES,
            },
            "authority": "repository-evidence-only",
            "execution_authority": "external",
            "result_authority": "external",
            "certification_authority": "external",
            "storage": "request-scoped-not-persisted",
        }

    @operation_response("changed_set_verification")
    @reconcile_decision
    @decision_scoped
    def changed_set(
        self: ReadScopeOwner,
        paths: Sequence[str],
        *,
        limit: int = 100,
        correlation_bundles: Sequence[Mapping[str, object]] | None = None,
        path_mappings: Sequence[Mapping[str, object]] | None = None,
        collection_report: object | None = None,
    ) -> dict[str, object]:
        """Observe changed sources and qualified logical verification targets.

        File-level membership is exact for the returned nominations only. It
        is not exhaustive consumer coverage or native collected test membership.
        Runtime observations and collector reports retain their original claims.
        """
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        normalized = _changed_paths(paths, limit)
        if path_mappings is not None and correlation_bundles is None:
            raise ValueError("path_mappings requires correlation_bundles")
        changes = [self._changed_path_observation(path, limit) for path in normalized]
        target_paths = self._changed_targets(changes)
        targets = [self._changed_target(path) for path in target_paths[:limit]]
        packet = self._changed_packet(
            normalized, changes, targets, limit=limit, target_count=len(target_paths)
        )
        packet["correlation"] = (
            self._collection_correlation.observe(
                correlation_bundles,
                path_mappings=path_mappings,
                include_relationships=False,
            )
            if correlation_bundles is not None
            else None
        )
        packet["collection"] = (
            self.observe_membership(collection_report)
            if collection_report is not None
            else None
        )
        self._changed_recheck(changes, targets)
        packet["repository"], packet["freshness"] = self._changed_repository()
        packet["evidence_identity"] = evidence_identity(
            operation_schema("changed_set_verification"), packet
        )
        if (
            len(json.dumps(packet, ensure_ascii=False, allow_nan=False).encode("utf-8"))
            > _MAX_PACKET_BYTES
        ):
            raise ValueError(
                "changed-set verification packet exceeds byte bound; reduce paths or limit"
            )
        return packet
