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
        "ground_truth_status": "valid",
        "corpus_class": "qualification",
        "lifecycle": "active",
        "task_family": "owner-selection",
        "risk_class": "change-support",
        "label_basis": "independently reviewed repository evidence",
        "benchmark_registry": "hashmarks.repository-quality-registry.v1",
        "ground_truth_schema": "hashmarks.repository-quality-ground-truth.v1",
        "metric_policy": "hashmarks.lexicographic-quality.v1",
        "qualification_policy": "hashmarks.repository-quality-qualification.v1",
        "evaluation_profile": "change-support.v1",
        "proof_mode": "unit",
        "semantic_truth": "unique-owner",
        "admitted_evidence_truth": "sufficient",
        "expected_owner": "src/widget.py::widget",
    }
    value.update(overrides)
    return value


def _qualification_rows():
    cases = [
        _case(case_id="unique"),
        _case(
            case_id="ambiguous", semantic_truth="true-ambiguity", expected_owner=None
        ),
        _case(case_id="non-edit", semantic_truth="non-edit", expected_owner=None),
        _case(
            case_id="test-edit",
            semantic_truth="explicit-test-edit",
            expected_owner=None,
        ),
    ]
    observed = [
        {"state": "resolved", "owner": "src/widget.py::widget"},
        {"state": "ambiguous", "owner": None},
        {"state": "no-edit-authority", "owner": None},
        {"state": "explicit-test-target", "owner": None},
    ]
    return [evaluate_case(case, result) for case, result in zip(cases, observed)]


def test_sufficient_unique_owner_resolves_without_authority_violation() -> None:
    row = evaluate_case(
        _case(), {"state": "resolved", "owner": "src/widget.py::widget"}
    )
    report = summarize([row, *_qualification_rows()[1:]])
    assert report["qualification"] == "qualified"
    assert report["hard_zero"]["false_owner"] == 0
    assert report["selective_quality"]["selective_owner_risk"] == 0
    assert report["selective_quality"]["resolvable_owner_coverage"] == 1


def test_wrong_resolved_owner_is_non_compensatory_failure() -> None:
    row = evaluate_case(_case(), {"state": "resolved", "owner": "src/other.py::widget"})
    report = summarize([row, *_qualification_rows()[1:]])
    assert report["qualification"] == "not-qualified"
    assert report["hard_zero"]["false_owner"] == 1
    assert report["selective_quality"]["selective_owner_risk"] == 1


def test_insufficient_evidence_abstention_is_not_counted_as_missed_resolution() -> None:
    row = evaluate_case(
        _case(admitted_evidence_truth="insufficient"),
        {"state": "unresolved", "owner": None},
    )
    report = summarize([row])
    assert report["qualification"] == "benchmark-not-ready"
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
    report = summarize([*_qualification_rows()[:1], row, *_qualification_rows()[2:]])
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
    report = summarize([row, *_qualification_rows()[1:]])
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


def test_empty_corpus_cannot_qualify() -> None:
    report = summarize([])
    assert report["qualification"] == "benchmark-not-ready"
    assert report["benchmark_health"]["score_bearing_cases"] == 0


def test_shadow_only_corpus_cannot_qualify() -> None:
    row = evaluate_case(
        _case(corpus_class="shadow"),
        {"state": "resolved", "owner": "src/widget.py::widget"},
    )
    report = summarize([row])
    assert report["qualification"] == "benchmark-not-ready"
    assert report["benchmark_health"]["score_bearing_cases"] == 0


def test_uncertain_ground_truth_requires_adjudication_before_qualification() -> None:
    valid = evaluate_case(
        _case(case_id="valid"),
        {"state": "resolved", "owner": "src/widget.py::widget"},
    )
    uncertain = evaluate_case(
        _case(
            case_id="uncertain",
            ground_truth_status="insufficient-ground-truth",
            corpus_class="shadow",
        ),
        {"state": "unresolved", "owner": None},
    )
    report = summarize([valid, *_qualification_rows()[1:], uncertain])
    assert report["qualification"] == "needs-adjudication"
    assert report["benchmark_health"]["needs_adjudication"] == 1


def test_invalid_case_blocks_benchmark_readiness() -> None:
    valid = evaluate_case(
        _case(case_id="valid"),
        {"state": "resolved", "owner": "src/widget.py::widget"},
    )
    invalid = evaluate_case(
        _case(case_id="invalid", ground_truth_status="invalid-case"),
        {"state": "unresolved", "owner": None},
    )
    report = summarize([valid, invalid])
    assert report["qualification"] == "benchmark-not-ready"
    assert report["benchmark_health"]["invalid_cases"] == 1


def test_historical_and_canary_cases_are_evidence_but_not_score_bearing() -> None:
    active = evaluate_case(
        _case(case_id="active"),
        {"state": "resolved", "owner": "src/widget.py::widget"},
    )
    historical = evaluate_case(
        _case(case_id="historical", lifecycle="historical"),
        {"state": "resolved", "owner": "src/other.py::widget"},
    )
    canary = evaluate_case(
        _case(case_id="canary", corpus_class="canary"),
        {"state": "resolved", "owner": "src/other.py::widget"},
    )
    report = summarize([active, *_qualification_rows()[1:], historical, canary])
    assert report["qualification"] == "qualified"
    assert report["benchmark_health"]["total_cases"] == 6
    assert report["benchmark_health"]["score_bearing_cases"] == 4
    assert report["hard_zero"]["false_owner"] == 0


