from __future__ import annotations

from collections.abc import Mapping, Sequence

OBSERVATION_STATES = frozenset(
    {"known-present", "known-absent", "unknown", "incomplete", "stale", "unsupported"}
)


def _observation_state(packet: Mapping[str, object]) -> str:
    state = packet.get("state", "unknown")
    if not isinstance(state, str) or state not in OBSERVATION_STATES:
        return "unknown"
    return state


def _stable_rows(rows: object) -> dict[str, Mapping[str, object]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        return {}
    indexed: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        identity = row.get("identity")
        if isinstance(identity, str) and identity:
            indexed[identity] = row
    return indexed


def observation_delta(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> dict[str, object]:
    """Compare two repository observations without turning difference into policy.

    Stable observation identities are authoritative for row matching. Repository
    change and observer-capability change remain separate axes so a better
    observer cannot be mistaken for changed repository bytes.
    """
    before_repository = before.get("repository")
    after_repository = after.get("repository")
    before_observer = before.get("observer")
    after_observer = after.get("observer")

    repository_changed = before_repository != after_repository
    observer_changed = before_observer != after_observer

    before_state = _observation_state(before)
    after_state = _observation_state(after)

    before_rows = _stable_rows(before.get("observations"))
    after_rows = _stable_rows(after.get("observations"))
    before_ids = set(before_rows)
    after_ids = set(after_rows)

    added = sorted(after_ids - before_ids)
    removed = sorted(before_ids - after_ids)
    retained = sorted(before_ids & after_ids)
    changed = [
        identity
        for identity in retained
        if before_rows[identity] != after_rows[identity]
    ]
    unchanged = [identity for identity in retained if identity not in changed]

    return {
        "schema": "hashmarks.observation-delta.v1",
        "repository": {
            "before": before_repository,
            "after": after_repository,
            "changed": repository_changed,
        },
        "observer": {
            "before": before_observer,
            "after": after_observer,
            "changed": observer_changed,
        },
        "completeness": {
            "before": before_state,
            "after": after_state,
            "changed": before_state != after_state,
        },
        "observations": {
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": unchanged,
        },
        "cause": (
            "repository-and-observer-changed"
            if repository_changed and observer_changed
            else "repository-changed"
            if repository_changed
            else "observer-changed"
            if observer_changed
            else "observation-only"
        ),
        "authority": "repository-intelligence-only",
        "execution_effect": "none",
    }
