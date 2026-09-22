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
        "reviewer_identity": "reviewer:fixture",
        "adjudication_state": "reviewed",
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
    assert report["qualification"] == "qualified"
    assert report["benchmark_health"]["needs_adjudication"] == 0
    assert report["benchmark_health"]["diagnostic_needs_adjudication"] == 1


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
    assert (
        report["slice_quality"]["macro_by_task_family"]["owner-selection"]["cases"] == 4
    )
    assert (
        report["slice_quality"]["macro_by_risk_class"]["change-support"]["cases"] == 4
    )
    assert (
        report["slice_quality"]["macro_by_evaluation_profile"]["change-support.v1"][
            "cases"
        ]
        == 4
    )
    assert "score" not in report


def test_proof_mode_registry_reports_missing_modes_without_inventing_proof() -> None:
    report = summarize(_qualification_rows())
    proof = report["benchmark_health"]["proof_modes"]
    assert proof["counts"]["unit"] == 4
    assert proof["present"] == ["unit"]
    assert proof["missing"] == ["adversarial", "boundary", "lifecycle", "mutation"]


def test_ranking_metrics_are_diagnostic_and_do_not_change_authority() -> None:
    ranked = evaluate_case(
        _case(case_id="ranked"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "ranking": {"rank": 2},
            "verification": {"rank": 5},
        },
    )
    report = summarize([ranked, *_qualification_rows()[1:]])
    assert report["qualification"] == "qualified"
    assert report["ranking_quality"]["owner"]["recall_at_1"] == 0
    assert report["ranking_quality"]["owner"]["recall_at_5"] == 1
    assert report["ranking_quality"]["owner"]["mrr"] == 0.5
    assert report["ranking_quality"]["verification"]["recall_at_5"] == 1


def test_stability_metrics_are_unknown_without_observations() -> None:
    report = summarize(_qualification_rows())
    assert report["stability_quality"]["paraphrase_owner_stable"] is None
    assert report["stability_quality"]["projection_authority_stable"] is None


def test_stability_observations_report_rates_without_granting_authority() -> None:
    stable = evaluate_case(
        _case(case_id="stable"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "stability": {
                "paraphrase_owner_stable": True,
                "retrieval_bound_owner_stable": True,
                "projection_authority_stable": True,
                "generation_authority_stable": False,
            },
        },
    )
    report = summarize([stable, *_qualification_rows()[1:]])
    assert report["qualification"] == "qualified"
    assert report["stability_quality"]["paraphrase_owner_stable"] == 1
    assert report["stability_quality"]["generation_authority_stable"] == 0


def test_economics_missing_is_unknown_and_observed_values_are_bounded_diagnostics() -> (
    None
):
    baseline = summarize(_qualification_rows())
    assert baseline["economics"]["cases"] == 0
    assert baseline["economics"]["metrics"]["latency_ms"]["min"] is None
    measured = evaluate_case(
        _case(case_id="measured"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "economics": {
                "latency_ms": 12,
                "rows_inspected": 40,
                "candidate_count": 5,
                "peak_memory_bytes": 1024,
            },
        },
    )
    report = summarize([measured, *_qualification_rows()[1:]])
    assert report["economics"]["metrics"]["latency_ms"] == {
        "samples": 1,
        "min": 12,
        "max": 12,
    }
    assert report["qualification"] == "qualified"


def test_pending_active_qualification_case_requires_adjudication() -> None:
    pending = evaluate_case(
        _case(case_id="pending", adjudication_state="pending"),
        {"state": "resolved", "owner": "src/widget.py::widget"},
    )
    report = summarize([*_qualification_rows(), pending])
    assert report["qualification"] == "needs-adjudication"
    assert report["benchmark_health"]["needs_adjudication"] == 1


def test_invalid_shadow_case_is_diagnostic_not_qualification_blocking() -> None:
    invalid = evaluate_case(
        _case(
            case_id="invalid-shadow",
            corpus_class="shadow",
            ground_truth_status="invalid-case",
        ),
        {"state": "unresolved", "owner": None},
    )
    report = summarize([*_qualification_rows(), invalid])
    assert report["qualification"] == "qualified"
    assert report["benchmark_health"]["invalid_cases"] == 0
    assert report["benchmark_health"]["diagnostic_invalid_cases"] == 1


def test_new_authority_identity_vetoes_are_non_compensatory() -> None:
    for metric in (
        "producer_identity_mismatch_accepted",
        "evidence_receipt_mismatch_accepted",
        "selection_membership_mismatch_accepted",
        "missing_required_authority_provenance",
        "synthetic_command_overrides_proven_command",
        "conflicting_commands_incorrectly_resolved",
        "false_premise_accepted_as_authority",
    ):
        observed = {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            metric: True,
        }
        row = evaluate_case(_case(case_id=metric), observed)
        report = summarize([row, *_qualification_rows()[1:]])
        assert report["qualification"] == "not-qualified"
        assert report["hard_zero"][metric] == 1


