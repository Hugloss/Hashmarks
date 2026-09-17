from __future__ import annotations

from collections.abc import Mapping


def require_mapping_for_validation(
    value: object,
    *,
    reason: str,
) -> tuple[Mapping[str, object], list[str]]:
    """Return an object-shaped validation input or a fail-closed empty view."""
    if isinstance(value, Mapping):
        return value, []
    return {}, [reason]
