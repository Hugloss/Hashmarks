"""Content facts derived from one already qualified source-member byte capture.

Signatures describe observed bytes, not file integrity, execution behavior, or
consumer policy. An LFS pointer describes an external object; it is not that
object and never triggers hydration.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy

from .repository_observation import evidence_identity

SOURCE_CONTENT_SCHEMA = "hashmarks.source-content.v1"
_LFS_PREFIX = b"version https://git-lfs.github.com/spec/"
_LFS_POINTER = re.compile(
    rb"version https://git-lfs\.github\.com/spec/v1\n"
    rb"oid sha256:([0-9a-f]{64})\nsize (0|[1-9][0-9]{0,19})\n"
)
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),
    (b"PK\x05\x06", "application/zip"),
    (b"\x1f\x8b", "application/gzip"),
)


def _media_type(raw: bytes) -> str | None:
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    return next(
        (media for signature, media in _SIGNATURES if raw.startswith(signature)), None
    )


def _content_kind(raw: bytes, media_type: str | None) -> str:
    if media_type is not None or b"\x00" in raw:
        return "binary"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return "binary"
    return "text"


def _observe_pointer(packet: dict[str, object], raw: bytes) -> None:
    match = _LFS_POINTER.fullmatch(raw)
    if match is None:
        packet.update(
            state="unavailable",
            kind="unknown",
            reason="lfs-pointer-syntax-unsupported",
            lfs={"state": "unqualified-pointer", "object_bytes_observed": False},
        )
        return
    packet.update(
        kind="lfs-pointer",
        lfs={
            "state": "pointer",
            "oid": "sha256:" + match[1].decode("ascii"),
            "size": int(match[2]),
            "object_bytes_observed": False,
        },
    )


def source_content_observation(
    member: Mapping[str, object], raw: bytes | None
) -> dict[str, object]:
    """Project bounded source bytes without reading or establishing source authority."""
    observed = raw is not None and member.get("state") == "known-present"
    packet: dict[str, object] = {
        "schema": SOURCE_CONTENT_SCHEMA,
        "source_member": deepcopy(dict(member)),
        "state": "observed" if observed else "unavailable",
        "kind": "unknown",
        "byte_count": len(raw) if observed and raw is not None else None,
        "media_type": None,
        "media_type_basis": "not-established",
        "integrity": "not-validated",
        "lfs": None,
        "reason": None
        if observed
        else member.get("reason", "source-bytes-not-observed"),
    }
    if observed and raw is not None:
        if raw.startswith(_LFS_PREFIX):
            _observe_pointer(packet, raw)
        else:
            media = _media_type(raw)
            packet.update(
                kind=_content_kind(raw, media),
                media_type=media,
                media_type_basis="signature-only"
                if media is not None
                else "not-established",
            )
    packet["evidence_identity"] = evidence_identity(SOURCE_CONTENT_SCHEMA, packet)
    return packet
