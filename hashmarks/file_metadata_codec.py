"""Exact SQLite-safe codec for filesystem metadata overflow cache accelerators.

Ordinary signed-64 metadata stays in SQLite INTEGER columns. Rows containing any
wider value carry one canonical decimal ASCII BLOB with the five exact stat
integers; integer columns keep only bind-safe placeholders for those rows.
"""

from __future__ import annotations

_METADATA_FIELD_COUNT = 5
_METADATA_INTEGER_MAX_CHARS = 128
_METADATA_OVERFLOW_MAX_BYTES = (_METADATA_INTEGER_MAX_CHARS * _METADATA_FIELD_COUNT) + (
    _METADATA_FIELD_COUNT - 1
)
_SQLITE_INTEGER_MIN = -(2**63)
_SQLITE_INTEGER_MAX = 2**63 - 1


class MetadataCodecError(ValueError):
    """Raised when persisted filesystem metadata is not canonical."""


def _is_sqlite_integer(value: int) -> bool:
    return _SQLITE_INTEGER_MIN <= value <= _SQLITE_INTEGER_MAX


def _require_metadata_integers(values: tuple[int, int, int, int, int]) -> None:
    if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
        raise MetadataCodecError("filesystem metadata must contain integers")


def encode_metadata_fields(
    values: tuple[int, int, int, int, int],
) -> tuple[tuple[int, int, int, int, int], bytes | None]:
    _require_metadata_integers(values)
    if all(_is_sqlite_integer(value) for value in values):
        return values, None
    encoded = ",".join(str(value) for value in values).encode("ascii")
    if len(encoded) > _METADATA_OVERFLOW_MAX_BYTES:
        raise MetadataCodecError("filesystem metadata overflow payload is too large")
    stored = tuple(value if _is_sqlite_integer(value) else 0 for value in values)
    return stored, encoded  # type: ignore[return-value]


def _overflow_parts(value: object) -> list[str]:
    if (
        not isinstance(value, bytes)
        or not value
        or len(value) > _METADATA_OVERFLOW_MAX_BYTES
    ):
        raise MetadataCodecError(
            "persisted filesystem metadata overflow payload is invalid"
        )
    try:
        parts = value.decode("ascii").split(",")
    except UnicodeDecodeError as exc:
        raise MetadataCodecError(
            "persisted filesystem metadata overflow payload is not ASCII"
        ) from exc
    if len(parts) != _METADATA_FIELD_COUNT:
        raise MetadataCodecError(
            "persisted filesystem metadata overflow payload has invalid field count"
        )
    return parts


def _decode_integer(text: str) -> int:
    if not text or len(text) > _METADATA_INTEGER_MAX_CHARS:
        raise MetadataCodecError(
            "persisted filesystem metadata integer has invalid length"
        )
    try:
        number = int(text)
    except ValueError as exc:
        raise MetadataCodecError(
            "persisted filesystem metadata is not an integer"
        ) from exc
    if str(number) != text:
        raise MetadataCodecError("persisted filesystem metadata is not canonical")
    return number


def decode_overflow_metadata(value: object) -> tuple[int, int, int, int, int]:
    decoded = tuple(_decode_integer(text) for text in _overflow_parts(value))
    if all(_is_sqlite_integer(number) for number in decoded):
        raise MetadataCodecError(
            "overflow payload must contain an out-of-range integer"
        )
    return decoded  # type: ignore[return-value]
