"""Immutable JSON value semantics shared by bounded evidence owners.

This owns representation and equality only. Domain admission, identities and
payload budgets remain with the evidence producer that uses the value.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field


def _normalize(value: object, active: set[int]) -> object:
    if value is None or type(value) in (bool, int, float, str):
        return value
    if not isinstance(value, (Mapping, list, tuple)):
        raise ValueError("unsupported JSON value type")
    identity = id(value)
    if identity in active:
        raise ValueError("cyclic JSON value")
    active.add(identity)
    try:
        return _normalize_container(value, active)
    finally:
        active.remove(identity)


def _normalize_container(
    value: Mapping[object, object] | list[object] | tuple[object, ...], active: set[int]
) -> object:
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ValueError("JSON object keys must be strings")
        return {key: _normalize(item, active) for key, item in value.items()}
    return [_normalize(item, active) for item in value]


@dataclass(frozen=True, slots=True)
class CanonicalJsonValue:
    """Compare canonical bytes, never Python's coercing container equality.

    Every construction validates the input. Tuples normalize to arrays; booleans,
    integers and floats retain their JSON representations. No mutable input or
    decoded value is retained in the equality/hash domain.
    """

    value: InitVar[object]
    name: InitVar[str] = "value"
    _encoded: bytes = field(init=False, repr=False)

    def __post_init__(self, value: object, name: str) -> None:
        try:
            encoded = json.dumps(
                _normalize(value, set()),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError(
                f"{name} must contain finite JSON-compatible values"
            ) from exc
        object.__setattr__(self, "_encoded", encoded)

    @property
    def encoded(self) -> bytes:
        return self._encoded

    def to_value(self) -> object:
        """Return detached JSON-native data without transferring value ownership."""
        return json.loads(self._encoded)
