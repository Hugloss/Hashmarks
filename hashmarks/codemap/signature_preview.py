"""Bound Python signature text at the agent-facing projection boundary."""

from __future__ import annotations

from collections import defaultdict

from .model import PYTHON_SIGNATURE_PREVIEW_BYTES, SignatureDisclosure
from .python_ast import estimate_tokens


def signature_disclosure(
    path: str, signature: str | None, *, max_bytes: int = PYTHON_SIGNATURE_PREVIEW_BYTES
) -> SignatureDisclosure:
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


def _distinct_binding_lines(outline: str, symbols: list[dict[str, object]]) -> str:
    """Collapse matching binding entries only when one source range accounts for them all."""
    bindings: dict[tuple[str, object], list[tuple[object, object]]] = defaultdict(list)
    for row in symbols:
        signature = row["signature"]
        line = row["start_line"]
        if (
            row["kind"] == "binding"
            and isinstance(signature, str)
            and line == row["end_line"]
        ):
            bindings[signature, line].append(
                (row.get("start_byte_column"), row.get("end_byte_column"))
            )
    # Identical syntax can appear in distinct statements on one physical
    # line. A display line alone does not establish that their bindings share
    # a statement; retain every occurrence when the recorded ranges differ.
    shared = {
        f"{signature}  [{line}-{line}]"
        for (signature, line), ranges in bindings.items()
        if len(ranges) > 1
        and len(set(ranges)) == 1
        and (ranges[0] == (None, None) or None not in ranges[0])
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


def _outline_line(index: int, symbol: dict[str, object], inline_previews: bool) -> str:
    qualname = str(symbol["qualname"])
    if not symbol.get("signature_truncated"):
        display = symbol["signature"]
    elif inline_previews:
        display = f"{qualname} [signature preview] {symbol['signature_preview']}…"
    else:
        display = (
            f"{qualname} [signature preview at /symbols/{index}/signature_preview]"
        )
    return f"{'  ' * qualname.count('.')}{display}  [{symbol['start_line']}-{symbol['end_line']}]"


def outline_disclosure(
    path: str,
    outline: str,
    symbols: list[dict[str, object]],
    *,
    inline_previews: bool = False,
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
        outline = "\n".join(
            _outline_line(index, symbol, inline_previews)
            for index, symbol in enumerate(symbols)
        )
    if path.lower().endswith((".py", ".pyi")):
        outline = _distinct_binding_lines(outline, symbols)
    return {
        "outline": outline,
        "outline_tokens": estimate_tokens(outline),
        "symbols": symbols,
        **({"outline_signature_previews": previews} if previews else {}),
    }
