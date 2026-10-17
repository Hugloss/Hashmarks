"""Owner-independent verification observation values, without task services."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from hashmarks.operation_contract import operation_schema

if TYPE_CHECKING:
    from .decision_session import ReadScope
    from .query_router import NormalizedTaskQuery
    from .task_evidence_types import TaskCandidate, VerificationRelevance


def verification_without_edit_owner(current_path: str) -> VerificationRelevance:
    selected: TaskCandidate | None = None
    if current_path:
        selected = {
            "path": current_path,
            "selection_reason": "canonical-verification-without-edit-owner",
            "reference_symbols": [],
            "namespace_overlap": 0,
            "task_anchor_terms": [],
            "test_symbol": None,
        }
    return {
        "schema": operation_schema("verification_relevance"),
        "selected": selected,
        "candidates": [selected] if selected else [],
        "selection_reason": "no-edit-owner",
        "selection_changed": False,
        "authority": "bounded-index-evidence-not-verification-execution",
        "secret_knowledge_used": False,
    }


@dataclass(frozen=True)
class _VerificationSelectionState:
    generation: int
    identity_generation: int | None
    stale: bool
    verify: Mapping[str, object] | None
    action: Mapping[str, object]
    verification_digest: str


@dataclass(frozen=True)
class VerificationRequest:
    scope: ReadScope
    query: NormalizedTaskQuery
    owner_state: Literal["nominated", "admitted", "unresolved"]
    edit: Mapping[str, object] | None
    current_verify: Mapping[str, object] | None
    rows: tuple[Mapping[str, object], ...]
