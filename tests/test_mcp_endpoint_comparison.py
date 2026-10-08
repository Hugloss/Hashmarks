from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from hashmarks.codemap.repository_delta import (
    RepositoryDeltaMixin,
    RepositoryGenerationBinding,
)
from hashmarks.evidence_presentation import (
    FORMATS,
    present_repository_evidence,
    presentation_response,
)
from hashmarks.mcp_contract import tool_contract
from hashmarks.mcp_server import build_server
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError
from hashmarks.operation_contract import operation_schema

_MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None


def _repo(root: Path) -> Path:
    repo = root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "owner.py").write_text(
        "def owner(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    return repo


def _diagnostic(*, collection: str, rows: list[dict[str, object]]) -> dict[str, object]:
    return RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pyright",
        binding=RepositoryGenerationBinding("repo-identity", 1),
        diagnostics=rows,
        outcome="fail",
        collection_state=collection,
        environment_identity="same-environment",
        scope_paths=["src/owner.py"],
    )


@pytest.mark.parametrize("format", ["structured", "compact", "text"])
def test_structural_comparison_preserves_incomparability(
    tmp_path: Path, format: str
) -> None:
    surface = HashmarksMcpSurface(
        str(_repo(tmp_path)), state_dir=str(tmp_path / "state")
    )
    try:
        before = {
            "schema": operation_schema("structural_locality"),
            "target": "owner",
            "nodes": [{"symbol_id": "unqualified:old"}],
            "dimensions": {"symbol_count": 1},
        }
        after = {
            **before,
            "nodes": [{"symbol_id": "unqualified:new"}],
            "dimensions": {"symbol_count": 2},
        }
        result = surface.evidence_comparison(before, after)
        assert result["schema"] == operation_schema("evidence_comparison", "structural")
        assert result["comparable"] is False
        assert result["incomparability_reasons"]
        projection = present_repository_evidence(result, format=format)
        assert projection["supported"] is True
        assert projection["groups"][0]["family"] == "qualification"
        assert projection["groups"][0]["findings"][0]["kind"] == (
            "structural_endpoints_incomparable"
        )
        row = projection["groups"][0]["findings"][0]
        assert row["source_refs"] == ["/incomparability_reasons"]
        assert row["details"] == result["incomparability_reasons"]
        context = projection["source_context"][0]["details"]
        assert context["comparable"] is False
        assert context["incomparability_reasons"] == result["incomparability_reasons"]
        excluded = {
            section["source_ref"]: section
            for section in projection["unprojected_sections"]
        }
        for field in ("introduced_symbol_ids", "removed_symbol_ids", "dimension_delta"):
            assert excluded["/" + field]["native_item_count"] == 1
        if format == "text":
            assert '"comparable":false' in projection["text"]
            assert '"source_ref":"/dimension_delta"' in projection["text"]
        assert all(
            row["assertion"] != "observed_change"
            for group in projection["groups"]
            for row in group["findings"]
        )
    finally:
        surface.close()


def test_binding_comparison_reuses_current_repository_identity(tmp_path: Path) -> None:
    surface = HashmarksMcpSurface(
        str(_repo(tmp_path)), state_dir=str(tmp_path / "state")
    )
    try:
        current = surface.repository_evidence(
            {
                "bindings": [
                    {
                        "binding_id": "consumer:scope",
                        "evidence": [{"scope": "member", "path": "src/owner.py"}],
                    }
                ],
                "include_relationships": False,
            }
        )
        assert current["schema"] == operation_schema(
            "repository_evidence", "observation"
        )
        result = surface.evidence_comparison(current, current, result_mode="bindings")
        assert result["schema"] == operation_schema("evidence_comparison", "bindings")
        assert result["bindings"]["preserved"] == ["consumer:scope"]
        assert result["bindings"]["changed"] == []
        foreign = {
            **current,
            "repository": {**current["repository"], "repository_identity": "foreign"},
        }
        with pytest.raises(McpSurfaceError, match="mismatch"):
            surface.evidence_comparison(current, foreign, result_mode="bindings")
    finally:
        surface.close()


def test_incomplete_diagnostics_never_imply_resolution(tmp_path: Path) -> None:
    original = {
        "tool": "pyright",
        "rule": "E1",
        "path": "src/owner.py",
        "line": 5,
        "message": "missing argument",
    }
    before = _diagnostic(collection="fresh-complete", rows=[original])
    after = _diagnostic(collection="fresh-partial", rows=[])
    surface = HashmarksMcpSurface(
        str(_repo(tmp_path)), state_dir=str(tmp_path / "state")
    )
    try:
        delta = surface.evidence_comparison(
            before,
            after,
            result_mode="diagnostics",
            changed_paths=["src/owner.py"],
        )
        assert delta["schema"] == operation_schema("evidence_comparison", "diagnostics")
        qualification = delta["diagnostics"]["qualification"]
        assert qualification["qualified_removed_identities"] == []
        assert qualification["unqualified_removed_identities"] == [
            before["diagnostics"][0]["identity"]
        ]
        projection = present_repository_evidence(delta, format="structured")
        assert projection["groups"][0]["family"] == "diagnostic"
        assert projection["groups"][0]["findings"][0]["assertion"] == "producer_claim"
        with pytest.raises(McpSurfaceError, match="identity mismatch"):
            tampered = {
                **before,
                "diagnostics": [{**before["diagnostics"][0], "message": "tampered"}],
            }
            surface.evidence_comparison(tampered, after, result_mode="diagnostics")
    finally:
        surface.close()


