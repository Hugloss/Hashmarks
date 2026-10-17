"""JSON CLI adapters preserve canonical repository observations."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records, assert_text

from hashmarks.adapters import uv_lock_dependency_observation
from hashmarks.codemap import CodeMap
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation
from hashmarks.operation_contract import operation_schema
from scripts.repository_evaluation.backend_grading import validate_transport_capture
from scripts.repository_evaluation.backend_transport import capture_cli, capture_mcp
from scripts.repository_evaluation.operations import observe_case


@pytest.fixture
def observation_inputs(
    tmp_path: Path,
) -> tuple[Path, Path, list[dict[str, object]], list[dict[str, object]]]:
    root, state = tmp_path / "repo", tmp_path / "state"
    root.mkdir()
    (root / "backend.py").write_text("def handler():\n    return 1\n")
    (root / "alternative.py").write_text("def handler():\n    return 2\n")
    fixture = Path(__file__).parent / "fixtures/dependency_dogfood/uv/v1/uv.lock"
    cases: list[dict[str, object]] = [
        {
            "operation": "dependency_codemap",
            "inputs": {
                "snapshot": uv_lock_dependency_observation(lock=fixture.read_bytes())
            },
        },
        {
            "operation": "repository_intelligence_query",
            "inputs": {
                "surface_name": "cross-repository",
                "task": "Inspect handler changes",
                "changed_paths": ["backend.py"],
            },
        },
        {
            "operation": "correlate_evidence",
            "inputs": {
                "path_mappings": [{"external_prefix": "/app", "repository_prefix": ""}],
                "bundles": [
                    {
                        "bundle_id": "runtime:1",
                        "producer": {"kind": "external-runtime-producer-claim"},
                        "scope": {"kind": "repository-frames"},
                        "completeness": "complete",
                        "truncation": "complete",
                        "anchors": [
                            {
                                "anchor_id": "qualified",
                                "path": "/app/backend.py",
                                "line": 2,
                                "symbol": "handler",
                                "member_revision": hash_file(
                                    root / "backend.py", domain=FILE_DOMAIN
                                ).hash,
                            },
                            {
                                "anchor_id": "stale",
                                "path": "/app/backend.py",
                                "line": 2,
                                "symbol": "handler",
                                "member_revision": "0" * 64,
                            },
                            {"anchor_id": "ambiguous", "symbol": "handler"},
                            {
                                "anchor_id": "conflicting",
                                "path": "/app/backend.py",
                                "line": 2,
                                "symbol": "missing",
                            },
                        ],
                    }
                ],
            },
        },
    ]
    with CodeMap(root, state_dir=state) as codemap:
        codemap.index.sync()
        packets = [observe_case(codemap, case) for case in cases]
        correlation = packets[-1]
        assert correlation["causation"] == "not-inferred"
        assert correlation["storage"] == "request-scoped-not-persisted"
        bundle = assert_object(assert_array(correlation["bundles"])[0])
        anchors = {row["anchor_id"]: row for row in assert_records(bundle["anchors"])}
        assert {
            key: assert_object(row["resolution"])["state"]
            for key, row in anchors.items()
        } == {
            "qualified": "resolved-unique",
            "stale": "resolved-unique",
            "ambiguous": "resolved-ambiguous",
            "conflicting": "claim-conflict",
        }
        assert {
            key: assert_object(row["source_equivalence"])["state"]
            for key, row in anchors.items()
        } == {
            "qualified": "proven",
            "stale": "mismatch",
            "ambiguous": "unknown",
            "conflicting": "unknown",
        }
        bounded: dict[str, object] = {
            "operation": "correlate_evidence",
            "inputs": {
                **assert_object(cases[-1]["inputs"]),
                "include_relationships": False,
                "relationship_limit_per_path": 1,
                "previous_correlation": correlation,
            },
        }
        cases.append(bounded)
        packets.append(observe_case(codemap, bounded))
    return root, state, cases, packets


def _assert_captures(
    captures: list[dict[str, object]], packet: dict[str, object], operation: str
) -> None:
    assert {row["format"] for row in captures} == {
        "none",
        "structured",
        "compact",
        "text",
    }
    for capture in captures:
        validate_transport_capture(capture)
        response = assert_object(capture["response"])
        if operation == "repository_intelligence_query":
            assert response["schema"] == operation_schema(operation)
            assert response["result"] == packet["result"]
            assert response["execution_effect"] == "none"
            native = response["result"]
        else:
            native = response.get("result", response)
            assert native == packet
        if capture["format"] != "none":
            assert validate_evidence_presentation(
                assert_object(native), assert_object(response["presentation"])
            )["valid"]
        else:
            assert "presentation" not in response


def test_cli_json_observations_keep_canonical_evidence_in_every_format(
    observation_inputs: tuple[
        Path, Path, list[dict[str, object]], list[dict[str, object]]
    ],
) -> None:
    root, state, cases, packets = observation_inputs
    for case, packet in zip(cases, packets, strict=True):
        _assert_captures(
            capture_cli(root, state, case), packet, assert_text(case["operation"])
        )


@pytest.mark.host_mcp_sdk
def test_official_mcp_matches_json_cli_observation_contract(
    observation_inputs: tuple[
        Path, Path, list[dict[str, object]], list[dict[str, object]]
    ],
) -> None:
    root, state, cases, packets = observation_inputs
    for case, packet in zip(cases, packets, strict=True):
        _assert_captures(
            capture_mcp(root, state, case), packet, assert_text(case["operation"])
        )


@pytest.mark.parametrize(
    "command,input_data,reason",
    [
        ("dependency-codemap", [], "one JSON object"),
        ("dependency-codemap", {"snapshot": []}, "snapshot must be a JSON object"),
        (
            "dependency-codemap",
            {"snapshot": {}, "argv": ["echo"]},
            "unknown observation input",
        ),
        (
            "repository-intelligence-query",
            {"surface_name": 1},
            "surface_name must be a string",
        ),
        (
            "repository-intelligence-query",
            {"surface_name": "unknown", "task": "inspect"},
            "surface must be one of",
        ),
        (
            "repository-intelligence-query",
            {
                "surface_name": "cross-repository",
                "task": "inspect",
                "changed_paths": [1],
            },
            "changed_paths member must be a string",
        ),
        ("correlate-evidence", {}, "bundles must be a JSON array"),
        ("correlate-evidence", {"bundles": {}}, "bundles must be a JSON array"),
        (
            "correlate-evidence",
            {"bundles": [1]},
            "bundles member must be a JSON object",
        ),
        (
            "correlate-evidence",
            {"bundles": [], "argv": ["echo"]},
            "unknown observation input",
        ),
        (
            "correlate-evidence",
            {"bundles": [], "path_mappings": {}},
            "path_mappings must be a JSON array",
        ),
        (
            "correlate-evidence",
            {"bundles": [], "path_mappings": [1]},
            "path_mappings member must be a JSON object",
        ),
        (
            "correlate-evidence",
            {"bundles": [], "include_relationships": 1},
            "include_relationships must be a boolean",
        ),
        (
            "correlate-evidence",
            {"bundles": [], "relationship_limit_per_path": True},
            "relationship_limit_per_path must be an integer",
        ),
        (
            "correlate-evidence",
            {"bundles": [], "relationship_limit_per_path": 1.0},
            "relationship_limit_per_path must be an integer",
        ),
        (
            "correlate-evidence",
            {"bundles": [], "relationship_limit_per_path": 0},
            "relationship_limit_per_path must be between 1 and 1000",
        ),
        (
            "correlate-evidence",
            {"bundles": [], "previous_correlation": []},
            "previous_correlation must be a JSON object",
        ),
    ],
)
def test_json_observation_cli_rejects_malformed_or_execution_inputs(
    tmp_path: Path, command: str, input_data: object, reason: str
) -> None:
    source = tmp_path / "request.json"
    source.write_text(json.dumps(input_data))
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "hashmarks.cli",
            "--workspace",
            str(tmp_path),
            command,
            "--input-json",
            str(source),
        ],
        env={**os.environ, "HASHMARKS_NO_UPDATE_CHECK": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert reason in completed.stderr + completed.stdout
    assert "Traceback" not in completed.stderr + completed.stdout
