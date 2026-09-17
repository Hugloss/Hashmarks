from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import time
from pathlib import Path
from functools import wraps
from typing import Any, Callable, Iterable, Mapping, ParamSpec, Sequence, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")

def _decision_scoped(
    method: Callable[_P, _R], *, allow_incomplete: bool
) -> Callable[_P, _R]:
    """Bind one public CodeMap decision to one freshness/readiness sample."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        if self._decision_session_depth == 0:
            incomplete_build = self.store.meta("sync.build_state") == "BUILDING"
            preflight = getattr(self, "_decision_preflight", None)
            if preflight is not None and not (allow_incomplete and incomplete_build):
                preflight(method.__name__, args, kwargs)
        with self.decision_session(_allow_incomplete=allow_incomplete):
            return method(self, *args, **kwargs)
    return wrapped


def decision_scoped(method: Callable[_P, _R]) -> Callable[_P, _R]:
    """Bind a decision to one complete repository-intelligence generation."""
    return _decision_scoped(method, allow_incomplete=False)


def incomplete_decision_scoped(method: Callable[_P, _R]) -> Callable[_P, _R]:
    """Allow a safety-reporting decision to describe an incomplete generation."""
    return _decision_scoped(method, allow_incomplete=True)


def diagnostic_producer(method: Callable[_P, _R]) -> Callable[_P, _R]:
    """Measure one high-level repository-intelligence producer when diagnostics are active."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        if not getattr(self, "_decision_diagnostics_enabled", False):
            return method(self, *args, **kwargs)
        with self._decision_diagnostic_span(method.__name__, args, kwargs):
            return method(self, *args, **kwargs)
    return wrapped


