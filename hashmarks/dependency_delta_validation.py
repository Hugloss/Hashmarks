"""Pure correspondence replay for retained dependency endpoint deltas."""

from __future__ import annotations

from collections.abc import Mapping

from hashmarks.codemap.dependency_resolution_delta import DependencyResolutionDeltaMixin
from hashmarks.codemap.dependency_resolution_evidence import _canonical


def validate_dependency_delta(
    value: object, before: Mapping[str, object], after: Mapping[str, object]
) -> dict[str, object]:
    """Replay exact native delta facts without reobserving or authenticating source."""
    reasons: list[str] = []
    try:
        expected = DependencyResolutionDeltaMixin.delta(before, after)
        if not isinstance(value, dict) or _canonical(value) != _canonical(expected):
            reasons.append(
                "dependency delta differs from qualified endpoint observations"
            )
    except (TypeError, ValueError, RecursionError) as exc:
        reasons.append(str(exc))
    return {
        "valid": not reasons,
        "reasons": reasons,
        "authority": "content-integrity-and-correspondence-only",
        "repository_binding": "not-reobserved",
        "producer_authenticity": "not-checked",
        "execution_authority": "external",
    }