def test_ndcg_is_reported_as_ranking_quality_not_authority() -> None:
    ranked = evaluate_case(
        _case(case_id="ndcg"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "ranking": {"rank": 2},
        },
    )
    report = summarize([ranked, *_qualification_rows()[1:]])
    assert report["qualification"] == "qualified"
    assert report["ranking_quality"]["owner"]["ndcg"] is not None


def test_evidence_retention_is_diagnostic() -> None:
    retained = evaluate_case(
        _case(case_id="retained"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "evidence_retention": {
                "related_dependency_retained": True,
                "impact_evidence_retained": True,
                "caller_callee_retained": False,
            },
        },
    )
    report = summarize([retained, *_qualification_rows()[1:]])
    assert report["qualification"] == "qualified"
    assert report["evidence_retention"]["related_dependency_retained"] == 1
    assert report["evidence_retention"]["caller_callee_retained"] == 0


def test_environment_fingerprint_and_mode_are_diagnostic() -> None:
    measured = evaluate_case(
        _case(case_id="environment"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "environment": {"fingerprint": "sha256:env", "mode": "cold"},
        },
    )
    report = summarize([measured, *_qualification_rows()[1:]])
    assert report["environment_health"] == {
        "cases": 1,
        "modes": {"cold": 1},
        "fingerprints": ["sha256:env"],
    }


def test_metamorphic_family_membership_is_visible() -> None:
    mutated = evaluate_case(
        _case(case_id="metamorphic", metamorphic_family="irrelevant-file-addition"),
        {"state": "resolved", "owner": "src/widget.py::widget"},
    )
    report = summarize([mutated, *_qualification_rows()[1:]])
    assert report["metamorphic_health"] == {
        "families": {"irrelevant-file-addition": 1},
        "cases": 1,
        "executed": 0,
        "executed_families": {},
        "violations": 0,
    }


def test_review_provenance_changes_case_identity() -> None:
    assert case_identity(_case()) != case_identity(
        _case(reviewer_identity="reviewer:other")
    )


def test_partial_stability_observations_remain_unknown_per_metric() -> None:
    row = evaluate_case(
        _case(case_id="partial-stability"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "stability": {"paraphrase_owner_stable": True},
        },
    )
    report = summarize([row, *_qualification_rows()[1:]])
    assert report["stability_quality"]["paraphrase_owner_stable"] == 1
    assert report["stability_quality"]["retrieval_bound_owner_stable"] is None


def test_partial_retention_observations_remain_unknown_per_metric() -> None:
    row = evaluate_case(
        _case(case_id="partial-retention"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "evidence_retention": {"related_dependency_retained": True},
        },
    )
    report = summarize([row, *_qualification_rows()[1:]])
    assert report["evidence_retention"]["related_dependency_retained"] == 1
    assert report["evidence_retention"]["impact_evidence_retained"] is None


@pytest.mark.parametrize("rank", [0, -1])
def test_invalid_ranking_rank_fails_closed(rank: int) -> None:
    row = evaluate_case(
        _case(case_id=f"rank-{rank}"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "ranking": {"rank": rank},
        },
    )
    with pytest.raises(ValueError, match="rank must be >= 1"):
        summarize([row, *_qualification_rows()[1:]])


def test_negative_economics_fail_closed() -> None:
    row = evaluate_case(
        _case(case_id="negative-economics"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "economics": {"latency_ms": -1},
        },
    )
    with pytest.raises(ValueError, match="non-negative"):
        summarize([row, *_qualification_rows()[1:]])


def test_invalid_environment_mode_and_missing_fingerprint_fail_closed() -> None:
    invalid_mode = evaluate_case(
        _case(case_id="invalid-mode"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "environment": {"fingerprint": "sha256:env", "mode": "cached-ish"},
        },
    )
    with pytest.raises(ValueError, match="environment mode"):
        summarize([invalid_mode, *_qualification_rows()[1:]])

    missing_fingerprint = evaluate_case(
        _case(case_id="missing-fingerprint"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "environment": {"mode": "cold"},
        },
    )
    with pytest.raises(ValueError, match="environment fingerprint"):
        summarize([missing_fingerprint, *_qualification_rows()[1:]])


def test_pending_active_case_is_not_mislabeled_as_diagnostic() -> None:
    pending = evaluate_case(
        _case(case_id="pending-active", adjudication_state="pending"),
        {"state": "resolved", "owner": "src/widget.py::widget"},
    )
    report = summarize([*_qualification_rows(), pending])
    assert report["qualification"] == "needs-adjudication"
    assert report["benchmark_health"]["needs_adjudication"] == 1
    assert report["benchmark_health"]["diagnostic_needs_adjudication"] == 0


