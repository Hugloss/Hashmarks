"""Pure producer-packet to rendered-projection conformance check."""

from __future__ import annotations

import json
from collections.abc import Mapping

from hashmarks.evidence_presentation import present_repository_evidence


def validate_evidence_presentation(
    packet: Mapping[str, object], projection: Mapping[str, object]
) -> dict[str, object]:
    """Prove that a claimed presentation is exactly the producer-owned projection.

    This is a pure conformance check: it uses no CodeMap, source reads, inference,
    or alternate presentation rules. Different display row caps remain legitimate.
    A host-modified/truncated response does not qualify as this native projection.
    """
    if not isinstance(projection, Mapping):
        raise ValueError("evidence presentation must be a mapping")
    mode = projection.get("format")
    if mode not in ("structured", "compact", "text"):
        raise ValueError(
            "evidence presentation format must be structured, compact or text"
        )
    expected = present_repository_evidence(packet, format=str(mode))

    def canonical(value: object) -> bytes:
        try:
            return json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("evidence presentation contains nonportable data") from exc

    if canonical(dict(projection)) != canonical(expected):
        raise ValueError("evidence presentation differs from native source projection")
    return {
        "valid": True,
        "format": mode,
        "source_evidence_identity": expected["source_evidence_identity"],
        "coverage": expected["coverage"],
        "authority": "conformance-only",
    }
