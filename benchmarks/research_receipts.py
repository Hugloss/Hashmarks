from __future__ import annotations

import hashlib
import json
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

SCHEMA = "hashmarks.research-work-receipt.v1"
SUMMARY_SCHEMA = "hashmarks.research-durability-summary.v1"


def canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    if os.name != "nt":
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def work_identity(
    *, protocol_identity: str, work_id: str, work_payload: object, lane: str = "default"
) -> dict[str, str]:
    return {
        "protocol_identity": str(protocol_identity),
        "lane": str(lane),
        "work_id": str(work_id),
        "work_sha256": canonical_sha256(work_payload),
    }


def evaluate_with_receipt(
    *,
    receipt_path: Path,
    identity: dict[str, str],
    evaluate: Callable[[], dict[str, Any]],
) -> tuple[dict[str, Any], bool]:
    """Return one exact research result, reusing only an identity-matched receipt.

    This preserves completed measurement/evidence work across outer-process death.
    It is not runtime retry/resume/process authority.
    """
    if receipt_path.exists():
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            payload.get("schema") != SCHEMA
            or payload.get("identity") != identity
            or payload.get("complete") is not True
        ):
            raise ValueError("research work receipt identity mismatch")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("research work receipt result is malformed")
        return result, True
    result = evaluate()
    atomic_write_json(
        receipt_path,
        {
            "schema": SCHEMA,
            "identity": identity,
            "complete": True,
            "result": result,
        },
    )
    return result, False


def durability_summary(
    *,
    expected_work_ids: Iterable[str],
    completed_work_ids: Iterable[str],
    reused: int,
    created: int,
) -> dict[str, Any]:
    expected = set(map(str, expected_work_ids))
    completed = set(map(str, completed_work_ids))
    missing = sorted(expected - completed)
    return {
        "schema": SUMMARY_SCHEMA,
        "expected_items": len(expected),
        "complete_items": len(expected.intersection(completed)),
        "missing_items": missing,
        "reused_items": int(reused),
        "new_items": int(created),
        "complete": not missing,
        "timing_comparable": int(reused) == 0,
        "note": "receipts preserve research evidence across outer-process termination; timing after reuse is not a clean-run performance claim",
    }
