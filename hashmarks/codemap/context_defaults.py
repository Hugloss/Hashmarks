from __future__ import annotations

from dataclasses import dataclass

from .model import ContextDisclosure


@dataclass(frozen=True, slots=True)
class RepositoryContextDefaults:
    """Default bounds for public repository context projections."""

    token_budget: int = 4000
    limit: int = 30
    disclosure: ContextDisclosure = ContextDisclosure.SOURCE


REPOSITORY_CONTEXT_DEFAULTS = RepositoryContextDefaults()
