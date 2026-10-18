from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, TypedDict

from hashmarks.operation_contract import operation_schema, validate_operation_response
from hashmarks.paths import normalize_relative_path

from .context_defaults import REPOSITORY_CONTEXT_DEFAULTS
from .decision_session import ReadScopeOwner, decision_scoped
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
from .repository_domains import is_test_path
from .singleflight import SingleFlight
from .work_context import WorkContextProjection

if TYPE_CHECKING:
    from .context_cache import ContextCache
    from .decision_session import DecisionScope
    from .evidence_graph import RepositoryRelationships
    from .find_engine import RepositorySearch
    from .repository_source import RepositorySource


@dataclass(frozen=True, slots=True)
class _ContextPackMetadata:
    query: str
    token_budget: int
    level: ContextDisclosure
    confidence: str
    generation: int
    identity_generation: int | None
    stale: bool | None


@dataclass(slots=True)
class _ContextItemState:
    items: list[ContextItem]
    used: int
    seen: set[tuple[str, str | None]]
    item_index: dict[tuple[str, str | None], int]


class TaskContextPlan(TypedDict):
    schema: str
    task: str
    query: str
    intent: str
    token_budget: int
    disclosure: str
    limit: int
    reasons: list[str]
    ranking_effect: str


class RepositoryContext(WorkContextProjection, ReadScopeOwner):
    """Own context disclosure and reuse over already-qualified repository evidence."""

    def __init__(
        self,
        source: RepositorySource,
        search: RepositorySearch,
        relationships: RepositoryRelationships,
        cache: ContextCache,
    ) -> None:
        if search.reads is not source.reads or relationships.reads is not source.reads:
            raise ValueError("Context inputs must share one repository read scope")
        self.source = source
        self.search = search
        self.relationships = relationships
        self.cache = cache
        self.native = relationships.native
        self.files = source.files
        self.store = source.store
        self.workspace = source.workspace
        self._context_flight: SingleFlight[ContextPack] = SingleFlight()

    @property
    def reads(self) -> DecisionScope:
        return self.source.reads

    @decision_scoped
    def orient(self, *, max_areas: int = 12) -> dict[str, object]:
        self.reads.ready()
        stats = self.store.stats()
        areas = list(self.store.top_level_counts().items())[:max_areas]
        generation, identity_generation, stale = self.reads.generation_status()
        result: dict[str, object] = {
            "schema": operation_schema("repository_context"),
            "workspace": str(self.workspace),
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "languages": self.store.language_counts(),
            "areas": [{"path": path, "indexed_files": count} for path, count in areas],
            "stats": stats,
            "projects": self.native._fresh_project_nodes()[:20],
            "project_edges": self.native._fresh_project_edges()[:40],
            "frequent_dependency_targets": [
                {"target": target, "references": count}
                for target, count in self.store.top_edge_targets(10)
            ],
            "guidance": "Use find/outline/symbol/deps before reading full files.",
        }
        return validate_operation_response("repository_context", result)

    def _context_freshness_warnings(self, stale: bool | None) -> tuple[str, ...]:
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
        return {
            "schema": "hashmarks.context-action.v1",
            "retrieval_protocol": "hashmarks.progressive-context.v0.10.14",
            "workspace_fingerprint": self.store.meta("workspace_fingerprint", "") or "",
            "codemap_generation": generation,
            "policy_fingerprint": self.files.policy_fingerprint(),
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

    @decision_scoped
    def task_plan(
        self,
        task: str,
        *,
        min_budget: int = 512,
        max_budget: int = 2400,
    ) -> TaskContextPlan:
        """Return a deterministic, bounded evidence-budget plan for one task.

        This is advisory policy over existing retrieval/disclosure primitives. It
        does not alter ``context()`` defaults or canonical ``find_task()`` ranking.
        """
        if min_budget < 128:
            raise ValueError("min_budget must be at least 128")
        if max_budget < min_budget:
            raise ValueError("max_budget must be >= min_budget")
        views = self.search.task_query_views(task)
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

    @decision_scoped
    def task(
        self,
        task: str,
        *,
        token_budget: int | None = None,
        disclosure: ContextDisclosure | str | None = None,
    ) -> ContextPack:
        """Build context using a deterministic adaptive plan unless overridden."""
        plan = self.task_plan(task)
        budget = (
            int(plan["token_budget"]) if token_budget is None else int(token_budget)
        )
        level: ContextDisclosure | str = (
            str(plan["disclosure"]) if disclosure is None else disclosure
        )
        return self.build(
            str(plan["query"]),
            token_budget=budget,
            limit=int(plan["limit"]),
            disclosure=level,
        )

    @decision_scoped
    def build(
        self,
        query: str,
        *,
        token_budget: int = REPOSITORY_CONTEXT_DEFAULTS.token_budget,
        limit: int = REPOSITORY_CONTEXT_DEFAULTS.limit,
        disclosure: ContextDisclosure | str = REPOSITORY_CONTEXT_DEFAULTS.disclosure,
    ) -> ContextPack:
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
        self.reads.ready()
        generation, _identity_generation, stale = self.reads.generation_status()
        key = (
            "context-flight.v1",
            self.store.meta("workspace_fingerprint", "") or "",
            generation,
            self.files.policy_fingerprint(),
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
        action: dict[str, object],
        metadata: _ContextPackMetadata,
    ) -> ContextPack | None:
        cached = self.cache.get(action)
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
            query=metadata.query,
            budget=metadata.token_budget,
            disclosure=metadata.level,
            estimated_tokens=int(cached.payload.get("estimated_tokens", 0)),
            confidence=str(cached.payload.get("confidence", metadata.confidence)),
            abstained=False,
            generation=metadata.generation,
            identity_generation=metadata.identity_generation,
            stale=metadata.stale,
            cache_hit=True,
            context_action_hash=cached.action_hash,
            context_result_digest=cached.result_digest.as_key(),
            items=cached_items,
            warnings=self._context_freshness_warnings(metadata.stale),
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

    @staticmethod
    def _context_dependency_item(
        dep: dict[str, object],
        raw_edge: dict[str, object],
        hit: SearchHit,
        remaining_tokens: int,
        seen: set[tuple[str, str | None]],
    ) -> tuple[tuple[str, str], ContextItem] | None:
        if (
            EvidenceVisibility(str(dep["evidence_visibility"]))
            is EvidenceVisibility.DENY
        ):
            return None
        key = (str(dep["path"]), str(dep["qualname"]))
        if key in seen:
            return None
        content = str(dep["signature"] or dep["qualname"])
        tokens = estimate_tokens(content)
        if tokens <= 0 or tokens > remaining_tokens:
            return None
        return key, ContextItem(
            path=str(dep["path"]),
            representation="signature",
            content=content,
            estimated_tokens=tokens,
            symbol=str(dep["qualname"]),
            reason=f"{raw_edge.get('kind')} dependency of {hit.qualname}",
        )

    def _context_add_dependency_evidence(
        self,
        hits: tuple[SearchHit, ...],
        state: _ContextItemState,
        token_budget: int,
    ) -> None:
        evidence_hits = [hit for hit in hits[:4] if hit.qualname is not None]
        evidence_edge_map = self.reads.edges_from_many(
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
        dependency_rows = self.reads.exact_symbol_candidates(
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
                deps_by_short.setdefault(alias, []).append(dep)
        for hit, raw_edge in edge_rows:
            if state.used >= token_budget:
                break
            target = str(raw_edge.get("target", ""))
            short = target.rsplit(".", 1)[-1].lower()
            for dep in deps_by_short.get(short, ())[:3]:
                admitted = self._context_dependency_item(
                    dep,
                    raw_edge,
                    hit,
                    token_budget - state.used,
                    state.seen,
                )
                if admitted is None:
                    continue
                dep_key, item = admitted
                state.seen.add(dep_key)
                state.item_index[dep_key] = len(state.items)
                state.items.append(item)
                state.used += item.estimated_tokens
                break

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
        query_tokens = {value.lower() for value in _WORD_RE.findall(query)}
        wants_tests = bool(query_tokens & {"test", "tests", "testing", "spec", "specs"})
        upgrade_hits = [
            (hit, hit.start_line, hit.end_line)
            for hit in hits
            if hit.qualname is not None
            and hit.signature is not None
            and hit.evidence_visibility is EvidenceVisibility.SOURCE
            and hit.start_line is not None
            and hit.end_line is not None
            and hit.score >= 45
            and ((not is_test_path(hit.path)) or wants_tests)
        ]
        upgrade_hits.sort(
            key=lambda item: (
                is_test_path(item[0].path) and not wants_tests,
                -item[0].score,
                item[0].path,
            )
        )
        upgrades = 0
        for hit, start, end in upgrade_hits:
            if upgrades >= 4:
                break
            key = (hit.path, hit.qualname)
            index = item_index.get(key)
            if index is None:
                continue
            current = items[index]
            try:
                body = self.source.slice(hit.path, start, end, qualname=hit.qualname)
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

    def _context_items(
        self,
        query: str,
        hits: tuple[SearchHit, ...],
        metadata: _ContextPackMetadata,
    ) -> _ContextItemState:
        if metadata.level is ContextDisclosure.ORIENT:
            items, used = self._context_orientation_items(
                hits, token_budget=metadata.token_budget
            )
            return _ContextItemState(items, used, set(), {})
        items, used, seen, item_index = self._context_outline_items(
            hits, token_budget=metadata.token_budget
        )
        state = _ContextItemState(items, used, seen, item_index)
        if metadata.level in {ContextDisclosure.EVIDENCE, ContextDisclosure.SOURCE}:
            self._context_add_dependency_evidence(hits, state, metadata.token_budget)
        if metadata.level is ContextDisclosure.SOURCE:
            state.used = self._context_upgrade_source_items(
                hits,
                query=query,
                items=state.items,
                used=state.used,
                item_index=state.item_index,
                token_budget=metadata.token_budget,
            )
        return state

    def _context_pack_metadata(
        self,
        query: str,
        token_budget: int,
        level: ContextDisclosure,
        hits: tuple[SearchHit, ...],
    ) -> _ContextPackMetadata:
        best = hits[0].score if hits else 0.0
        confidence = (
            "high" if best >= 70 else "medium" if best >= 30 else "insufficient"
        )
        generation, identity_generation, stale = self.reads.generation_status()
        return _ContextPackMetadata(
            query=query,
            token_budget=token_budget,
            level=level,
            confidence=confidence,
            generation=generation,
            identity_generation=identity_generation,
            stale=stale,
        )

    def _context_impl(
        self,
        query: str,
        *,
        token_budget: int = 4000,
        limit: int = 30,
        disclosure: ContextDisclosure | str = ContextDisclosure.SOURCE,
    ) -> ContextPack:
        """Build one bounded context projection from a shared evidence base."""
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

        hits = self.search.find(query, limit=limit)
        metadata = self._context_pack_metadata(query, token_budget, level, hits)
        if metadata.confidence == "insufficient":
            return ContextPack(
                query=query,
                budget=token_budget,
                disclosure=level,
                estimated_tokens=0,
                confidence=metadata.confidence,
                abstained=True,
                generation=metadata.generation,
                identity_generation=metadata.identity_generation,
                stale=metadata.stale,
                warnings=(
                    "retrieval confidence insufficient; repository context omitted",
                ),
            )

        action = self._context_action(
            query=query,
            token_budget=token_budget,
            limit=limit,
            level=level,
            generation=metadata.generation,
            hits=hits,
        )
        cache_allowed = metadata.stale is False or (
            metadata.stale is None and level is not ContextDisclosure.SOURCE
        )
        if cache_allowed:
            cached_pack = self._context_cached_pack(action, metadata)
            if cached_pack is not None:
                return cached_pack

        item_state = self._context_items(query, hits, metadata)

        freshness_warnings = self._context_freshness_warnings(metadata.stale)
        context_items = tuple(item_state.items)
        action_hash = None
        result_digest = None
        if cache_allowed:
            stored = self.cache.put(
                action,
                self._context_payload(
                    context_items,
                    estimated_tokens=item_state.used,
                    confidence=metadata.confidence,
                ),
            )
            action_hash = stored.action_hash
            result_digest = stored.result_digest.as_key()
        return ContextPack(
            query=query,
            budget=token_budget,
            disclosure=level,
            estimated_tokens=item_state.used,
            confidence=metadata.confidence,
            abstained=False,
            generation=self.store.generation(),
            identity_generation=metadata.identity_generation,
            stale=metadata.stale,
            cache_hit=False,
            context_action_hash=action_hash,
            context_result_digest=result_digest,
            items=context_items,
            warnings=freshness_warnings,
        )

    def _instruction_seed_paths(
        self,
        query: str,
        *,
        seed_limit: int,
    ) -> tuple[list[str], str]:
        try:
            rel = normalize_relative_path(query, allow_root=False)
        except ValueError:
            rel = None
        candidate = None if rel is None else self.workspace / rel
        if rel is not None and candidate is not None and candidate.exists():
            return [rel], "explicit-path"

        seed_paths: list[str] = []
        for hit in self.search.find_task(query, limit=seed_limit):
            if hit.path not in seed_paths:
                seed_paths.append(hit.path)
        return seed_paths, "task-retrieval"

    @decision_scoped
    def instruction_scope(
        self, query: str, *, seed_limit: int = 8
    ) -> dict[str, object]:
        """Compose selected instruction paths without moving retrieval into Source."""
        if seed_limit < 1:
            raise ValueError("seed_limit must be >= 1")
        self.reads.ready()
        paths, basis = self._instruction_seed_paths(query, seed_limit=seed_limit)
        return self.source.instruction_scope(paths, query=query, scope_source=basis)
