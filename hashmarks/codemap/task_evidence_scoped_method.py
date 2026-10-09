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

    def _task_evidence_attach_scip_discovery(
        self, packet: dict[str, object]
    ) -> None:
        """Expose native semantic facts only for a current, proven task owner."""
        ownership = packet.get("ownership")
        freshness = packet.get("freshness")
        if not isinstance(ownership, Mapping) or not isinstance(freshness, Mapping):
            return
        if (
            ownership.get("status") != "resolved"
            or ownership.get("proof_scope_complete") is not True
            or ownership.get("authority") != "repository-ownership-only"
            or freshness.get("state") != "current"
        ):
            return
        owner = ownership.get("owner")
        if not isinstance(owner, Mapping):
            return
        path = str(owner.get("path") or "")
        qualname = str(owner.get("qualname") or "")
        if not path or not qualname:
            return
        if self._task_evidence_visibility(path) not in {
            EvidenceVisibility.SOURCE,
            EvidenceVisibility.OUTLINE,
        }:
            return
        if (
            self.policy.decide(path).evidence_visibility is EvidenceVisibility.DENY
            or not self._indexed_path_current(path)
        ):
            return
        current = self.store.symbol_at(path, qualname)
        if current is None:
            return
        discovery = self._scip_compact_discovery(current)
        if discovery is not None:
            packet["semantic_relationships"] = discovery
