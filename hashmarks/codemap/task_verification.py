"""Task-taking verification views; the verifier consumes explicit evidence values."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.operation_contract import operation_response

from .decision_session import ReadScopeOwner, decision_scoped, diagnostic_producer
from .task_evidence_types import VerificationRelevance
from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS

if TYPE_CHECKING:
    from .repository_tasks import RepositoryTasks


class TaskVerificationMixin(ReadScopeOwner):
    @operation_response("verification_relevance")
    def verification_relevance(
        self,
        task: str,
        *,
        limit: int = VERIFICATION_RELEVANCE_DEFAULTS.limit,
        candidate_limit: int = VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit,
    ) -> VerificationRelevance:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        action = self.action_map(task, limit=limit)
        relevance = action.get("verification_relevance")
        if not isinstance(relevance, dict):
            raise RuntimeError("task action map did not produce verification relevance")
        return self.verification.bounded_relevance(relevance, candidate_limit)

    @operation_response("verification_ownership")
    def verification_ownership_graph(
        self,
        task: str,
        *,
        limit: int = VERIFICATION_RELEVANCE_DEFAULTS.limit,
        candidate_limit: int = VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        self.prepare(task, limit)
        return self._observe_verification_ownership(
            task, limit=limit, candidate_limit=candidate_limit
        )

    @decision_scoped
    def _observe_verification_ownership(
        self, task: str, *, limit: int, candidate_limit: int
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        action = self.action_map(task, limit=limit)
        relevance = action.get("verification_relevance")
        if not isinstance(relevance, dict):
            raise RuntimeError("task action map did not produce verification relevance")
        bounded = self.verification.bounded_relevance(relevance, candidate_limit)
        edit_paths = sorted(set(self.verification._verification_edit_paths(action)))
        authority = self.ownership.repository_graph(edit_paths) if edit_paths else None
        return self.verification.ownership_relationships(
            task, action, bounded, authority
        )

    @diagnostic_producer
    def explain_verification_selection(
        self,
        task: str,
        member_path: str | Path | None = None,
        *,
        limit: int = VERIFICATION_RELEVANCE_DEFAULTS.limit,
        candidate_limit: int = 16,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        self.prepare(task, limit)
        return self._observe_verification_explanation(
            task, member_path, limit=limit, candidate_limit=candidate_limit
        )

    @decision_scoped
    def _observe_verification_explanation(
        self,
        task: str,
        member_path: str | Path | None,
        *,
        limit: int,
        candidate_limit: int,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        relevance = self.verification_relevance(
            task, limit=limit, candidate_limit=candidate_limit
        )
        return self.verification.explain_relevance(
            task, relevance, member_path, limit=limit, candidate_limit=candidate_limit
        )
