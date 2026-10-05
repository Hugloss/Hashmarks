from __future__ import annotations

from pathlib import Path

import pytest

import hashmarks.codemap.find_engine as find_engine_module
import hashmarks.evidence_context as evidence_context_module
from hashmarks.codemap import CodeMap
from hashmarks.freshness import FRESHNESS_STATES, freshness_state


def test_freshness_contract_single_owns_vocabulary_and_serialization() -> None:
    assert FRESHNESS_STATES == frozenset({"current", "stale", "unknown"})
    assert [freshness_state(value) for value in (True, False, None)] == [
        "stale",
        "current",
        "unknown",
    ]
    assert evidence_context_module.FRESHNESS_STATES is FRESHNESS_STATES
    assert find_engine_module.freshness_state is freshness_state


def test_find_claim_admission_consumes_canonical_freshness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "owner.py").write_text(
        "def widget():\n    return 1\n",
        encoding="utf-8",
    )

    with CodeMap(repo) as codemap:
        codemap.sync()
        monkeypatch.setattr(
            find_engine_module,
            "freshness_state",
            lambda _stale: "stale",
        )
        result = codemap.find_packet("src/missing.py")

    assert result["freshness"] == "stale"
    assert result["negative_evidence"] == "not-admissible"
    assert "repository-freshness-stale" in result["admissibility_reasons"]
