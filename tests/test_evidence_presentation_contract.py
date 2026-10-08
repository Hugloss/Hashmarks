from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_intelligence_query import (
    QUERY_SURFACES,
    RepositoryIntelligenceQueryOptions,
)
from hashmarks.codemap.repository_delta import (
    RepositoryDeltaMixin,
    RepositoryGenerationBinding,
)
from hashmarks.codemap.structural_locality import structural_locality_delta
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient
from hashmarks.evidence_presentation import (
    FORMATS,
    present_repository_evidence,
    presentation_response,
)
from hashmarks.mcp_contract import (
    MCP_TOOL_CONTRACTS,
    contract_from_tool_models,
    tool_contract,
)
from hashmarks.mcp_server import _call_surface, build_server
from hashmarks.operation_contract import operation_schema

_MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None


def _findings(projection: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for group in projection["groups"] for row in group["findings"]]


@pytest.fixture(scope="module")
def native_packets(
    tmp_path_factory: pytest.TempPathFactory,
) -> list[tuple[str, str, dict[str, Any]]]:
    root = tmp_path_factory.mktemp("presentation")
    (root / "src").mkdir()
    (root / "tests").mkdir()
    owner = root / "src" / "owner.py"
    owner.write_text("import os\ndef widget(): return 1\n", encoding="utf-8")
    (root / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\ndef test_widget(): assert widget() == 1\n",
        encoding="utf-8",
    )
    task, paths = "inspect src/owner.py widget", ["src/owner.py"]
    dependency = {
        "schema": "hashmarks.dependency-resolution.v3",
        "producer": {
            "kind": "neutral",
            "schema_version": "1",
            "adapter_semantics": "test.neutral.v1",
        },
        "scope": {},
        "contexts": ["test"],
        "roots": [],
        "components": [],
        "selections": [],
        "inventory": [],
        "relationships": [],
        "module_ownership": [],
        "repository_inputs": [],
        "evidence_sources": [],
        "coverage": [],
    }
    group = {
        "group_id": "explicit",
        "semantic_namespace": "test",
        "concept": {"kind": "value", "identity": "widget"},
        "scope": {},
        "correspondence": {"state": "declared", "basis": {"provider": "test"}},
        "declarations": [
            {
                "declaration_id": "one",
                "value_state": "resolved",
                "value": 1,
                "producer": {"kind": "fixture"},
                "evidence": [{"path": paths[0], "start_line": 2, "end_line": 2}],
            }
        ],
        "coverage": {
            "state": "complete",
            "truncation": "complete",
            "expected_declaration_ids": ["one"],
            "scope": {},
            "provenance": {"provider": "test"},
        },
    }
    bundle = {
        "bundle_id": "one",
        "producer": {"kind": "fixture"},
        "completeness": "complete",
        "scope": {},
        "truncation": "complete",
        "anchors": [
            {
                "anchor_id": "one",
                "path": paths[0],
                "line": 2,
                "metadata": {"message": "caller claim"},
            }
        ],
    }
    with CodeMap(root, state_dir=root / "state") as codemap:
        codemap.sync()
        snapshot = codemap.repository_intelligence_snapshot(task, paths)
        previous = codemap.task_evidence(task)
        binding = codemap.repository_evidence_bindings(
            [
                {
                    "binding_id": "one",
                    "evidence": [{"path": paths[0], "start_line": 2, "end_line": 2}],
                }
            ]
        )
        observation = codemap.dependency_resolution_evidence(dependency)
        declarations = codemap.repository_declarations([group])
        locality = codemap.structural_locality("src/owner.py::widget")
        external = RepositoryDeltaMixin.external_diagnostic_observation(
            producer="test-diagnostics",
            binding=RepositoryGenerationBinding("fixture-repository", 1),
            diagnostics=[
                {
                    "tool": "pyright",
                    "rule": "fixture",
                    "path": paths[0],
                    "line": 2,
                    "message": "fixture diagnostic",
                }
            ],
            outcome="fail",
            environment_identity="fixture-env",
            scope_paths=paths,
            collection_state="fresh-complete",
        )
        packets = [
            ("repository_context", "default", codemap.orient()),
            ("find", "default", codemap.find_packet("widget")),
            ("task_evidence", "default", previous),
            ("change_impact", "default", codemap.task_change_impact(task, paths)),
            ("correlate_evidence", "default", codemap.correlate_evidence([bundle])),
            (
                "dependency_codemap",
                "observation",
                codemap.dependency_codemap(dependency),
            ),
            (
                "dependency_codemap",
                "explain",
                codemap.dependency_resolution_explain(observation),
            ),
            (
                "dependency_codemap",
                "compare",
                codemap.dependency_resolution_delta(observation, observation),
            ),
            ("repository_declarations", "observation", declarations),
            (
                "repository_declarations",
                "explain",
                codemap.repository_declaration_explain(declarations),
            ),
            (
                "source_observation",
                "member",
                codemap.source_observation(paths[0], literal="widget"),
            ),
            (
                "source_observation",
                "scope",
                codemap.scoped_source_occurrences(paths, literal="widget"),
            ),
            ("repository_evidence", "observation", binding),
            (
                "repository_evidence",
                "coverage",
                codemap.repository_evidence_coverage(
                    binding, changed_paths=paths, change_set_complete=False
                ),
            ),
            ("repository_findings", "default", codemap.repository_findings()),
            (
                "structural_locality",
                "default",
                locality,
            ),
            (
                "evidence_comparison",
                "structural",
                structural_locality_delta(locality, locality),
            ),
            (
                "evidence_comparison",
                "bindings",
                codemap.repository_evidence_binding_delta(binding, binding),
            ),
            (
                "evidence_comparison",
                "diagnostics",
                RepositoryDeltaMixin.diagnostic_observation_delta(external, external),
            ),
        ]
        owner.write_text("import sys\ndef widget(): return 2\n", encoding="utf-8")
        packets.append(
            (
                "post_change",
                "default",
                codemap.task_post_change_delta(task, paths, previous_evidence=previous),
            )
        )
        for surface in QUERY_SURFACES:
            profiles = (
                ("compact", "standard", "audit")
                if surface == "profile"
                else ("compact",)
            )
            for profile in profiles:
                packets.append(
                    (
                        "repository_intelligence_query",
                        "default",
                        codemap.repository_intelligence_query(
                            surface,
                            task,
                            paths,
                            options=RepositoryIntelligenceQueryOptions(
                                profile=profile, previous_snapshot=snapshot
                            ),
                        ),
                    )
                )
    return packets


