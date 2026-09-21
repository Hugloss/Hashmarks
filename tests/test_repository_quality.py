from __future__ import annotations

import pytest

from scripts.agent_evaluation.repository_quality import (
    case_identity,
    evaluate_case,
    summarize,
)


def _case(**overrides):
    value = {
        "schema": "hashmarks.repository-quality-case.v1",
        "case_id": "case-1",
        "repository_identity": "sha256:repo",
        "source_identity": "sha256:source",
        "ground_truth_basis": "reviewed repository evidence",
        "semantic_truth": "unique-owner",
        "admitted_evidence_truth": "sufficient",
        "expected_owner": "src/widget.py::widget",
    }
    value.update(overrides)
    return value


def test_sufficient_unique_owner_resolves_without_authority_violation() -> None:
    row = evaluate_case(
        _case(), {"state": "resolved", "owner": "src/widget.py::widget"}
    )
    report = summarize([row])
    assert report["qualification"] == "qualified"
    assert report["hard_zero"]["false_owner"] == 0
    assert report["selective_quality"]["selective_owner_risk"] == 0
    assert report["selective_quality"]["resolvable_owner_coverage"] == 1


def test_wrong_resolved_owner_is_non_compensatory_failure() -> None:
    row = evaluate_case(_case(), {"state": "resolved", "owner": "src/other.py::widget"})
    report = summarize([row])
    assert report["qualification"] == "not-qualified"
    assert report["hard_zero"]["false_owner"] == 1
    assert report["selective_quality"]["selective_owner_risk"] == 1


def test_insufficient_evidence_abstention_is_not_counted_as_missed_resolution() -> None:
    row = evaluate_case(
        _case(admitted_evidence_truth="insufficient"),
        {"state": "unresolved", "owner": None},
    )
    report = summarize([row])
    assert report["qualification"] == "qualified"
    assert report["hard_zero"]["sufficient_unique_reported_unresolved"] == 0
    assert report["selective_quality"]["sufficient_unique_cases"] == 0
    assert report["selective_quality"]["resolvable_owner_coverage"] is None


def test_true_ambiguity_cannot_be_collapsed_to_unique_owner() -> None:
    row = evaluate_case(
        _case(
            semantic_truth="true-ambiguity",
            admitted_evidence_truth="sufficient",
            expected_owner=None,
        ),
        {"state": "resolved", "owner": "src/widget.py::widget"},
    )
    report = summarize([row])
    assert report["qualification"] == "not-qualified"
    assert report["hard_zero"]["true_ambiguity_collapsed"] == 1
    assert report["hard_zero"]["false_unique"] == 1


def test_non_edit_task_cannot_gain_edit_authority() -> None:
    row = evaluate_case(
        _case(
            semantic_truth="non-edit",
            admitted_evidence_truth="sufficient",
            expected_owner=None,
        ),
        {"state": "resolved", "owner": "src/widget.py::widget"},
    )
    assert summarize([row])["hard_zero"]["non_edit_promoted_to_edit"] == 1


def test_projection_authority_leak_is_a_hard_veto() -> None:
    row = evaluate_case(
        _case(),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "candidate_promoted_during_projection": True,
        },
    )
    report = summarize([row])
    assert report["qualification"] == "not-qualified"
    assert report["hard_zero"]["candidate_promoted_during_projection"] == 1


def test_case_schema_requires_owner_only_for_unique_truth() -> None:
    with pytest.raises(ValueError, match="expected_owner"):
        evaluate_case(
            _case(semantic_truth="true-ambiguity"),
            {"state": "ambiguous", "owner": None},
        )


def test_missing_metrics_are_unknown_not_zero() -> None:
    report = summarize(
        [
            evaluate_case(
                _case(), {"state": "resolved", "owner": "src/widget.py::widget"}
            )
        ]
    )
    assert report["missing_metric_policy"] == "unknown-not-zero"


def test_case_identity_binds_ground_truth_and_repository_authority() -> None:
    original = _case()
    changed_truth = _case(expected_owner="src/other.py::widget")
    changed_source = _case(source_identity="sha256:other-source")
    assert case_identity(original) != case_identity(changed_truth)
    assert case_identity(original) != case_identity(changed_source)


def test_corpus_identity_is_order_independent_but_membership_sensitive() -> None:
    first = evaluate_case(
        _case(case_id="first"),
        {"state": "resolved", "owner": "src/widget.py::widget"},
    )
    second = evaluate_case(
        _case(case_id="second"),
        {"state": "resolved", "owner": "src/widget.py::widget"},
    )
    forward = summarize([first, second])["corpus"]["identity"]
    reverse = summarize([second, first])["corpus"]["identity"]
    singleton = summarize([first])["corpus"]["identity"]
    assert forward == reverse
    assert forward != singleton
