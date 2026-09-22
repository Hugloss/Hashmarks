from __future__ import annotations

import json
from pathlib import Path

from scripts.repository_evaluation.merge_runs import merge_runs

ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict[str, object]:
    return json.loads(
        (
            ROOT / "scripts/repository_evaluation/retained_measurement_authority.json"
        ).read_text()
    )


def test_retained_good_work_inventory_is_complete() -> None:
    doc = _manifest()
    assert len(doc["required_capabilities"]) == 13
    assert len(doc["negative_guardrails"]) == 8
    assert len(set(doc["required_capabilities"])) == 13
    assert len(set(doc["negative_guardrails"])) == 8


def test_measurement_authority_remains_outside_product_runtime() -> None:
    for path in (ROOT / "hashmarks").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "repository-evaluation-profile" not in text
        assert "performance-measurement-only" not in text


def test_like_fallback_keeps_recall_and_now_has_explicit_stable_order() -> None:
    text = (ROOT / "hashmarks/codemap/store_queries.py").read_text(encoding="utf-8")
    broad = text[
        text.index("def search_candidates") : text.index("def exact_symbol_candidates")
    ]
    assert (
        "WHERE lower(s.name) LIKE ? OR lower(s.qualname) LIKE ? OR lower(s.signature) LIKE ? OR lower(s.path) LIKE ?"
        in broad
    )
    assert "ORDER BY s.path,s.start_line,s.qualname" in broad
    assert "WHERE lower(path) LIKE ? ORDER BY path LIMIT ?" in broad
    assert " UNION " not in broad.upper()
    assert " EXISTS " not in broad.upper()
    assert 'q = f"%{query.lower()}%"' in broad


def test_controller_cutoff_has_no_product_failure_authority() -> None:
    evaluation = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (ROOT / "scripts/repository_evaluation").glob("*.py")
    )
    assert "performance-measurement-only" in evaluation
    assert "CONTROLLER_TIMEOUT" not in evaluation
    assert "TIMEOUT_FAIL" not in evaluation


def test_resume_receipts_suppress_timing_authority() -> None:
    first = {
        "suite": "authority",
        "protocol_identity": "sha256:protocol",
        "repository_identity": "sha256:repository",
        "producer_implementation_identity": "sha256:producer",
        "producer_artifact_identity": None,
        "cases_sha256": "sha256:cases",
        "shard_count": 2,
        "shard_index": 0,
        "timing_comparable": True,
        "cases": [],
    }
    resumed = {**first, "shard_index": 1, "timing_comparable": False}

    assert merge_runs([first, resumed])["timing_comparable"] is False
