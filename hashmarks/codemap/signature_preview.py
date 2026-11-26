"""Bound Python signature text at the agent-facing projection boundary."""

from __future__ import annotations

from collections import Counter

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


def _signature_text(record: dict[str, object]) -> str:
    value = record.get("signature_preview", record.get("signature"))
    return value if isinstance(value, str) else ""


def _fit_signature(record: dict[str, object], budget_bytes: int) -> int:
    text = _signature_text(record)
    size = len(text.encode("utf-8"))
    if size > budget_bytes:
        record.update(
            signature_disclosure(str(record["path"]), text, max_bytes=budget_bytes)
        )
        size = len(_signature_text(record).encode("utf-8"))
    return size


def share_source_signature_budget(
    selected: dict[str, object], matches: list[dict[str, object]], budget_bytes: int
) -> None:
    """Count both appearances of the selected Python signature in the source projection."""
    if not matches or not str(selected["path"]).lower().endswith((".py", ".pyi")):
        return
    if (
        sum(len(_signature_text(row).encode("utf-8")) for row in [selected, *matches])
        <= budget_bytes
    ):
        return
    # Leave at least one share for the explicitly selected occurrence. Short
    # signatures and multibyte prefix boundaries free additional bytes for it.
    share = budget_bytes // (len(matches) + 1)
    choices_used = sum(_fit_signature(row, share) for row in matches)
    _fit_signature(selected, budget_bytes - choices_used)


def _distinct_whole_binding_lines(
    outline: str, symbols: list[dict[str, object]]
) -> str:
    """Display one whole-line assignment once even when it declares several names."""
    bindings = Counter(
        (row["signature"], row["start_line"])
        for row in symbols
        if row["kind"] == "binding"
        and isinstance(row["signature"], str)
        and row["start_line"] == row["end_line"]
        and row.get("start_byte_column") is None
        and row.get("end_byte_column") is None
    )
    shared = {
        f"{signature}  [{line}-{line}]"
        for (signature, line), count in bindings.items()
        if count > 1
    }
    if not shared:
        return outline
    rendered = []
    displayed: set[str] = set()
    for line in outline.split("\n"):
        if line in displayed:
            continue
        rendered.append(line)
        if line in shared:
            displayed.add(line)
    return "\n".join(rendered)


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
    if path.lower().endswith((".py", ".pyi")):
        outline = _distinct_whole_binding_lines(outline, symbols)
    return {
        "outline": outline,
        "outline_tokens": estimate_tokens(outline),
        "symbols": symbols,
        **({"outline_signature_previews": previews} if previews else {}),
    }
