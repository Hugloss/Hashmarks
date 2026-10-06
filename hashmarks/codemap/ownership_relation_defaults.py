from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OwnershipRelationOptions:
    """Default public bounds for ownership-relation graph requests."""

    max_depth: int = 2


OWNERSHIP_RELATION_DEFAULT_OPTIONS = OwnershipRelationOptions()
