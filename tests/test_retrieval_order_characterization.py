from __future__ import annotations

from scripts.repository_evaluation.retrieval_order_characterization import (
    SCHEMA,
    characterize_retrieval_order,
)


def test_same_content_aba_satisfies_stable_retrieval_contract() -> None:
    result = characterize_retrieval_order(files=72, broad_limit=24, find_limit=10)

    assert result["schema"] == SCHEMA
    assert result["authority"] == "retrieval-contract-verification"
    assert result["cold_run_stable"] is True
    assert result["same_content_after_aba"] is True
    assert result["broad_subset_changed_after_aba"] is False
    assert result["find_result_changed_after_aba"] is False
    assert result["initial_content_identity"] == result["restored_content_identity"]
    assert result["before_broad"] == result["after_broad"]
    assert result["before_find"] == result["after_find"]
    assert result["decision"] == "STABLE_CONTRACT_SATISFIED"
    assert result["product_contract_enforced"] is True


def test_characterization_rejects_uncapped_fixture() -> None:
    try:
        characterize_retrieval_order(files=10, broad_limit=10, find_limit=5)
    except ValueError as exc:
        assert "files must exceed broad_limit" in str(exc)
    else:
        raise AssertionError("expected invalid characterization protocol")
