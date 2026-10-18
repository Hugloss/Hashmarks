"""Task evidence receipts over supplied action/verification facts and source binding."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from hashmarks.operation_contract import operation_schema
from hashmarks.verification_selection import (
    VerificationSelectionEnvelopeState,
    downstream_consumption_contract,
    verification_membership_from_selection,
    verification_selection_envelope,
)

from .repository_observation import packet_digest
from .verification_relevance_model import _VerificationSelectionState

if TYPE_CHECKING:
    from .repository_tasks import RepositoryTasks
    from .task_evidence_types import TaskVerificationPlan


class TaskReceiptsMixin:
    def _decision_evidence_receipt(
        self,
        task: str,
        action: Mapping[str, object],
        verification: Mapping[str, object],
    ) -> dict[str, object]:
        """Return one compact identity for the repository-owned decision evidence.

        The receipt is intentionally independent of worker projection size.  A
        full decision packet, action brief, and task-evidence packet generated from
        the same repository generation and action evidence therefore carry the
        same identity even when their visible context budgets differ.
        """
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        generation, identity_generation, stale = self.reads.generation_status()

        def anchor(value: object) -> dict[str, object] | None:
            if not isinstance(value, Mapping) or not value.get("path"):
                return None
            row: dict[str, object] = {"path": str(value["path"])}
            for key in ("name", "qualname", "verification_test_symbol"):
                if value.get(key) is not None:
                    row[key] = str(value[key])
            return row

        ownership = action.get("ownership_resolution")
        ownership = ownership if isinstance(ownership, Mapping) else {}
        owner_path = ownership.get("owner_path")
        owner_path = owner_path if isinstance(owner_path, list) else []
        normalized_owner_path = [
            {
                "from": str(edge.get("from") or ""),
                "to": str(edge.get("to") or ""),
                "relation": str(edge.get("relation") or ""),
            }
            for edge in owner_path
            if isinstance(edge, Mapping)
        ]
        ambiguity = action.get("ambiguity")
        ambiguity = ambiguity if isinstance(ambiguity, Mapping) else {}
        payload: dict[str, object] = {
            "schema": "hashmarks.decision-evidence.v1",
            "repository_identity": self.reads.repository_identity(),
            "codemap_generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "task_identity": packet_digest("hashmarks.task.v1", {"task": task}),
            "edit": anchor(action.get("edit")),
            "verify": anchor(action.get("verify")),
            "contract": anchor(action.get("contract")),
            "ownership": {
                "selected": str(ownership.get("selected") or ""),
                "via": str(ownership.get("via") or ""),
                "owner_path": normalized_owner_path,
            },
            "ambiguity": {
                "ambiguous": bool(ambiguity.get("ambiguous")),
                "reason": str(ambiguity.get("reason") or ""),
            },
            "verification_plan_digest": packet_digest(
                "hashmarks.verification-plan.v1", verification
            ),
        }
        evidence_identity = packet_digest("hashmarks.decision-evidence.v1", payload)
        return {
            "schema": "hashmarks.decision-evidence-receipt.v1",
            "evidence_identity": evidence_identity,
            "repository_identity": payload["repository_identity"],
            "task_identity": payload["task_identity"],
            "codemap_generation": generation,
            "stale": stale,
        }

    def _verification_selection_evidence_hashes(
        self,
        action: Mapping[str, object],
        verification_digest: str,
    ) -> dict[str, str]:
        return {
            "verification_plan": f"sha256:{verification_digest}",
            "verification_relevance": "sha256:"
            + packet_digest(
                operation_schema("verification_relevance"),
                action.get("verification_relevance"),
            ),
            "ownership": "sha256:"
            + packet_digest(
                "hashmarks.ownership-resolution.v1",
                action.get("ownership_resolution"),
            ),
        }

    def _verification_selection_artifacts(
        self,
        state: _VerificationSelectionState,
    ) -> tuple[dict[str, object] | None, str, dict[str, object] | None]:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        membership = verification_membership_from_selection(state.verify)
        source_identity = self.source.packet_identity(
            generation=state.generation,
            identity_generation=state.identity_generation,
            stale=state.stale,
        )
        if membership is None:
            return None, source_identity, None
        owner_evidence = state.action.get("ownership_resolution")
        owner_evidence = owner_evidence if isinstance(owner_evidence, Mapping) else None
        envelope = verification_selection_envelope(
            VerificationSelectionEnvelopeState(
                repository_identity=self.reads.repository_identity(),
                source_identity=source_identity,
                codemap_generation=state.generation,
                identity_generation=state.identity_generation,
                stale=state.stale,
                membership=membership,
                owner_evidence=owner_evidence,
                evidence_hashes=self._verification_selection_evidence_hashes(
                    state.action,
                    state.verification_digest,
                ),
            )
        )
        return membership, source_identity, envelope

    @staticmethod
    def _verification_selection_identity_fields(
        membership: Mapping[str, object] | None,
        source_identity: str,
        envelope: Mapping[str, object] | None,
    ) -> dict[str, object]:
        producer = (
            cast("Mapping[str, object]", envelope.get("producer", {}))
            if envelope is not None
            else None
        )
        return {
            "source_identity": source_identity,
            "verification_membership_identity": (
                membership.get("membership_identity")
                if membership is not None
                else None
            ),
            "verification_selection_envelope_identity": (
                envelope.get("envelope_identity") if envelope is not None else None
            ),
            "verification_selection_producer_implementation_identity": (
                producer.get("implementation_identity")
                if producer is not None
                else None
            ),
        }

    def _task_decision_verification_plan(
        self,
        verify: Mapping[str, object] | None,
    ) -> TaskVerificationPlan:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        if verify is None:
            return {
                "schema": "hashmarks.verification-plan.v1",
                "available": False,
                "reason": "no-verification-surface",
            }
        test_symbol = verify.get("verification_test_symbol")
        symbol = (
            str(test_symbol)
            if test_symbol is not None
            else str(verify.get("name"))
            if verify.get("name") is not None
            else None
        )
        qualname = (
            str(verify.get("qualname")) if verify.get("qualname") is not None else None
        )
        return self.verification.plan(
            str(verify["path"]),
            symbol=symbol,
            qualname=qualname,
        )

    @staticmethod
    def _downstream_verification_contract(
        selection_envelope: Mapping[str, object] | None,
    ) -> dict[str, object] | None:
        if selection_envelope is None:
            return None
        return downstream_consumption_contract(selection_envelope)
