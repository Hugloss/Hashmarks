from __future__ import annotations

from typing import TYPE_CHECKING, cast

from .change_impact import ChangeImpactOptions
from .decision_session import diagnostic_producer

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from .engine import CodeMap


class ChangeIntelligenceMixin:
    """Compact product projection over existing change/selection authority."""

    @diagnostic_producer
    def change_intelligence_brief(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        limit: int = 20,
        per_role: int = 3,
        impact_limit_per_surface: int = 4,
        max_depth: int = 3,
    ) -> dict[str, object]:
        """Return bounded repository intelligence for an explicit change set."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        impact = self.task_change_impact(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            options=ChangeImpactOptions(
                impact_limit_per_surface=impact_limit_per_surface,
                max_depth=max_depth,
                project_impact_encoding="compact",
            ),
        )
        action = self.task_action_map(task, limit=limit, per_role=per_role)
        verify = (
            action.get("verify") if isinstance(action.get("verify"), dict) else None
        )
        verification_path = str(verify.get("path") or "") if verify else ""
        explanation = self.explain_verification_selection(
            task,
            verification_path or None,
            limit=limit,
            candidate_limit=16,
        )
        generation, identity_generation, stale = self._generation_status()
        ownership = action.get("ownership_resolution")
        ownership_projection = None
        if isinstance(ownership, dict):
            ownership_projection = {
                key: ownership[key]
                for key in ("selected", "via", "owner_path")
                if key in ownership
            }
        changed_rows = (
            impact.get("changed") if isinstance(impact.get("changed"), list) else []
        )
        changed_paths_normalized = [
            str(row.get("path") or "")
            for row in changed_rows
            if isinstance(row, dict) and row.get("path")
        ]
        symbols_by_path = self.store.symbols_for_paths_many(
            changed_paths_normalized, limit_per_path=16
        )
        changed: list[dict[str, object]] = []
        for row in changed_rows:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "")
            file_row = self._session_file_row(path)
            revision = (
                None
                if file_row is None or not file_row["file_digest"]
                else str(file_row["file_digest"])
            )
            symbols = [
                str(symbol.get("qualname") or symbol.get("name") or "")
                for symbol in symbols_by_path.get(path, ())
                if str(symbol.get("qualname") or symbol.get("name") or "")
            ]
            item = dict(row)
            item["revision"] = revision
            if symbols:
                item["symbols"] = symbols
            changed.append(item)
        surfaces = (
            impact.get("surfaces") if isinstance(impact.get("surfaces"), dict) else {}
        )
        payload: dict[str, object] = {
            "schema": "hashmarks.change-intelligence-brief.v1",
            "repository": {
                "repository_identity": self._repository_packet_identity(),
                "source_identity": self._source_packet_identity(
                    generation=generation,
                    identity_generation=identity_generation,
                    stale=stale,
                ),
                "codemap_generation": generation,
                "identity_generation": identity_generation,
                "stale": stale is not False,
            },
            "task_identity": self._packet_digest("hashmarks.task.v1", {"task": task}),
            "changed": changed,
            "affected": surfaces,
            "ownership": ownership_projection,
            "verification": {
                "member": verification_path or None,
                "test_symbol": verify.get("verification_test_symbol")
                if verify
                else None,
                "explanation_identity": explanation["explanation_identity"],
                "reason": explanation["reason"],
                "facts": explanation["facts"],
            },
            "freshness": {
                "state": (
                    "stale"
                    if stale is True
                    else "current"
                    if stale is False
                    else "unknown"
                ),
                "generation_bound": True,
            },
            "bounds": dict(impact.get("bounds") or {}),
            "completeness": "not-claimed",
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }
        if "project_impact" in impact:
            payload["project_impact"] = impact["project_impact"]
        payload["brief_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.change-intelligence-brief.v1",
            payload,
        )
        return payload
