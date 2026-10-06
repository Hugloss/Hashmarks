from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VerificationRelevanceOptions:
    """Default bounds for public verification evidence projections."""

    limit: int = 20
    candidate_limit: int = 8


VERIFICATION_RELEVANCE_DEFAULT_OPTIONS = VerificationRelevanceOptions()
