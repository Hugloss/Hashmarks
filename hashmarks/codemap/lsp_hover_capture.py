"""Validate externally supplied LSP hover as bounded, non-relational producer text.

This module neither launches a language server nor interprets hover contents as
repository definitions, types, trusted instructions or relationship edges.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .semantic_relationship_source import validated_range

_MAX_HOVER_BYTES = 8_192
_MAX_BLOCK_BYTES = 4_096
_MAX_MARKED_STRINGS = 8


def _bounded_text(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"LSP hover {field} must be text")
    if len(value.encode("utf-8")) > _MAX_BLOCK_BYTES:
        raise ValueError(f"LSP hover {field} exceeds source text bound")
    return value


def _contents(value: object) -> object:
    if isinstance(value, str):
        return _bounded_text(value, field="contents")
    if isinstance(value, list):
        if len(value) > _MAX_MARKED_STRINGS:
            raise ValueError("LSP hover marked strings exceed entry bound")
        return [_marked_string(item) for item in value]
    if not isinstance(value, Mapping):
        raise ValueError("LSP hover contents must be MarkedString or MarkupContent")
    if set(value) == {"kind", "value"}:
        if value["kind"] not in ("plaintext", "markdown"):
            raise ValueError("LSP hover markup kind must be plaintext or markdown")
        return {
            "kind": value["kind"],
            "value": _bounded_text(value["value"], field="markup value"),
        }
    return _marked_string(value)


def _marked_string(value: object) -> object:
    if isinstance(value, str):
        return _bounded_text(value, field="marked string")
    if not isinstance(value, Mapping) or set(value) != {"language", "value"}:
        raise ValueError("LSP hover MarkedString requires language and value")
    language = value["language"]
    if not isinstance(language, str) or not 1 <= len(language) <= 64:
        raise ValueError("LSP hover language must be bounded nonempty text")
    return {
        "language": language,
        "value": _bounded_text(value["value"], field="marked value"),
    }


def normalize_hover_observation(capture: Mapping[str, Any]) -> dict[str, Any]:
    """Admit LSP 3.x Hover/MarkedString variants without making semantic claims."""
    partial = capture.get("partial_results", [])
    if not isinstance(partial, list) or partial:
        raise ValueError("LSP hover does not support partial result batches")
    response = capture["response"]
    if "error" in response:
        state = "producer-error"
        contents = None
        source_range = None
    elif response["result"] is None:
        state = "no-hover-returned"
        contents = None
        source_range = None
    else:
        result = response["result"]
        if (
            not isinstance(result, Mapping)
            or set(result) - {"contents", "range"}
            or "contents" not in result
        ):
            raise ValueError("LSP hover result requires contents and optional range")
        contents = _contents(result["contents"])
        source_range = (
            validated_range(result["range"]) if "range" in result else None
        )
        state = "hover-returned"
    # Limit aggregate transported values separately from the capture input limit.
    if len(json.dumps(contents, ensure_ascii=False).encode("utf-8")) > _MAX_HOVER_BYTES:
        raise ValueError("LSP hover aggregate contents exceed byte bound")
    return {
        "state": state,
        "contents": contents,
        "range": source_range,
        "authority": "caller-supplied-producer-claim",
        "semantic_correspondence": "not-established",
        "negative_evidence_admissible": False,
    }


def validate_hover_observation(value: object, *, response_error: object) -> None:
    """Reject invented hover authority even when the outer digest is recomputed."""
    if not isinstance(value, Mapping) or set(value) != {
        "state",
        "contents",
        "range",
        "authority",
        "semantic_correspondence",
        "negative_evidence_admissible",
    }:
        raise ValueError("invalid normalized hover evidence fields")
    if (
        value["authority"] != "caller-supplied-producer-claim"
        or value["semantic_correspondence"] != "not-established"
        or value["negative_evidence_admissible"] is not False
    ):
        raise ValueError("LSP hover cannot grant semantic or absence authority")
    if value["state"] not in (
        "hover-returned",
        "no-hover-returned",
        "producer-error",
    ):
        raise ValueError("invalid LSP hover observation state")
    if (value["state"] == "producer-error") != (response_error is not None):
        raise ValueError("LSP hover error state contradicts response provenance")
    if value["state"] != "hover-returned":
        if value["contents"] is not None or value["range"] is not None:
            raise ValueError("missing/error hover cannot carry result contents")
        return
    normalized = _contents(value["contents"])
    if normalized != value["contents"]:
        raise ValueError("hover contents not canonical")
    if value["range"] is not None:
        normalized_range = validated_range(value["range"])
        if normalized_range != value["range"]:
            raise ValueError("hover range not canonical")
    if (
        len(json.dumps(value["contents"], ensure_ascii=False).encode("utf-8"))
        > _MAX_HOVER_BYTES
    ):
        raise ValueError("LSP hover aggregate contents exceed byte bound")
