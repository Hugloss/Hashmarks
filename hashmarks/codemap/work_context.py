from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.symbolic_identity import symbolic_nomination_record, symbolic_task_terms

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .engine import CodeMap


class WorkContextMixin:
    def _mandatory_work_context_items(
        self,
        action: dict[str, object],
    ) -> tuple[list[dict[str, object]], set[str]]:
        mandatory: list[dict[str, object]] = []
        seen: set[str] = set()
        by_path: dict[str, dict[str, object]] = {}
        for role in ("edit", "verify", "contract"):
            row = action.get(role)
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "")
            if not path:
                continue
            existing = by_path.get(path)
            if existing is not None:
                covered = existing.setdefault("covered_roles", [str(existing["role"])])
                if isinstance(covered, list) and role not in covered:
                    covered.append(role)
                continue
            seen.add(path)
            item = self._work_context_anchor(row, role=role)
            item["covered_roles"] = [role]
            by_path[path] = item
            mandatory.append(item)
        return mandatory, seen

    def _optional_work_context_items(
        self,
        action: dict[str, object],
        *,
        seen: set[str],
    ) -> list[dict[str, object]]:
        optional: list[dict[str, object]] = []
        for key, role in (("related", "related"), ("inspect", "inspect")):
            rows = action.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                path = str(row.get("path") or "")
                if not path or path in seen:
                    continue
                seen.add(path)
                item = self._work_context_anchor(row, role=role)
                item["mandatory"] = False
                optional.append(item)
        return optional

    @staticmethod
    def _select_mandatory_work_context(
        mandatory: list[dict[str, object]],
        *,
        token_budget: int,
    ) -> tuple[list[dict[str, object]], int]:
        selected: list[dict[str, object]] = []
        used = 0
        for item in mandatory:
            cost = int(item["estimated_tokens"])
            if used + cost <= token_budget:
                selected.append(item)
                used += cost
        return selected, used

    @staticmethod
    def _work_context_role_state(
        action: dict[str, object],
        selected: list[dict[str, object]],
    ) -> tuple[dict[str, bool], list[str], list[str]]:
        roles = ("edit", "verify", "contract")
        role_coverage = {
            role: any(
                role in (item.get("covered_roles") or [item["role"]])
                for item in selected
            )
            for role in roles
        }
        required_roles = [role for role in roles if isinstance(action.get(role), dict)]
        missing_roles = [role for role in required_roles if not role_coverage[role]]
        return role_coverage, required_roles, missing_roles

    @staticmethod
    def _append_optional_work_context(
        selected: list[dict[str, object]],
        optional: list[dict[str, object]],
        *,
        used: int,
        token_budget: int,
    ) -> int:
        for item in optional:
            cost = int(item["estimated_tokens"])
            if used + cost > token_budget:
                continue
            selected.append(item)
            used += cost
        return used

    @staticmethod
    def _work_context_evidence_metrics(
        selected: list[dict[str, object]],
        *,
        used: int,
        safe: bool,
    ) -> dict[str, object]:
        supplied_bytes = sum(
            len(str(item["content"]).encode("utf-8")) for item in selected
        )
        useful_role_bytes = sum(
            len(str(item["content"]).encode("utf-8"))
            for item in selected
            if item["role"] in {"edit", "verify", "contract", "related", "inspect"}
        )
        duplicate_evidence_bytes = 0
        seen_content: set[tuple[str, str]] = set()
        for item in selected:
            identity = (str(item["path"]), str(item["content"]))
            size = len(str(item["content"]).encode("utf-8"))
            if identity in seen_content:
                duplicate_evidence_bytes += size
            seen_content.add(identity)
        return {
            "supplied_bytes": supplied_bytes,
            "useful_role_bytes": useful_role_bytes,
            "duplicate_evidence_bytes": duplicate_evidence_bytes,
            "useful_bytes_ratio": (
                useful_role_bytes / supplied_bytes if supplied_bytes else 0.0
            ),
            "tokens_per_safe_packet": used if safe else None,
        }

    def work_context(
        self,
        action: dict[str, object],
        *,
        token_budget: int = 512,
    ) -> dict[str, object]:
        """Build a deterministic, role-preserving worker context projection.

        Mandatory action anchors are selected before discretionary evidence. A
        larger budget therefore cannot evict edit/verification/contract evidence
        that fit at a smaller budget. The allocator does not rerank repository
        evidence and does not read SECRET benchmark data.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if token_budget < 1:
            raise ValueError("token_budget must be >= 1")

        mandatory, seen = self._mandatory_work_context_items(action)
        optional = self._optional_work_context_items(action, seen=seen)
        selected, used = self._select_mandatory_work_context(
            mandatory,
            token_budget=token_budget,
        )
        role_coverage, required_roles, missing_roles = self._work_context_role_state(
            action,
            selected,
        )
        if not missing_roles:
            used = self._append_optional_work_context(
                selected,
                optional,
                used=used,
                token_budget=token_budget,
            )
        safe = not missing_roles
        return {
            "schema": "hashmarks.agent-work-context.v1",
            "budget": token_budget,
            "estimated_tokens": used,
            "safe": safe,
            "required_roles": required_roles,
            "missing_roles": missing_roles,
            "role_coverage": role_coverage,
            "items": selected,
            "evidence_metrics": self._work_context_evidence_metrics(
                selected,
                used=used,
                safe=safe,
            ),
            "allocation": "mandatory-skeleton-then-discretionary",
            "monotonic_contract": "mandatory membership may only grow with budget",
        }

    def work_context_budget_sweep(
        self,
        action: dict[str, object],
        *,
        budgets: Sequence[int] = (128, 192, 256, 384, 512),
    ) -> dict[str, object]:
        """Measure minimum sufficient worker evidence without changing retrieval."""
        normalized = sorted({int(value) for value in budgets})
        if not normalized or normalized[0] < 1:
            raise ValueError("budgets must contain positive integers")
        rows: list[dict[str, object]] = []
        previous_mandatory: set[tuple[str, str]] = set()
        monotonic = True
        for budget in normalized:
            packet = self.work_context(action, token_budget=budget)
            mandatory = {
                (str(item["role"]), str(item["path"]))
                for item in packet["items"]
                if bool(item["mandatory"])
            }
            if not previous_mandatory.issubset(mandatory):
                monotonic = False
            previous_mandatory = mandatory
            metrics = dict(packet["evidence_metrics"])
            rows.append(
                {
                    "budget": budget,
                    "safe": bool(packet["safe"]),
                    "estimated_tokens": int(packet["estimated_tokens"]),
                    "role_coverage": dict(packet["role_coverage"]),
                    **metrics,
                }
            )
        safe_budgets = [int(row["budget"]) for row in rows if bool(row["safe"])]
        return {
            "schema": "hashmarks.work-context-budget-sweep.v1",
            "rows": rows,
            "mandatory_monotonic": monotonic,
            "smallest_safe_budget": min(safe_budgets) if safe_budgets else None,
            "safe_budgets": safe_budgets,
            "optimization_target": "minimum-safe-evidence",
        }

    def _symbolic_task_nomination(self, task: str) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        terms = symbolic_task_terms(task)
        if not terms:
            return symbolic_nomination_record(task=task, terms=(), candidates=())
        candidates = self._session_exact_symbol_candidates(terms, limit=96)
        return symbolic_nomination_record(
            task=task,
            terms=terms,
            candidates=candidates,
        )

    def _retrieval_stability_snapshot(
        self,
        task: str,
        *,
        limit: int,
        replay: int,
    ) -> dict[str, object]:
        hits = self.find_task(task, limit=limit)
        rows = [
            {
                "rank": rank,
                "path": hit.path,
                "kind": hit.kind,
                "score": round(float(hit.score), 12),
            }
            for rank, hit in enumerate(hits, 1)
        ]
        payload = json.dumps(
            rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        return {
            "replay": replay,
            "fingerprint": "sha256:"
            + hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "rows": rows,
        }

    @staticmethod
    def _first_retrieval_difference(
        baseline: list[object],
        candidate: list[object],
    ) -> int | None:
        for index in range(max(len(baseline), len(candidate))):
            left = baseline[index] if index < len(baseline) else None
            right = candidate[index] if index < len(candidate) else None
            if left != right:
                return index + 1
        return None

    @classmethod
    def _retrieval_stability_divergences(
        cls,
        snapshots: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        baseline_raw = snapshots[0]["rows"]
        baseline = baseline_raw if isinstance(baseline_raw, list) else []
        divergences: list[dict[str, object]] = []
        for snapshot in snapshots[1:]:
            rows_raw = snapshot["rows"]
            rows = rows_raw if isinstance(rows_raw, list) else []
            if rows == baseline:
                continue
            divergences.append(
                {
                    "replay": snapshot["replay"],
                    "fingerprint": snapshot["fingerprint"],
                    "first_different_rank": cls._first_retrieval_difference(
                        baseline,
                        rows,
                    ),
                }
            )
        return divergences

    def retrieval_stability(
        self,
        task: str,
        *,
        limit: int = 20,
        repeats: int = 3,
    ) -> dict[str, object]:
        """Replay canonical task retrieval and report deterministic stability.

        Replays bypass only the generation-bound find_task result cache. The
        underlying query formulation, routing, candidate retrieval, fusion, and
        preservation rules are unchanged. This is a diagnostic gate, not a new
        ranker or source of retrieval authority.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if repeats < 2:
            raise ValueError("repeats must be >= 2")
        if repeats > 20:
            raise ValueError("repeats must be <= 20")

        generation = self.store.generation()
        cache_key = (generation, task, int(limit))
        original_cached = self._task_result_cache.get(cache_key)
        snapshots: list[dict[str, object]] = []
        try:
            for replay in range(1, repeats + 1):
                self._task_result_cache.pop(cache_key, None)
                snapshots.append(
                    self._retrieval_stability_snapshot(
                        task,
                        limit=limit,
                        replay=replay,
                    )
                )
        finally:
            self._task_result_cache.pop(cache_key, None)
            if original_cached is not None:
                self._task_result_cache[cache_key] = original_cached

        divergences = self._retrieval_stability_divergences(snapshots)
        return {
            "schema": "hashmarks.retrieval-stability.v1",
            "task": task,
            "generation": generation,
            "limit": limit,
            "repeats": repeats,
            "stable": not divergences,
            "baseline_fingerprint": snapshots[0]["fingerprint"],
            "fingerprints": [snapshot["fingerprint"] for snapshot in snapshots],
            "divergences": divergences,
            "cache_policy": "bypass-task-result-cache-only",
            "ranking_effect": "none",
        }

    @staticmethod
    def _retrieval_explanation_specs(
        views: dict[str, str],
        *,
        limit: int,
    ) -> list[tuple[str, str, float, int]]:
        fetch = max(40, min(80, limit * 4))
        evidence_fetch = max(24, min(40, limit * 2))
        specs = [
            ("base", views["base"], 1.2, fetch),
            ("governance", views["governance"], 1.0, fetch),
        ]
        if views["evidence"] not in {views["base"], views["governance"]}:
            specs.append(("evidence", views["evidence"], 0.8, evidence_fetch))
        return specs

    def _retrieval_lane_projection(
        self,
        *,
        lane: str,
        query: str,
        weight: float,
        view_fetch: int,
        selected_paths: set[str],
    ) -> tuple[dict[str, list[dict[str, object]]], dict[str, float], str | None]:
        contributions: dict[str, list[dict[str, object]]] = {}
        totals: dict[str, float] = {}
        base_first: str | None = None
        distinct: set[str] = set()
        rank = 0
        for hit in self.find(query, limit=view_fetch):
            if hit.path in distinct:
                continue
            distinct.add(hit.path)
            rank += 1
            if lane == "base" and rank == 1:
                base_first = hit.path
            contribution = weight / (60.0 + rank)
            totals[hit.path] = contribution
            if hit.path in selected_paths:
                contributions.setdefault(hit.path, []).append(
                    {
                        "lane": lane,
                        "query": query,
                        "path_rank": rank,
                        "weight": weight,
                        "rrf_contribution": round(contribution * 1000.0, 6),
                    }
                )
        return contributions, totals, base_first

    def _retrieval_rrf_projection(
        self,
        specs: list[tuple[str, str, float, int]],
        *,
        selected_paths: set[str],
    ) -> tuple[dict[str, list[dict[str, object]]], dict[str, float], str | None]:
        seen_queries: set[str] = set()
        contributions: dict[str, list[dict[str, object]]] = {}
        totals: dict[str, float] = {}
        base_first: str | None = None
        for lane, query, weight, view_fetch in specs:
            if query in seen_queries:
                continue
            seen_queries.add(query)
            lane_contributions, lane_totals, lane_base_first = (
                self._retrieval_lane_projection(
                    lane=lane,
                    query=query,
                    weight=weight,
                    view_fetch=view_fetch,
                    selected_paths=selected_paths,
                )
            )
            for path, value in lane_totals.items():
                totals[path] = totals.get(path, 0.0) + value
            for path, rows in lane_contributions.items():
                contributions.setdefault(path, []).extend(rows)
            if base_first is None and lane_base_first is not None:
                base_first = lane_base_first
        return contributions, totals, base_first

    @staticmethod
    def _ordinary_retrieval_paths(
        totals: dict[str, float],
        *,
        base_first: str | None,
        limit: int,
    ) -> list[str]:
        ranked_rrf = sorted(totals, key=lambda path: (-totals[path], path))
        ordinary: list[str] = []
        if base_first is not None:
            ordinary.append(base_first)
        for path in ranked_rrf:
            if path not in ordinary:
                ordinary.append(path)
            if len(ordinary) >= limit:
                break
        return ordinary

    @staticmethod
    def _retrieval_selection_reason(
        *,
        path: str,
        final_rank: int,
        base_first: str | None,
        ordinary: set[str],
    ) -> str:
        if final_rank == 1 and path == base_first:
            return "strongest-base-path-preservation"
        if path in ordinary:
            return "rrf"
        name = Path(path).name
        if name == "AGENTS.md":
            return "scoped-authority-preservation"
        if name == "README.md":
            return "conceptual-scoped-readme-preservation"
        return "bounded-post-fusion-preservation"

    def _retrieval_explanation_rows(
        self,
        selected: Sequence[object],
        *,
        base_first: str | None,
        ordinary: set[str],
        totals: dict[str, float],
        contributions: dict[str, list[dict[str, object]]],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for final_rank, hit in enumerate(selected, 1):
            rows.append(
                {
                    "path": hit.path,
                    "final_rank": final_rank,
                    "final_score": round(hit.score, 6),
                    "selection_reason": self._retrieval_selection_reason(
                        path=hit.path,
                        final_rank=final_rank,
                        base_first=base_first,
                        ordinary=ordinary,
                    ),
                    "rrf_score": round(totals.get(hit.path, 0.0) * 1000.0, 6),
                    "discovered_by": contributions.get(hit.path, []),
                }
            )
        return rows

    def explain_task_retrieval(
        self, task: str, *, limit: int = 20
    ) -> dict[str, object]:
        """Explain canonical task retrieval without changing its selection semantics.

        The explanation recomputes the same bounded task-query views used by
        find_task and reports path-level RRF contribution/provenance for the
        already-selected canonical result. It is observational only.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if limit < 1:
            raise ValueError("limit must be >= 1")
        selected = self.find_task(task, limit=limit)
        selected_paths = {hit.path for hit in selected}
        views = self.task_query_views(task)
        specs = self._retrieval_explanation_specs(views, limit=limit)
        contributions, totals, base_first = self._retrieval_rrf_projection(
            specs,
            selected_paths=selected_paths,
        )
        ordinary = set(
            self._ordinary_retrieval_paths(
                totals,
                base_first=base_first,
                limit=limit,
            )[:limit]
        )
        rows = self._retrieval_explanation_rows(
            selected,
            base_first=base_first,
            ordinary=ordinary,
            totals=totals,
            contributions=contributions,
        )
        return {
            "schema": "hashmarks.task-retrieval-provenance.v1",
            "task": task,
            "generation": self.store.generation(),
            "views": views,
            "selected": rows,
            "ranking_effect": "none",
            "evidence": "bounded replay of canonical task-query views and path-level weighted RRF",
        }
