"""Native fact qualification binds every retained target and source context."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.repository_evaluation.backend_native_witnesses import (
    native_fact_witnesses,
    native_witness_gate,
)
from scripts.repository_evaluation.backend_transport import _capture
from scripts.repository_evaluation.common import write_json


@pytest.fixture
def native_observations(
    tmp_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path], Path]:
    output = tmp_path / "observations"
    sources = {}
    workflow = {"id": "handler", "repository": "repo", "before": "old", "after": "new"}
    rule = {"source_labels": {}, "native_oracles": {}}
    for stage, name, value in (("before", "old", 1), ("after", "new", 2)):
        source = tmp_path / name
        source.mkdir()
        (source / "backend.py").write_text(f"def handler():\n    return {value}\n")
        sources[name] = source
        rule["source_labels"][stage] = [{"path": "backend.py", "symbol": "handler"}]
        packet = {
            "target": "backend.py::handler",
            "negative_evidence_admissible": False,
        }
        write_json(output / stage / "api.json", packet)
        write_json(
            output / stage / "cli.json",
            [
                {
                    "format": "none",
                    **_capture(packet, json.dumps(packet), transport="cli"),
                }
            ],
        )
        write_json(output / stage / "mcp.json", [])
        write_json(
            output / stage / "definition-token.json", {"unique_definition_token": True}
        )
        rule["native_oracles"][stage] = {
            "backend.py::handler": {
                "checks": [
                    {
                        "id": "exact-target",
                        "pointer": "/target",
                        "predicate": "equals",
                        "value": "backend.py::handler",
                        "source_paths": ["backend.py"],
                    }
                ],
                "definition_checks": [
                    {
                        "id": "definition-token",
                        "pointer": "/unique_definition_token",
                        "predicate": "equals",
                        "value": True,
                        "source_paths": ["backend.py"],
                    }
                ],
            }
        }
    return workflow, rule, sources, output


def test_native_facts_retain_source_stage_target_and_actual_artifact(
    native_observations: tuple[dict[str, Any], dict[str, Any], dict[str, Path], Path],
) -> None:
    witnesses = native_fact_witnesses(*native_observations)
    assert native_witness_gate(witnesses) is True
    assert {(w["stage"], w["surface"], w["gate"]) for w in witnesses} == {
        (stage, surface, gate)
        for stage in ("before", "after")
        for surface, gate in (
            ("api", "native_binding"),
            ("cli", "native_binding"),
            ("api", "native_definition"),
        )
    }
    assert {w["unit_id"] for w in witnesses} == {"handler::backend.py::handler"}
    assert all(w["artifact_scope"] == "native" for w in witnesses)
    before, after = (
        next(w for w in witnesses if w["stage"] == stage)
        for stage in ("before", "after")
    )
    assert (
        before["source_bindings"][0]["revision"]
        != after["source_bindings"][0]["revision"]
    )
    assert (
        before["oracle_pointer"]
        == "/cases/handler/native_oracles/before/backend.py::handler/checks/0"
    )


def test_wrong_native_endpoint_cannot_hide_behind_other_passing_targets(
    native_observations: tuple[dict[str, Any], dict[str, Any], dict[str, Path], Path],
) -> None:
    workflow, rule, sources, output = native_observations
    write_json(output / "after/api.json", {"target": "other.py::handler"})
    witnesses = native_fact_witnesses(workflow, rule, sources, output)
    assert native_witness_gate(witnesses) is False
    assert any(w["state"] == "PASS" for w in witnesses)
    assert any(w["state"] == "FAIL" and w["stage"] == "after" for w in witnesses)


def test_missing_native_artifact_cannot_preserve_a_fact_pass(
    native_observations: tuple[dict[str, Any], dict[str, Any], dict[str, Path], Path],
) -> None:
    native_observations[3].joinpath("after/api.json").unlink()
    with pytest.raises(ValueError, match="not a repository file"):
        native_fact_witnesses(*native_observations)
    assert native_witness_gate([]) is None


def test_definition_boolean_cannot_be_replaced_with_an_integer(
    native_observations: tuple[dict[str, Any], dict[str, Any], dict[str, Path], Path],
) -> None:
    write_json(
        native_observations[3] / "after/definition-token.json",
        {"unique_definition_token": 1},
    )
    assert native_witness_gate(native_fact_witnesses(*native_observations)) is False