def test_new_top_level_authority_vetoes_are_non_compensatory() -> None:
    for metric in (
        "false_authority",
        "false_safe_edit",
        "unjustified_actionable_finding",
    ):
        row = evaluate_case(
            _case(case_id=metric),
            {"state": "resolved", "owner": "src/widget.py::widget", metric: True},
        )
        report = summarize([row, *_qualification_rows()[1:]])
        assert report["qualification"] == "not-qualified"
        assert report["hard_zero"][metric] == 1



def test_structured_authority_observation_derives_false_authority_veto() -> None:
    row = evaluate_case(
        _case(case_id="derived-false-authority"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "authority_observation": {
                "owner_resolved": True,
                "resolved_owner": "src/widget.py::widget",
                "candidate_owner": "src/widget.py::widget",
                "proof_complete": False,
            },
        },
    )
    report = summarize([row, *_qualification_rows()[1:]])
    assert report["hard_zero"]["false_authority"] == 1
    assert report["qualification"] == "not-qualified"


def test_external_evidence_cannot_confer_repository_authority() -> None:
    row = evaluate_case(
        _case(case_id="external-authority"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "authority_observation": {
                "owner_resolved": True,
                "resolved_owner": "src/widget.py::widget",
                "candidate_owner": "src/widget.py::widget",
                "proof_complete": True,
                "external_evidence_only": True,
            },
        },
    )
    report = summarize([row, *_qualification_rows()[1:]])
    assert report["hard_zero"]["external_evidence_authority_leak"] == 1


def test_contradicted_finding_cannot_remain_actionable() -> None:
    row = evaluate_case(
        _case(case_id="contradicted-finding"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "finding_observation": {
                "actionable": True,
                "admissible_evidence": True,
                "contradicted": True,
            },
        },
    )
    report = summarize([row, *_qualification_rows()[1:]])
    assert report["hard_zero"]["unjustified_actionable_finding"] == 1


def test_presentation_metamorphic_drift_is_hard_failure() -> None:
    row = evaluate_case(
        _case(case_id="presentation-drift", metamorphic_family="retrieval-limit"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "metamorphic_observation": {
                "family": "retrieval-limit",
                "baseline_authority_proof_identity": "sha256:a",
                "candidate_authority_proof_identity": "sha256:b",
                "expected_relation": "invariant",
            },
        },
    )
    report = summarize([row, *_qualification_rows()[1:]])
    assert report["metamorphic_health"]["executed"] == 1
    assert report["metamorphic_health"]["violations"] == 1
    assert report["hard_zero"]["metamorphic_authority_drift"] == 1
    assert report["qualification"] == "not-qualified"


def test_generation_mutation_must_change_authority_when_expected() -> None:
    row = evaluate_case(
        _case(case_id="generation-mutation", metamorphic_family="generation-mutation"),
        {
            "state": "resolved",
            "owner": "src/widget.py::widget",
            "metamorphic_observation": {
                "family": "generation-mutation",
                "baseline_authority_proof_identity": "sha256:same",
                "candidate_authority_proof_identity": "sha256:same",
                "expected_relation": "change",
            },
        },
    )
    report = summarize([row, *_qualification_rows()[1:]])
    assert report["hard_zero"]["metamorphic_authority_drift"] == 1


def test_changed_authority_transition_requires_named_admissible_evidence() -> None:
    with pytest.raises(ValueError, match="named admissible evidence"):
        evaluate_case(
            _case(case_id="unnamed-transition"),
            {
                "state": "resolved",
                "owner": "src/widget.py::widget",
                "authority_transition": {"before": "sha256:a", "after": "sha256:b"},
            },
        )


def test_proof_profile_minimums_are_visible_without_silently_granting_readiness() -> None:
    report = summarize(_qualification_rows())
    profiles = report["benchmark_health"]["proof_profiles"]
    assert profiles["change-support.v1"]["adequate"] is False
    assert profiles["change-support.v1"]["missing"] == {
        "boundary": 1,
        "adversarial": 1,
    }
    assert profiles["release-critical.v1"]["adequate"] is False


def test_uncertainty_is_descriptive_and_never_a_qualification_threshold() -> None:
    report = summarize(_qualification_rows())
    interval = report["uncertainty"]["resolvable_owner_coverage_95pct"]
    assert interval["successes"] == 1
    assert interval["total"] == 1
    assert interval["estimate"] == 1
    assert interval["low"] < interval["high"]
    assert report["uncertainty"]["interpretation"] == (
        "descriptive-only-no-qualification-threshold"
    )
    assert report["qualification"] == "qualified"
