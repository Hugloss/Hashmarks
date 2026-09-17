from __future__ import annotations

import threading
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class IdentityCycleError(RuntimeError):
    """Raised when an identity graph contains a dependency cycle."""


@dataclass
class _Node(Generic[K, V]):
    compute: Callable[[dict[K, V]], V]
    dependencies: tuple[K, ...] = ()
    value: V | None = None
    initialized: bool = False
    version: int = 0
    dirty: bool = True
    dep_versions: dict[K, int] = field(default_factory=dict)


class IdentityGraph(Generic[K, V]):
    """Small thread-safe DICE-like lazy incremental graph.

    A dirty leaf is recomputed on demand. Its version advances only when its
    canonical value actually changes, giving an equality cutoff for parents.
    """

    def __init__(self):
        self._nodes: dict[K, _Node[K, V]] = {}
        self._lock = threading.RLock()

    def add(
        self,
        key: K,
        compute: Callable[[dict[K, V]], V],
        *,
        dependencies: tuple[K, ...] = (),
    ) -> None:
        with self._lock:
            if key in self._nodes:
                raise KeyError(f"node already exists: {key!r}")
            self._nodes[key] = _Node(compute=compute, dependencies=dependencies)

    def invalidate(self, key: K) -> None:
        with self._lock:
            self._nodes[key].dirty = True

    def invalidate_many(self, keys: Iterable[K]) -> None:
        with self._lock:
            for key in keys:
                self._nodes[key].dirty = True

    def version(self, key: K) -> int:
        with self._lock:
            self._get_locked(key, ())
            return self._nodes[key].version

    def get(self, key: K) -> V:
        with self._lock:
            return self._get_locked(key, ())

    def _get_locked(self, key: K, stack: tuple[K, ...]) -> V:
        if key in stack:
            start = stack.index(key)
            cycle = stack[start:] + (key,)
            rendered = " -> ".join(repr(item) for item in cycle)
            raise IdentityCycleError(f"identity dependency cycle: {rendered}")

        try:
            node = self._nodes[key]
        except KeyError as exc:
            raise KeyError(f"unknown identity node: {key!r}") from exc

        next_stack = stack + (key,)
        dep_values: dict[K, V] = {}
        dep_changed = False

        for dep_key in node.dependencies:
            dep_values[dep_key] = self._get_locked(dep_key, next_stack)
            dep_version = self._nodes[dep_key].version
            if node.dep_versions.get(dep_key) != dep_version:
                dep_changed = True

        if node.initialized and not node.dirty and not dep_changed:
            return node.value  # type: ignore[return-value]

        old_value = node.value
        new_value = node.compute(dep_values)
        node.dep_versions = {
            dep_key: self._nodes[dep_key].version for dep_key in node.dependencies
        }
        node.dirty = False

        if not node.initialized or new_value != old_value:
            node.value = new_value
            node.version += 1
        else:
            node.value = old_value

        node.initialized = True
        return node.value  # type: ignore[return-value]