def test_missing_critical_semantic_slice_prevents_qualification() -> None:
    report = summarize(
        [
            evaluate_case(
                _case(),
                {"state": "resolved", "owner": "src/widget.py::widget"},
            )
        ]
    )
    assert report["qualification"] == "benchmark-not-ready"
    assert report["benchmark_health"]["critical_slices"]["missing"] == {
        "true-ambiguity": 1,
        "non-edit": 1,
        "explicit-test-edit": 1,
    }


def test_complete_critical_semantic_slices_allow_qualification() -> None:
    report = summarize(_qualification_rows())
    assert report["qualification"] == "qualified"
    assert report["benchmark_health"]["critical_slices"]["adequate"] is True


def test_state_confusion_is_canonical_and_abstention_metrics_are_derived() -> None:
    rows = _qualification_rows()
    report = summarize(rows)
    assert report["state_confusion"] == {
        "explicit-test-edit|sufficient|explicit-test-target": 1,
        "non-edit|sufficient|no-edit-authority": 1,
        "true-ambiguity|sufficient|ambiguous": 1,
        "unique-owner|sufficient|resolved": 1,
    }
    assert report["abstention_quality"]["true_ambiguity_precision"] == 1
    assert report["abstention_quality"]["true_ambiguity_recall"] == 1
    assert report["abstention_quality"]["non_edit_specificity"] == 1


def test_unjustified_unresolved_is_visible_without_parallel_authority_logic() -> None:
    unresolved = evaluate_case(
        _case(case_id="unresolved"),
        {"state": "unresolved", "owner": None},
    )
    report = summarize([unresolved, *_qualification_rows()[1:]])
    assert report["qualification"] == "not-qualified"
    assert report["hard_zero"]["sufficient_unique_reported_unresolved"] == 1
    assert report["state_confusion"]["unique-owner|sufficient|unresolved"] == 1
    assert report["abstention_quality"]["unjustified_unresolved_rate"] == 1
    assert report["abstention_quality"]["justified_unresolved_rate"] == 0


def test_insufficient_evidence_unresolved_is_justified_abstention() -> None:
    unresolved = evaluate_case(
        _case(
            case_id="insufficient",
            semantic_truth="insufficient-owner-evidence",
            admitted_evidence_truth="insufficient",
            expected_owner=None,
        ),
        {"state": "unresolved", "owner": None},
    )
    report = summarize([*_qualification_rows(), unresolved])
    assert report["qualification"] == "qualified"
    assert report["abstention_quality"]["justified_unresolved_rate"] == 1
    assert report["abstention_quality"]["unjustified_unresolved_rate"] == 0


def test_false_ambiguity_reduces_precision_and_remains_hard_failure() -> None:
    false_ambiguous = evaluate_case(
        _case(case_id="false-ambiguous"),
        {"state": "ambiguous", "owner": None},
    )
    report = summarize([false_ambiguous, *_qualification_rows()[1:]])
    assert report["qualification"] == "not-qualified"
    assert report["hard_zero"]["sufficient_unique_reported_ambiguous"] == 1
    assert report["abstention_quality"]["true_ambiguity_precision"] == 0.5
    assert report["abstention_quality"]["true_ambiguity_recall"] == 1


def test_policy_identity_is_bound_into_case_identity() -> None:
    original = _case()
    changed = _case(evaluation_profile="release-critical.v1")
    assert case_identity(original) != case_identity(changed)


def test_policy_version_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="metric_policy"):
        evaluate_case(
            _case(metric_policy="hashmarks.lexicographic-quality.v0"),
            {"state": "resolved", "owner": "src/widget.py::widget"},
        )


def test_qualification_identity_ignores_diagnostic_membership() -> None:
    active = _qualification_rows()
    shadow = evaluate_case(
        _case(case_id="shadow", corpus_class="shadow"),
        {"state": "resolved", "owner": "src/widget.py::widget"},
    )
    baseline = summarize(active)
    with_shadow = summarize([*active, shadow])
    assert baseline["corpus"]["identity"] != with_shadow["corpus"]["identity"]
    assert (
        baseline["corpus"]["qualification_identity"]
        == with_shadow["corpus"]["qualification_identity"]
    )


def test_slice_quality_reports_task_risk_and_profile_without_global_score() -> None:
    report = summarize(_qualification_rows())
    assert report["slice_quality"]["macro_by_task_family"]["owner-selection"]["cases"] == 4
    assert report["slice_quality"]["macro_by_risk_class"]["change-support"]["cases"] == 4
    assert (
        report["slice_quality"]["macro_by_evaluation_profile"]["change-support.v1"]["cases"]
        == 4
    )
    assert "score" not in report


def test_proof_mode_registry_reports_missing_modes_without_inventing_proof() -> None:
    report = summarize(_qualification_rows())
    proof = report["benchmark_health"]["proof_modes"]
    assert proof["counts"]["unit"] == 4
    assert proof["present"] == ["unit"]
    assert proof["missing"] == ["adversarial", "boundary", "lifecycle", "mutation"]
