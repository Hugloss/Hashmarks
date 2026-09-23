from pathlib import Path


def test_post_rcr_policy_requires_product_value() -> None:
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    policy = Path("docs/maintainers/RESPONSIBILITY_REFACTORING.md").read_text(
        encoding="utf-8"
    )

    assert "G55 — Post-RCR work is product-value driven" in agents
    assert "Ruff/LOC alone do not authorize a phase" in agents
    for decision in (
        "KEEP COHESIVE",
        "REFACTOR INTERNALLY",
        "EXTRACT RESPONSIBILITY",
        "DECOMPOSE MULTIPLE RESPONSIBILITIES",
    ):
        assert decision in policy
