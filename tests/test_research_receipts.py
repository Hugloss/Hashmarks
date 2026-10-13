from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from benchmarks.research_receipts import (
    durability_summary,
    evaluate_with_receipt,
    work_identity,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_research_receipt_reuses_exact_completed_work(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    identity = work_identity(
        protocol_identity="sha256:protocol",
        lane="group-0",
        work_id="task-a",
        work_payload={"task": "A"},
    )
    calls = 0

    def run() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"value": 1}

    first, reused_first = evaluate_with_receipt(
        receipt_path=path, identity=identity, evaluate=run
    )
    second, reused_second = evaluate_with_receipt(
        receipt_path=path, identity=identity, evaluate=run
    )
    assert first == second == {"value": 1}
    assert reused_first is False and reused_second is True
    assert calls == 1


def test_research_receipt_rejects_identity_drift(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    first = work_identity(protocol_identity="p1", work_id="a", work_payload={"x": 1})
    evaluate_with_receipt(
        receipt_path=path, identity=first, evaluate=lambda: {"ok": True}
    )
    changed = work_identity(protocol_identity="p2", work_id="a", work_payload={"x": 1})
    try:
        evaluate_with_receipt(
            receipt_path=path, identity=changed, evaluate=lambda: {"ok": False}
        )
    except ValueError as exc:
        assert "identity mismatch" in str(exc)
    else:
        raise AssertionError("identity drift must fail closed")


def test_durability_summary_marks_resumed_timing_noncomparable() -> None:
    summary = durability_summary(
        expected_work_ids=["a", "b"], completed_work_ids=["a"], reused=1, created=0
    )
    assert summary["complete"] is False
    assert summary["missing_items"] == ["b"]
    assert summary["timing_comparable"] is False


def test_research_receipt_rejects_changed_result_bytes(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    identity = work_identity(protocol_identity="p", work_id="a", work_payload={})
    evaluate_with_receipt(
        receipt_path=path, identity=identity, evaluate=lambda: {"authority": False}
    )
    payload = json.loads(path.read_text())
    payload["result"]["authority"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="result integrity"):
        evaluate_with_receipt(
            receipt_path=path, identity=identity, evaluate=lambda: {"authority": True}
        )
