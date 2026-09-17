from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


def dispatch_json_request(
    raw: bytes,
    dispatch: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Decode one local IPC request and serialize unexpected failures once."""

    try:
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        return dispatch(request)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
