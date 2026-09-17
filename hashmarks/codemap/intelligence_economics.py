from __future__ import annotations

from .decision_session import diagnostic_producer

from collections.abc import Mapping, Sequence
import json
from pathlib import Path


class IntelligenceEconomicsMixin:
    """Deterministic economics of Hashmarks-owned repository-intelligence evidence.

    Measurements are derived only from repository-intelligence artifacts Hashmarks
    already owns.  They never describe agent runtime, model tokens, tool calls,
    execution attempts, billing, scheduling, retry, or certification state.
    """

    @staticmethod
    def _economics_bytes(value: object) -> int:
        return len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))

    @staticmethod
    def _economics_bps(saved: int, baseline: int) -> int:
        if baseline <= 0:
            return 0
        return (max(0, saved) * 10_000) // baseline

    @staticmethod
    def _economics_mapping(value: object) -> Mapping[str, object]:
        return value if isinstance(value, Mapping) else {}

    @classmethod
    def _economics_counts(cls, snapshot: Mapping[str, object]) -> dict[str, object]:
        affected = cls._economics_mapping(snapshot.get("affected"))
        freshness = cls._economics_mapping(snapshot.get("freshness"))
        verification = cls._economics_mapping(snapshot.get("verification"))
        affected_rows = sum(len(rows) for rows in affected.values() if isinstance(rows, list))
        freshness_states: dict[str, int] = {}
        for raw in freshness.values():
            row = cls._economics_mapping(raw)
            state = str(row.get("state") or "unknown")
            freshness_states[state] = freshness_states.get(state, 0) + 1
        return {
            "changed_paths": len(cls._economics_mapping(snapshot.get("paths"))),
            "affected_rows": affected_rows,
            "freshness_entries": len(freshness),
            "freshness_states": dict(sorted(freshness_states.items())),
            "ownership_present": snapshot.get("ownership") is not None,
            "verification_selected": bool(verification.get("member")),
            "project_impact_present": snapshot.get("project_impact") is not None,
        }

    @diagnostic_producer
    def intelligence_economics_receipt(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        previous_snapshot: Mapping[str, object] | None = None,
        limit: int = 20,
        per_role: int = 3,
        impact_limit_per_surface: int = 4,
        max_depth: int = 3,
    ) -> dict[str, object]:
        if not task.strip():
            raise ValueError("task must not be empty")
        if not changed_paths:
            raise ValueError("changed_paths must not be empty")

        snapshot = self.repository_intelligence_snapshot(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=impact_limit_per_surface,
            max_depth=max_depth,
        )
        profiles = {
            name: self._profile_from_snapshot(snapshot, profile=name)
            for name in ("compact", "standard", "audit")
        }
        sizes = {name: self._economics_bytes(value) for name, value in profiles.items()}
        audit_bytes = sizes["audit"]
        profile_economics = {
            name: {
                "serialized_bytes": sizes[name],
                "saved_vs_audit_bytes": audit_bytes - sizes[name],
                "saved_vs_audit_bps": self._economics_bps(audit_bytes - sizes[name], audit_bytes),
                "profile_identity": profiles[name]["profile_identity"],
            }
            for name in ("compact", "standard", "audit")
        }

        payload: dict[str, object] = {
            "schema": "hashmarks.intelligence-economics-receipt.v1",
            "source_snapshot_identity": snapshot["snapshot_identity"],
            "profile_economics": profile_economics,
            "evidence_counts": self._economics_counts(snapshot),
            "measurement": {
                "unit": "serialized-json-utf8-bytes",
                "scope": "hashmarks-owned-derived-repository-intelligence",
                "excluded": [
                    "agent-runtime",
                    "model-tokens",
                    "tool-calls",
                    "execution-attempts",
                    "billing",
                    "scheduling",
                    "retry",
                    "certification",
                ],
            },
            "bounds": dict(self._economics_mapping(snapshot.get("bounds"))),
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }

        if previous_snapshot is not None:
            delta = self.repository_intelligence_delta(
                task,
                changed_paths,
                previous_snapshot=previous_snapshot,
                limit=limit,
                per_role=per_role,
                impact_limit_per_surface=impact_limit_per_surface,
                max_depth=max_depth,
            )
            previous_bytes = self._economics_bytes(previous_snapshot)
            current_bytes = self._economics_bytes(snapshot)
            delta_bytes = self._economics_bytes(delta)
            pair_bytes = previous_bytes + current_bytes
            payload["delta_economics"] = {
                "from_snapshot_identity": previous_snapshot.get("snapshot_identity"),
                "to_snapshot_identity": snapshot["snapshot_identity"],
                "delta_identity": delta["delta_identity"],
                "previous_snapshot_bytes": previous_bytes,
                "current_snapshot_bytes": current_bytes,
                "delta_bytes": delta_bytes,
                "retransmit_pair_bytes": pair_bytes,
                "saved_vs_retransmit_pair_bytes": pair_bytes - delta_bytes,
                "saved_vs_retransmit_pair_bps": self._economics_bps(pair_bytes - delta_bytes, pair_bytes),
            }

        payload["receipt_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.intelligence-economics-receipt.v1", payload,
        )
        return payload
