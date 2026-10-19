"""Pure byte-range projections of the existing Source member observation."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping

from .repository_observation import evidence_identity

SOURCE_RANGE_RECEIPT_SCHEMA = "hashmarks.source-range-receipt.v1"


def validate_source_range(start_byte: int, end_byte: int, max_bytes: int) -> None:
    """Validate zero-based half-open coordinates before accessing source."""
    if any(type(bound) is not int for bound in (start_byte, end_byte, max_bytes)):
        raise ValueError("source range coordinates and max_bytes must be integers")
    if start_byte < 0 or end_byte < start_byte:
        raise ValueError("source range requires 0 <= start_byte <= end_byte")
    if not 1 <= max_bytes <= 8_388_608:
        raise ValueError("max_bytes must be between 1 and 8388608")


def source_range_evidence(
    raw: bytes,
    member: Mapping[str, object],
    start_byte: int,
    end_byte: int,
) -> dict[str, object]:
    """Bind exact bytes and coordinates to their full member revision."""
    if end_byte > len(raw):
        raise ValueError("source range extends beyond the observed member")
    selected = raw[start_byte:end_byte]
    content: dict[str, object] = {
        "encoding": "base64",
        "data": base64.b64encode(selected).decode("ascii"),
        "byte_count": len(selected),
        "digest": "sha256:" + hashlib.sha256(selected).hexdigest(),
    }
    return {
        "availability": "observed",
        "completeness": "complete",
        "truncation": "complete",
        "source_byte_count": len(raw),
        "content": content,
        "observation_identity": evidence_identity(
            SOURCE_RANGE_RECEIPT_SCHEMA,
            {
                "path": member["path"],
                "member_revision": member["member_revision"],
                "start_byte": start_byte,
                "end_byte": end_byte,
                "source_byte_count": len(raw),
                "content_digest": content["digest"],
            },
        ),
    }
