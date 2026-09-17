from copy import deepcopy

import pytest

from hashmarks.codemap.decision_contract import DecisionPacketContract
from hashmarks.generation_domain import MAX_PORTABLE_GENERATION


def packet():
    return {
        "schema": "hashmarks.task-decision-packet.v2",
        "task": "fix owner",
        "edit": {"path": "src/a.py"},
        "verify": {"path": "tests/test_a.py"},
        "discrimination": {"needed": True, "reason": "competing", "ambiguity": {"ambiguous": True}},
        "identity": {"codemap_complete": True, "stale": False},
        "canonical_generation": 1,
    }


@pytest.mark.parametrize("value", [True, False, -1, MAX_PORTABLE_GENERATION + 1])
def test_decision_generation_rejects_invalid_portable_domain(value):
    value_packet = packet()
    value_packet["canonical_generation"] = value
    with pytest.raises(ValueError):
        DecisionPacketContract.parse(value_packet)


@pytest.mark.parametrize("value", ["false", 1, 0, None])
def test_decision_ambiguity_rejects_non_boolean(value):
    value_packet = packet()
    value_packet["discrimination"]["ambiguity"]["ambiguous"] = value
    with pytest.raises(ValueError):
        DecisionPacketContract.parse(value_packet)


@pytest.mark.parametrize("field", ["edit", "verify"])
@pytest.mark.parametrize("path", ["", "   "])
def test_decision_selection_rejects_blank_path(field, path):
    value_packet = packet()
    value_packet[field] = {"path": path}
    with pytest.raises(ValueError):
        DecisionPacketContract.parse(value_packet)


def test_decision_generation_accepts_zero_and_portable_maximum():
    for value in (0, MAX_PORTABLE_GENERATION):
        value_packet = packet()
        value_packet["canonical_generation"] = value
        assert DecisionPacketContract.parse(value_packet).canonical_generation == value
