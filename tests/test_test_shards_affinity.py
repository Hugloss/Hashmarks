from __future__ import annotations

from pathlib import Path

from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.test_shards import (
    ENVELOPE_SCHEMA,
    ISOLATED_NODEIDS,
    _balanced_shard_buckets,
    _packet_identity,
    node_membership_identity,
    plan,
    selection_membership_identity,
    validate_test_shard_plan,
    validate_work_selection_envelope,
    work_selection_envelope,
)


def test_ordinary_file_groups_preserve_membership_and_exact_byte_weights() -> None:
    nodes = [
        ("tests/test_a.py::test_alpha", 10),
        ("tests/test_a.py::test_beta", 20),
        ("tests/test_b.py::test_alpha", 12),
        ("tests/test_b.py::test_beta", 18),
        ("tests/test_c.py::test_alpha", 5),
        ("tests/test_c.py::test_beta", 5),
    ]
    buckets, weights, isolated_count = _balanced_shard_buckets(nodes, 2)
    by_node = dict(nodes)

    assert isolated_count == 0
    assert all(buckets)
    assert sorted(nodeid for bucket in buckets for nodeid in bucket) == sorted(by_node)
    assert weights == [sum(by_node[nodeid] for nodeid in bucket) for bucket in buckets]
    for path in ("tests/test_a.py", "tests/test_b.py", "tests/test_c.py"):
        owners = {
            index
            for index, bucket in enumerate(buckets)
            for nodeid in bucket
            if nodeid.split("::", 1)[0] == path
        }
        assert len(owners) == 1


def test_too_few_ordinary_files_preserve_node_balancing_and_nonempty_shards() -> None:
    nodes = [
        ("tests/test_a.py::test_alpha", 9),
        ("tests/test_a.py::test_beta", 7),
        ("tests/test_a.py::test_gamma", 5),
        ("tests/test_a.py::test_delta", 3),
    ]

    buckets, weights, isolated_count = _balanced_shard_buckets(nodes, 3)

    assert isolated_count == 0
    assert buckets == [
        ["tests/test_a.py::test_alpha"],
        ["tests/test_a.py::test_beta"],
        ["tests/test_a.py::test_gamma", "tests/test_a.py::test_delta"],
    ]
    assert weights == [9, 7, 8]


def test_file_groups_keep_all_isolated_nodes_in_declared_singleton_order() -> None:
    path = ISOLATED_NODEIDS[0].split("::", 1)[0]
    ordinary = [(f"{path}::test_ordinary_a", 6), (f"{path}::test_ordinary_b", 5)]
    nodes = [
        *ordinary,
        ("tests/test_other.py::test_ordinary", 4),
        *(
            (nodeid, index + 1)
            for index, nodeid in enumerate(reversed(ISOLATED_NODEIDS))
        ),
    ]

    buckets, weights, isolated_count = _balanced_shard_buckets(
        nodes, len(ISOLATED_NODEIDS) + 2
    )

    assert isolated_count == len(ISOLATED_NODEIDS)
    assert buckets[:isolated_count] == [[nodeid] for nodeid in ISOLATED_NODEIDS]
    assert buckets[isolated_count:] == [
        [nodeid for nodeid, _weight in ordinary],
        ["tests/test_other.py::test_ordinary"],
    ]
    by_node = dict(nodes)
    assert weights == [sum(by_node[nodeid] for nodeid in bucket) for bucket in buckets]
    assert sum(map(len, buckets)) == len(nodes)


def test_file_group_assignment_is_deterministic_for_reordered_input_and_ties() -> None:
    nodes = [
        ("tests/test_a.py::test_alpha", 4),
        ("tests/test_a.py::test_beta", 6),
        ("tests/test_b.py::test_alpha", 5),
        ("tests/test_b.py::test_beta", 5),
        ("tests/test_c.py::test_one", 10),
        ("tests/test_d.py::test_one", 1),
    ]
    expected = (
        [
            ["tests/test_a.py::test_alpha", "tests/test_a.py::test_beta"],
            ["tests/test_b.py::test_alpha", "tests/test_b.py::test_beta"],
            ["tests/test_c.py::test_one", "tests/test_d.py::test_one"],
        ],
        [10, 10, 11],
        0,
    )

    assert _balanced_shard_buckets(nodes, 3) == expected
    assert _balanced_shard_buckets(list(reversed(nodes)), 3) == expected
    assert _balanced_shard_buckets(nodes[::2] + nodes[1::2], 3) == expected


def test_generated_file_local_plan_validates_and_preserves_flat_membership(
    tmp_path: Path,
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    expected: list[str] = []
    for name in ("a", "b", "c"):
        (tests / f"test_{name}.py").write_text(
            "def test_alpha(): pass\ndef test_beta(): pass\n", encoding="utf-8"
        )
        expected.extend(
            f"tests/test_{name}.py::{symbol}" for symbol in ("test_alpha", "test_beta")
        )

    payload = plan(tmp_path, 2)
    rows = assert_records(payload["shards"])

    assert validate_test_shard_plan(payload)["valid"] is True
    assert selection_membership_identity(payload) == node_membership_identity(expected)
    assert payload["test_node_count"] == len(expected)
    for name in ("a", "b", "c"):
        members = {
            f"tests/test_{name}.py::test_alpha",
            f"tests/test_{name}.py::test_beta",
        }
        assert sum(members <= set(assert_array(row["nodeids"])) for row in rows) == 1


def test_previous_algorithm_is_rejected_even_with_valid_envelope_identity(
    tmp_path: Path,
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_a.py").write_text("def test_alpha(): pass\n", encoding="utf-8")
    envelope = work_selection_envelope(tmp_path, 1)
    assert_object(envelope["producer"])["algorithm"] = (
        "hashmarks.pytest-test-node-shards.v4"
    )
    body = {key: value for key, value in envelope.items() if key != "envelope_identity"}
    envelope["envelope_identity"] = _packet_identity(ENVELOPE_SCHEMA, body)

    checked = validate_work_selection_envelope(envelope)

    assert checked["valid"] is False
    assert "unsupported-producer-algorithm" in checked["reasons"]
    assert "envelope-identity-mismatch" not in checked["reasons"]
