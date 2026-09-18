from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from .decision_session import incomplete_decision_scoped
from .evidence_verification import _VerificationSelectionState

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .engine import CodeMap


def _append_decision_candidate(
    row: object, candidates: list[dict[str, object]], seen: set[str]
) -> None:
    if not isinstance(row, dict):
        return
    path = str(row.get("path") or "")
    if not path or path in seen:
        return
    seen.add(path)
    candidates.append(
        {
            "path": path,
            "canonical_rank": int(row.get("canonical_rank") or 0),
            "roles": list(row.get("roles") or []),
        }
    )


@dataclass
class _DecisionPacketTiming:
    """Measure the existing packet phases within one projection call."""

    started: float = field(default_factory=time.perf_counter)
    phase_started: float = field(init=False)
    phase_seconds: dict[str, float] = field(default_factory=dict)
    total_seconds: float = 0.0

    def __post_init__(self) -> None:
        self.phase_started = self.started

    def begin_phase(self) -> None:
        self.phase_started = time.perf_counter()

    def record(self, phase: str) -> None:
        self.phase_seconds[phase] = time.perf_counter() - self.phase_started

    def finish(self) -> None:
        self.total_seconds = time.perf_counter() - self.started

    def as_payload(self, *, session_active: bool) -> dict[str, object]:
        return {
            "schema": "hashmarks.task-decision-metrics.v1",
            "seconds": {
                "action_map": self.phase_seconds["action_map"],
                "work_context": self.phase_seconds["work_context"],
                "verification_plan": self.phase_seconds["verification_plan"],
                "packet_assembly": self.phase_seconds["packet_assembly"],
                "total": self.total_seconds,
            },
            "session_active": session_active,
        }


