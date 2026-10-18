from __future__ import annotations

from pathlib import Path

import pytest
from contract_assertions import assert_integer, assert_number, assert_object

from benchmarks import derived_authority_economics as derived
from benchmarks.derived_authority_economics import (
    measure_derived_authority_economics,
)
from hashmarks.codemap import CodeMap


def test_derived_authority_economics_proves_explicit_packet_reuse() -> None:
    receipt = measure_derived_authority_economics(iterations=2, scale=4)

    assert receipt["schema"] == "hashmarks.derived-authority-economics-diagnostic.v1"
    assert receipt["fixture"] == {
        "dependency_components": 4,
        "declarations": 4,
        "iterations": 2,
    }
    assert receipt["repository_reobservation_calls"] == 0
    assert assert_object(receipt["persistent_state_bytes"])["growth"] == 0
    assert assert_object(receipt["retention"])["required_for_correctness"] is False
    assert assert_object(receipt["retention"])["measured_server_history_bytes"] == 0

    dependency = assert_object(assert_object(receipt["serialized_size"])["dependency"])
    declarations = assert_object(
        assert_object(receipt["serialized_size"])["declarations"]
    )
    assert assert_integer(dependency["before_observation_bytes"]) > 0
    assert assert_integer(dependency["after_observation_bytes"]) > 0
    assert assert_integer(dependency["caller_endpoint_pair_bytes"]) > assert_integer(
        dependency["delta_bytes"]
    )
    assert assert_integer(dependency["delta_saved_vs_pair_bytes"]) > 0
    assert assert_integer(dependency["explanation_bytes"]) > 0
    assert assert_integer(declarations["observation_bytes"]) > 0
    assert assert_integer(declarations["explanation_bytes"]) > 0

    for value in assert_object(receipt["operations"]).values():
        operation = assert_object(value)
        assert operation["repository_reobservation_calls"] == 0
        assert assert_integer(operation["peak_tracemalloc_bytes"]) > 0
        latency = assert_object(operation["latency"])
        assert (
            0 <= assert_number(latency["min_ns"]) <= assert_number(latency["median_ns"])
        )
        assert (
            assert_number(latency["median_ns"])
            <= assert_number(latency["p95_ns"])
            <= assert_number(latency["max_ns"])
        )


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


def test_explicit_packet_measurement_detects_reobservation_at_source_owner(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("def owner(): return 1\n", encoding="utf-8")
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as repo:
        repo.index.sync()
        expected = repo.source.member("owner.py")
        with pytest.raises(
            RuntimeError, match="unexpectedly re-observed repository members"
        ):
            derived._explicit_operation_metrics(
                repo,
                lambda: repo.source.member("owner.py"),
                expected=expected,
                iterations=1,
            )
