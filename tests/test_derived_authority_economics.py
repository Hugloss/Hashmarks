from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from benchmarks import derived_authority_economics as derived
from benchmarks.derived_authority_economics import (
    measure_derived_authority_economics,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_derived_authority_economics_proves_explicit_packet_reuse() -> None:
    receipt = measure_derived_authority_economics(iterations=2, scale=4)

    assert receipt["schema"] == "hashmarks.derived-authority-economics-diagnostic.v1"
    assert receipt["fixture"] == {
        "dependency_components": 4,
        "declarations": 4,
        "iterations": 2,
    }
    assert receipt["repository_reobservation_calls"] == 0
    assert receipt["persistent_state_bytes"]["growth"] == 0
    assert receipt["retention"]["required_for_correctness"] is False
    assert receipt["retention"]["measured_server_history_bytes"] == 0

    dependency = receipt["serialized_size"]["dependency"]
    declarations = receipt["serialized_size"]["declarations"]
    assert dependency["before_observation_bytes"] > 0
    assert dependency["after_observation_bytes"] > 0
    assert dependency["caller_endpoint_pair_bytes"] > dependency["delta_bytes"]
    assert dependency["delta_saved_vs_pair_bytes"] > 0
    assert dependency["explanation_bytes"] > 0
    assert declarations["observation_bytes"] > 0
    assert declarations["explanation_bytes"] > 0

    for operation in receipt["operations"].values():
        assert operation["repository_reobservation_calls"] == 0
        assert operation["peak_tracemalloc_bytes"] > 0
        latency = operation["latency"]
        assert 0 <= latency["min_ns"] <= latency["median_ns"]
        assert latency["median_ns"] <= latency["p95_ns"] <= latency["max_ns"]


@pytest.mark.parametrize(
    ("iterations", "scale", "message"),
    [
        (0, 4, "iterations must be positive"),
        (1, 1, "scale must be between 2 and 128"),
        (1, 129, "scale must be between 2 and 128"),
    ],
)
def test_derived_authority_economics_rejects_invalid_bounds(
    iterations: int,
    scale: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        measure_derived_authority_economics(
            iterations=iterations,
            scale=scale,
        )


def test_derived_authority_parser_owns_normal_profile_defaults() -> None:
    args = derived._parser().parse_args([])

    assert args.iterations == 100
    assert args.scale == 64
    assert args.real_iterations == 25
    assert args.fixture_root == Path("tests/fixtures/dependency_dogfood")
    assert args.output is None
