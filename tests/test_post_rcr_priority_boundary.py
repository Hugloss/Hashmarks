from pathlib import Path


def test_post_rcr_policy_requires_product_value() -> None:
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    review = Path("docs/development/reviews/POST_RCR_PRIORITY_REVIEW.md").read_text(
        encoding="utf-8"
    )
    assert "G55 — Post-RCR work is product-value driven" in agents
    assert "Ruff/LOC alone do not authorize a phase" in agents
    assert "normal RRF remains authoritative" in review
    assert "REFactor internally".upper() in review.upper()
