from __future__ import annotations

MAX_PORTABLE_INTEGER = (1 << 53) - 1


def is_portable_nonnegative_integer(value: object) -> bool:
    """Return whether value is losslessly portable through JSON number consumers."""
    return type(value) is int and 0 <= value <= MAX_PORTABLE_INTEGER


def require_portable_nonnegative_integer(value: object, *, field: str) -> int:
    if not is_portable_nonnegative_integer(value):
        raise ValueError(f"{field} must be an integer in [0, {MAX_PORTABLE_INTEGER}]")
    return value


def require_optional_portable_nonnegative_integer(value: object, *, field: str) -> int | None:
    if value is None:
        return None
    return require_portable_nonnegative_integer(value, field=field)


def require_nonblank_string(value: object, *, field: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field} must be a nonblank string")
    return value