def test_every_native_mode_is_preserved_and_projected_without_reads(
    native_packets, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_read(*_args, **_kwargs):
        raise AssertionError("presentation must not read repository files")

    monkeypatch.setattr(Path, "read_bytes", no_read)
    monkeypatch.setattr(Path, "read_text", no_read)
    for operation, mode, native in native_packets:
        before = copy.deepcopy(native)
        for format in FORMATS:
            response: dict[str, Any] = presentation_response(
                operation, native, format=format, result_mode=mode
            )
            tool_contract(operation).validate_response(
                response, result_mode=mode, presentation=format
            )
            if format == "none":
                assert response is native
                continue
            assert response["result"] == (
                native["result"]
                if operation == "repository_intelligence_query"
                else native
            )
            assert response["presentation"]["supported"] is True
            assert response["presentation"]["coverage"] == "projection-only"
        assert native == before


def test_source_refs_point_to_exact_records_and_details_are_independent(
    native_packets,
) -> None:
    for operation, _mode, native in native_packets:
        source = (
            native["result"] if operation == "repository_intelligence_query" else native
        )
        projected: dict[str, Any] = present_repository_evidence(
            source, format="structured"
        )
        for row in _findings(projected):
            value = source
            pointer = row["source_refs"][0]
            for part in pointer.split("/")[1:] if pointer else ():
                key = part.replace("~1", "/").replace("~0", "~")
                value = value[int(key)] if isinstance(value, list) else value[key]
            assert row["details"] == value
        wire_source = json.loads(json.dumps(source, sort_keys=True))
        assert (
            present_repository_evidence(wire_source, format="structured") == projected
        )
        assert present_repository_evidence(
            wire_source, format="text"
        ) == present_repository_evidence(source, format="text")
        original = copy.deepcopy(source)
        for row in _findings(projected):
            if isinstance(row["details"], dict):
                row["details"]["mutation"] = True
        assert source == original


def test_revision_edges_claims_and_text_keep_semantic_details() -> None:
    delta = {
        "schema": "hashmarks.repository-intelligence-delta.v1",
        "semantic": {
            "dependencies_removed": [
                {"path": "a.py", "source": "a", "target": "os", "kind": "import"}
            ],
            "dependencies_added": [
                {"path": "a.py", "source": "a", "target": "sys", "kind": "import"}
            ],
            "possible_symbol_moves": [{"name": "widget", "from": "a.py", "to": "b.py"}],
        },
        "changes": [{"path": ["paths", "a.py", "revision"], "value": "new-revision"}],
        "completeness": {"scope": "bounded"},
    }
    projected: dict[str, Any] = present_repository_evidence(delta, format="text")
    assert any(row["kind"] == "member_revision_changed" for row in _findings(projected))
    for expected in (
        '"target":"os"',
        '"target":"sys"',
        '"name":"widget"',
        '"from":"a.py"',
        '"to":"b.py"',
        "new-revision",
        "candidate_correspondence",
    ):
        assert expected in projected["text"]
    dependency = {
        "schema": operation_schema("dependency_codemap", "compare"),
        "comparability": "not-comparable",
        "producer_authority": "caller-claimed",
        "before_observation_identity": "old",
        "after_observation_identity": "new",
        "components_added": ["new-component"],
        "component_selection_transitions": [
            {
                "component_id": "lib",
                "changed": [{"before": {"version": "1"}, "after": {"version": "2"}}],
            }
        ],
    }
    claim: dict[str, Any] = present_repository_evidence(dependency, format="text")
    assert all(row["assertion"] == "producer_claim" for row in _findings(claim))
    assert claim["source_evidence_identity"] is None
    assert claim["source_identities"]["before_observation_identity"] == "old"
    assert "not-comparable" in claim["text"] and '"version":"2"' in claim["text"]


def test_projection_bounds_cannot_create_negative_evidence() -> None:
    packet = {
        "schema": operation_schema("find"),
        "results": [{"path": f"file{i}.py"} for i in range(60)],
        "truncated": True,
        "freshness": "unknown",
        "negative_evidence": "not-admissible",
        "future_section": ["unprojected"],
    }
    for format, selected in (("structured", 48), ("compact", 5), ("text", 5)):
        result: dict[str, Any] = present_repository_evidence(packet, format=format)
        group = result["groups"][0]
        assert len(group["findings"]) == selected
        assert group["omitted_from_presentation"] == 60 - selected
        assert (
            result["source_context"][0]["details"]["negative_evidence"]
            == "not-admissible"
        )
        assert result["unprojected_sections"] == [
            {
                "source_ref": "/future_section",
                "reason": "not-projected",
                "native_item_count": 1,
            },
        ]
    with pytest.raises(ValueError, match="malformed evidence"):
        present_repository_evidence(
            {"schema": operation_schema("find"), "results": [None]}
        )
    empty: dict[str, Any] = present_repository_evidence(
        {"schema": operation_schema("find"), "results": []}, format="text"
    )
    assert "No displayed findings in this projection" in empty["text"]


def test_mcp_rejects_invalid_presentation_before_producer_and_wrapper_drift() -> None:
    calls = []

    def producer():
        calls.append(True)
        return {"schema": operation_schema("find"), "results": []}

    with pytest.raises(ValueError, match="presentation must be"):
        _call_surface(
            tool_contract("find"), ValueError, producer, presentation="invalid"
        )
    assert not calls
    response: dict[str, Any] = _call_surface(
        tool_contract("find"), ValueError, producer, presentation="compact"
    )
    assert calls == [True]
    for key, value in (
        ("operation", "task_evidence"),
        ("result_mode", "explain"),
        ("authority", "authoritative"),
    ):
        changed = copy.deepcopy(response)
        changed[key] = value
        with pytest.raises(RuntimeError, match="drift"):
            tool_contract("find").validate_response(changed, presentation="compact")
    for key, value in (
        ("schema", "wrong"),
        ("source_schema", "wrong"),
        ("format", "text"),
        ("source_evidence_identity", "forged"),
        ("source_identities", {"before_observation_identity": "forged"}),
    ):
        changed = copy.deepcopy(response)
        changed["presentation"][key] = value
        with pytest.raises(RuntimeError, match="drift"):
            tool_contract("find").validate_response(changed, presentation="compact")


@pytest.mark.host_mcp_sdk
@pytest.mark.skipif(not _MCP_AVAILABLE, reason="MCP extra is not installed")
def test_actual_sdk_advertises_all_format_selectors(tmp_path: Path) -> None:
    server: Any = build_server(tmp_path, state_dir=tmp_path / "state")
    try:
        tools = asyncio.run(server.list_tools())
        manifest: dict[str, Any] = contract_from_tool_models("test", tuple(tools))
        assert len(manifest["tools"]) == 14
        for tool, contract in zip(tools, MCP_TOOL_CONTRACTS, strict=True):
            field = tool.input_schema["properties"]["presentation"]
            assert field["enum"] == list(FORMATS)
            assert field["default"] == contract.default_presentation
    finally:
        server._hashmarks_surface.close()


def test_service_transports_presentation_and_rejects_older_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = {}

    class Map:
        def repository_intelligence_query(self, _surface, _task, _paths, *, options):
            captured["options"] = options
            return {
                "schema": operation_schema("repository_intelligence_query"),
                "presentation": {"format": options.presentation},
            }

    service = CodeMapService(tmp_path, socket_path=tmp_path / "unused.sock")
    monkeypatch.setattr(service, "_map", Map)
    client = CodeMapServiceClient(tmp_path, socket_path=tmp_path / "unused.sock")
    monkeypatch.setattr(
        client,
        "request",
        lambda _operation, **request: service._repository_intelligence_query_response(
            request
        ),
    )
    for format in FORMATS:
        response = client.repository_intelligence_query(
            "profile",
            "inspect widget",
            ["owner.py"],
            options=RepositoryIntelligenceQueryOptions(presentation=format),
        )
        assert captured["options"].presentation == format
        assert response["presentation"]["format"] == format
    monkeypatch.setattr(
        client,
        "request",
        lambda *_args, **_kwargs: {
            "repository_intelligence_query": {
                "schema": operation_schema("repository_intelligence_query")
            }
        },
    )
    with pytest.raises(ValueError, match="unsupported presentation"):
        client.repository_intelligence_query(
            "profile",
            "inspect widget",
            ["owner.py"],
            options=RepositoryIntelligenceQueryOptions(presentation="text"),
        )


@pytest.mark.host_mcp_sdk
@pytest.mark.skipif(not _MCP_AVAILABLE, reason="MCP extra is not installed")
def test_sdk_calls_all_tools_with_native_defaults_and_optional_formats(
    native_packets, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hashmarks.codemap.repository_intelligence_query import (
        repository_query_response,
    )

    packets = {(operation, mode): packet for operation, mode, packet in native_packets}
    server: Any = build_server(tmp_path, state_dir=tmp_path / "state")
    arguments = {
        "repository_context": {},
        "find": {"query": "widget"},
        "task_evidence": {"task": "inspect widget"},
        "change_impact": {"task": "inspect widget", "changed_paths": ["src/owner.py"]},
        "correlate_evidence": {"bundles": []},
        "dependency_codemap": {"snapshot": {}},
        "repository_declarations": {"groups": []},
        "post_change": {
            "task": "inspect widget",
            "changed_paths": ["src/owner.py"],
            "previous_evidence": {},
        },
        "repository_intelligence_query": {
            "surface_name": "economics",
            "task": "inspect widget",
            "changed_paths": ["src/owner.py"],
        },
        "source_observation": {"paths": ["src/owner.py"]},
        "repository_evidence": {"request": {}},
        "repository_findings": {},
        "structural_locality": {"target": "src/owner.py::widget"},
        "evidence_comparison": {"before": {}, "after": {}},
    }

    def frozen_producer(contract):
        def response(*_args, **kwargs):
            native = packets[
                contract.operation,
                kwargs.get("result_mode", contract.default_response_mode),
            ]
            if contract.operation == "repository_intelligence_query":
                return repository_query_response(
                    native["surface"],
                    native["result"],
                    presentation=kwargs["presentation"],
                )
            return native

        return response

    for contract in MCP_TOOL_CONTRACTS:
        monkeypatch.setattr(
            server._hashmarks_surface, contract.name, frozen_producer(contract)
        )

    async def exercise():
        for contract in MCP_TOOL_CONTRACTS:
            default = await server.call_tool(contract.name, arguments[contract.name])
            native = packets[contract.operation, contract.default_response_mode]
            expected = presentation_response(
                contract.operation, native, format=contract.default_presentation
            )
            assert default.structured_content == expected
            for format in FORMATS:
                called = await server.call_tool(
                    contract.name, {**arguments[contract.name], "presentation": format}
                )
                tool_contract(contract.name).validate_response(
                    called.structured_content, presentation=format
                )

    try:
        asyncio.run(exercise())
    finally:
        server._hashmarks_surface.close()


def test_diagnostic_detail_and_json_pointer_escaping_preserve_native_values() -> None:
    record = {
        "path": "src/old.py",
        "line": 9,
        "column": 3,
        "diagnostic_id": "lint:one",
        "tool": "fixture",
        "rule": "example-rule",
        "message": "line one\nline two",
        "severity": "advisory",
        "counter_evidence": {"state": "unknown"},
    }
    diagnostic = {
        "schema": "hashmarks.diagnostic-observation-delta.v1",
        "producer": {"kind": "fixture"},
        "collection_before": {"completeness": "complete"},
        "collection_after": {"completeness": "incomplete"},
        "diagnostics": {"removed": [record]},
    }
    result: dict[str, Any] = present_repository_evidence(diagnostic, format="text")
    finding = _findings(result)[0]
    assert finding["details"] == record
    assert finding["assertion"] == "producer_claim"
    assert result["source_evidence_identity"] is None
    assert "example-rule" in result["text"] and "line one\\nline two" in result["text"]
    assert "incomplete" in result["text"]
    snapshot = {
        "schema": "hashmarks.repository-intelligence-snapshot.v1",
        "paths": {"a~/b.py": {"member_state": "unknown", "revision": "exact-revision"}},
    }
    projection: dict[str, Any] = present_repository_evidence(snapshot)
    rows = _findings(projection)
    assert rows[0]["source_refs"] == ["/paths/a~0~1b.py/revision"]
    assert rows[1]["details"] == "unknown"
    with pytest.raises(ValueError, match="missing required"):
        present_repository_evidence({"schema": operation_schema("find")})


def test_omitted_record_qualifications_remain_visible_outside_display_bounds() -> None:
    packet = {
        "schema": operation_schema("find"),
        "freshness": "unknown",
        "results": [
            {
                "path": f"file{i}.py",
                "state": "ambiguous" if i == 9 else "observed",
                "negative_evidence": "not-admissible",
            }
            for i in range(10)
        ],
    }
    projected: dict[str, Any] = present_repository_evidence(packet, format="compact")
    assert projected["groups"][0]["omitted_from_presentation"] == 5
    omitted = next(
        context
        for context in projected["source_context"]
        if context["source_ref"] == "/results/9"
    )
    assert omitted["details"]["state"] == "ambiguous"
    assert omitted["details"]["negative_evidence"] == "not-admissible"
    row = _findings(projected)[0]
    assert row["source_context"]["freshness"] == "unknown"
    assert row["source_context"]["record_qualification"]["state"] == "observed"
