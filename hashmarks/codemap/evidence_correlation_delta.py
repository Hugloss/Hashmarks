"""Explicit endpoint comparison for external-to-repository correspondence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from .evidence_correlation_replay import _DELTA_SCHEMA
from .repository_observation import packet_digest

if TYPE_CHECKING:
    from .evidence_correlation import RepositoryCorrelation


class EvidenceCorrelationDeltaMixin:
    def delta(
        self,
        before: Mapping[str, object],
        after: Mapping[str, object],
    ) -> dict[str, object]:
        """Compare correlation packets without inferring causal meaning."""
        if TYPE_CHECKING:
            self = cast("RepositoryCorrelation", self)
        self._validate_correlation_packet(before, label="before")
        self._validate_correlation_packet(after, label="after")
        before_repository = before["repository_evidence"]
        after_repository = after["repository_evidence"]
        assert isinstance(before_repository, Mapping)
        assert isinstance(after_repository, Mapping)
        repository_delta = self.bindings.delta(
            before_repository,
            after_repository,
        )
        payload = self._correlation_delta_packet(
            before,
            after,
            repository_delta,
        )
        payload["delta_identity"] = "sha256:" + packet_digest(
            _DELTA_SCHEMA,
            payload,
        )
        return payload

    @staticmethod
    def _correlation_delta_packet(
        before: Mapping[str, object],
        after: Mapping[str, object],
        repository_delta: dict[str, object],
    ) -> dict[str, object]:
        definition_state = (
            "preserved"
            if before.get("evidence_definition_identity")
            == after.get("evidence_definition_identity")
            else "changed"
        )
        comparable = definition_state == "preserved"
        return {
            "schema": _DELTA_SCHEMA,
            "comparability": "comparable" if comparable else "not-comparable",
            "definition": {
                "state": definition_state,
                "before": before.get("evidence_definition_identity"),
                "after": after.get("evidence_definition_identity"),
            },
            "repository_evidence_delta": repository_delta if comparable else None,
            "before_correlation_identity": before.get("correlation_identity"),
            "after_correlation_identity": after.get("correlation_identity"),
            "authority": "repository-intelligence-only",
            "interpretation_authority": "consumer-owned",
            "causation": "not-inferred",
            "execution_effect": "none",
        }
