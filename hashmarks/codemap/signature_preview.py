"""Bound Python signature text at the agent-facing projection boundary."""

from __future__ import annotations

from .model import PYTHON_SIGNATURE_PREVIEW_BYTES
from .python_ast import estimate_tokens


def signature_disclosure(
    path: str, signature: str | None, *, max_bytes: int = PYTHON_SIGNATURE_PREVIEW_BYTES
) -> dict[str, object]:
    if signature is None or not path.lower().endswith((".py", ".pyi")):
        return {"signature": signature}
    encoded = signature.encode("utf-8")
    bound = min(PYTHON_SIGNATURE_PREVIEW_BYTES, max_bytes)
    if len(encoded) <= bound:
        return {"signature": signature}
    return {
        "signature": None,
        "signature_preview": encoded[:bound].decode("utf-8", errors="ignore"),
        "signature_truncated": True,
    }


def outline_disclosure(
    path: str, outline: str, symbols: list[dict[str, object]]
) -> dict[str, object]:
    """Render detached index rows, keeping long Python prefixes in one place."""
    previews = 0
    for symbol in symbols:
        signature = symbol.get("signature")
        if isinstance(signature, str):
            disclosure = signature_disclosure(path, signature)
            if disclosure.get("signature_truncated"):
                symbol.update(disclosure)
                previews += 1
    if previews:
        lines = []
        for index, symbol in enumerate(symbols):
            qualname = str(symbol["qualname"])
            display = (
                f"{qualname} [signature preview at /symbols/{index}/signature_preview]"
                if symbol.get("signature_truncated")
                else symbol["signature"]
            )
            lines.append(
                f"{'  ' * qualname.count('.')}{display}  [{symbol['start_line']}-{symbol['end_line']}]"
            )
        outline = "\n".join(lines)
    return {
        "outline": outline,
        "outline_tokens": estimate_tokens(outline),
        "symbols": symbols,
        **({"outline_signature_previews": previews} if previews else {}),
    }
