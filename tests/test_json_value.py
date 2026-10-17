"""Type-preserving immutable values at the repository evidence boundary."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from hashmarks.json_value import CanonicalJsonValue


@pytest.mark.parametrize(
    "left,right", [(True, 1), (False, 0), (1, 1.0), (None, "null")]
)
def test_scalar_types_and_nested_values_have_distinct_identity(
    left: object, right: object
) -> None:
    assert CanonicalJsonValue(left) != CanonicalJsonValue(right)
    assert CanonicalJsonValue({"nested": [left]}) != CanonicalJsonValue(
        {"nested": [right]}
    )
    assert len({CanonicalJsonValue(left), CanonicalJsonValue(right)}) == 2


def test_json_roundtrip_order_and_tuple_normalization_are_semantic_noops() -> None:
    raw = {"b": (1, True, 1.0), "a": {"x": None}}
    value = CanonicalJsonValue(raw)
    assert value == CanonicalJsonValue(json.loads(json.dumps(raw)))
    assert value == CanonicalJsonValue({"a": {"x": None}, "b": [1, True, 1.0]})
    assert value != CanonicalJsonValue({"b": [True, 1, 1.0], "a": {"x": None}})


def test_inputs_outputs_and_frozen_storage_cannot_mutate_value_identity() -> None:
    raw = {"items": [1]}
    value = CanonicalJsonValue(raw)
    raw["items"].append(2)
    decoded = value.to_value()
    assert isinstance(decoded, dict)
    decoded["items"].append(3)
    assert value.to_value() == {"items": [1]}
    mutable: Any = value
    with pytest.raises(FrozenInstanceError):
        mutable._encoded = b"false"


@pytest.mark.parametrize(
    "value",
    [
        {1: "number"},
        {1: "number", "1": "string"},
        {"bad": {False: 0}},
        b"bytes",
        {1, 2},
        object(),
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_nonportable_values_fail_at_construction(value: object) -> None:
    with pytest.raises(ValueError, match="JSON-compatible"):
        CanonicalJsonValue(value)


def test_cycles_are_rejected_but_repeated_subvalues_are_allowed() -> None:
    cycle: list[object] = []
    cycle.append(cycle)
    with pytest.raises(ValueError, match="JSON-compatible"):
        CanonicalJsonValue(cycle)
    shared = [1]
    assert CanonicalJsonValue([shared, shared]).to_value() == [[1], [1]]
