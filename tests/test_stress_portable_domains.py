from __future__ import annotations

from dataclasses import replace
from typing import Literal, cast

import pytest

from hashmarks.portable_scalar import MAX_PORTABLE_INTEGER
from hashmarks.product_acceptance import scale_class_contract
from scripts.agent_evaluation.experimentability import (
    ExperimentRepositoryState,
    experiment_environment,
    normalize_capabilities,
)


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        -1,
        1.0,
        1.5,
        float("nan"),
        float("inf"),
        1 << 53,
        10**100,
        "1",
        None,
    ],
)
def test_scale_contract_rejects_nonportable_file_counts(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        scale_class_contract(files=cast(int, value), source_bytes=1)


@pytest.mark.parametrize(
    "value",
    [True, False, -1, 1.0, float("nan"), float("inf"), 1 << 53, 10**100, "1", None],
)
def test_scale_contract_rejects_nonportable_source_bytes(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        scale_class_contract(files=1, source_bytes=cast(int, value))


def test_scale_contract_accepts_portable_boundaries() -> None:
    assert scale_class_contract(files=0, source_bytes=0)["observed"] == {
        "files": 0,
        "source_bytes": 0,
    }
    assert (
        scale_class_contract(
            files=MAX_PORTABLE_INTEGER, source_bytes=MAX_PORTABLE_INTEGER
        )["class"]
        == "large"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("codemap_generation", True),
        ("codemap_generation", -1),
        ("codemap_generation", 1.5),
        ("codemap_generation", 1 << 53),
        ("identity_generation", False),
        ("identity_generation", -1),
        ("identity_generation", 1.5),
        ("identity_generation", 1 << 53),
        ("seed", True),
        ("seed", -1),
        ("seed", 1.5),
        ("seed", float("nan")),
        ("seed", float("inf")),
        ("seed", 1 << 53),
    ],
)
def test_experiment_environment_rejects_nonportable_numeric_identity(
    field: Literal["codemap_generation", "identity_generation", "seed"], value: object
) -> None:
    state = ExperimentRepositoryState("repo", 1, 1)
    seed: int | None = 1
    # Cross the static type boundary deliberately to exercise runtime rejection.
    if field == "seed":
        seed = cast(int, value)
    elif field == "codemap_generation":
        state = replace(state, codemap_generation=cast(int, value))
    else:
        state = replace(state, identity_generation=cast(int, value))
    with pytest.raises((TypeError, ValueError)):
        experiment_environment(
            hashmarks_version="0.13.0",
            repository_state=state,
            seed=seed,
        )


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None, [], {}])
def test_capabilities_reject_boolean_coercion(value: object) -> None:
    with pytest.raises(ValueError):
        normalize_capabilities({"semantic_nomination": cast(bool, value)})


def test_experiment_environment_accepts_portable_boundaries_and_is_deterministic() -> (
    None
):
    state = ExperimentRepositoryState(
        repository_identity="repo",
        codemap_generation=0,
        identity_generation=None,
    )
    first = experiment_environment(
        hashmarks_version="0.13.0",
        repository_state=state,
        seed=MAX_PORTABLE_INTEGER,
        capabilities={"semantic_nomination": False},
    )
    second = experiment_environment(
        hashmarks_version="0.13.0",
        repository_state=state,
        seed=MAX_PORTABLE_INTEGER,
        capabilities={"semantic_nomination": False},
    )
    assert first == second
    assert first["capabilities"]["values"]["semantic_nomination"] is False
