from __future__ import annotations

FRESHNESS_STATES = frozenset({"current", "stale", "unknown"})


def freshness_state(stale: bool | None) -> str:
    """Return the canonical serialized repository freshness state."""
    if stale is True:
        return "stale"
    if stale is False:
        return "current"
    return "unknown"
