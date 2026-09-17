from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .decision_session import diagnostic_producer

if TYPE_CHECKING:
    from pathlib import Path

    from .engine import CodeMap


class VerificationExplanationMixin:
    """Bounded explanations over existing verification-selection semantics."""

    @staticmethod
    def _verification_reason_facts(
        row: Mapping[str, object],
    ) -> list[dict[str, object]]:
        facts: list[dict[str, object]] = []
        strength = str(row.get("reference_strength") or "none")
        if strength != "none":
            facts.append({"reason": "reference-evidence", "strength": strength})
        via = row.get("indirect_via_paths")
        if isinstance(via, list) and via:
            facts.append({"reason": "bounded-indirect-path", "paths": list(via)})
        namespace = row.get("namespace_terms")
        if isinstance(namespace, list) and namespace:
            facts.append({"reason": "namespace-locality", "terms": list(namespace)})
        anchors = row.get("task_anchor_terms")
        if isinstance(anchors, list) and anchors:
            facts.append({"reason": "task-anchor", "terms": list(anchors)})
        rank = row.get("canonical_rank")
        if isinstance(rank, int):
            facts.append({"reason": "canonical-rank", "rank": rank})
        return facts

    @diagnostic_producer
    def explain_verification_selection(
        self,
        task: str,
        member_path: str | Path | None = None,
        *,
        limit: int = 20,
        candidate_limit: int = 16,
    ) -> dict[str, object]:
        """Explain selection/non-selection without adding execution semantics."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        relevance = self.verification_relevance(
            task,
            limit=limit,
            candidate_limit=candidate_limit,
        )
        selected = relevance.get("selected")
        selected_row = selected if isinstance(selected, Mapping) else None
        selected_path = str(selected_row.get("path") or "") if selected_row else ""
        requested = (
            normalize_relative_path(member_path, allow_root=False)
            if member_path is not None
            else selected_path
        )
        candidates = relevance.get("candidates")
        rows = (
            [row for row in candidates if isinstance(row, Mapping)]
            if isinstance(candidates, list)
            else []
        )
        requested_row = next(
            (row for row in rows if str(row.get("path") or "") == requested), None
        )

        if requested and requested == selected_path and selected_row is not None:
            status = "selected"
            reason = str(relevance.get("selection_reason") or "selected-verification")
            facts = self._verification_reason_facts(selected_row)
        elif requested_row is not None:
            status = "not-selected"
            selected_score = (
                self._verification_candidate_score(selected_row)
                if selected_row is not None
                else None
            )
            requested_score = self._verification_candidate_score(requested_row)
            reason = (
                "lower-bounded-verification-evidence"
                if selected_score is not None and requested_score < selected_score
                else "canonical-selection-retained"
            )
            facts = self._verification_reason_facts(requested_row)
        else:
            status = "insufficient-evidence"
            reason = "not-in-bounded-candidate-set"
            facts = []

        generation, identity_generation, stale = self._generation_status()
        payload: dict[str, object] = {
            "schema": "hashmarks.verification-selection-explanation.v1",
            "repository_identity": self._repository_packet_identity(),
            "source_identity": self._source_packet_identity(
                generation=generation,
                identity_generation=identity_generation,
                stale=stale,
            ),
            "task_identity": self._packet_digest("hashmarks.task.v1", {"task": task}),
            "member": requested or None,
            "selected_member": selected_path or None,
            "status": status,
            "reason": reason,
            "facts": facts,
            "bounds": {"candidate_limit": min(int(candidate_limit), 16)},
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }
        payload["explanation_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.verification-selection-explanation.v1",
            payload,
        )
        return payload
