from __future__ import annotations


class UserFacingError(RuntimeError):
    """Expected operation error safe to present at a public transport boundary."""


class RepositoryCliError(UserFacingError):
    """Repository-intelligence CLI request failed for a caller-visible reason."""


class OptionalFeatureError(UserFacingError):
    """An explicitly requested optional feature is unavailable in this environment."""
