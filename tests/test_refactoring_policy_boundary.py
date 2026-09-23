from pathlib import Path


def test_refactoring_policy_requires_measured_product_value_and_current_decisions() -> (
    None
):
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    policy = Path("docs/maintainers/RESPONSIBILITY_REFACTORING.md").read_text(
        encoding="utf-8"
    )
    invariants = Path("docs/reference/INVARIANTS.md").read_text(encoding="utf-8")

    assert "Structural cleanup requires measured product value" in agents
    assert "Ruff/LOC alone do not authorize a refactor" in agents
    assert "do not create a parallel phase-history document" in policy
    assert "A6. APIs have one current supported spelling." in invariants

    for decision in (
        "KEEP COHESIVE",
        "REFACTOR INTERNALLY",
        "EXTRACT RESPONSIBILITY",
        "DECOMPOSE MULTIPLE RESPONSIBILITIES",
    ):
        assert decision in policy
