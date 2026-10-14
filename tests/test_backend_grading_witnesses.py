"""Required facts must have artifact/source bindings and reproducible witnesses."""

from dataclasses import replace
from typing import Any, cast

import pytest

from scripts.repository_evaluation.backend_grading import (
    FactObservation,
    grade_fact_observation,
    validate_transport_capture,
)
from scripts.repository_evaluation.backend_transport import _capture


@pytest.fixture
def observation() -> FactObservation:
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


def test_witness_binds_check_source_and_artifact(observation: FactObservation) -> None:
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
def test_matching_fact_without_required_binding_is_incomplete(
    observation: FactObservation, missing: str
) -> None:
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
    observation: FactObservation, predicate: str, expected: bool | None
) -> None:
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
def test_capture_grade_cannot_disagree_with_actual_wire(mutation: str) -> None:
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


@pytest.mark.parametrize(
    "field,value",
    [
        ("stage", "unknown"),
        ("surface", "summary"),
        ("format", "html"),
        ("oracle_pointer", "not-a-pointer"),
        ("artifact", ("../escape.json", b"{}")),
        (
            "source_bindings",
            ({"repository": "repo", "path": "../escape.py", "revision": "r"},),
        ),
    ],
)
def test_witness_context_and_references_fail_closed(
    observation: FactObservation, field: str, value: object
) -> None:
    with pytest.raises(ValueError, match="witness"):
        replace(observation, **{field: value})


def test_owner_binding_cannot_qualify_a_missing_test_source(
    observation: FactObservation,
) -> None:
    rule = {
        "checks": [
            {
                "id": "test",
                "pointer": "/value",
                "predicate": "equals",
                "value": 1,
                "source_paths": ["test_owner.py"],
            }
        ]
    }
    result = grade_fact_observation({"value": 1}, rule, observation)
    assert result["gate"] is None
    assert result["witnesses"][0]["source_bindings"] == []


def test_comparison_bindings_distinguish_revision_roles_and_reject_duplicates(
    observation: FactObservation,
) -> None:
    before = {
        "repository": "repo",
        "path": "owner.py",
        "revision": "old",
        "stage": "before",
    }
    after = {**before, "revision": "new", "stage": "after"}
    comparison = replace(observation, stage="delta", source_bindings=(before, after))
    assert comparison.source_bindings == (before, after)
    with pytest.raises(ValueError, match="duplicate source"):
        replace(observation, source_bindings=(before, before))
    with pytest.raises(ValueError, match="invalid revision stage"):
        replace(observation, source_bindings=({**before, "stage": "unknown"},))


def _qualified_check(selectors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "checks": [
            {
                "id": "endpoint",
                "pointer": "/value",
                "predicate": "equals",
                "value": 1,
                "source_bindings": selectors,
            }
        ]
    }


def test_same_relative_path_in_another_repository_cannot_bind_a_fact(
    observation: FactObservation,
) -> None:
    rule = _qualified_check([{"repository": "peer", "path": "owner.py"}])
    result = grade_fact_observation({"value": 1}, rule, observation)
    assert result["gate"] is None
    assert result["witnesses"][0]["reason"] == "missing-source-binding"
    assert result["witnesses"][0]["source_bindings"] == []


def test_qualified_fact_retains_only_its_repository_endpoint(
    observation: FactObservation,
) -> None:
    peer = {"repository": "peer", "path": "owner.py", "revision": "peer-revision"}
    observation = replace(
        observation, source_bindings=(*observation.source_bindings, peer)
    )
    rule = _qualified_check([{"repository": "peer", "path": "owner.py"}])
    result = grade_fact_observation({"value": 1}, rule, observation)
    assert result["gate"] is True
    assert result["witnesses"][0]["source_bindings"] == [peer]
    rule["checks"][0].pop("source_bindings")
    rule["checks"][0]["source_paths"] = ["owner.py"]
    with pytest.raises(ValueError, match="ambiguous source path"):
        grade_fact_observation({"value": 1}, rule, observation)


def test_qualified_comparison_cannot_substitute_the_other_revision(
    observation: FactObservation,
) -> None:
    binding = {**observation.source_bindings[0], "stage": "before"}
    observation = replace(observation, stage="delta", source_bindings=(binding,))
    rule = _qualified_check(
        [{"repository": "repo", "path": "owner.py", "stage": "after"}]
    )
    assert grade_fact_observation({"value": 1}, rule, observation)["gate"] is None


@pytest.mark.parametrize(
    "selectors",
    [
        [],
        [{"path": "owner.py"}],
        [{"repository": "repo", "path": "../owner.py"}],
        [{"repository": "repo", "path": "owner.py", "stage": None}],
        [{"repository": "repo", "path": "owner.py"}] * 2,
    ],
)
def test_malformed_qualified_selectors_fail_closed(
    observation: FactObservation, selectors: list[Any]
) -> None:
    with pytest.raises(ValueError):
        grade_fact_observation({"value": 1}, _qualified_check(selectors), observation)


def test_known_fact_failure_survives_missing_qualified_binding(
    observation: FactObservation,
) -> None:
    rule = _qualified_check([{"repository": "peer", "path": "owner.py"}])
    result = grade_fact_observation({"value": 2}, rule, observation)
    assert result["gate"] is False


def test_path_and_qualified_selectors_cannot_be_combined(
    observation: FactObservation,
) -> None:
    rule = _qualified_check([{"repository": "repo", "path": "owner.py"}])
    rule["checks"][0]["source_paths"] = ["owner.py"]
    with pytest.raises(ValueError, match="cannot mix"):
        grade_fact_observation({"value": 1}, rule, observation)
