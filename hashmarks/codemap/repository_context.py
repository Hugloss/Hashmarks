from __future__ import annotations

import time
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .decision_session import decision_scoped
from .model import (
    ContextDisclosure,
    ContextItem,
    ContextPack,
    EvidenceVisibility,
    SearchHit,
)
from .python_ast import estimate_tokens
from .query_primitives import _TASK_EVIDENCE_FAMILIES, _TASK_GOVERNANCE_CUES, _WORD_RE
from .query_router import route_query

if TYPE_CHECKING:
    from .engine import CodeMap


class ContextPlanningMixin:
    def _resolve_edge(self, edge: dict) -> dict:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        value = dict(edge)
        target = str(value.get("target", ""))
        resolved_paths = (
            self._resolve_import_paths(str(value.get("path", "")), target)
            if value.get("kind") == "import"
            else []
        )
        short = target.rsplit(".", 1)[-1]
        resolved_symbols = [
            {
                "path": row["path"],
                "qualname": row["qualname"],
                "signature": row["signature"],
            }
            for row in self.store.symbols_named(short, limit=8)
            if EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        ]
        value["resolved_paths"] = resolved_paths
        value["resolved_symbols"] = resolved_symbols
        return value

    def deps(self, query: str) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        matches = self.store.symbol(query)
        if matches:
            visible_matches = [
                match
                for match in matches
                if EvidenceVisibility(str(match["evidence_visibility"]))
                is not EvidenceVisibility.DENY
            ]
            edge_map = self._session_edges_from_many(
                [
                    (str(match["path"]), str(match["qualname"]))
                    for match in visible_matches
                ],
                limit_per_seed=100,
            )
            rows = [
                row
                for match in visible_matches
                for row in edge_map.get(
                    (str(match["path"]), str(match["qualname"])), ()
                )
            ]
            native_rows = [
                row
                for match in visible_matches
                for row in self._fresh_native_edges_from(
                    str(match["path"]), str(match["qualname"])
                )
            ]
            return {
                "schema": "hashmarks.deps.v1",
                "query": query,
                **self._query_freshness_fields(),
                "edges": [self._resolve_edge(row) for row in rows],
                "native_edges": native_rows,
                "native_file_edges": [
                    row
                    for match in matches
                    for row in self._fresh_native_file_edges_from(str(match["path"]))
                ],
            }
        rel = normalize_relative_path(query, allow_root=False)
        self._ensure_path_current(rel)
        return {
            "schema": "hashmarks.deps.v1",
            "query": query,
            **self._query_freshness_fields(),
            "edges": [self._resolve_edge(row) for row in self.store.edges_from(rel)],
            "native_edges": self._fresh_native_edges_from(rel),
            "native_file_edges": self._fresh_native_file_edges_from(rel),
        }

    def refs(self, query: str) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        rows = [
            row
            for row in self.store.refs(query)
            if EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        ]
        native_rows = self._fresh_native_refs(query)
        native_file_rows = self._session_file_rows(
            str(row["path"]) for row in native_rows
        )
        native = [
            row
            for row in native_rows
            if (mapped := native_file_rows.get(str(row["path"]))) is not None
            and EvidenceVisibility(str(mapped["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        ]
        return {
            "schema": "hashmarks.refs.v1",
            "query": query,
            **self._query_freshness_fields(),
            "references": rows,
            "native_references": native,
        }

    def orient(self, *, max_areas: int = 12) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        stats = self.store.stats()
        areas = list(self.store.top_level_counts().items())[:max_areas]
        generation, identity_generation, stale = self._generation_status()
        return {
            "schema": "hashmarks.repository-capsule.v1",
            "workspace": str(self.workspace),
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "languages": self.store.language_counts(),
            "areas": [{"path": path, "indexed_files": count} for path, count in areas],
            "stats": stats,
            "projects": self._fresh_project_nodes()[:20],
            "project_edges": self._fresh_project_edges()[:40],
            "frequent_dependency_targets": [
                {"target": target, "references": count}
                for target, count in self.store.top_edge_targets(10)
            ],
            "guidance": "Use find/outline/symbol/deps before reading full files.",
        }

    def _source_slice(
        self, path: str, start: int, end: int, *, qualname: str | None = None
    ) -> str:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_path_current(path)
        row = self._session_file_row(path)
        if row is None:
            raise FileNotFoundError(path)
        visibility = EvidenceVisibility(str(row["evidence_visibility"]))
        if visibility is not EvidenceVisibility.SOURCE:
            raise PermissionError(
                f"source body is not visible under the evidence policy: {path}"
            )
        if qualname is not None:
            current = self.store.symbol_at(path, qualname)
            if current is not None:
                start = int(current["start_line"])
                end = int(current["end_line"])
        lines = (
            (self.workspace / path)
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()
        )
        return "\n".join(lines[start - 1 : end])

    def _context_freshness_warnings(self, stale: bool | None) -> tuple[str, ...]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if stale is not None:
            return ()
        last_sync_raw = self.store.meta("last_sync_unix", "") or ""
        if last_sync_raw:
            try:
                last_sync = float(last_sync_raw)
                age = max(0.0, time.time() - last_sync)
                return (
                    f"CodeMap was explicitly reconciled {age:.1f}s ago, but filesystem continuity since that checkpoint is not proven; keep `hashmarks map watch` active (or use the identity daemon generation boundary) for continuously proven freshness",
                )
            except ValueError:
                pass
        return (
            "CodeMap has indexed state, but filesystem continuity is not proven; run `hashmarks map sync` for a fresh checkpoint or keep `hashmarks map watch` active for continuous freshness",
        )

    def _context_action(
        self,
        *,
        query: str,
        token_budget: int,
        limit: int,
        level: ContextDisclosure,
        generation: int,
        hits: tuple[SearchHit, ...],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return {
            "schema": "hashmarks.context-action.v1",
            "retrieval_protocol": "hashmarks.progressive-context.v0.10.14",
            "workspace_fingerprint": self.store.meta("workspace_fingerprint", "") or "",
            "codemap_generation": generation,
            "policy_fingerprint": self.policy.fingerprint(),
            "query": query,
            "token_budget": token_budget,
            "limit": limit,
            "disclosure": level.value,
            "hits": [
                {
                    "path": hit.path,
                    "score": hit.score,
                    "kind": hit.kind,
                    "qualname": hit.qualname,
                    "signature": hit.signature,
                    "start_line": hit.start_line,
                    "end_line": hit.end_line,
                    "visibility": hit.evidence_visibility.value,
                }
                for hit in hits
            ],
        }

    @staticmethod
    def _context_payload(
        items: tuple[ContextItem, ...], *, estimated_tokens: int, confidence: str
    ) -> dict[str, object]:
        return {
            "schema": "hashmarks.context-payload.v1",
            "estimated_tokens": estimated_tokens,
            "confidence": confidence,
            "items": [item.as_dict() for item in items],
        }

    def task_context_plan(
        self,
        task: str,
        *,
        min_budget: int = 512,
        max_budget: int = 2400,
    ) -> dict[str, object]:
        """Return a deterministic, bounded evidence-budget plan for one task.

        This is advisory policy over existing retrieval/disclosure primitives. It
        does not alter ``context()`` defaults or canonical ``find_task()`` ranking.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if min_budget < 128:
            raise ValueError("min_budget must be at least 128")
        if max_budget < min_budget:
            raise ValueError("max_budget must be >= min_budget")
        views = self.task_query_views(task)
        route = route_query(views["base"])
        words = {value.lower() for value in _WORD_RE.findall(task)}
        governance = bool(words & _TASK_GOVERNANCE_CUES)
        evidence_family = any(
            bool(words & cues) for cues, _values in _TASK_EVIDENCE_FAMILIES
        )
        base_by_intent = {
            "identifier": 768,
            "path": 704,
            "config": 1152,
            "test": 1024,
            "structural": 1024,
            "relationship": 1408,
            "conceptual": 1536,
            "hybrid": 1280,
        }
        budget = base_by_intent.get(route.intent.value, 1280)
        reasons = [f"route:{route.intent.value}"]
        if governance:
            budget += 256
            reasons.append("governance-cues")
        if evidence_family:
            budget += 192
            reasons.append("evidence-family-cues")
        budget = max(min_budget, min(max_budget, budget))
        if route.intent.value in {"identifier", "path"}:
            disclosure = ContextDisclosure.OUTLINE.value
        elif route.intent.value in {"relationship", "structural", "test", "config"}:
            disclosure = ContextDisclosure.EVIDENCE.value
        else:
            disclosure = (
                ContextDisclosure.EVIDENCE.value
                if governance or evidence_family
                else ContextDisclosure.OUTLINE.value
            )
        return {
            "schema": "hashmarks.task-context-plan.v1",
            "task": task,
            "query": task,
            "intent": route.intent.value,
            "token_budget": budget,
            "disclosure": disclosure,
            "limit": 20,
            "reasons": reasons,
            "ranking_effect": "none",
        }

    def task_context(
        self,
        task: str,
        *,
        token_budget: int | None = None,
        disclosure: ContextDisclosure | str | None = None,
    ) -> ContextPack:
        """Build context using a deterministic adaptive plan unless overridden."""
        plan = self.task_context_plan(task)
        budget = (
            int(plan["token_budget"]) if token_budget is None else int(token_budget)
        )
        level: ContextDisclosure | str = (
            str(plan["disclosure"]) if disclosure is None else disclosure
        )
        return self.context(
            str(plan["query"]),
            token_budget=budget,
            limit=int(plan["limit"]),
            disclosure=level,
        )

    @decision_scoped
    def context(
        self,
        query: str,
        *,
        token_budget: int = 4000,
        limit: int = 30,
        disclosure: ContextDisclosure | str = ContextDisclosure.SOURCE,
    ) -> ContextPack:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if token_budget < 128:
            raise ValueError("token budget must be at least 128")
        try:
            level = (
                disclosure
                if isinstance(disclosure, ContextDisclosure)
                else ContextDisclosure(disclosure)
            )
        except ValueError as exc:
            allowed = ", ".join(value.value for value in ContextDisclosure)
            raise ValueError(
                f"invalid context disclosure {disclosure!r}; expected one of: {allowed}"
            ) from exc
        self._ensure_map_ready()
        generation, _identity_generation, stale = self._generation_status()
        key = (
            "context-flight.v1",
            self.store.meta("workspace_fingerprint", "") or "",
            generation,
            self.policy.fingerprint(),
            query,
            int(token_budget),
            int(limit),
            level.value,
        )
        # Structural context can share an ephemeral computation when continuity
        # is unknown. Exact source sharing requires positive freshness, matching
        # the persistent CAS boundary. Known-stale requests never share.
        share_allowed = stale is False or (
            stale is None and level is not ContextDisclosure.SOURCE
        )
        if not share_allowed:
            return self._context_impl(
                query, token_budget=token_budget, limit=limit, disclosure=level
            )
        pack, shared = self._context_flight.run(
            key,
            lambda: self._context_impl(
                query, token_budget=token_budget, limit=limit, disclosure=level
            ),
        )
        return replace(pack, shared_flight=True) if shared else pack

    def _context_cached_pack(
        self,
        *,
        action: dict[str, object],
        query: str,
        token_budget: int,
        level: ContextDisclosure,
        confidence: str,
        generation: int,
        identity_generation: int,
        stale: bool | None,
    ) -> ContextPack | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        cached = self.context_cache.get(action)
        if cached is None:
            return None
        raw_items = cached.payload.get("items", [])
        if not isinstance(raw_items, list):
            return None
        cached_items = tuple(
            ContextItem(
                path=str(item["path"]),
                representation=str(item["representation"]),
                content=str(item["content"]),
                estimated_tokens=int(item["estimated_tokens"]),
                symbol=None if item.get("symbol") is None else str(item["symbol"]),
                reason=None if item.get("reason") is None else str(item["reason"]),
            )
            for item in raw_items
            if isinstance(item, dict)
        )
        return ContextPack(
            query=query,
            budget=token_budget,
            disclosure=level,
            estimated_tokens=int(cached.payload.get("estimated_tokens", 0)),
            confidence=str(cached.payload.get("confidence", confidence)),
            abstained=False,
            generation=generation,
            identity_generation=identity_generation,
            stale=stale,
            cache_hit=True,
            context_action_hash=cached.action_hash,
            context_result_digest=cached.result_digest.as_key(),
            items=cached_items,
            warnings=self._context_freshness_warnings(stale),
        )

    def _context_orientation_items(
        self,
        hits: tuple[SearchHit, ...],
        *,
        token_budget: int,
    ) -> tuple[list[ContextItem], int]:
        items: list[ContextItem] = []
        used = 0
        seen: set[tuple[str, str | None]] = set()
        for hit in hits[:16]:
            key = (hit.path, hit.qualname)
            if key in seen:
                continue
            label = hit.path if hit.qualname is None else f"{hit.path}::{hit.qualname}"
            tokens = estimate_tokens(label)
            if tokens <= 0 or used + tokens > token_budget:
                continue
            seen.add(key)
            items.append(
                ContextItem(
                    path=hit.path,
                    representation="candidate",
                    content=label,
                    estimated_tokens=tokens,
                    symbol=hit.qualname,
                    reason=f"ranked orientation candidate; relevance {hit.score:.1f}",
                )
            )
            used += tokens
        return items, used

    def _context_outline_items(
        self,
        hits: tuple[SearchHit, ...],
        *,
        token_budget: int,
    ) -> tuple[
        list[ContextItem],
        int,
        set[tuple[str, str | None]],
        dict[tuple[str, str | None], int],
    ]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        items: list[ContextItem] = []
        used = 0
        seen: set[tuple[str, str | None]] = set()
        item_index: dict[tuple[str, str | None], int] = {}
        for hit in hits[:16]:
            key = (hit.path, hit.qualname)
            if key in seen:
                continue
            if hit.qualname is None and any(
                existing_path == hit.path for existing_path, _ in seen
            ):
                continue
            if hit.qualname is not None and hit.signature is not None:
                content = hit.signature
                representation = "signature"
                symbol = hit.qualname
            else:
                row = self.store.outline(hit.path)
                if (
                    row is None
                    or EvidenceVisibility(str(row["evidence_visibility"]))
                    is EvidenceVisibility.DENY
                ):
                    continue
                content = str(row["outline"] or hit.path)
                representation = "outline"
                symbol = None
            tokens = estimate_tokens(content)
            if tokens <= 0 or used + tokens > token_budget:
                continue
            seen.add(key)
            item_index[key] = len(items)
            items.append(
                ContextItem(
                    path=hit.path,
                    representation=representation,
                    content=content,
                    estimated_tokens=tokens,
                    symbol=symbol,
                    reason=f"structural orientation; ranked relevance {hit.score:.1f}",
                )
            )
            used += tokens
        return items, used, seen, item_index

    def _context_add_dependency_evidence(
        self,
        hits: tuple[SearchHit, ...],
        *,
        items: list[ContextItem],
        used: int,
        seen: set[tuple[str, str | None]],
        item_index: dict[tuple[str, str | None], int],
        token_budget: int,
    ) -> int:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        evidence_hits = [hit for hit in hits[:4] if hit.qualname is not None]
        evidence_edge_map = self._session_edges_from_many(
            [(hit.path, str(hit.qualname)) for hit in evidence_hits], limit_per_seed=12
        )
        edge_rows = [
            (hit, raw_edge)
            for hit in evidence_hits
            for raw_edge in evidence_edge_map.get((hit.path, str(hit.qualname)), ())[
                :12
            ]
        ]
        dependency_shorts = [
            str(raw_edge.get("target", "")).rsplit(".", 1)[-1]
            for _, raw_edge in edge_rows
            if str(raw_edge.get("target", ""))
        ]
        dependency_rows = self._session_exact_symbol_candidates(
            dependency_shorts, limit=max(12, min(500, len(set(dependency_shorts)) * 3))
        )
        deps_by_short: dict[str, list[dict]] = {}
        wanted = {value.lower() for value in dependency_shorts}
        for dep in dependency_rows:
            aliases = {
                str(dep.get("name") or "").lower(),
                str(dep.get("qualname") or "").rsplit(".", 1)[-1].lower(),
            }
            for alias in aliases.intersection(wanted):
                bucket = deps_by_short.setdefault(alias, [])
                if len(bucket) < 3:
                    bucket.append(dep)
        for hit, raw_edge in edge_rows:
            if used >= token_budget:
                break
            target = str(raw_edge.get("target", ""))
            short = target.rsplit(".", 1)[-1].lower()
            for dep in deps_by_short.get(short, ()):
                if (
                    EvidenceVisibility(str(dep["evidence_visibility"]))
                    is EvidenceVisibility.DENY
                ):
                    continue
                dep_key = (str(dep["path"]), str(dep["qualname"]))
                if dep_key in seen:
                    continue
                content = str(dep["signature"] or dep["qualname"])
                tokens = estimate_tokens(content)
                if tokens <= 0 or used + tokens > token_budget:
                    continue
                seen.add(dep_key)
                item_index[dep_key] = len(items)
                items.append(
                    ContextItem(
                        path=str(dep["path"]),
                        representation="signature",
                        content=content,
                        estimated_tokens=tokens,
                        symbol=str(dep["qualname"]),
                        reason=f"{raw_edge.get('kind')} dependency of {hit.qualname}",
                    )
                )
                used += tokens
                break
        return used

    def _context_upgrade_source_items(
        self,
        hits: tuple[SearchHit, ...],
        *,
        query: str,
        items: list[ContextItem],
        used: int,
        item_index: dict[tuple[str, str | None], int],
        token_budget: int,
    ) -> int:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        query_tokens = {value.lower() for value in _WORD_RE.findall(query)}
        wants_tests = bool(query_tokens & {"test", "tests", "testing", "spec", "specs"})
        upgrade_hits = [
            hit
            for hit in hits
            if hit.qualname is not None
            and hit.signature is not None
            and hit.evidence_visibility is EvidenceVisibility.SOURCE
            and hit.start_line is not None
            and hit.end_line is not None
            and hit.score >= 45
            and ((not self._is_test_path(hit.path)) or wants_tests)
        ]
        upgrade_hits.sort(
            key=lambda hit: (
                self._is_test_path(hit.path) and not wants_tests,
                -hit.score,
                hit.path,
            )
        )
        upgrades = 0
        for hit in upgrade_hits:
            if upgrades >= 4:
                break
            key = (hit.path, hit.qualname)
            index = item_index.get(key)
            if index is None:
                continue
            current = items[index]
            try:
                body = self._source_slice(
                    hit.path, hit.start_line, hit.end_line, qualname=hit.qualname
                )
            except (OSError, PermissionError):
                continue
            body_tokens = estimate_tokens(body)
            delta = body_tokens - current.estimated_tokens
            if (
                not body
                or body_tokens <= current.estimated_tokens
                or used + delta > token_budget
            ):
                continue
            items[index] = ContextItem(
                path=hit.path,
                representation="source-range",
                content=body,
                estimated_tokens=body_tokens,
                symbol=hit.qualname,
                reason=f"source upgrade after evidence; ranked relevance {hit.score:.1f}",
            )
            used += delta
            upgrades += 1
        return used

    def _context_impl(
        self,
        query: str,
        *,
        token_budget: int = 4000,
        limit: int = 30,
        disclosure: ContextDisclosure | str = ContextDisclosure.SOURCE,
    ) -> ContextPack:
        """Build one bounded context projection from a shared evidence base."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if token_budget < 128:
            raise ValueError("token budget must be at least 128")
        try:
            level = (
                disclosure
                if isinstance(disclosure, ContextDisclosure)
                else ContextDisclosure(disclosure)
            )
        except ValueError as exc:
            allowed = ", ".join(value.value for value in ContextDisclosure)
            raise ValueError(
                f"invalid context disclosure {disclosure!r}; expected one of: {allowed}"
            ) from exc

        hits = self.find(query, limit=limit)
        best = hits[0].score if hits else 0.0
        confidence = (
            "high" if best >= 70 else "medium" if best >= 30 else "insufficient"
        )
        generation, identity_generation, stale = self._generation_status()
        if confidence == "insufficient":
            return ContextPack(
                query=query,
                budget=token_budget,
                disclosure=level,
                estimated_tokens=0,
                confidence=confidence,
                abstained=True,
                generation=generation,
                identity_generation=identity_generation,
                stale=stale,
                warnings=(
                    "retrieval confidence insufficient; repository context omitted",
                ),
            )

        action = self._context_action(
            query=query,
            token_budget=token_budget,
            limit=limit,
            level=level,
            generation=generation,
            hits=hits,
        )
        cache_allowed = stale is False or (
            stale is None and level is not ContextDisclosure.SOURCE
        )
        if cache_allowed:
            cached_pack = self._context_cached_pack(
                action=action,
                query=query,
                token_budget=token_budget,
                level=level,
                confidence=confidence,
                generation=generation,
                identity_generation=identity_generation,
                stale=stale,
            )
            if cached_pack is not None:
                return cached_pack

        if level is ContextDisclosure.ORIENT:
            items, used = self._context_orientation_items(
                hits, token_budget=token_budget
            )
        else:
            items, used, seen, item_index = self._context_outline_items(
                hits, token_budget=token_budget
            )
            if level in {ContextDisclosure.EVIDENCE, ContextDisclosure.SOURCE}:
                used = self._context_add_dependency_evidence(
                    hits,
                    items=items,
                    used=used,
                    seen=seen,
                    item_index=item_index,
                    token_budget=token_budget,
                )
            if level is ContextDisclosure.SOURCE:
                used = self._context_upgrade_source_items(
                    hits,
                    query=query,
                    items=items,
                    used=used,
                    item_index=item_index,
                    token_budget=token_budget,
                )

        freshness_warnings = self._context_freshness_warnings(stale)
        context_items = tuple(items)
        action_hash = None
        result_digest = None
        if cache_allowed:
            stored = self.context_cache.put(
                action,
                self._context_payload(
                    context_items, estimated_tokens=used, confidence=confidence
                ),
            )
            action_hash = stored.action_hash
            result_digest = stored.result_digest.as_key()
        return ContextPack(
            query=query,
            budget=token_budget,
            disclosure=level,
            estimated_tokens=used,
            confidence=confidence,
            abstained=False,
            generation=self.store.generation(),
            identity_generation=identity_generation,
            stale=stale,
            cache_hit=False,
            context_action_hash=action_hash,
            context_result_digest=result_digest,
            items=context_items,
            warnings=freshness_warnings,
        )
