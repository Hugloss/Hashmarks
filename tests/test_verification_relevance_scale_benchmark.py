from __future__ import annotations

from scripts.metrics_verification_relevance_scale import collect


def test_verification_relevance_scale_qualification_preserves_local_authority() -> None:
    result = collect(sizes=(10, 50, 100))
    assert result["baseline_correct"] == 0
    assert result["selected_correct"] == 3
    assert result["unsafe_regressions"] == 0
    assert result["selection_changes"] == 3
    assert result["max_candidate_count"] == 101
    assert result["secret_knowledge_used_by_selector"] is False
