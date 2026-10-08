"""Hermes-inspired regression: external verification freshness is coverage-bound.

The consumer owns agent reads, verification execution and changed-path reporting.
Hashmarks may describe their evidence, never infer a complete change universe
from a partial list or turn a producer claim into canonical repository proof.
"""

import pytest

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
    assert (
        packet["reason"] == "declared-complete-change-set-outside-observation-scope"
    )
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
