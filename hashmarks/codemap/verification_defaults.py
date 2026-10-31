from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VerificationRelevanceOptions:
    """Default bounds for public verification relevance projections."""

    limit: int = 20
    candidate_limit: int = 8
    literal_file_reader_paths: int = 64
    literal_file_read_sites: int = 64


VERIFICATION_RELEVANCE_DEFAULTS = VerificationRelevanceOptions()
