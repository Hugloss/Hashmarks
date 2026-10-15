"""Required caller scope survives diagnostic-delta validation."""

import pytest

from hashmarks.codemap.diagnostic_observation import validated_diagnostic_delta
from hashmarks.codemap.repository_delta import (
    RepositoryDeltaMixin,
    RepositoryGenerationBinding,
)


def test_missing_changed_paths_is_not_an_explicit_empty_scope() -> None:
    observation = RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pyright",
        binding=RepositoryGenerationBinding("repository:fixture", 4),
        environment_identity="environment:fixture",
        diagnostics=[],
        outcome="pass",
        scope_paths=("src/owner.py",),
        collection_state="fresh-complete",
    )
    delta = RepositoryDeltaMixin.diagnostic_observation_delta(
        observation, observation, changed_paths=[]
    )
    assert validated_diagnostic_delta(delta)
    change_set = delta["change_set"]
    assert isinstance(change_set, dict)
    del change_set["paths"]
    with pytest.raises(ValueError, match="changed_paths must be a sequence"):
        validated_diagnostic_delta(delta)
