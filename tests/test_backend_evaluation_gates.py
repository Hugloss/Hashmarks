"""Hard backend QA failures cannot disappear behind missing or positive proof."""

from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.repository_evaluation.backend_gates import combine_required
from scripts.repository_evaluation.backend_workflows import _authority_safe, _gates


@pytest.mark.parametrize(
    "observations,expected",
    [
        ([], None),
        ([None], None),
        ([True], True),
        ([True, None], None),
        ([None, False], False),
        ([False, None], False),
        ([True, False], False),
    ],
)
def test_required_proof_is_non_vacuous_and_failure_preserving(observations, expected):
    assert combine_required(observations) is expected


@pytest.mark.parametrize("invalid", [0, 1, "PASS", {}])
def test_gate_values_cannot_gain_authority_by_truthiness(invalid):
    with pytest.raises(ValueError, match="bool or None"):
        combine_required([invalid])


def _stage():
    transport = {
        "parity": True,
        "authority": True,
        "revision": True,
        "initial_size": True,
        "initial_evidence": True,
    }
    return {
        "packet": {
            "ownership": {"owner": {"path": "backend.py"}},
            "retrieval": {"results": [{"path": "backend.py"}]},
        },
        "grade": {"classification": "PASS", "authority_violations": 0},
        "revision_bound": True,
        "cli": deepcopy(transport),
        "mcp": deepcopy(transport),
        "initial": {
            "packet": {"ownership": {"owner": {"path": "backend.py"}}},
            "revision_bound": True,
            "cli": deepcopy(transport),
            "mcp": deepcopy(transport),
        },
    }


def _evaluate(before, after):
    return _gates(
        before,
        after,
        {"passed": True},
        {
            "expected_owner_path": "backend.py",
            "owner_oracle": {
                "scope": "file",
                "resolution": "unique",
                "candidates": [{"path": "backend.py"}],
            },
        },
        {"classification": "PASS", "authority_violations": 0},
    )


def test_after_initial_oversize_is_a_hard_gate_independent_of_recall():
    before, after = _stage(), _stage()
    after["initial"]["mcp"]["initial_size"] = False
    gates = _evaluate(before, after)
    assert gates["initial_size"] is False
    assert gates["initial_evidence"] is True


def test_known_after_transport_failure_dominates_missing_before_proof():
    before, after = _stage(), _stage()
    before["mcp"]["parity"] = None
    after["mcp"]["parity"] = False
    gates = _evaluate(before, after)
    assert gates["mcp"] is False
    assert gates["presentation"] is False


def test_initial_profile_failure_cannot_be_hidden_by_full_profile():
    before, after = _stage(), _stage()
    after["initial"]["cli"]["authority"] = False
    assert _evaluate(before, after)["authority"] is False


def test_missing_initial_proof_cannot_be_certified_by_full_profile():
    before, after = _stage(), _stage()
    after["initial"]["mcp"]["initial_size"] = None
    assert _evaluate(before, after)["initial_size"] is None


def test_owner_recall_requires_the_after_stage():
    before, after = _stage(), _stage()
    after["packet"]["retrieval"]["results"] = []
    assert _evaluate(before, after)["owner_top_three"] is False


def test_wrong_symbol_in_correct_file_is_not_exact_owner_proof():
    expected = {
        "path": "backend.py",
        "qualname": "CorrectOwner",
        "start_line": 1,
        "end_line": 2,
    }
    rule = {
        "owner_oracle": {
            "scope": "symbol",
            "resolution": "unique",
            "candidates": [expected],
        }
    }
    packet = {"ownership": {"owner": {**expected, "qualname": "WrongOwner"}}}
    assert _authority_safe(packet, rule) is False
    packet["ownership"]["owner"] = expected
    assert _authority_safe(packet, rule) is True


def test_legacy_file_label_does_not_qualify_exact_symbol_authority():
    assert (
        _authority_safe(
            {"ownership": {"owner": {"path": "backend.py", "qualname": "Anything"}}},
            {"expected_owner_path": "backend.py"},
        )
        is None
    )


def test_ambiguous_oracle_cannot_admit_unique_owner():
    packet = {"ownership": {"owner": {"path": "backend.py"}}}
    assert (
        _authority_safe(
            packet,
            {
                "owner_oracle": {
                    "scope": "file",
                    "resolution": "ambiguous",
                    "candidates": [{"path": "backend.py"}, {"path": "other.py"}],
                }
            },
        )
        is False
    )


def test_native_failure_survives_missing_workflow_report():
    from scripts.repository_evaluation.aggregate_backend import _merge_suite
    from scripts.repository_evaluation.backend_matrix import capability_matrix

    suite = {
        "workflows": [
            {
                "id": "one",
                "repository": "repo",
                "problem_id": "bug",
                "capabilities": [18],
                "native_required": True,
            }
        ]
    }
    merged = _merge_suite(
        "suite", suite, {}, {"one": {"gates": {"after_binding": False}}}
    )
    assert (
        capability_matrix(merged["workflows"], merged["outcomes"])["status"] == "FAIL"
    )
    assert {row["proof"] for row in merged["missing"]} == {"workflow-report"}


def test_rejected_presentation_is_retained_as_failure_evidence():
    from scripts.repository_evaluation.backend_gates import presentation_conformance

    result = presentation_conformance({}, {"format": "bad"})
    assert result["valid"] is False
    error = result["error"]
    assert isinstance(error, str)
    assert "format" in error


def test_symbol_recall_rejects_right_file_with_wrong_declaration():
    from scripts.repository_evaluation.backend_grading import _owner_top_three

    expected = {
        "path": "backend.py",
        "qualname": "Worker.run",
        "start_line": 3,
        "end_line": 5,
    }
    rule = {
        "owner_oracle": {
            "scope": "symbol",
            "resolution": "unique",
            "candidates": [expected],
        }
    }
    packet = {
        "retrieval": {
            "results": [
                {
                    "path": "backend.py",
                    "symbol": "Worker.other",
                    "start_line": 3,
                    "end_line": 5,
                }
            ]
        }
    }
    assert _owner_top_three(packet, rule) is False
    packet["retrieval"]["results"][0]["symbol"] = "Worker.run"
    assert _owner_top_three(packet, rule) is True


def test_symbol_recall_accepts_qualified_bounded_declaration_without_ownership():
    from scripts.repository_evaluation.backend_grading import _owner_top_three

    expected = {
        "path": "backend.py",
        "qualname": "Worker.run",
        "start_line": 3,
        "end_line": 5,
    }
    rule = {
        "owner_oracle": {
            "scope": "symbol",
            "resolution": "unique",
            "candidates": [expected],
        }
    }
    declaration = {
        "path": "backend.py",
        "symbol": "Worker.run",
        "start_line": 3,
        "end_line": 5,
    }
    context = {
        "authority": "indexed-lexical-declarations-only",
        "ownership_authority": False,
        "negative_evidence_admissible": False,
        "source_revision": "bound-source",
        "declarations": [declaration],
    }
    packet = {
        "retrieval": {
            "results": [
                {
                    "path": "backend.py",
                    "symbol": "Worker",
                    "class_declarations": context,
                }
            ]
        }
    }
    assert _owner_top_three(packet, rule) is True
    context["ownership_authority"] = True
    assert _owner_top_three(packet, rule) is False
