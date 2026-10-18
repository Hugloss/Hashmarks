from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records, assert_text

from hashmarks.codemap.diagnostic_observation import external_diagnostic_observation
from hashmarks.codemap.repository_delta import (
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
    return external_diagnostic_observation(
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
        assert assert_records(projection["groups"])[0]["family"] == "qualification"
        assert assert_records(assert_records(projection["groups"])[0]["findings"])[0][
            "kind"
        ] == ("structural_endpoints_incomparable")
        row = assert_records(assert_records(projection["groups"])[0]["findings"])[0]
        assert row["source_refs"] == ["/incomparability_reasons"]
        assert row["details"] == result["incomparability_reasons"]
        context = assert_object(
            assert_records(projection["source_context"])[0]["details"]
        )
        assert context["comparable"] is False
        assert context["incomparability_reasons"] == result["incomparability_reasons"]
        excluded = {
            section["source_ref"]: section
            for section in assert_records(projection["unprojected_sections"])
        }
        for field in ("introduced_symbol_ids", "removed_symbol_ids", "dimension_delta"):
            assert excluded["/" + field]["native_item_count"] == 1
        if format == "text":
            assert '"comparable":false' in assert_text(projection["text"])
            assert '"source_ref":"/dimension_delta"' in assert_text(projection["text"])
        assert all(
            row["assertion"] != "observed_change"
            for group in assert_records(projection["groups"])
            for row in assert_records(group["findings"])
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
        assert assert_object(result["bindings"])["preserved"] == ["consumer:scope"]
        assert assert_object(result["bindings"])["changed"] == []
        foreign = {
            **current,
            "repository": {
                **assert_object(current["repository"]),
                "repository_identity": "foreign",
            },
        }
        with pytest.raises(McpSurfaceError, match="mismatch"):
            surface.evidence_comparison(current, foreign, result_mode="bindings")
    finally:
        surface.close()


def test_incomplete_diagnostics_never_imply_resolution(tmp_path: Path) -> None:
    original: dict[str, object] = {
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
        qualification = assert_object(delta["diagnostics"])["qualification"]
        assert assert_object(qualification)["qualified_removed_identities"] == []
        assert assert_object(qualification)["unqualified_removed_identities"] == [
            assert_records(before["diagnostics"])[0]["identity"]
        ]
        projection = present_repository_evidence(delta, format="structured")
        assert assert_records(projection["groups"])[0]["family"] == "diagnostic"
        assert (
            assert_records(assert_records(projection["groups"])[0]["findings"])[0][
                "assertion"
            ]
            == "producer_claim"
        )
        with pytest.raises(McpSurfaceError, match="identity mismatch"):
            tampered = {
                **before,
                "diagnostics": [
                    {**assert_records(before["diagnostics"])[0], "message": "tampered"}
                ],
            }
            surface.evidence_comparison(tampered, after, result_mode="diagnostics")
    finally:
        surface.close()


def test_diagnostic_comparison_transports_other_member_locality(
    tmp_path: Path,
) -> None:
    scope = ["src/owner.py", "src/consumer.py"]

    def observation(rows: list[dict[str, object]]) -> dict[str, object]:
        return external_diagnostic_observation(
            producer="pyright",
            binding=RepositoryGenerationBinding("repo-identity", 1),
            diagnostics=rows,
            outcome="fail",
            collection_state="fresh-complete",
            environment_identity="same-environment",
            scope_paths=scope,
        )

    before = observation([{"tool": "pyright", "rule": "old", "path": "src/owner.py"}])
    after = observation([{"tool": "pyright", "rule": "new", "path": "src/consumer.py"}])
    surface = HashmarksMcpSurface(
        str(_repo(tmp_path)), state_dir=str(tmp_path / "state")
    )
    try:
        delta = surface.evidence_comparison(
            before, after, result_mode="diagnostics", changed_paths=["src/owner.py"]
        )
        locality = assert_object(delta["diagnostics"])["path_locality"]
        rows = assert_records(assert_object(locality)["rows"])
        assert len(rows) == 2
        assert {(row["change_kind"], row["locality"]) for row in rows} == {
            ("removed", "on-reported-changed-path"),
            ("added", "outside-reported-changed-paths"),
        }
        assert all(row["collection_qualification"] == "qualified" for row in rows)
        assert all(row["causality"] == "not-asserted" for row in rows)
        presentation = present_repository_evidence(delta, format="compact")
        assert any(
            finding["kind"] == "diagnostic_path_locality"
            for group in assert_records(presentation["groups"])
            for finding in assert_records(group["findings"])
        )
    finally:
        surface.close()


def test_diagnostic_comparison_transports_revision_only_changes(tmp_path: Path) -> None:
    before = _diagnostic(collection="fresh-complete", rows=[])
    after = {**before, "source_revisions": {"src/owner.py": "b" * 64}}
    before["source_revisions"] = {"src/owner.py": "a" * 64}
    surface = HashmarksMcpSurface(
        str(_repo(tmp_path)), state_dir=str(tmp_path / "state")
    )
    try:
        delta = surface.evidence_comparison(before, after, result_mode="diagnostics")
        assert assert_object(delta["source_revisions"])["changed"] is True
        assert (
            assert_object(delta["source_revisions"])["before"]
            == before["source_revisions"]
        )
        assert (
            assert_object(delta["source_revisions"])["after"]
            == after["source_revisions"]
        )
        assert assert_object(delta["diagnostics"])["added"] == []
        assert assert_object(delta["diagnostics"])["removed"] == []
        projection = present_repository_evidence(delta, format="compact")
        assert any(
            row["kind"] == "diagnostic_source_revisions"
            and row["details"] == delta["source_revisions"]
            and row["assertion"] == "producer_claim"
            for group in assert_records(projection["groups"])
            for row in assert_records(group["findings"])
        )
        with pytest.raises(McpSurfaceError, match="source_revisions"):
            surface.evidence_comparison(
                before,
                {**after, "source_revisions": {"outside.py": "b" * 64}},
                result_mode="diagnostics",
            )
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
            surface.evidence_comparison(json.loads("[]"), {}, result_mode="structural")
        with pytest.raises(McpSurfaceError, match="exceeds"):
            surface.evidence_comparison({"large": "x" * 600000}, {})
    finally:
        surface.close()


def test_comparison_contract_is_mode_specific_and_read_only() -> None:
    contract = tool_contract("evidence_comparison")
    assert contract.response_modes == (
        "structural",
        "bindings",
        "diagnostics",
        "relationships",
    )
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
    rows = [
        row
        for group in assert_records(projection["groups"])
        for row in assert_records(group["findings"])
    ]
    measurement = next(row for row in rows if row["kind"] == "dimension_delta")
    assert measurement["source_refs"] == ["/dimension_delta"]
    assert measurement["details"] == {"static_callers": 2}
    assert measurement["assertion"] == "observed_change"


@pytest.mark.host_mcp_sdk
@pytest.mark.skipif(not _MCP_AVAILABLE, reason="MCP extra is not installed")
def test_sdk_comparisons_preserve_real_endpoints_in_all_formats(tmp_path: Path) -> None:
    from mcp.types import CallToolResult

    repo = _repo(tmp_path)
    server = build_server(repo, state_dir=tmp_path / "state")
    surface = getattr(server, "_hashmarks_surface", None)
    assert isinstance(surface, HashmarksMcpSurface)

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
            if mode == "diagnostics":
                request.update(changed_paths=["src/owner.py"], change_set_complete=True)
            baseline = await server.call_tool("evidence_comparison", request)
            assert isinstance(baseline, CallToolResult)
            assert baseline.is_error is not True
            native = baseline.structured_content
            assert isinstance(native, dict)
            if mode == "structural":
                assert native["comparable"] is (left is not right)
                if native["comparable"]:
                    assert native["dimension_delta"]["symbol_count"] == 1
            if mode == "diagnostics":
                assert native["change_set"]["completeness"] == "caller-claimed-complete"
                assert native["diagnostics"]["path_deltas"][0]["edit_relation"] == (
                    "reported-changed"
                )
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
                assert isinstance(result, CallToolResult)
                assert result.is_error is not True
                assert result.structured_content == presentation_response(
                    "evidence_comparison", native, format=format, result_mode=mode
                )

    try:
        asyncio.run(exercise())
    finally:
        surface.close()
