"""Diagnostic admission is bounded and non-strengthening through every consumer."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

import pytest
from contract_assertions import assert_object

from hashmarks import CodeMap, validate_repository_intelligence_evidence
from hashmarks.codemap.diagnostic_observation import DIAGNOSTIC_ENDPOINT_MAX_BYTES
from hashmarks.codemap.repository_delta import RepositoryGenerationBinding
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path


def _observe(rows: object = None) -> dict[str, object]:
    return CodeMap.external_diagnostic_observation(
        producer="example-test",
        binding=RepositoryGenerationBinding("repo:fixture", 1),
        diagnostics=[{"path": "src.py", "line": 1, "message": "claim"}]
        if rows is None
        else cast("Sequence[Mapping[str, object]]", rows),
        outcome="fail",
        scope_paths=["src.py"],
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("producer", ""),
        ("repository_identity", ""),
        ("codemap_generation", True),
        ("codemap_generation", -1),
        ("environment_identity", []),
        ("outcome", []),
        ("authority", "execution"),
        ("execution_effect", "run"),
        ("collection", {"state": "fresh-complete", "authority": "authenticated"}),
        ("diagnostic_count", True),
        ("scope_paths", [f"{n}.py" for n in range(33)]),
        ("diagnostics", ({"path": "src.py"},)),
    ],
)
def test_header_mutations_fail_core_projection_and_public_validation(
    field: str,
    value: object,
) -> None:
    original = _observe()
    malformed = {**original, field: value}
    with pytest.raises(ValueError):
        CodeMap.diagnostic_observation_delta(original, malformed)
    with pytest.raises(ValueError):
        CodeMap.diagnostic_source_revision_evidence(malformed, [])
    assert validate_repository_intelligence_evidence(malformed)["valid"] is False


@pytest.mark.parametrize(
    "rows",
    [
        "not-a-list",
        [None],
        [{"line": True}],
        [{"column": 0}],
        [{"message": "x" * 8193}],
        [{"path": []}],
        [{"metadata": float("nan")}],
        [{"metadata": float("inf")}],
        [{"metadata": {1: "number", "1": "string"}}],
        [{"metadata": {False: "boolean-key"}}],
        [{"message": str(n)} for n in range(257)],
        [{"metadata": "x" * DIAGNOSTIC_ENDPOINT_MAX_BYTES}],
    ],
)
def test_constructor_rejects_malformed_or_oversized_rows(rows: object) -> None:
    with pytest.raises(ValueError):
        _observe(rows)


def test_exact_duplicates_preserve_occurrences_and_conflicting_metadata_rejects() -> (
    None
):
    row = {"path": "src.py", "line": 1, "message": "claim"}
    packet = _observe([row, row])
    delta = CodeMap.diagnostic_observation_delta(packet, packet)
    facts = assert_object(delta["diagnostics"])
    assert packet["diagnostic_count"] == 2
    assert facts["before_count"] == facts["unchanged_count"] == 1
    counts = {"before": 2, "after": 2, "authority": "producer-claimed"}
    assert facts["occurrence_counts"] == counts
    checked = validate_repository_intelligence_evidence(delta)
    assert checked["valid"] is True
    assert (
        assert_object(checked["normalized"])["diagnostic_occurrence_counts"] == counts
    )
    with pytest.raises(ValueError, match="conflicting diagnostic"):
        _observe([row, {**row, "metadata": {"different": True}}])


def test_input_rows_are_detached_and_unlocated_claims_are_preserved() -> None:
    row: Any = {"path": "../outside.py", "metadata": {"sample": [1]}}
    packet: Any = _observe([row])
    row["metadata"]["sample"].append(2)
    assert packet["diagnostics"][0]["metadata"] == {"sample": [1]}
    delta: Any = CodeMap.diagnostic_observation_delta(_observe([]), packet)
    assert delta["diagnostics"]["path_locality"]["rows"][0]["locality"] == "unknown"


def test_legacy_delta_without_occurrence_counts_remains_readable() -> None:
    packet = _observe()
    delta: Any = CodeMap.diagnostic_observation_delta(packet, packet)
    del delta["diagnostics"]["occurrence_counts"]
    assert validate_repository_intelligence_evidence(delta)["valid"] is True


@pytest.mark.parametrize("count", [False, -1, 0, 257])
def test_serialized_occurrence_counts_cannot_erase_unique_facts(count: object) -> None:
    packet = _observe()
    delta: Any = CodeMap.diagnostic_observation_delta(packet, packet)
    delta["diagnostics"]["occurrence_counts"]["after"] = count
    assert validate_repository_intelligence_evidence(delta)["valid"] is False


def test_mcp_cannot_bypass_endpoint_authority_or_row_limits(tmp_path: Path) -> None:
    packet: Any = _observe()
    surface = HashmarksMcpSurface(str(tmp_path))
    try:
        for malformed in (
            {**packet, "execution_effect": "run"},
            {
                **packet,
                "diagnostics": packet["diagnostics"] * 257,
                "diagnostic_count": 257,
            },
        ):
            with pytest.raises(McpSurfaceError):
                surface.evidence_comparison(
                    packet, malformed, result_mode="diagnostics"
                )
    finally:
        surface.close()


def test_current_repository_freshness_never_attests_producer_freshness() -> None:
    packet = _observe()
    current = CodeMap.external_observation_freshness(
        packet, current_repository_identity="repo:fixture", current_generation=1
    )
    assert current["state"] == "current"
    assert current["freshness_scope"] == "repository-correspondence-only"
    assert current["producer_freshness"] == "unknown"
    assert validate_repository_intelligence_evidence(current)["valid"] is True
    forged = deepcopy(current)
    forged["producer_freshness"] = "current"
    assert validate_repository_intelligence_evidence(forged)["valid"] is False


def test_changed_producer_metadata_is_preserved_without_fabricating_code_changes() -> (
    None
):
    before = _observe(
        [{"path": "src.py", "message": "claim", "producer_time": "earlier"}]
    )
    after = _observe([{"path": "src.py", "message": "claim", "producer_time": "later"}])
    delta: Any = CodeMap.diagnostic_observation_delta(before, after)
    facts = delta["diagnostics"]
    assert facts["unchanged_count"] == 1
    assert facts["added"] == facts["removed"] == []
    assert delta["source_revisions"]["changed"] is False
    assert facts["changed_claims"][0]["before"]["producer_time"] == "earlier"
    assert facts["changed_claims"][0]["after"]["producer_time"] == "later"
    checked: Any = validate_repository_intelligence_evidence(delta)
    assert checked["valid"] is True
    assert checked["normalized"]["diagnostic_changed_claims"] == facts["changed_claims"]
    for format in ("structured", "compact", "text"):
        projection: Any = present_repository_evidence(delta, format=format)
        observations = [
            row
            for group in projection["groups"]
            for row in group["findings"]
            if row["kind"] == "diagnostic_claim_metadata_changed"
        ]
        assert observations and all(
            row["assertion"] == "producer_claim" for row in observations
        )
    facts["changed_claims"][0]["after"]["message"] = "substituted"
    assert validate_repository_intelligence_evidence(delta)["valid"] is False


@pytest.mark.parametrize("before_value,after_value", [(True, 1), (False, 0), (1, 1.0)])
def test_type_distinct_metadata_is_a_change_and_conflicting_duplicates_reject(
    before_value: object, after_value: object
) -> None:
    row = {"path": "src.py", "line": 1, "message": "claim"}
    old = {**row, "metadata": {"nested": [before_value]}}
    new = {**row, "metadata": {"nested": [after_value]}}
    for rows in ([old, new], [new, old]):
        with pytest.raises(ValueError, match="conflicting diagnostic"):
            _observe(rows)
    delta: Any = CodeMap.diagnostic_observation_delta(_observe([old]), _observe([new]))
    assert len(delta["diagnostics"]["changed_claims"]) == 1
    assert validate_repository_intelligence_evidence(delta)["valid"] is True


def test_json_roundtrip_does_not_invent_a_metadata_change() -> None:
    import json

    before = _observe([{"path": "src.py", "metadata": {"items": (True, 1, 1.0)}}])
    after = json.loads(json.dumps(before))
    delta: Any = CodeMap.diagnostic_observation_delta(before, after)
    assert before == after
    assert delta["diagnostics"]["changed_claims"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("producer", []),
        ("environment_identity", {}),
        ("codemap_generation", True),
        ("outcome", []),
    ],
)
def test_retained_delta_endpoint_headers_use_original_admission(
    field: str, value: object
) -> None:
    packet = _observe()
    delta: Any = CodeMap.diagnostic_observation_delta(packet, packet)
    axis = {
        "producer": "producer_context",
        "environment_identity": "producer_context",
        "codemap_generation": "generation",
        "outcome": "outcome",
    }[field]
    if axis == "producer_context":
        delta[axis]["before"][field] = value
    else:
        delta[axis]["before"] = value
    assert validate_repository_intelligence_evidence(delta)["valid"] is False


def test_serialized_type_conflict_cannot_bypass_constructor_admission() -> None:
    packet: Any = _observe([{"path": "src.py", "metadata": True}])
    packet["diagnostics"].append({**packet["diagnostics"][0], "metadata": 1})
    packet["diagnostic_count"] = 2
    assert validate_repository_intelligence_evidence(packet)["valid"] is False
    with pytest.raises(ValueError, match="conflicting diagnostic"):
        CodeMap.diagnostic_observation_delta(packet, packet)


def test_mcp_retains_type_distinct_metadata_changes_and_rejects_conflicting_rows(
    tmp_path: Path,
) -> None:
    before = _observe([{"path": "src.py", "metadata": {"flag": True}}])
    after = _observe([{"path": "src.py", "metadata": {"flag": 1}}])
    surface = HashmarksMcpSurface(str(tmp_path))
    try:
        actual: Any = surface.evidence_comparison(
            before, after, result_mode="diagnostics"
        )
        assert actual == CodeMap.diagnostic_observation_delta(before, after)
        assert len(actual["diagnostics"]["changed_claims"]) == 1
        malformed: Any = deepcopy(before)
        malformed["diagnostics"].extend(after["diagnostics"])
        malformed["diagnostic_count"] = 2
        with pytest.raises(McpSurfaceError, match="conflicting diagnostic"):
            surface.evidence_comparison(before, malformed, result_mode="diagnostics")
    finally:
        surface.close()
