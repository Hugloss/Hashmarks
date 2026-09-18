from __future__ import annotations

import json
import sys

import pytest

from hashmarks import test_shards


@pytest.fixture
def shard_cli_plan(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    payload = {
        "schema": test_shards.SCHEMA,
        "plan_identity": "sha256:plan",
        "shards": [
            {"index": 0, "nodeids": ["tests/test_a.py::test_a"], "weight_bytes": 10},
            {"index": 1, "nodeids": ["tests/test_b.py::test_b"], "weight_bytes": 20},
        ],
    }
    monkeypatch.setattr(test_shards, "plan", lambda root, count: payload)
    monkeypatch.setattr(
        test_shards,
        "work_selection_envelope",
        lambda root, count, **kwargs: {
            "schema": test_shards.ENVELOPE_SCHEMA,
            "plan": payload,
        },
    )
    return payload


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (
            [],
            "0: 1 tests / 10 source-weight bytes\n1: 1 tests / 20 source-weight bytes\n",
        ),
        (["--shard", "1"], "tests/test_b.py::test_b\n"),
    ],
)
def test_test_shards_cli_plain_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    shard_cli_plan: dict[str, object],
    args: list[str],
    expected: str,
) -> None:
    monkeypatch.setattr(sys, "argv", ["test-shards", "--shards", "2", *args])
    assert test_shards.main() == 0
    assert capsys.readouterr().out == expected


@pytest.mark.parametrize(
    "args",
    [["--json"], ["--shard", "1", "--json"], ["--envelope", "--json"], ["--envelope"]],
)
def test_test_shards_cli_json_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    shard_cli_plan: dict[str, object],
    args: list[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["test-shards", "--shards", "2", *args])
    assert test_shards.main() == 0
    output = json.loads(capsys.readouterr().out)
    if "--envelope" in args:
        assert output["schema"] == test_shards.ENVELOPE_SCHEMA
        assert output["plan"] == shard_cli_plan
    elif "--shard" in args:
        assert output["nodeids"] == ["tests/test_b.py::test_b"]
        assert output["plan_identity"] == "sha256:plan"
    else:
        assert output == shard_cli_plan


def test_test_shards_cli_rejects_invalid_selection(
    monkeypatch: pytest.MonkeyPatch,
    shard_cli_plan: dict[str, object],
) -> None:
    monkeypatch.setattr(sys, "argv", ["test-shards", "--shards", "2", "--shard", "2"])
    with pytest.raises(SystemExit, match="shard_index must be between 0 and 1"):
        test_shards.main()
    monkeypatch.setattr(sys, "argv", ["test-shards", "--shard", "0", "--envelope"])
    with pytest.raises(SystemExit, match="--envelope cannot be combined with --shard"):
        test_shards.main()
