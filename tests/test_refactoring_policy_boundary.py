from pathlib import Path


def test_refactoring_policy_requires_measured_product_value_without_phase_history() -> None:
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    policy = Path("docs/maintainers/RESPONSIBILITY_REFACTORING.md").read_text(
        encoding="utf-8"
    )

    assert "Structural cleanup requires measured product value" in agents
    assert "Ruff/LOC alone do not authorize a refactor" in agents
    assert "do not create a parallel phase-history document" in policy

    for label in range(55, 66):
        assert f"### G{label} —" not in agents

    for historical in (
        "Post-RCR",
        "RCR-01",
        "RCR-08",
        "Starting authority: exact DEVELOPMENT",
        "Execution status after BO",
        "Closed phase evidence:",
        "Compatibility aliases may preserve v0.11 public names",
    ):
        assert historical not in policy

    for decision in (
        "KEEP COHESIVE",
        "REFACTOR INTERNALLY",
        "EXTRACT RESPONSIBILITY",
        "DECOMPOSE MULTIPLE RESPONSIBILITIES",
    ):
        assert decision in policy