def test_comparison_rejects_unsupported_modes_and_irrelevant_scope(
    tmp_path: Path,
) -> None:
    surface = HashmarksMcpSurface(
        str(_repo(tmp_path)), state_dir=str(tmp_path / "state")
    )
    try:
        with pytest.raises(McpSurfaceError, match="result_mode must be"):
            surface.evidence_comparison({}, {}, result_mode="history")
        with pytest.raises(McpSurfaceError, match="only valid for diagnostics"):
            surface.evidence_comparison({}, {}, changed_paths=["src/owner.py"])
        with pytest.raises(McpSurfaceError, match="must be an object"):
            surface.evidence_comparison([], {}, result_mode="structural")
        with pytest.raises(McpSurfaceError, match="exceeds"):
            surface.evidence_comparison({"large": "x" * 600000}, {})
    finally:
        surface.close()


def test_comparison_contract_is_mode_specific_and_read_only() -> None:
    contract = tool_contract("evidence_comparison")
    assert contract.response_modes == ("structural", "bindings", "diagnostics")
    assert contract.response_schema_for_mode("bindings") == operation_schema(
        "evidence_comparison", "bindings"
    )
    correct = {"schema": operation_schema("evidence_comparison", "diagnostics")}
    assert contract.validate_response(correct, result_mode="diagnostics") == correct
    with pytest.raises(RuntimeError, match="response schema drift"):
        contract.validate_response(correct, result_mode="structural")


def test_comparable_structural_measurement_retains_exact_source_reference() -> None:
    packet = {
        "schema": operation_schema("evidence_comparison", "structural"),
        "comparable": True,
        "incomparability_reasons": [],
        "introduced_symbol_ids": ["src/owner.py::renamed"],
        "removed_symbol_ids": [],
        "verification_paths_added": [],
        "verification_paths_removed": [],
        "dimension_delta": {"static_callers": 2},
    }
    projection = present_repository_evidence(packet, format="structured")
    rows = [row for group in projection["groups"] for row in group["findings"]]
    measurement = next(row for row in rows if row["kind"] == "dimension_delta")
    assert measurement["source_refs"] == ["/dimension_delta"]
    assert measurement["details"] == {"static_callers": 2}
    assert measurement["assertion"] == "observed_change"


@pytest.mark.host_mcp_sdk
@pytest.mark.skipif(not _MCP_AVAILABLE, reason="MCP extra is not installed")
def test_sdk_comparisons_preserve_real_endpoints_in_all_formats(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    server: Any = build_server(repo, state_dir=tmp_path / "state")
    surface = server._hashmarks_surface

    async def exercise() -> None:
        before = surface.structural_locality("src/owner.py::owner")
        (repo / "src" / "owner.py").write_text(
            "def helper(value: int) -> int:\n    return value + 2\n\n"
            "def owner(value: int) -> int:\n    return helper(value)\n",
            encoding="utf-8",
        )
        after = surface.structural_locality("src/owner.py::owner")
        binding = surface.repository_evidence(
            {
                "bindings": [
                    {
                        "binding_id": "sdk:scope",
                        "evidence": [{"scope": "member", "path": "src/owner.py"}],
                    }
                ],
                "include_relationships": False,
            }
        )
        diagnostic_before = _diagnostic(
            collection="fresh-complete",
            rows=[{"path": "src/owner.py", "line": 2, "message": "fixture diagnostic"}],
        )
        diagnostic_after = _diagnostic(collection="fresh-partial", rows=[])
        for mode, left, right in (
            ("structural", before, after),
            ("structural", before, before),
            ("bindings", binding, binding),
            ("diagnostics", diagnostic_before, diagnostic_after),
        ):
            request = {"before": left, "after": right, "result_mode": mode}
            baseline = await server.call_tool("evidence_comparison", request)
            assert baseline.is_error is not True
            native = baseline.structured_content
            assert isinstance(native, dict)
            if mode == "structural":
                assert native["comparable"] is (left is not right)
                if native["comparable"]:
                    assert native["dimension_delta"]["symbol_count"] == 1
            if mode == "diagnostics":
                assert (
                    native["diagnostics"]["qualification"][
                        "qualified_removed_identities"
                    ]
                    == []
                )
            for format in FORMATS:
                result = await server.call_tool(
                    "evidence_comparison", {**request, "presentation": format}
                )
                assert result.is_error is not True
                assert result.structured_content == presentation_response(
                    "evidence_comparison", native, format=format, result_mode=mode
                )

    try:
        asyncio.run(exercise())
    finally:
        surface.close()
