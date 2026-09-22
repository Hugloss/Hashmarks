from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SURFACES = {
    "orient",
    "outline",
    "affected",
    "tests",
    "task-evidence",
    "findings",
    "mcp",
    "compact",
}


def surface_convergence(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    seen: dict[str, str] = {}
    missing_identity: list[str] = []
    for row in observations:
        surface = str(row.get("surface") or "")
        if surface not in SURFACES:
            raise ValueError(f"unsupported convergence surface: {surface}")
        identity = str(row.get("authority_proof_identity") or "")
        if not identity:
            missing_identity.append(surface)
        else:
            seen[surface] = identity
    identities = sorted(set(seen.values()))
    return {
        "observed_surfaces": sorted(seen),
        "missing_identity": sorted(missing_identity),
        "authority_proof_identities": identities,
        "converged": bool(seen) and not missing_identity and len(identities) == 1,
    }


def require_surface_convergence(
    observations: Sequence[Mapping[str, Any]],
    required: Sequence[str],
) -> dict[str, Any]:
    result = surface_convergence(observations)
    observed = set(result["observed_surfaces"])
    unknown = sorted(set(required) - SURFACES)
    if unknown:
        raise ValueError(f"unsupported required convergence surfaces: {unknown}")
    missing = sorted(set(required) - observed)
    return {
        **result,
        "required_surfaces": sorted(set(required)),
        "missing_surfaces": missing,
        "complete": result["converged"] and not missing,
    }
