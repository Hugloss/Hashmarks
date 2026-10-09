"""Hermes-inspired regression: external verification freshness is coverage-bound.

The consumer owns agent reads, verification execution and changed-path reporting.
Hashmarks may describe their evidence, never infer a complete change universe
from a partial list or turn a producer claim into canonical repository proof.
"""

import pytest

from hashmarks import validate_repository_intelligence_evidence
from hashmarks.codemap.repository_delta import (
    RepositoryDeltaMixin,
    RepositoryGenerationBinding,
)


def _observed_verification() -> dict[str, object]:
    return RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pyright",
        binding=RepositoryGenerationBinding("sha256:before", 4),
        diagnostics=[],
        outcome="pass",
        collection_state="fresh-complete",
        scope_paths=["src/owner.py", "tests/test_owner.py"],
    )


def _freshness(
    *,
    changed_paths: list[str],
    change_set_complete: bool = False,
    dependency_paths: list[str] | None = None,
) -> dict[str, object]:
    return RepositoryDeltaMixin.external_observation_freshness(
        _observed_verification(),
        current_repository_identity="sha256:after",
        current_generation=5,
        changed_paths=changed_paths,
        dependency_paths=dependency_paths or [],
        change_set_complete=change_set_complete,
    )


def test_disjoint_partial_change_set_cannot_prove_verification_fresh() -> None:
    packet = _freshness(changed_paths=["docs/guide.md"])

    assert packet["state"] == "unknown"
    assert packet["reason"] == "change-set-completeness-unproven"
    assert packet["change_set_completeness"] == "unknown"
    assert packet["intersection"] == []
    assert packet["authority"] == "observation-freshness-only"


def test_default_empty_change_set_cannot_prove_verification_fresh() -> None:
    packet = _freshness(changed_paths=[])

    assert packet["state"] == "unknown"
    assert packet["reason"] == "change-set-completeness-unproven"


def test_even_claimed_complete_empty_paths_cannot_explain_changed_endpoint() -> None:
    packet = _freshness(changed_paths=[], change_set_complete=True)

    assert packet["state"] == "unknown"
    assert packet["reason"] == "changed-endpoint-without-path-change-evidence"
    assert packet["change_set_completeness"] == "caller-claimed-complete"


def test_disjoint_declared_complete_change_set_yields_conditional_current() -> None:
    packet = _freshness(
        changed_paths=["docs/guide.md"],
        change_set_complete=True,
    )

    assert packet["state"] == "current"
    assert packet["reason"] == "declared-complete-change-set-outside-observation-scope"
    assert packet["change_set_completeness"] == "caller-claimed-complete"


@pytest.mark.parametrize("complete", [False, True])
def test_observed_relevant_change_is_stale_even_without_complete_list(
    complete: bool,
) -> None:
    packet = _freshness(
        changed_paths=["src/owner.py", "docs/guide.md"],
        change_set_complete=complete,
    )
    assert packet["state"] == "stale"
    assert packet["reason"] == "relevant-repository-evidence-changed"
    assert packet["intersection"] == ["src/owner.py"]


def test_dependency_intersection_is_stale_with_partial_changed_paths() -> None:
    packet = _freshness(
        changed_paths=["src/dependency.py"],
        dependency_paths=["src/dependency.py"],
    )
    assert packet["state"] == "stale"
    assert packet["intersection"] == ["src/dependency.py"]


def test_unchanged_observation_binding_needs_no_change_set_claim() -> None:
    packet = RepositoryDeltaMixin.external_observation_freshness(
        _observed_verification(),
        current_repository_identity="sha256:before",
        current_generation=4,
    )
    assert packet["state"] == "current"
    assert packet["reason"] == "repository-and-generation-unchanged"
    assert packet["change_set_completeness"] == "unknown"


@pytest.mark.parametrize("bad", [None, 0, 1, "true", [], {}])
def test_change_set_completeness_requires_a_real_boolean(bad: object) -> None:
    with pytest.raises(ValueError, match="change_set_complete must be a boolean"):
        RepositoryDeltaMixin.external_observation_freshness(
            _observed_verification(),
            current_repository_identity="sha256:after",
            current_generation=5,
            changed_paths=["docs/guide.md"],
            change_set_complete=bad,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("changed_paths", "complete", "state", "stale"),
    [
        (["docs/guide.md"], False, "unknown", None),
        ([], False, "unknown", None),
        ([], True, "unknown", None),
        (["docs/guide.md"], True, "current", False),
        (["src/owner.py"], False, "stale", True),
        (["src/owner.py"], True, "stale", True),
    ],
)
def test_public_validation_preserves_external_freshness_qualification(
    changed_paths: list[str], complete: bool, state: str, stale: bool | None
) -> None:
    packet = _freshness(changed_paths=changed_paths, change_set_complete=complete)
    checked = validate_repository_intelligence_evidence(packet)

    assert checked["valid"] is True
    assert checked["reasons"] == []
    normalized = checked["normalized"]
    assert normalized["freshness_state"] == state
    assert normalized["stale"] is stale
    assert normalized["change_set_completeness"] == packet["change_set_completeness"]
    assert normalized["freshness_reason"] == packet["reason"]

    required = validate_repository_intelligence_evidence(packet, require_fresh=True)
    assert required["valid"] is (state == "current")
    assert required["reasons"] == (
        [] if state == "current" else ["fresh-evidence-required"]
    )


@pytest.mark.parametrize("complete", [False, True])
def test_normalized_freshness_distinguishes_unchanged_and_conditional_current(
    complete: bool,
) -> None:
    unchanged = RepositoryDeltaMixin.external_observation_freshness(
        _observed_verification(),
        current_repository_identity="sha256:before",
        current_generation=4,
        change_set_complete=complete,
    )
    conditional = _freshness(changed_paths=["docs/guide.md"], change_set_complete=True)
    checked_unchanged = validate_repository_intelligence_evidence(
        unchanged, require_fresh=True
    )
    checked_conditional = validate_repository_intelligence_evidence(
        conditional, require_fresh=True
    )

    assert checked_unchanged["valid"] is True
    assert checked_conditional["valid"] is True
    assert checked_unchanged["normalized"]["freshness_reason"] == (
        "repository-and-generation-unchanged"
    )
    assert checked_conditional["normalized"]["freshness_reason"] == (
        "declared-complete-change-set-outside-observation-scope"
    )
    assert checked_conditional["normalized"]["change_set_completeness"] == (
        "caller-claimed-complete"
    )


@pytest.mark.parametrize("bad", [None, True, "complete", [], {}, 0])
def test_public_validation_rejects_invalid_change_set_qualification(
    bad: object,
) -> None:
    packet = _freshness(changed_paths=["docs/guide.md"], change_set_complete=True)
    packet["change_set_completeness"] = bad

    checked = validate_repository_intelligence_evidence(packet)

    assert checked["valid"] is False
    assert "invalid-change-set-completeness" in checked["reasons"]
    assert checked["normalized"] is None
