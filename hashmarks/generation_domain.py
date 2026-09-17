from __future__ import annotations

MAX_PORTABLE_GENERATION = (1 << 53) - 1


def is_valid_generation(value: object) -> bool:
    """Return whether *value* is a lossless JSON-portable repository generation."""
    return type(value) is int and 0 <= value <= MAX_PORTABLE_GENERATION


def require_generation(value: object, *, field: str) -> int:
    if not is_valid_generation(value):
        raise ValueError(
            f"{field} must be an integer in [0, {MAX_PORTABLE_GENERATION}]"
        )
    return value
