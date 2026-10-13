"""Required facts must have artifact/source bindings and reproducible witnesses."""

from dataclasses import replace

import pytest

from scripts.repository_evaluation.backend_grading import (
    FactObservation,
    grade_fact_observation,
    validate_transport_capture,
)
from scripts.repository_evaluation.backend_transport import _capture


@pytest.fixture
def observation():
    return FactObservation(
        "facts",
        "problem",
        "before",
        "default",
        "api",
        "none",
        "/cases/problem/before/checks",
        ("before/api.json", b'{"value":1}'),
        ({"repository": "repo", "path": "owner.py", "revision": "revision"},),
    )


def test_witness_binds_check_source_and_artifact(observation):
    rule = {
        "checks": [
            {"id": "value", "pointer": "/value", "predicate": "equals", "value": 1}
        ]
    }
    result = grade_fact_observation({"value": 1}, rule, observation)
    assert result["gate"] is True
    witness = result["witnesses"][0]
    assert witness["state"] == "PASS"
    assert witness["artifact"] == "before/api.json"
    assert witness["oracle_pointer"] == "/cases/problem/before/checks/0"
    assert witness["source_bindings"] == list(observation.source_bindings)
    witness["source_bindings"][0]["path"] = "changed.py"
    assert observation.source_bindings[0]["path"] == "owner.py"


@pytest.mark.parametrize("missing", ["artifact", "source"])
def test_matching_fact_without_required_binding_is_incomplete(observation, missing):
    observation = (
        replace(observation, artifact=None)
        if missing == "artifact"
        else replace(observation, source_bindings=())
    )
    rule = {
        "checks": [
            {"id": "value", "pointer": "/value", "predicate": "equals", "value": 1}
        ]
    }
    assert grade_fact_observation({"value": 1}, rule, observation)["gate"] is None


@pytest.mark.parametrize("predicate,expected", [("equals", False), ("excludes", None)])
def test_missing_supported_positive_fact_fails_without_inventing_absence(
    observation, predicate, expected
):
    rule = {
        "checks": [
            {
                "id": "value",
                "pointer": "/value",
                "predicate": predicate,
                "value": 1,
                "support": "supported",
            }
        ]
    }
    assert grade_fact_observation({}, rule, observation)["gate"] is expected


@pytest.mark.parametrize("mutation", ["tokens", "bytes", "response"])
def test_capture_grade_cannot_disagree_with_actual_wire(mutation):
    capture = {
        "format": "none",
        **_capture({"value": 1}, '{"value":1}', transport="cli"),
    }
    validate_transport_capture(capture)
    if mutation == "tokens":
        capture["estimated_tokens"] = 0
    elif mutation == "bytes":
        capture["utf8_bytes"] = 0
    else:
        capture["response"] = {"value": True}
    with pytest.raises(ValueError, match="differs from visible bytes"):
        validate_transport_capture(capture)
