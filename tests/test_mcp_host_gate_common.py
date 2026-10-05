from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mcp_host_gate_common.py"
SPEC = importlib.util.spec_from_file_location("mcp_host_gate_common_test", SCRIPT)
assert SPEC and SPEC.loader
common = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = common
SPEC.loader.exec_module(common)


def test_basic_qualification_response_requires_exact_structured_json() -> None:
    with pytest.raises(common.HostGateError, match="exact JSON object"):
        common.validate_basic_qualification_response(
            "find",
            "schema hashmarks.find.v2 appears here",
            host="fixture",
        )


def test_basic_qualification_response_requires_fixture_semantics() -> None:
    with pytest.raises(common.HostGateError, match="src/feature.py"):
        common.validate_basic_qualification_response(
            "find",
            '{"schema":"hashmarks.find.v2","results":[]}',
            host="fixture",
        )

    result = common.validate_basic_qualification_response(
        "find",
        {
            "content": [
                {
                    "type": "text",
                    "text": (
                        '{"schema":"hashmarks.find.v2",'
                        '"results":[{"path":"src/feature.py"}]}'
                    ),
                }
            ]
        },
        host="fixture",
    )
    assert result["results"] == [{"path": "src/feature.py"}]


def test_basic_qualification_repository_context_requires_generation() -> None:
    with pytest.raises(common.HostGateError, match="integer generation"):
        common.validate_basic_qualification_response(
            "repository_context",
            {"schema": "hashmarks.repository-capsule.v1"},
            host="fixture",
        )

    result = common.validate_basic_qualification_response(
        "repository_context",
        {
            "structuredContent": {
                "schema": "hashmarks.repository-capsule.v1",
                "generation": 3,
            }
        },
        host="fixture",
    )
    assert result["generation"] == 3


def test_basic_qualification_request_binds_fixture_arguments() -> None:
    assert common.validate_basic_qualification_request(
        "find",
        {"query": "flare041", "limit": 5},
        host="fixture",
    ) == {"query": "flare041", "limit": 5}

    with pytest.raises(common.HostGateError, match="fixture contract"):
        common.validate_basic_qualification_request(
            "find",
            {"query": "other", "limit": 5},
            host="fixture",
        )


def test_basic_qualification_proof_roundtrips_semantic_authority() -> None:
    proof = common.basic_qualification_proof(
        generation=7,
        find_paths={"src/feature.py", "tests/test_feature.py"},
    )

    assert common.validate_basic_qualification_proof(proof) is None
    assert proof["repository_context"] == {
        "schema": "hashmarks.repository-capsule.v1",
        "generation": 7,
    }
    assert proof["find"] == {
        "schema": "hashmarks.find.v2",
        "paths": ["src/feature.py", "tests/test_feature.py"],
    }


def test_basic_qualification_proof_rejects_missing_or_wrong_semantics() -> None:
    assert (
        common.validate_basic_qualification_proof(None)
        == "receipt predates semantic qualification proof"
    )

    proof = common.basic_qualification_proof(
        generation=1,
        find_paths={"src/wrong.py"},
    )
    error = common.validate_basic_qualification_proof(proof)
    assert error is not None
    assert "src/feature.py" in error