class DecisionSessionMixin:
    """Generation-bound read-only evidence reuse for CodeMap decisions."""
    @contextmanager
    def decision_session(self, *, diagnostics: bool = False, _allow_incomplete: bool = False):
        """Reuse immutable evidence primitives across many decisions on one generation.

        The session is read-only and generation-bound. It never caches final
        decisions and raises if the CodeMap generation changes while active.
        """
        if self._decision_session_depth == 0:
            observation = self._ensure_map_ready(_allow_incomplete=_allow_incomplete)
            self._decision_diagnostics_enabled = bool(diagnostics)
            self._decision_diagnostics_started_ns = time.perf_counter_ns() if diagnostics else 0
            self._decision_diagnostics_stack.clear()
            self._decision_diagnostics_spans.clear()
            self._decision_diagnostics_producers.clear()
            self._decision_diagnostics_sequence = 0
            generation = self.store.generation()
            self._decision_session_observation = observation
            self._decision_session_generation = generation
            self._decision_symbols_cache.clear()
            self._decision_file_row_cache.clear()
            self._decision_module_paths_cache.clear()
            self._decision_exact_symbols_cache.clear()
            self._decision_refs_cache.clear()
            self._decision_edges_from_cache.clear()
            self._decision_edges_for_path_cache.clear()
            self._decision_df_cache.clear()
            self._decision_candidates_cache.clear()
            self._decision_repository_identity_cache = None
            self._decision_snapshot_cache.clear()
            self._decision_task_action_cache.clear()
            self._decision_change_impact_owner_chain_cache.clear()
            self._decision_ownership_import_paths_cache.clear()
            self._decision_session_stats = {"task_result_hit": 0, "task_result_miss": 0, "symbols_hit": 0, "symbols_miss": 0, "file_row_hit": 0, "file_row_miss": 0, "module_paths_hit": 0, "module_paths_miss": 0, "exact_symbols_hit": 0, "exact_symbols_miss": 0, "refs_hit": 0, "refs_miss": 0, "edges_from_hit": 0, "edges_from_miss": 0, "edges_for_path_hit": 0, "edges_for_path_miss": 0, "df_hit": 0, "df_miss": 0, "candidates_hit": 0, "candidates_miss": 0, "snapshot_hit": 0, "snapshot_miss": 0, "task_action_hit": 0, "task_action_miss": 0, "impact_owner_chain_hit": 0, "impact_owner_chain_miss": 0, "ownership_import_paths_hit": 0, "ownership_import_paths_miss": 0}
            self.store.reset_read_counters()
        else:
            generation = self.store.generation()
        if self._decision_session_depth > 0 and self._decision_session_generation != generation:
            raise RuntimeError("CodeMap generation changed before nested decision session")
        self._decision_session_depth += 1
        try:
            yield self
            if self.store.generation() != self._decision_session_generation:
                raise RuntimeError("CodeMap generation changed during decision session")
        finally:
            self._decision_session_depth -= 1
            if self._decision_session_depth == 0:
                if self._decision_diagnostics_enabled:
                    self._decision_diagnostics_last = self._decision_diagnostics_receipt()
                self._decision_diagnostics_enabled = False
                self._decision_session_generation = None
                self._decision_session_observation = None
                self._decision_symbols_cache.clear()
                self._decision_file_row_cache.clear()
                self._decision_module_paths_cache.clear()
                self._decision_exact_symbols_cache.clear()
                self._decision_refs_cache.clear()
                self._decision_edges_from_cache.clear()
                self._decision_edges_for_path_cache.clear()
                self._decision_df_cache.clear()
                self._decision_candidates_cache.clear()
                self._decision_repository_identity_cache = None
                self._decision_snapshot_cache.clear()
                self._decision_task_action_cache.clear()
                self._decision_change_impact_owner_chain_cache.clear()
                self._decision_ownership_import_paths_cache.clear()

    @staticmethod
    def _diagnostic_normalize(value: object) -> object:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return value.as_posix()
        if isinstance(value, Mapping):
            return {str(k): DecisionSessionMixin._diagnostic_normalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
        if isinstance(value, (list, tuple)):
            return [DecisionSessionMixin._diagnostic_normalize(v) for v in value]
        return f"<{type(value).__module__}.{type(value).__qualname__}>"

    def _diagnostic_request_identity(self, name: str, args: tuple[object, ...], kwargs: Mapping[str, object]) -> str:
        payload = {
            "producer": name,
            "args": self._diagnostic_normalize(args),
            "kwargs": self._diagnostic_normalize(kwargs),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @contextmanager
    def _decision_diagnostic_span(self, name: str, args: tuple[object, ...], kwargs: Mapping[str, object]):
        self._decision_diagnostics_sequence += 1
        span_id = self._decision_diagnostics_sequence
        parent_id = self._decision_diagnostics_stack[-1]["id"] if self._decision_diagnostics_stack else None
        frame: dict[str, Any] = {
            "id": span_id,
            "name": name,
            "parent_id": parent_id,
            "started_ns": time.perf_counter_ns(),
            "child_ns": 0,
            "request_identity": self._diagnostic_request_identity(name, args, kwargs),
        }
        self._decision_diagnostics_stack.append(frame)
        try:
            yield
        finally:
            ended_ns = time.perf_counter_ns()
            current = self._decision_diagnostics_stack.pop()
            inclusive_ns = ended_ns - int(current["started_ns"])
            exclusive_ns = max(0, inclusive_ns - int(current["child_ns"]))
            if self._decision_diagnostics_stack:
                self._decision_diagnostics_stack[-1]["child_ns"] += inclusive_ns
            producer = self._decision_diagnostics_producers.setdefault(name, {
                "calls": 0, "inclusive_ns": 0, "exclusive_ns": 0, "request_identities": set(),
            })
            producer["calls"] += 1
            producer["inclusive_ns"] += inclusive_ns
            producer["exclusive_ns"] += exclusive_ns
            producer["request_identities"].add(str(current["request_identity"]))
            if len(self._decision_diagnostics_spans) < 256:
                self._decision_diagnostics_spans.append({
                    "id": span_id,
                    "parent_id": parent_id,
                    "producer": name,
                    "request_identity": current["request_identity"],
                    "inclusive_ns": inclusive_ns,
                    "exclusive_ns": exclusive_ns,
                })

    def _decision_diagnostics_receipt(self) -> dict[str, object]:
        stats = self.decision_session_stats()
        producers: dict[str, object] = {}
        for name, row in sorted(self._decision_diagnostics_producers.items()):
            unique = len(row["request_identities"])
            calls = int(row["calls"])
            producers[name] = {
                "calls": calls,
                "unique_requests": unique,
                "duplicate_calls": max(0, calls - unique),
                "inclusive_ns": int(row["inclusive_ns"]),
                "exclusive_ns": int(row["exclusive_ns"]),
            }
        reuse = {k: int(v) for k, v in stats.items() if k.endswith("_hit") or k.endswith("_miss")}
        store_reads = {k: int(v) for k, v in stats.items() if k.startswith("store_")}
        return {
            "schema": "hashmarks.decision-session-diagnostics.v1",
            "generation": self._decision_session_generation,
            "wall_time_ns": max(0, time.perf_counter_ns() - self._decision_diagnostics_started_ns),
            "producers": producers,
            "spans": list(self._decision_diagnostics_spans),
            "span_limit": 256,
            "spans_truncated": len(self._decision_diagnostics_spans) >= 256,
            "reuse": reuse,
            "store_reads": store_reads,
            "storage": "derived-not-persisted",
            "authority": "runtime-diagnostics-only",
            "execution_effect": "none",
        }

    def decision_session_diagnostics(self) -> dict[str, object] | None:
        """Return the most recently completed opt-in decision-session diagnostics receipt."""
        if self._decision_diagnostics_last is None:
            return None
        return json.loads(json.dumps(self._decision_diagnostics_last))

    def decision_session_stats(self) -> dict[str, int]:
        value = dict(self._decision_session_stats)
        for key, count in self.store.read_counters().items():
            value[f"store_{key}"] = int(count)
        return value

    def _session_symbols_for_path(self, path: str) -> list[dict[str, object]]:
        if self._decision_session_depth <= 0:
            return self.store.symbols_for_path(path)
        generation = int(self._decision_session_generation or self.store.generation())
        key = (generation, path)
        cached = self._decision_symbols_cache.get(key)
        if cached is not None:
            self._decision_session_stats["symbols_hit"] += 1
            return cached
        self._decision_session_stats["symbols_miss"] += 1
        value = self.store.symbols_for_path(path)
        self._decision_symbols_cache[key] = value
        return value

    def _session_file_row(self, path: str) -> dict[str, object] | None:
        if self._decision_session_depth <= 0:
            row = self.store.file_row(path)
            return None if row is None else dict(row)
        generation = int(self._decision_session_generation or self.store.generation())
        key = (generation, path)
        if key in self._decision_file_row_cache:
            self._decision_session_stats["file_row_hit"] += 1
            return self._decision_file_row_cache[key]
        self._decision_session_stats["file_row_miss"] += 1
        row = self.store.file_row(path)
        value = None if row is None else dict(row)
        self._decision_file_row_cache[key] = value
        return value

    def _session_module_paths(self, module: str) -> list[str]:
        normalized = module.strip(".")
        if not normalized:
            return []
        if self._decision_session_depth <= 0:
            return self.store.module_paths(normalized)
        generation = int(self._decision_session_generation or self.store.generation())
        key = (generation, normalized)
        cached = self._decision_module_paths_cache.get(key)
        if cached is not None:
            self._decision_session_stats["module_paths_hit"] += 1
            return list(cached)
        self._decision_session_stats["module_paths_miss"] += 1
        value = tuple(self.store.module_paths(normalized))
        self._decision_module_paths_cache[key] = value
        return list(value)

    def _session_preload_module_paths(self, modules: Iterable[str]) -> None:
        """Preload exact module identities that are already known by the caller.

        This collapses a set of independent indexed module lookups into one SQL
        read while retaining the exact ordered-prefix semantics of
        ``_session_module_paths``.  It is generation-local evidence only.
        """
        if self._decision_session_depth <= 0:
            return
        generation = int(self._decision_session_generation or self.store.generation())
        normalized = sorted({str(module).strip(".") for module in modules if str(module).strip(".")})
        missing = [module for module in normalized if (generation, module) not in self._decision_module_paths_cache]
        if not missing:
            return
        grouped = self.store.module_paths_many(missing)
        for module in missing:
            self._decision_module_paths_cache[(generation, module)] = tuple(grouped.get(module, ()))
            self._decision_session_stats["module_paths_miss"] += 1

    def _session_exact_symbol_candidates(
        self,
        terms: Sequence[str],
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        """Reuse exact-symbol evidence by its generation-stable query identity.

        The store orders exact symbols deterministically by ``path,start_line``.
        Therefore a cached result produced with a larger limit is an exact prefix
        source for a later smaller-limit request.  A larger later request still
        performs a physical read and replaces the cached prefix.  This cache is
        disposable process-local evidence only; it never stores a final decision.
        """
        normalized = tuple(sorted({str(term).lower() for term in terms if term}))
        requested = int(limit)
        if requested < 1 or not normalized:
            return []
        if self._decision_session_depth <= 0:
            return self.store.exact_symbol_candidates(list(normalized), limit=requested)
        generation = int(self._decision_session_generation or self.store.generation())
        key = (generation, normalized)
        cached = self._decision_exact_symbols_cache.get(key)
        if cached is not None and cached[0] >= requested:
            self._decision_session_stats["exact_symbols_hit"] += 1
            return [dict(row) for row in cached[1][:requested]]
        self._decision_session_stats["exact_symbols_miss"] += 1
        value = self.store.exact_symbol_candidates(list(normalized), limit=requested)
        self._decision_exact_symbols_cache[key] = (requested, tuple(dict(row) for row in value))
        return value

    def _session_refs_many(
        self,
        targets: Iterable[str],
        *,
        limit_per_target: int,
    ) -> dict[str, list[dict[str, object]]]:
        """Reuse per-target reverse-reference prefixes within one generation."""
        unique = list(dict.fromkeys(str(target) for target in targets if target))
        if not unique:
            return {}
        requested = min(max(1, int(limit_per_target)), 1024)
        if self._decision_session_depth <= 0:
            return self.store.refs_many(unique, limit_per_target=requested)
        generation = int(self._decision_session_generation or self.store.generation())
        target_short = {target: target.rsplit(".", 1)[-1] for target in unique}
        missing_shorts = list(dict.fromkeys(
            short for short in target_short.values()
            if (generation, short) not in self._decision_refs_cache
            or self._decision_refs_cache[(generation, short)][0] < requested
        ))
        if missing_shorts:
            fetched = self.store.refs_many(missing_shorts, limit_per_target=requested)
            for short in missing_shorts:
                self._decision_refs_cache[(generation, short)] = (
                    requested,
                    tuple(dict(row) for row in fetched.get(short, ())),
                )
                self._decision_session_stats["refs_miss"] += 1
        result: dict[str, list[dict[str, object]]] = {}
        missing_set = set(missing_shorts)
        for target in unique:
            short = target_short[target]
            if short not in missing_set:
                self._decision_session_stats["refs_hit"] += 1
            cached = self._decision_refs_cache.get((generation, short))
            result[target] = [] if cached is None else [dict(row) for row in cached[1][:requested]]
        return result

    def _session_edges_from_many(
        self,
        seeds: Iterable[tuple[str, str]],
        *,
        limit_per_seed: int,
    ) -> dict[tuple[str, str], list[dict[str, object]]]:
        """Reuse bounded path+source edge prefixes for already-known seeds."""
        unique = list(dict.fromkeys(
            (str(path), str(source)) for path, source in seeds if path and source
        ))
        if not unique:
            return {}
        requested = min(max(1, int(limit_per_seed)), 1024)
        if self._decision_session_depth <= 0:
            return self.store.edges_from_many(unique, limit_per_seed=requested)
        generation = int(self._decision_session_generation or self.store.generation())
        missing = [
            seed for seed in unique
            if (generation, seed[0], seed[1]) not in self._decision_edges_from_cache
            or self._decision_edges_from_cache[(generation, seed[0], seed[1])][0] < requested
        ]
        if missing:
            fetched = self.store.edges_from_many(missing, limit_per_seed=requested)
            for seed in missing:
                self._decision_edges_from_cache[(generation, seed[0], seed[1])] = (
                    requested,
                    tuple(dict(row) for row in fetched.get(seed, ())),
                )
                self._decision_session_stats["edges_from_miss"] += 1
        result: dict[tuple[str, str], list[dict[str, object]]] = {}
        missing_set = set(missing)
        for seed in unique:
            if seed not in missing_set:
                self._decision_session_stats["edges_from_hit"] += 1
            cached = self._decision_edges_from_cache.get((generation, seed[0], seed[1]))
            result[seed] = [] if cached is None else [dict(row) for row in cached[1][:requested]]
        return result

    def _session_edges_for_paths_many(
        self,
        paths: Iterable[str],
        *,
        limit_per_path: int,
    ) -> dict[str, list[dict[str, object]]]:
        """Reuse bounded path-level edge prefixes within one decision generation."""
        unique = list(dict.fromkeys(str(path) for path in paths if path))
        if not unique:
            return {}
        requested = min(max(1, int(limit_per_path)), 1024)
        if self._decision_session_depth <= 0:
            return self.store.edges_for_paths_many(unique, limit_per_path=requested)
        generation = int(self._decision_session_generation or self.store.generation())
        missing = [
            path for path in unique
            if (generation, path) not in self._decision_edges_for_path_cache
            or self._decision_edges_for_path_cache[(generation, path)][0] < requested
        ]
        if missing:
            fetched = self.store.edges_for_paths_many(missing, limit_per_path=requested)
            for path in missing:
                self._decision_edges_for_path_cache[(generation, path)] = (
                    requested,
                    tuple(dict(row) for row in fetched.get(path, ())),
                )
                self._decision_session_stats["edges_for_path_miss"] += 1
        result: dict[str, list[dict[str, object]]] = {}
        missing_set = set(missing)
        for path in unique:
            if path not in missing_set:
                self._decision_session_stats["edges_for_path_hit"] += 1
            cached = self._decision_edges_for_path_cache.get((generation, path))
            result[path] = [] if cached is None else [dict(row) for row in cached[1][:requested]]
        return result

    def _session_file_rows(self, paths: Iterable[str]) -> dict[str, dict[str, object]]:
        unique = sorted({str(path) for path in paths if path})
        if not unique:
            return {}
        if self._decision_session_depth <= 0:
            return self.store.file_rows(unique)
        generation = int(self._decision_session_generation or self.store.generation())
        missing = [path for path in unique if (generation, path) not in self._decision_file_row_cache]
        if missing:
            rows = self.store.file_rows(missing)
            for path in missing:
                self._decision_file_row_cache[(generation, path)] = rows.get(path)
                self._decision_session_stats["file_row_miss"] += 1
        output: dict[str, dict[str, object]] = {}
        for path in unique:
            value = self._decision_file_row_cache.get((generation, path))
            if value is not None:
                output[path] = value
            if path not in missing:
                self._decision_session_stats["file_row_hit"] += 1
        return output

    def _session_preload_symbols(self, paths: Sequence[str]) -> None:
        if self._decision_session_depth <= 0:
            return
        generation = int(self._decision_session_generation or self.store.generation())
        missing = sorted({path for path in paths if path and (generation, path) not in self._decision_symbols_cache})
        if not missing:
            return
        grouped: dict[str, list[dict[str, object]]] = {path: [] for path in missing}
        # A global LIMIT across multiple paths can starve later paths and must
        # not be cached as if each per-path list were complete.  The caller has
        # already bounded the candidate path set, so preload complete symbol
        # evidence for exactly those paths in one query.
        for row in self.store.symbols_for_paths_complete(missing):
            path = str(row.get("path") or "")
            if path in grouped:
                value = dict(row)
                value.pop("row_type", None)
                grouped[path].append(value)
        for path, rows in grouped.items():
            self._decision_symbols_cache[(generation, path)] = rows
            self._decision_session_stats["symbols_miss"] += 1

    def _session_symbols_for_paths(self, paths: Sequence[str], *, limit: int) -> list[dict[str, object]]:
        """Return symbol rows for a path set while reusing per-path session evidence."""
        unique = sorted({str(path) for path in paths if path})
        if not unique:
            return []
        if self._decision_session_depth <= 0:
            return self.store.symbols_for_paths(unique, limit=limit)
        self._session_preload_symbols(unique)
        rows: list[dict[str, object]] = []
        for path in unique:
            for row in self._session_symbols_for_path(path):
                rows.append({"row_type": "symbol", **row})
                if len(rows) >= limit:
                    return rows
        return rows

    def _session_lexical_document_frequencies(self, terms: Sequence[str]) -> tuple[int, dict[str, int]]:
        # The SQLite query canonicalizes to a lower-cased set; mirror that in the
        # process-local key so reordered/duplicated equivalent queries share evidence.
        normalized = tuple(sorted({str(term).lower() for term in terms if term}))
        if self._decision_session_depth <= 0:
            return self.store.lexical_document_frequencies(normalized)
        generation = int(self._decision_session_generation or self.store.generation())
        key = (generation, normalized)
        cached = self._decision_df_cache.get(key)
        if cached is not None:
            self._decision_session_stats["df_hit"] += 1
            return cached
        self._decision_session_stats["df_miss"] += 1
        value = self.store.lexical_document_frequencies(normalized)
        self._decision_df_cache[key] = value
        return value

    def _session_lexical_file_candidates(self, terms: Sequence[str], *, limit: int) -> list[dict[str, object]]:
        # Cache by the store's true semantic identity, not caller token order.
        normalized = tuple(sorted({str(term).lower() for term in terms if term}))
        if self._decision_session_depth <= 0:
            return self.store.lexical_file_candidates(normalized, limit=limit)
        generation = int(self._decision_session_generation or self.store.generation())
        key = (generation, normalized, int(limit))
        cached = self._decision_candidates_cache.get(key)
        if cached is not None:
            self._decision_session_stats["candidates_hit"] += 1
            return cached
        self._decision_session_stats["candidates_miss"] += 1
        value = self.store.lexical_file_candidates(normalized, limit=limit)
        self._decision_candidates_cache[key] = value
        return value
