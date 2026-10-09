"""Non-authoritative method retrieval within one explicit class scope."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from .model import EvidenceVisibility

if TYPE_CHECKING:
    from .engine import CodeMap


class TaskEvidenceScopedMethodMixin:
    def _task_evidence_named_class_scope(
        self, task: str
    ) -> tuple[str, str, EvidenceVisibility] | None:
        """Bind one explicitly named class to current visible repository symbols."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        terms = self._task_action_exact_identifier_terms(task)
        if re.search(r"\bmethod\b", task, flags=re.IGNORECASE) is None or not terms:
            return None
        indexed = self._session_exact_symbol_candidates(terms, limit=65)
        classes = [
            row
            for row in indexed
            if row.get("kind") == "class"
            and str(row.get("name") or "").lower() in terms
        ]
        if len(indexed) >= 65 or len(classes) != 1:
            return None
        owner = classes[0]
        path = str(owner.get("path") or "")
        qualname = str(owner.get("qualname") or "")
        if not path or not qualname:
            return None
        visibility = self._task_evidence_visibility(path)
        admitted = (
            visibility in {EvidenceVisibility.SOURCE, EvidenceVisibility.OUTLINE}
            and self.policy.decide(path).evidence_visibility
            is not EvidenceVisibility.DENY
            and self._indexed_path_current(path)
        )
        if not admitted:
            return None
        assert visibility is not None
        return path, qualname, visibility

    def _task_evidence_scoped_method_supplement(
        self,
        task: str,
        query_tokens: Sequence[tuple[str, ...]],
        frequencies: Mapping[str, int],
        total: int,
        existing_keys: set[tuple[str, str]],
    ) -> dict[str, object] | None:
        """Expose a lexical member of one named class without owner authority."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        scope = self._task_evidence_named_class_scope(task)
        if scope is None:
            return None
        path, qualname, visibility = scope
        members = [
            row
            for row in self._session_symbols_for_path(path)
            if row.get("kind") == "method" and str(row.get("parent") or "") == qualname
        ]
        scored = sorted(
            (
                (
                    self._task_evidence_symbol_relevance(
                        str(row.get("name") or ""), query_tokens, frequencies, total
                    ),
                    str(row.get("qualname") or ""),
                    row,
                )
                for row in members
            ),
            key=lambda item: (-item[0], item[1]),
        )
        for score, member_name, member in scored:
            if score <= 0:
                break
            key = (path, member_name)
            if key not in existing_keys:
                existing_keys.add(key)
                return self._task_evidence_supplement_row(
                    path, member, score=score, visibility=visibility
                )
        return None

    @staticmethod
    def _task_evidence_scip_owner_claim(
        packet: Mapping[str, object],
    ) -> Mapping[str, object] | None:
        """Use only the complete, admitted owner; never a retrieval candidate."""
        ownership = packet.get("ownership")
        if not isinstance(ownership, Mapping):
            return None
        if (
            ownership.get("status") != "resolved"
            or ownership.get("proof_scope_complete") is not True
            or ownership.get("authority") != "repository-ownership-only"
        ):
            return None
        owner = ownership.get("owner")
        return owner if isinstance(owner, Mapping) else None

    def _task_evidence_current_scip_symbol(
        self, owner: Mapping[str, object]
    ) -> Mapping[str, object] | None:
        """Rebind the admitted locator to an exact, visible current symbol."""
        path = str(owner.get("path") or "")
        qualname = str(owner.get("qualname") or "")
        if not path or not qualname:
            return None
        if self._task_evidence_visibility(path) not in {
            EvidenceVisibility.SOURCE,
            EvidenceVisibility.OUTLINE,
        }:
            return None
        if (
            self.policy.decide(path).evidence_visibility is EvidenceVisibility.DENY
            or not self._indexed_path_current(path)
        ):
            return None
        return self.store.symbol_at(path, qualname)

    def _task_evidence_attach_scip_discovery(
        self,
        packet: dict[str, object],
        supplied_observations: Sequence[Mapping[str, object]] = (),
        *,
        selection_generation: int | None = None,
    ) -> None:
        """Expose retained SCIP observations without changing task ownership."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if supplied_observations:
            packet["supplied_observation_accounting"] = {
                "received": len(supplied_observations),
                "retained": 0,
                "omitted": len(supplied_observations),
                "capture_identities": [
                    row["capture_identity"] for row in supplied_observations
                ],
                "reason": "task-owner-or-freshness-not-qualified",
            }
        owner = self._task_evidence_scip_owner_claim(packet)
        freshness = packet.get("freshness")
        if owner is None or not isinstance(freshness, Mapping):
            return
        if freshness.get("state") not in {"current", "unknown"}:
            return
        from .semantic_relationship_model import compact_relationships
        from .semantic_relationship_observation import semantic_relationship_observation

        with self.decision_session(expected_generation=selection_generation):
            current = self._task_evidence_current_scip_symbol(owner)
            if current is None:
                return
            observation = semantic_relationship_observation(
                self, current, supplied_observations
            )
            compact = compact_relationships(observation)
            discovery = self._scip_compact_discovery(current)
        if supplied_observations:
            retained = sum(
                "method" in row["scope"] for row in observation["observations"]
            )
            packet["supplied_observation_accounting"] = {
                "received": len(supplied_observations),
                "retained": retained,
                "omitted": len(supplied_observations) - retained,
                "capture_identities": [
                    row["capture_identity"] for row in supplied_observations
                ],
                "reason": "observation-bounds"
                if retained < len(supplied_observations)
                else "current-request-projection",
            }
        if (
            discovery is not None
            or supplied_observations
            or compact["observed_relationship_count"]
        ):
            packet["semantic_relationships"] = {
                **(discovery or compact),
                "repository_freshness": freshness["state"],
                "observed_relationship_count_scope": (
                    "exact-owner-scip-definition-outgoing"
                    if discovery is not None
                    else "explicit-producer-claims-associated-with-owner"
                ),
                "associated_observed_relationship_count": compact[
                    "observed_relationship_count"
                ],
                "associated_observed_relationship_count_scope": (
                    "explicit-producer-claims-associated-with-owner"
                ),
                "evidence": compact,
                "evidence_refs": {
                    "ownership": "/ownership",
                    "source": "/ownership/source_evidence",
                    "verification": "/verification",
                },
            }
