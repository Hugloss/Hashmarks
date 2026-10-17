"""Failure-preserving composition of required backend QA observations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from hashmarks.evidence_presentation_conformance import validate_evidence_presentation


def combine_required(values: Iterable[bool | None]) -> bool | None:
    """Known failure dominates missing proof; an empty set is not proof."""
    observed = list(values)
    if any(value is not None and type(value) is not bool for value in observed):
        raise ValueError("backend gate observations must be bool or None")
    if any(value is False for value in observed):
        return False
    if not observed or any(value is None for value in observed):
        return None
    return True


def fact_state(classification: object) -> bool | None:
    """Keep missing source facts distinct from observed contradictions."""
    if classification == "PASS":
        return True
    if classification == "OTHER_FAILURE":
        return False
    if classification == "INCOMPLETE":
        return None
    raise ValueError(f"unsupported backend fact classification: {classification}")


def presentation_conformance(
    packet: Mapping[str, object], projection: Mapping[str, object]
) -> dict[str, object]:
    """Retain rejected projections as failed QA evidence instead of losing them."""
    try:
        return validate_evidence_presentation(packet, projection)
    except ValueError as error:
        return {"valid": False, "error": str(error)}
