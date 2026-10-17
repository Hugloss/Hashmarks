from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Concatenate, ParamSpec, Protocol, TypeVar

from .repository_index_store import git_base_identity
from .store_queries import MAX_REFERENCE_QUERY_ROWS

if TYPE_CHECKING:
    from hashmarks.client import RepositoryObservation

    from .indexing_lifecycle import RepositoryIndex
    from .repository_index_store import WorkspaceMapStore
    from .repository_observation import RepositoryObservationSource
    from .watch_continuity import WatchContinuityRecord


class ReadScopeOwner(Protocol):
    """A static, single-capability contract for read-scoped operations."""

    if TYPE_CHECKING:

        @property
        def reads(self) -> DecisionScope: ...


@dataclass(frozen=True, eq=False)
class ReadScope:
    """One disposable reuse scope bound to existing repository authority.

    Object identity scopes local memoization only; it is not a serialized
    repository identity, generation, history record or execution lease.
    """

    generation: int
    observation: RepositoryObservation | None


_P = ParamSpec("_P")
_R = TypeVar("_R")
_S = TypeVar("_S", bound=ReadScopeOwner)


@dataclass
class _DecisionDiagnosticFrame:
    id: int
    name: str
    parent_id: int | None
    started_ns: int
    request_identity: str
    child_ns: int = 0


@dataclass
class _DecisionProducerStats:
    calls: int = 0
    inclusive_ns: int = 0
    exclusive_ns: int = 0
    request_identities: set[str] = field(default_factory=set)


class DecisionRefreshRequired(RuntimeError):
    """Signal that one path must refresh before a read-only decision restarts."""

    def __init__(self, path: str) -> None:
        super().__init__(f"CodeMap path refresh required before decision: {path}")
        self.path = path


