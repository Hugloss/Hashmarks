from scripts.agent_evaluation.economics import (
    complementarity_comparison,
    summarize_complementarity_lane,
    verification_surface,
    verification_surface_equivalent,
)


def test_pytest_more_specific_selector_satisfies_file_authority() -> None:
    authority = ["python", "-m", "pytest", "-q", "tests/test_widget.py"]
    candidate = ["python", "-m", "pytest", "-q", "tests/test_widget.py::test_widget"]
    assert verification_surface(candidate) == {
        "runner": "pytest",
        "surface": "tests/test_widget.py",
        "selector": "test_widget",
    }
    assert verification_surface_equivalent(candidate, authority) is True


def test_pytest_file_only_does_not_satisfy_secret_exact_selector() -> None:
    authority = ["python", "-m", "pytest", "-q", "tests/test_widget.py::test_widget"]
    candidate = ["python", "-m", "pytest", "-q", "tests/test_widget.py"]
    assert verification_surface_equivalent(candidate, authority) is False


def test_verification_surface_requires_same_runner_and_surface() -> None:
    assert verification_surface_equivalent(
        ["go", "test", "./route"], ["go", "test", "./route"]
    )
    assert not verification_surface_equivalent(
        ["go", "test", "./other"], ["go", "test", "./route"]
    )
    assert verification_surface_equivalent(
        ["tsc", "--noEmit", "-p", "tsconfig.json"],
        ["tsc", "--noEmit", "--project", "tsconfig.json"],
    )


def test_complementarity_summary_requires_preserved_success_and_lower_cost() -> None:
    native = summarize_complementarity_lane(
        "native",
        [
            {
                "verified_solution": True,
                "decision_visible_bytes": 1000,
                "repository_evidence_bytes": 1000,
                "decision_interactions": 4,
                "search_calls": 1,
                "read_calls": 2,
            },
            {
                "verified_solution": True,
                "decision_visible_bytes": 800,
                "repository_evidence_bytes": 800,
                "decision_interactions": 3,
                "search_calls": 1,
                "read_calls": 1,
            },
        ],
    )
    assisted = summarize_complementarity_lane(
        "hashmarks",
        [
            {
                "verified_solution": True,
                "decision_visible_bytes": 500,
                "repository_evidence_bytes": 100,
                "decision_interactions": 2,
                "search_calls": 0,
                "read_calls": 1,
            },
            {
                "verified_solution": True,
                "decision_visible_bytes": 500,
                "repository_evidence_bytes": 100,
                "decision_interactions": 2,
                "search_calls": 0,
                "read_calls": 1,
            },
        ],
    )
    comparison = complementarity_comparison(native, assisted)
    assert native["decision_visible_bytes_per_verified_solution"] == 900
    assert assisted["decision_visible_bytes_per_verified_solution"] == 500
    assert comparison["supports_complementarity_claim"] is True
    assert comparison["verified_rate_delta_pp"] == 0