class DecisionPacketMixin:
    @staticmethod
    def _decision_packet_candidates(
        action: Mapping[str, object],
        edit: Mapping[str, object] | None,
        verify: Mapping[str, object] | None,
    ) -> list[dict[str, object]]:
        """Project the bounded worker-visible candidate set used by ambiguity-discrimination evidence."""
        candidates: list[dict[str, object]] = []
        seen: set[str] = set()

        for row in (edit, verify, action.get("contract")):
            _append_decision_candidate(row, candidates, seen)
        for key in ("inspect", "related"):
            values = action.get(key)
            if not isinstance(values, list):
                continue
            for row in values:
                _append_decision_candidate(row, candidates, seen)
                if len(candidates) >= 6:
                    return candidates
        return candidates

    def _decision_packet_discrimination(
        self,
        *,
        action: Mapping[str, object],
        edit: Mapping[str, object] | None,
        verify: Mapping[str, object] | None,
        build: Mapping[str, object],
        limit: int,
    ) -> dict[str, object]:
        """Describe whether repository evidence needs more discrimination without choosing consumer workflow."""
        ambiguity = (
            action.get("ambiguity") if isinstance(action.get("ambiguity"), dict) else {}
        )
        needed = False
        reason = "resolved"
        if not bool(build.get("complete")):
            needed, reason = True, "codemap-generation-incomplete"
        elif edit is None:
            needed, reason = True, "no-supported-owner-candidate"
        elif bool(ambiguity.get("ambiguous")):
            needed, reason = True, "competing-action-roles"
        elif verify is None:
            needed, reason = True, "missing-verification-evidence"
        return {
            "needed": needed,
            "reason": reason,
            "candidates": self._decision_packet_candidates(action, edit, verify),
            "ambiguity": ambiguity if bool(ambiguity.get("ambiguous")) else None,
            "candidate_scope": "repository-evidence-only",
            "interpretation": "evidence-discrimination-only",
            "consumer_action": "external",
        }

    def _decision_packet_identity(
        self,
        *,
        task: str,
        action: Mapping[str, object],
        verify: Mapping[str, object] | None,
        verification: Mapping[str, object],
        work_context: Mapping[str, object],
        build: Mapping[str, object],
    ) -> tuple[dict[str, object], object, object, str]:
        """Bind packet evidence to repository, task, context and verification selection."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        generation, identity_generation, stale = self._generation_status()
        task_identity = self._packet_digest("hashmarks.task.v1", {"task": task})
        context_digest = self._packet_digest("hashmarks.work-context.v1", work_context)
        verification_digest = self._packet_digest(
            "hashmarks.verification-plan.v1", verification
        )
        verification_membership, source_identity, selection_envelope = (
            self._verification_selection_artifacts(
                _VerificationSelectionState(
                    generation=generation,
                    identity_generation=identity_generation,
                    stale=stale,
                    verify=verify,
                    action=action,
                    verification_digest=verification_digest,
                )
            )
        )
        selection_identity_fields = self._verification_selection_identity_fields(
            verification_membership,
            source_identity,
            selection_envelope,
        )
        repository_identity = self._repository_packet_identity()
        decision_generation = self._packet_digest(
            "hashmarks.decision-generation.v1",
            {
                "repository_identity": repository_identity,
                "codemap_generation": generation,
                "identity_generation": identity_generation,
                "task_identity": task_identity,
                "context_digest": context_digest,
                "verification_plan_digest": verification_digest,
                **selection_identity_fields,
            },
        )
        identity = {
            "schema": "hashmarks.worker-packet-identity.v1",
            "repository_identity": repository_identity,
            "codemap_generation": generation,
            "identity_generation": identity_generation,
            "stale": bool(stale) or not bool(build.get("complete")),
            "codemap_complete": bool(build.get("complete")),
            "codemap_build_state": build.get("state"),
            "task_identity": task_identity,
            "decision_generation": decision_generation,
            "context_digest": context_digest,
            "verification_plan_digest": verification_digest,
            **selection_identity_fields,
        }
        return (
            identity,
            verification_membership,
            selection_envelope,
            decision_generation,
        )

    @incomplete_decision_scoped
    def task_decision_packet(
        self,
        task: str,
        *,
        limit: int = 20,
        per_role: int = 3,
        token_budget: int = 512,
    ) -> dict[str, object]:
        """Return bounded repository evidence for one task decision."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        timing = _DecisionPacketTiming()
        action = self.task_action_map(
            task,
            limit=limit,
            per_role=per_role,
        )
        timing.record("action_map")
        edit = action.get("edit") if isinstance(action.get("edit"), dict) else None
        verify = (
            action.get("verify") if isinstance(action.get("verify"), dict) else None
        )
        build = self._codemap_build_state()
        discrimination = self._decision_packet_discrimination(
            action=action, edit=edit, verify=verify, build=build, limit=limit
        )

        timing.begin_phase()
        work_context = self.work_context(action, token_budget=token_budget)
        timing.record("work_context")
        timing.begin_phase()
        verification = self._task_decision_verification_plan(verify)
        timing.record("verification_plan")
        timing.begin_phase()
        identity, verification_membership, selection_envelope, _decision_generation = (
            self._decision_packet_identity(
                task=task,
                action=action,
                verify=verify,
                verification=verification,
                work_context=work_context,
                build=build,
            )
        )
        evidence_receipt = self._decision_evidence_receipt(task, action, verification)
        timing.record("packet_assembly")
        timing.finish()

        return {
            "schema": "hashmarks.task-decision-packet.v2",
            "task": task,
            "edit": edit,
            "verify": verify,
            "verification_relevance": action.get("verification_relevance"),
            "symbolic_nomination": self._symbolic_task_nomination(task),
            "verification_plan": verification,
            "verification_membership": verification_membership,
            "verification_selection_envelope": selection_envelope,
            "downstream_verification_contract": self._downstream_verification_contract(
                selection_envelope
            ),
            "evidence_surfaces": {
                "edit": None
                if edit is None
                else self._index_surface_for_path(str(edit.get("path") or "")),
                "verify": None
                if verify is None
                else self._index_surface_for_path(str(verify.get("path") or "")),
            },
            "contract": action.get("contract"),
            "ownership_resolution": action.get("ownership_resolution"),
            "ambiguity": action.get("ambiguity"),
            "discrimination": discrimination,
            "evidence_receipt": evidence_receipt,
            "canonical_generation": identity["codemap_generation"],
            "identity": identity,
            "work_context": work_context,
            "context_budget": {
                "requested_tokens": token_budget,
                "estimated_tokens": work_context["estimated_tokens"],
                "safe": bool(work_context["safe"]) and bool(build.get("complete")),
                "missing_roles": work_context["missing_roles"],
            },
            "authority": "repository-observation-only",
            "consumer_action": "external",
            "ranking_effect": "none",
            "discovery_effect": action.get("discovery_effect", "none"),
            "decision_metrics": timing.as_payload(
                session_active=self._decision_session_depth > 0
            ),
        }