def _decision_scoped(
    method: Callable[Concatenate[_S, _P], _R], *, allow_incomplete: bool
) -> Callable[Concatenate[_S, _P], _R]:
    """Bind one public CodeMap decision to one freshness/readiness sample."""

    @wraps(method)
    def wrapped(self: _S, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        owner = self.reads
        if owner._depth > 0:
            with owner.session(_allow_incomplete=allow_incomplete):
                return method(self, *args, **kwargs)

        refreshed: set[str] = set()
        while True:
            try:
                with owner.session(_allow_incomplete=allow_incomplete):
                    return method(self, *args, **kwargs)
            except DecisionRefreshRequired as exc:
                if exc.path in refreshed:
                    raise RuntimeError(
                        f"CodeMap path remained stale after refresh: {exc.path}"
                    ) from exc
                refreshed.add(exc.path)
                owner._index.reconcile_path(exc.path)

    return wrapped


def decision_scoped(
    method: Callable[Concatenate[_S, _P], _R],
) -> Callable[Concatenate[_S, _P], _R]:
    """Bind a decision to one complete repository-intelligence generation."""
    return _decision_scoped(method, allow_incomplete=False)


def incomplete_decision_scoped(
    method: Callable[Concatenate[_S, _P], _R],
) -> Callable[Concatenate[_S, _P], _R]:
    """Allow a safety-reporting decision to describe an incomplete generation."""
    return _decision_scoped(method, allow_incomplete=True)


def diagnostic_producer(
    method: Callable[Concatenate[_S, _P], _R],
) -> Callable[Concatenate[_S, _P], _R]:
    """Measure one high-level repository-intelligence producer when diagnostics are active."""

    @wraps(method)
    def wrapped(self: _S, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        owner = self.reads
        if not owner._diagnostics_enabled:
            return method(self, *args, **kwargs)
        with owner.diagnostic_span(
            getattr(method, "__name__", "unknown"), args, kwargs
        ):
            return method(self, *args, **kwargs)

    return wrapped


class DecisionScope:
    """Own generation-bound repository reads and primitive query reuse."""

    def __init__(
        self,
        index: RepositoryIndex,
        store: WorkspaceMapStore,
        observations: RepositoryObservationSource,
    ) -> None:
        self._index = index
        self._store = store
        self._observations = observations
        self.workspace = index.workspace
        self._scope: ReadScope | None = None
        self._depth = 0
        self._generation: int | None = None
        self._observation: RepositoryObservation | None = None
        self._symbols_cache: dict[tuple[int, str], list[dict[str, object]]] = {}
        self._file_row_cache: dict[tuple[int, str], dict[str, object] | None] = {}
        self._module_paths_cache: dict[tuple[int, str], tuple[str, ...]] = {}
        self._exact_symbols_cache: dict[
            tuple[int, tuple[str, ...]], tuple[int, tuple[dict[str, object], ...]]
        ] = {}
        self._refs_cache: dict[
            tuple[int, str], tuple[int, tuple[dict[str, object], ...]]
        ] = {}
        self._edges_from_cache: dict[
            tuple[int, str, str], tuple[int, tuple[dict[str, object], ...]]
        ] = {}
        self._edges_for_path_cache: dict[
            tuple[int, str], tuple[int, tuple[dict[str, object], ...]]
        ] = {}
        self._df_cache: dict[
            tuple[int, tuple[str, ...]], tuple[int, dict[str, int]]
        ] = {}
        self._candidates_cache: dict[
            tuple[int, tuple[str, ...], int, tuple[str, ...] | None],
            list[dict[str, object]],
        ] = {}
        self._repository_identity_cache: tuple[int, str] | None = None
        self._stats = {
            "task_result_hit": 0,
            "task_result_miss": 0,
            "symbols_hit": 0,
            "symbols_miss": 0,
            "file_row_hit": 0,
            "file_row_miss": 0,
            "module_paths_hit": 0,
            "module_paths_miss": 0,
            "exact_symbols_hit": 0,
            "exact_symbols_miss": 0,
            "refs_hit": 0,
            "refs_miss": 0,
            "edges_from_hit": 0,
            "edges_from_miss": 0,
            "edges_for_path_hit": 0,
            "edges_for_path_miss": 0,
            "df_hit": 0,
            "df_miss": 0,
            "candidates_hit": 0,
            "candidates_miss": 0,
            "snapshot_hit": 0,
            "snapshot_miss": 0,
            "task_action_hit": 0,
            "task_action_miss": 0,
            "impact_owner_chain_hit": 0,
            "impact_owner_chain_miss": 0,
            "ownership_import_paths_hit": 0,
            "ownership_import_paths_miss": 0,
        }
        self._diagnostics_enabled = False
        self._diagnostics_started_ns = 0
        self._diagnostics_sequence = 0
        self._diagnostics_stack: list[_DecisionDiagnosticFrame] = []
        self._diagnostics_spans: list[dict[str, object]] = []
        self._diagnostics_producers: dict[str, _DecisionProducerStats] = {}
        self._diagnostics_last: dict[str, object] | None = None

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def generation(self) -> int | None:
        return self._generation

    @property
    def observation(self) -> RepositoryObservation | None:
        return self._observation

    @property
    def scope(self) -> ReadScope | None:
        return self._scope

    def ready(self, *, _allow_incomplete: bool = False) -> RepositoryObservation | None:
        if self._depth > 0:
            return self._observation
        return self._index.ensure_ready(_allow_incomplete=_allow_incomplete)

    def count(self, name: str) -> None:
        self._stats[name] += 1

    def repository_identity(self) -> str:
        generation = self._store.generation()
        cached = self._repository_identity_cache
        if self._depth > 0 and cached is not None and cached[0] == generation:
            return cached[1]
        base = git_base_identity(self.workspace)
        if base:
            identity = f"git-tree:{base}"
        else:
            path_digest = hashlib.sha256(os.fsencode(str(self.workspace))).hexdigest()
            identity = f"workspace:{path_digest}"
        if self._depth > 0:
            self._repository_identity_cache = (generation, identity)
        return identity

    """Generation-bound read-only evidence reuse for CodeMap decisions."""

    def _clear_decision_session_caches(self) -> None:
        self._symbols_cache.clear()
        self._file_row_cache.clear()
        self._module_paths_cache.clear()
        self._exact_symbols_cache.clear()
        self._refs_cache.clear()
        self._edges_from_cache.clear()
        self._edges_for_path_cache.clear()
        self._df_cache.clear()
        self._candidates_cache.clear()
        self._repository_identity_cache = None

    def _begin_decision_session(
        self, *, diagnostics: bool, allow_incomplete: bool
    ) -> int:
        observation = self.ready(_allow_incomplete=allow_incomplete)
        self._diagnostics_enabled = bool(diagnostics)
        self._diagnostics_started_ns = time.perf_counter_ns() if diagnostics else 0
        self._diagnostics_stack.clear()
        self._diagnostics_spans.clear()
        self._diagnostics_producers.clear()
        self._diagnostics_sequence = 0
        generation = self._store.generation()
        self._observation = observation
        self._generation = generation
        self._scope = ReadScope(generation, observation)
        self._clear_decision_session_caches()
        self._stats = {
            "task_result_hit": 0,
            "task_result_miss": 0,
            "symbols_hit": 0,
            "symbols_miss": 0,
            "file_row_hit": 0,
            "file_row_miss": 0,
            "module_paths_hit": 0,
            "module_paths_miss": 0,
            "exact_symbols_hit": 0,
            "exact_symbols_miss": 0,
            "refs_hit": 0,
            "refs_miss": 0,
            "edges_from_hit": 0,
            "edges_from_miss": 0,
            "edges_for_path_hit": 0,
            "edges_for_path_miss": 0,
            "df_hit": 0,
            "df_miss": 0,
            "candidates_hit": 0,
            "candidates_miss": 0,
            "snapshot_hit": 0,
            "snapshot_miss": 0,
            "task_action_hit": 0,
            "task_action_miss": 0,
            "impact_owner_chain_hit": 0,
            "impact_owner_chain_miss": 0,
            "ownership_import_paths_hit": 0,
            "ownership_import_paths_miss": 0,
        }
        self._store.reset_read_counters()
        return generation

    def _finish_decision_session(self) -> None:
        if self._diagnostics_enabled:
            self._diagnostics_last = self._decision_diagnostics_receipt()
        self._diagnostics_enabled = False
        self._generation = None
        self._scope = None
        self._observation = None
        self._clear_decision_session_caches()

    def _decision_session_entry_generation(
        self,
        *,
        diagnostics: bool,
        allow_incomplete: bool,
        expected_generation: int | None,
    ) -> int:
        if self._depth == 0:
            generation = self._begin_decision_session(
                diagnostics=diagnostics,
                allow_incomplete=allow_incomplete,
            )
            if expected_generation is not None and generation != expected_generation:
                self._finish_decision_session()
                raise RuntimeError(
                    "CodeMap generation changed before expected decision session "
                    f"({expected_generation} -> {generation})"
                )
            return generation

        generation = self._store.generation()
        if self._generation != generation:
            raise RuntimeError(
                "CodeMap generation changed before nested decision session"
            )
        if expected_generation is not None and self._generation != expected_generation:
            raise RuntimeError(
                "CodeMap generation changed before expected decision session "
                f"({expected_generation} -> {self._generation})"
            )
        return generation

    @contextmanager
    def session(
        self,
        *,
        diagnostics: bool = False,
        _allow_incomplete: bool = False,
        expected_generation: int | None = None,
    ) -> Generator[ReadScope, None, None]:
        """Reuse immutable evidence primitives across many decisions on one generation.

        The session is read-only and generation-bound. It never caches final
        decisions and raises if the CodeMap generation changes while active.
        """
        generation = self._decision_session_entry_generation(
            diagnostics=diagnostics,
            allow_incomplete=_allow_incomplete,
            expected_generation=expected_generation,
        )
        self._depth += 1
        try:
            scope = self.scope
            assert scope is not None
            yield scope
            if self._store.generation() != self._generation:
                raise RuntimeError("CodeMap generation changed during decision session")
        finally:
            self._depth -= 1
            if self._depth == 0:
                self._finish_decision_session()

    @staticmethod
    def _diagnostic_normalize(value: object) -> object:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return value.as_posix()
        if isinstance(value, Mapping):
            return {
                str(k): DecisionScope._diagnostic_normalize(v)
                for k, v in sorted(value.items(), key=lambda item: str(item[0]))
            }
        if isinstance(value, (list, tuple)):
            return [DecisionScope._diagnostic_normalize(v) for v in value]
        return f"<{type(value).__module__}.{type(value).__qualname__}>"

    def _diagnostic_request_identity(
        self, name: str, args: tuple[object, ...], kwargs: Mapping[str, object]
    ) -> str:
        payload = {
            "producer": name,
            "args": self._diagnostic_normalize(args),
            "kwargs": self._diagnostic_normalize(kwargs),
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @contextmanager
    def diagnostic_span(
        self, name: str, args: tuple[object, ...], kwargs: Mapping[str, object]
    ) -> Generator[None, None, None]:
        self._diagnostics_sequence += 1
        span_id = self._diagnostics_sequence
        parent_id = self._diagnostics_stack[-1].id if self._diagnostics_stack else None
        frame = _DecisionDiagnosticFrame(
            id=span_id,
            name=name,
            parent_id=parent_id,
            started_ns=time.perf_counter_ns(),
            request_identity=self._diagnostic_request_identity(name, args, kwargs),
        )
        self._diagnostics_stack.append(frame)
        try:
            yield
        finally:
            ended_ns = time.perf_counter_ns()
            current = self._diagnostics_stack.pop()
            inclusive_ns = ended_ns - current.started_ns
            exclusive_ns = max(0, inclusive_ns - current.child_ns)
            if self._diagnostics_stack:
                self._diagnostics_stack[-1].child_ns += inclusive_ns
            producer = self._diagnostics_producers.setdefault(
                name, _DecisionProducerStats()
            )
            producer.calls += 1
            producer.inclusive_ns += inclusive_ns
            producer.exclusive_ns += exclusive_ns
            producer.request_identities.add(current.request_identity)

            if len(self._diagnostics_spans) < 256:
                self._diagnostics_spans.append(
                    {
                        "id": span_id,
                        "parent_id": parent_id,
                        "producer": name,
                        "request_identity": current.request_identity,
                        "inclusive_ns": inclusive_ns,
                        "exclusive_ns": exclusive_ns,
                    }
                )

    def _decision_diagnostics_receipt(self) -> dict[str, object]:
        stats = self.stats()
        producers: dict[str, object] = {}
        for name, row in sorted(self._diagnostics_producers.items()):
            unique = len(row.request_identities)
            calls = row.calls
            producers[name] = {
                "calls": calls,
                "unique_requests": unique,
                "duplicate_calls": max(0, calls - unique),
                "inclusive_ns": row.inclusive_ns,
                "exclusive_ns": row.exclusive_ns,
            }
        reuse = {
            k: int(v)
            for k, v in stats.items()
            if k.endswith("_hit") or k.endswith("_miss")
        }
        store_reads = {k: int(v) for k, v in stats.items() if k.startswith("store_")}
        return {
            "schema": "hashmarks.decision-session-diagnostics.v1",
            "generation": self._generation,
            "wall_time_ns": max(
                0, time.perf_counter_ns() - self._diagnostics_started_ns
            ),
            "producers": producers,
            "spans": list(self._diagnostics_spans),
            "span_limit": 256,
            "spans_truncated": len(self._diagnostics_spans) >= 256,
            "reuse": reuse,
            "store_reads": store_reads,
            "storage": "derived-not-persisted",
            "authority": "runtime-diagnostics-only",
            "execution_effect": "none",
        }

    def diagnostics(self) -> dict[str, object] | None:
        """Return the most recently completed opt-in decision-session diagnostics receipt."""
        if self._diagnostics_last is None:
            return None
        return json.loads(json.dumps(self._diagnostics_last))

    def stats(self) -> dict[str, int]:
        value = dict(self._stats)
        for key, count in self._store.read_counters().items():
            value[f"store_{key}"] = int(count)
        return value

    def symbols_for_path(self, path: str) -> list[dict[str, object]]:
        if self._depth <= 0:
            return self._store.symbols_for_path(path)
        generation = int(self._generation or self._store.generation())
        key = (generation, path)
        cached = self._symbols_cache.get(key)
        if cached is not None:
            self._stats["symbols_hit"] += 1
            return cached
        self._stats["symbols_miss"] += 1
        value = self._store.symbols_for_path(path)
        self._symbols_cache[key] = value
        return value

    def file_row(self, path: str) -> dict[str, object] | None:
        if self._depth <= 0:
            row = self._store.file_row(path)
            return None if row is None else dict(row)
        generation = int(self._generation or self._store.generation())
        key = (generation, path)
        if key in self._file_row_cache:
            self._stats["file_row_hit"] += 1
            return self._file_row_cache[key]
        self._stats["file_row_miss"] += 1
        row = self._store.file_row(path)
        value = None if row is None else dict(row)
        self._file_row_cache[key] = value
        return value

    def module_paths(self, module: str) -> list[str]:
        normalized = module.strip(".")
        if not normalized:
            return []
        if self._depth <= 0:
            return self._store.module_paths(normalized)
        generation = int(self._generation or self._store.generation())
        key = (generation, normalized)
        cached = self._module_paths_cache.get(key)
        if cached is not None:
            self._stats["module_paths_hit"] += 1
            return list(cached)
        self._stats["module_paths_miss"] += 1
        value = tuple(self._store.module_paths(normalized))
        self._module_paths_cache[key] = value
        return list(value)

    def preload_module_paths(self, modules: Iterable[str]) -> None:
        """Preload exact module identities that are already known by the caller.

        This collapses a set of independent indexed module lookups into one SQL
        read while retaining the exact ordered-prefix semantics of
        ``_session_module_paths``.  It is generation-local evidence only.
        """
        if self._depth <= 0:
            return
        generation = int(self._generation or self._store.generation())
        normalized = sorted(
            {str(module).strip(".") for module in modules if str(module).strip(".")}
        )
        missing = [
            module
            for module in normalized
            if (generation, module) not in self._module_paths_cache
        ]
        if not missing:
            return
        grouped = self._store.module_paths_many(missing)
        for module in missing:
            self._module_paths_cache[(generation, module)] = tuple(
                grouped.get(module, ())
            )
            self._stats["module_paths_miss"] += 1

    def exact_symbol_candidates(
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
        if self._depth <= 0:
            return self._store.exact_symbol_candidates(
                list(normalized), limit=requested
            )
        generation = int(self._generation or self._store.generation())
        key = (generation, normalized)
        cached = self._exact_symbols_cache.get(key)
        if cached is not None and cached[0] >= requested:
            self._stats["exact_symbols_hit"] += 1
            return [dict(row) for row in cached[1][:requested]]
        self._stats["exact_symbols_miss"] += 1
        value = self._store.exact_symbol_candidates(list(normalized), limit=requested)
        self._exact_symbols_cache[key] = (
            requested,
            tuple(dict(row) for row in value),
        )
        return value

    def refs_many(
        self,
        targets: Iterable[str],
        *,
        limit_per_target: int,
    ) -> dict[str, list[dict[str, object]]]:
        """Reuse per-target reverse-reference prefixes within one generation."""
        unique = list(dict.fromkeys(str(target) for target in targets if target))
        if not unique:
            return {}
        requested = min(max(1, int(limit_per_target)), MAX_REFERENCE_QUERY_ROWS)
        if self._depth <= 0:
            return self._store.refs_many(unique, limit_per_target=requested)
        generation = int(self._generation or self._store.generation())
        target_short = {target: target.rsplit(".", 1)[-1] for target in unique}
        missing_shorts = list(
            dict.fromkeys(
                short
                for short in target_short.values()
                if (generation, short) not in self._refs_cache
                or self._refs_cache[(generation, short)][0] < requested
            )
        )
        if missing_shorts:
            fetched = self._store.refs_many(missing_shorts, limit_per_target=requested)
            for short in missing_shorts:
                self._refs_cache[(generation, short)] = (
                    requested,
                    tuple(dict(row) for row in fetched.get(short, ())),
                )
                self._stats["refs_miss"] += 1
        result: dict[str, list[dict[str, object]]] = {}
        missing_set = set(missing_shorts)
        for target in unique:
            short = target_short[target]
            if short not in missing_set:
                self._stats["refs_hit"] += 1
            cached = self._refs_cache.get((generation, short))
            result[target] = (
                [] if cached is None else [dict(row) for row in cached[1][:requested]]
            )
        return result

    def edges_from_many(
        self,
        seeds: Iterable[tuple[str, str]],
        *,
        limit_per_seed: int,
    ) -> dict[tuple[str, str], list[dict[str, object]]]:
        """Reuse bounded path+source edge prefixes for already-known seeds."""
        unique = list(
            dict.fromkeys(
                (str(path), str(source)) for path, source in seeds if path and source
            )
        )
        if not unique:
            return {}
        requested = min(max(1, int(limit_per_seed)), 1024)
        if self._depth <= 0:
            return self._store.edges_from_many(unique, limit_per_seed=requested)
        generation = int(self._generation or self._store.generation())
        missing = [
            seed
            for seed in unique
            if (generation, seed[0], seed[1]) not in self._edges_from_cache
            or self._edges_from_cache[(generation, seed[0], seed[1])][0] < requested
        ]
        if missing:
            fetched = self._store.edges_from_many(missing, limit_per_seed=requested)
            for seed in missing:
                self._edges_from_cache[(generation, seed[0], seed[1])] = (
                    requested,
                    tuple(dict(row) for row in fetched.get(seed, ())),
                )
                self._stats["edges_from_miss"] += 1
        result: dict[tuple[str, str], list[dict[str, object]]] = {}
        missing_set = set(missing)
        for seed in unique:
            if seed not in missing_set:
                self._stats["edges_from_hit"] += 1
            cached = self._edges_from_cache.get((generation, seed[0], seed[1]))
            result[seed] = (
                [] if cached is None else [dict(row) for row in cached[1][:requested]]
            )
        return result

    def edges_for_paths_many(
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
        if self._depth <= 0:
            return self._store.edges_for_paths_many(unique, limit_per_path=requested)
        generation = int(self._generation or self._store.generation())
        missing = [
            path
            for path in unique
            if (generation, path) not in self._edges_for_path_cache
            or self._edges_for_path_cache[(generation, path)][0] < requested
        ]
        if missing:
            fetched = self._store.edges_for_paths_many(
                missing, limit_per_path=requested
            )
            for path in missing:
                self._edges_for_path_cache[(generation, path)] = (
                    requested,
                    tuple(dict(row) for row in fetched.get(path, ())),
                )
                self._stats["edges_for_path_miss"] += 1
        result: dict[str, list[dict[str, object]]] = {}
        missing_set = set(missing)
        for path in unique:
            if path not in missing_set:
                self._stats["edges_for_path_hit"] += 1
            cached = self._edges_for_path_cache.get((generation, path))
            result[path] = (
                [] if cached is None else [dict(row) for row in cached[1][:requested]]
            )
        return result

    def _cache_missing_file_rows(self, generation: int, missing: list[str]) -> None:
        if not missing:
            return
        rows = self._store.file_rows(missing)
        for path in missing:
            self._file_row_cache[(generation, path)] = rows.get(path)
            self._stats["file_row_miss"] += 1

    def file_rows(self, paths: Iterable[str]) -> dict[str, dict[str, object]]:
        unique = sorted({str(path) for path in paths if path})
        if not unique:
            return {}
        if self._depth <= 0:
            return self._store.file_rows(unique)
        generation = int(self._generation or self._store.generation())
        missing = [
            path for path in unique if (generation, path) not in self._file_row_cache
        ]
        self._cache_missing_file_rows(generation, missing)
        output: dict[str, dict[str, object]] = {}
        for path in unique:
            value = self._file_row_cache.get((generation, path))
            if value is not None:
                output[path] = value
            if path not in missing:
                self._stats["file_row_hit"] += 1
        return output

    def preload_symbols(self, paths: Sequence[str]) -> None:
        if self._depth <= 0:
            return
        generation = int(self._generation or self._store.generation())
        missing = sorted(
            {
                path
                for path in paths
                if path and (generation, path) not in self._symbols_cache
            }
        )
        if not missing:
            return
        grouped: dict[str, list[dict[str, object]]] = {path: [] for path in missing}
        # A global LIMIT across multiple paths can starve later paths and must
        # not be cached as if each per-path list were complete.  The caller has
        # already bounded the candidate path set, so preload complete symbol
        # evidence for exactly those paths in one query.
        for row in self._store.symbols_for_paths_complete(missing):
            path = str(row.get("path") or "")
            if path in grouped:
                value = dict(row)
                value.pop("row_type", None)
                grouped[path].append(value)
        for path, rows in grouped.items():
            self._symbols_cache[(generation, path)] = rows
            self._stats["symbols_miss"] += 1

    def symbols_for_paths(
        self, paths: Sequence[str], *, limit: int
    ) -> list[dict[str, object]]:
        """Return symbol rows for a path set while reusing per-path session evidence."""
        unique = sorted({str(path) for path in paths if path})
        if not unique:
            return []
        if self._depth <= 0:
            return self._store.symbols_for_paths(unique, limit=limit)
        self.preload_symbols(unique)
        rows: list[dict[str, object]] = []
        for path in unique:
            for row in self.symbols_for_path(path):
                rows.append({"row_type": "symbol", **row})
                if len(rows) >= limit:
                    return rows
        return rows

    def lexical_document_frequencies(
        self, terms: Sequence[str]
    ) -> tuple[int, dict[str, int]]:
        # The SQLite query canonicalizes to a lower-cased set; mirror that in the
        # process-local key so reordered/duplicated equivalent queries share evidence.
        normalized = tuple(sorted({str(term).lower() for term in terms if term}))
        if self._depth <= 0:
            return self._store.lexical_document_frequencies(list(normalized))
        generation = int(self._generation or self._store.generation())
        key = (generation, normalized)
        cached = self._df_cache.get(key)
        if cached is not None:
            self._stats["df_hit"] += 1
            return cached
        self._stats["df_miss"] += 1
        value = self._store.lexical_document_frequencies(list(normalized))
        self._df_cache[key] = value
        return value

    def lexical_file_candidates(
        self, terms: Sequence[str], *, limit: int, paths: Sequence[str] | None = None
    ) -> list[dict[str, object]]:
        # Cache by the store's true semantic identity, not caller token order.
        normalized = tuple(sorted({str(term).lower() for term in terms if term}))
        scope = None if paths is None else tuple(sorted(set(paths)))
        if self._depth <= 0:
            return self._store.lexical_file_candidates(
                list(normalized), limit=limit, paths=scope
            )
        generation = int(self._generation or self._store.generation())
        key = (generation, normalized, int(limit), scope)
        cached = self._candidates_cache.get(key)
        if cached is not None:
            self._stats["candidates_hit"] += 1
            return cached
        self._stats["candidates_miss"] += 1
        value = self._store.lexical_file_candidates(
            list(normalized), limit=limit, paths=scope
        )
        self._candidates_cache[key] = value
        return value

    def generation_status_with_watch(
        self,
        observation: RepositoryObservation | None,
        watch_record: WatchContinuityRecord | None,
    ) -> tuple[int, int | None, bool | None]:
        generation = self._store.generation()
        synced_raw = self._store.meta("identity_generation", "") or ""
        synced = None if not synced_raw else int(synced_raw)
        if observation is None:
            if self._depth > 0:
                observation = self._observation
            else:
                observation = self._observations.observe()
        if synced is not None and observation is not None:
            return generation, synced, observation.generation != synced
        stale = None if watch_record is None else watch_record.stale_for(generation)
        return generation, synced, stale

    def generation_status(
        self, observation: RepositoryObservation | None = None
    ) -> tuple[int, int | None, bool | None]:
        return self.generation_status_with_watch(
            observation, self._index.watch_continuity()
        )

    def freshness_fields(self) -> dict[str, object]:
        """Project existing CodeMap freshness authority into query responses."""
        generation, identity_generation, stale = self.generation_status()
        return {
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
        }
