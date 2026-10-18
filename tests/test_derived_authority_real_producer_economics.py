from __future__ import annotations

from pathlib import Path

import pytest
from contract_assertions import assert_integer, assert_object

from benchmarks.derived_authority_economics import (
    measure_real_producer_economics,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "dependency_dogfood"


def test_real_producer_economics_covers_existing_uv_and_maven_dogfood() -> None:
    receipt = measure_real_producer_economics(_FIXTURES, iterations=1)

    assert (
        receipt["schema"]
        == "hashmarks.derived-authority-real-producer-economics-diagnostic.v1"
    )
    producers = assert_object(receipt["producers"])
    assert set(producers) == {"uv", "maven"}
    assert set(assert_object(assert_object(producers["uv"])["transitions"])) == {
        "absent-to-v1",
        "v1-to-v2",
        "v2-to-absent",
        "absent-to-grouped",
        "grouped-to-absent",
    }
    assert set(assert_object(assert_object(producers["maven"])["transitions"])) == {
        "absent-to-v1",
        "v1-to-v2",
        "v2-to-absent",
    }

    expected_semantics = {
        "uv": "hashmarks.uv-dependency-adapter.v1",
        "maven": "hashmarks.maven-dependency-adapter.v1",
    }
    for producer, value in producers.items():
        producer_receipt = assert_object(value)
        for value in assert_object(producer_receipt["states"]).values():
            state = assert_object(value)
            assert state["adapter_semantics"] == expected_semantics[producer]
            assert assert_integer(state["artifact_bytes"]) > 0
            assert assert_integer(state["snapshot_bytes"]) > 0
            assert assert_integer(state["adapter_peak_tracemalloc_bytes"]) > 0
            assert assert_integer(assert_object(state["adapter_latency"])["min_ns"]) > 0

        for value in assert_object(producer_receipt["transitions"]).values():
            transition = assert_object(value)
            assert transition["comparability"] == "comparable"
            assert (
                assert_object(transition["change_axes"])["semantic_definition"]
                == "unchanged"
            )
            assert (
                assert_object(transition["change_axes"])["semantic_resolution"]
                == "changed"
            )
            assert transition["repository_reobservation_calls"] == 0
            assert transition["persistent_state_growth_bytes"] == 0
            assert (
                assert_integer(
                    assert_object(transition["serialized_size"])[
                        "caller_endpoint_pair_bytes"
                    ]
                )
                > 0
            )
            assert (
                assert_integer(
                    assert_object(transition["serialized_size"])["delta_bytes"]
                )
                > 0
            )
            assert (
                assert_integer(
                    assert_object(transition["serialized_size"])[
                        "after_explanation_bytes"
                    ]
                )
                > 0
            )
            for value in assert_object(transition["operations"]).values():
                operation = assert_object(value)
                assert operation["repository_reobservation_calls"] == 0
                assert assert_integer(assert_object(operation["latency"])["min_ns"]) > 0

    assert receipt["retention"] == {
        "server_history_required_for_correctness": False,
        "adapter_parse_owner": "producer-caller-edge",
        "explicit_packet_owner": "caller-working-set",
        "decision": "measure-real-latency-without-adding-server-history",
    }


@pytest.mark.parametrize("iterations", [0, -1])
def test_real_producer_economics_rejects_invalid_iterations(iterations: int) -> None:
    with pytest.raises(ValueError, match="iterations must be positive"):
        measure_real_producer_economics(_FIXTURES, iterations=iterations)


def test_real_producer_economics_requires_fixture_directory(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="fixture_root is not a directory"):
        measure_real_producer_economics(missing, iterations=1)
