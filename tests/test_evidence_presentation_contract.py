from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
from collections.abc import Callable, Mapping
from itertools import product
from pathlib import Path
from typing import TYPE_CHECKING, Never

import pytest
from contract_assertions import assert_array, assert_object, assert_records, assert_text

from hashmarks.codemap import CodeMap
from hashmarks.codemap.diagnostic_observation import (
    diagnostic_observation_delta,
    external_diagnostic_observation,
)
from hashmarks.codemap.repository_delta import (
    RepositoryGenerationBinding,
)
from hashmarks.codemap.repository_intelligence_query import (
    QUERY_SURFACES,
    RepositoryIntelligenceQueryOptions,
)
from hashmarks.codemap.semantic_relationship_delta import semantic_relationship_delta
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient
from hashmarks.codemap.static_python_backend_declarations import (
    StaticPythonBackendDeclarations,
)
from hashmarks.codemap.structural_locality_delta import structural_locality_delta
from hashmarks.evidence_presentation import (
    FORMATS,
    present_repository_evidence,
    presentation_response,
)
from hashmarks.mcp_contract import (
    MCP_TOOL_CONTRACTS,
    McpToolContract,
    contract_from_tool_models,
    tool_contract,
)
from hashmarks.mcp_server import _call_surface, build_server
from hashmarks.mcp_surface import HashmarksMcpSurface
from hashmarks.operation_contract import operation_schema

if TYPE_CHECKING:
    from mcp.server import MCPServer
    from mcp.types import CallToolResult

_MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None


def _sdk_server(value: object) -> MCPServer:
    from mcp.server import MCPServer

    assert isinstance(value, MCPServer)
    return value


def _server_surface(server: object) -> HashmarksMcpSurface:
    surface = getattr(server, "_hashmarks_surface", None)
    assert isinstance(surface, HashmarksMcpSurface)
    return surface


def _content_text(part: object) -> str:
    from mcp.types import TextContent

    assert isinstance(part, TextContent)
    return part.text


def _tool_reply(value: object) -> CallToolResult:
    from mcp.types import CallToolResult

    assert isinstance(value, CallToolResult)
    return value


def _findings(projection: dict[str, object]) -> list[dict[str, object]]:
    return [
        row
        for group in assert_records(projection["groups"])
        for row in assert_records(group["findings"])
    ]


def _fixture_diagnostic_delta(paths: list[str]) -> dict[str, object]:
    """Use one exact externally claimed endpoint without another analyzer."""
    external = external_diagnostic_observation(
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
    return diagnostic_observation_delta(external, external)


@pytest.fixture(scope="module")
def native_packets(
    tmp_path_factory: pytest.TempPathFactory,
) -> list[tuple[str, str, Mapping[str, object]]]:
    root = tmp_path_factory.mktemp("presentation")
    (root / "src").mkdir()
    (root / "tests").mkdir()
    owner = root / "src" / "owner.py"
    owner.write_text("import os\ndef widget(): return 1\n", encoding="utf-8")
    (root / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\ndef test_widget(): assert widget() == 1\n",
        encoding="utf-8",
    )
    (root / "src" / "observed.ts").write_text(
        "const client = transport; client.send();\n", encoding="utf-8"
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
        codemap.index.sync()
        snapshot = codemap.changes.snapshot(task, paths)
        previous = codemap.tasks.evidence(task)
        binding = codemap.bindings.observe(
            [
                {
                    "binding_id": "one",
                    "evidence": [{"path": paths[0], "start_line": 2, "end_line": 2}],
                }
            ]
        )
        observation = codemap.dependencies.observe(dependency)
        declarations = codemap.declarations.observe([group])
        locality = codemap.structure.locality("src/owner.py::widget")
        packets: list[tuple[str, str, Mapping[str, object]]] = [
            ("repository_context", "default", codemap.context.orient()),
            ("find", "default", codemap.search.packet("widget")),
            ("task_evidence", "default", previous),
            (
                "task_evidence",
                "initial",
                codemap.tasks.evidence(task, result_mode="initial"),
            ),
            ("change_impact", "default", codemap.changes.task_impact(task, paths)),
            ("correlate_evidence", "default", codemap.correlation.observe([bundle])),
            (
                "dependency_codemap",
                "observation",
                codemap.dependencies.codemap(dependency),
            ),
            (
                "dependency_codemap",
                "explain",
                codemap.dependencies.explain(observation),
            ),
            (
                "dependency_codemap",
                "compare",
                codemap.dependencies.delta(observation, observation),
            ),
            ("repository_declarations", "observation", declarations),
            (
                "repository_declarations",
                "discovery",
                codemap.declarations.operation(
                    [],
                    result_mode="discovery",
                    providers=(StaticPythonBackendDeclarations(paths=(paths[0],)),),
                ),
            ),
            (
                "repository_declarations",
                "explain",
                codemap.declarations.explain(declarations),
            ),
            (
                "source_observation",
                "member",
                codemap.source.observe(paths[0], literal="widget"),
            ),
            (
                "source_observation",
                "scope",
                codemap.source.scoped_occurrences(paths, literal="widget"),
            ),
            (
                "source_observation",
                "literals",
                codemap.source.scoped_literals(paths, ["widget", "missing"]),
            ),
            (
                "source_observation",
                "range",
                codemap.source.range_receipt(paths[0], start_byte=0, end_byte=6),
            ),
            (
                "source_observation",
                "ecmascript",
                codemap.source.ecmascript("src/observed.ts"),
            ),
            ("repository_evidence", "observation", binding),
            (
                "repository_evidence",
                "membership",
                codemap.verification.observe_membership(
                    {
                        "schema": "hashmarks.verification-membership-report.v1",
                        "selection_kind": "caller-selected",
                        "producer": {"name": "fixture"},
                        "provenance": {},
                        "scope": {"paths": paths},
                        "status": "succeeded",
                        "completeness": "complete",
                        "truncation": "complete",
                        "members": [{"path": paths[0]}],
                        "inputs": [{"path": paths[0], "member_revision": None}],
                    }
                ),
            ),
            (
                "repository_evidence",
                "coverage",
                codemap.bindings.coverage(
                    binding, changed_paths=paths, change_set_complete=False
                ),
            ),
            ("repository_findings", "default", codemap.ownership.findings()),
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
                codemap.bindings.delta(binding, binding),
            ),
            (
                "evidence_comparison",
                "diagnostics",
                _fixture_diagnostic_delta(paths),
            ),
        ]
        packets.append(
            (
                "structural_locality",
                "relationships",
                codemap.structure.locality(
                    "src/owner.py::widget", result_mode="relationships"
                ),
            )
        )
        packets.append(
            (
                "evidence_comparison",
                "relationships",
                semantic_relationship_delta(packets[-1][2], packets[-1][2]),
            )
        )
        owner.write_text("import sys\ndef widget(): return 2\n", encoding="utf-8")
        packets.append(
            (
                "post_change",
                "default",
                codemap.changes.task_delta(task, paths, previous_evidence=previous),
            )
        )
        packets.append(
            (
                "evidence_comparison",
                "structural",
                structural_locality_delta(
                    locality, codemap.structure.locality("src/owner.py::widget")
                ),
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
                        codemap.views.query(
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
    native_packets: list[tuple[str, str, Mapping[str, object]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert {
        (contract.operation, mode)
        for contract in MCP_TOOL_CONTRACTS
        for mode in contract.response_modes
    } <= {(operation, mode) for operation, mode, _packet in native_packets}

    def no_read(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError("presentation must not read repository files")

    monkeypatch.setattr(Path, "read_bytes", no_read)
    monkeypatch.setattr(Path, "read_text", no_read)
    for operation, mode, native in native_packets:
        before = copy.deepcopy(native)
        for format in FORMATS:
            response: dict[str, object] = presentation_response(
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
            assert assert_object(response["presentation"])["supported"] is True
            assert (
                assert_object(response["presentation"])["coverage"] == "projection-only"
            )
        assert native == before


def test_source_refs_point_to_exact_records_and_details_are_independent(
    native_packets: list[tuple[str, str, Mapping[str, object]]],
) -> None:
    for operation, _mode, native in native_packets:
        source = (
            assert_object(native["result"])
            if operation == "repository_intelligence_query"
            else native
        )
        projected: dict[str, object] = present_repository_evidence(
            source, format="structured"
        )
        for row in _findings(projected):
            if projected.get("reference_space") == "decoded-initial-data":
                from scripts.repository_evaluation.fact_grading import pointer_values

                values = pointer_values(
                    source, assert_text(assert_array(row["source_refs"])[0])
                )
                assert len(values) == 1
                value = values[0]
                # Initial locators explicitly retain display fields. Check each
                # field against the decoded source record, including typed
                # collection decoding, rather than following wire-table keys.
                if isinstance(row["details"], dict):
                    assert all(
                        assert_object(value)[key] == item
                        for key, item in row["details"].items()
                    )
                else:
                    assert row["details"] == value
                continue
            value: object = source
            pointer = assert_text(assert_array(row["source_refs"])[0])
            for part in pointer.split("/")[1:] if pointer else ():
                key = part.replace("~1", "/").replace("~0", "~")
                value = (
                    assert_array(value)[int(key)]
                    if isinstance(value, list)
                    else assert_object(value)[key]
                )
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
                assert_object(row["details"])["mutation"] = True
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
    projected: dict[str, object] = present_repository_evidence(delta, format="text")
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
        assert expected in assert_text(projected["text"])
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
    claim: dict[str, object] = present_repository_evidence(dependency, format="text")
    assert all(row["assertion"] == "producer_claim" for row in _findings(claim))
    assert claim["source_evidence_identity"] is None
    assert (
        assert_object(claim["source_identities"])["before_observation_identity"]
        == "old"
    )
    assert "not-comparable" in assert_text(
        claim["text"]
    ) and '"version":"2"' in assert_text(claim["text"])


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
        result: dict[str, object] = present_repository_evidence(packet, format=format)
        group = assert_records(result["groups"])[0]
        assert len(assert_array(group["findings"])) == selected
        assert group["omitted_from_presentation"] == 60 - selected
        assert (
            assert_object(
                assert_object(assert_records(result["source_context"])[0])["details"]
            )["negative_evidence"]
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
    empty: dict[str, object] = present_repository_evidence(
        {"schema": operation_schema("find"), "results": []}, format="text"
    )
    assert "No displayed findings in this projection" in assert_text(empty["text"])


def test_mcp_rejects_invalid_presentation_before_producer_and_wrapper_drift() -> None:
    calls = []

    def producer() -> dict[str, object]:
        calls.append(True)
        return {"schema": operation_schema("find"), "results": []}

    with pytest.raises(ValueError, match="presentation must be"):
        _call_surface(
            tool_contract("find"), ValueError, producer, presentation="invalid"
        )
    assert not calls
    response: dict[str, object] = _call_surface(
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
        assert_object(changed["presentation"])[key] = value
        with pytest.raises(RuntimeError, match="drift"):
            tool_contract("find").validate_response(changed, presentation="compact")


@pytest.mark.host_mcp_sdk
@pytest.mark.skipif(not _MCP_AVAILABLE, reason="MCP extra is not installed")
def test_actual_sdk_advertises_all_format_selectors(tmp_path: Path) -> None:
    server = _sdk_server(build_server(tmp_path, state_dir=tmp_path / "state"))
    try:
        tools = asyncio.run(server.list_tools())
        manifest: dict[str, object] = contract_from_tool_models("test", tuple(tools))
        assert len(assert_array(manifest["tools"])) == 14
        for tool, contract in zip(tools, MCP_TOOL_CONTRACTS, strict=True):
            field = assert_object(
                assert_object(tool.input_schema["properties"])["presentation"]
            )
            assert field["enum"] == list(FORMATS)
            assert field["default"] == contract.default_presentation
    finally:
        _server_surface(server).close()


def test_service_transports_presentation_and_rejects_older_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = {}

    class Views:
        def query(
            self,
            _surface: str,
            _task: str,
            _paths: list[str],
            *,
            options: RepositoryIntelligenceQueryOptions,
        ) -> dict[str, object]:
            captured["options"] = options
            return {
                "schema": operation_schema("repository_intelligence_query"),
                "presentation": {"format": options.presentation},
            }

    class Map:
        views = Views()

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
        assert assert_object(response["presentation"])["format"] == format
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
    native_packets: list[tuple[str, str, Mapping[str, object]]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hashmarks.codemap.repository_intelligence_query import (
        repository_query_response,
    )

    packets = {(operation, mode): packet for operation, mode, packet in native_packets}
    server = _sdk_server(build_server(tmp_path, state_dir=tmp_path / "state"))
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

    def frozen_producer(contract: McpToolContract) -> Callable[..., object]:
        def response(*_args: object, **kwargs: object) -> object:
            native = packets[
                contract.operation,
                assert_text(kwargs.get("result_mode", contract.default_response_mode)),
            ]
            if contract.operation == "repository_intelligence_query":
                return repository_query_response(
                    assert_text(native["surface"]),
                    assert_object(native["result"]),
                    presentation=assert_text(kwargs["presentation"]),
                )
            return native

        return response

    for contract in MCP_TOOL_CONTRACTS:
        monkeypatch.setattr(
            _server_surface(server), contract.name, frozen_producer(contract)
        )

    async def exercise() -> None:
        for contract in MCP_TOOL_CONTRACTS:
            default = _tool_reply(
                await server.call_tool(contract.name, arguments[contract.name])
            )
            native = packets[contract.operation, contract.default_response_mode]
            expected = presentation_response(
                contract.operation,
                native,
                format=contract.default_presentation,
                result_mode=contract.default_response_mode,
            )
            assert default.structured_content == expected
            for mode, format in product(contract.response_modes, FORMATS):
                request = {
                    **arguments[contract.name],
                    "presentation": format,
                    **(
                        {"result_mode": mode}
                        if len(contract.response_modes) > 1
                        else {}
                    ),
                }
                called = _tool_reply(await server.call_tool(contract.name, request))
                _assert_mode_delivery(
                    contract, called, packets[contract.operation, mode], mode, format
                )

    try:
        asyncio.run(exercise())
    finally:
        _server_surface(server).close()


def _assert_task_json_mirror(operation: str, reply: CallToolResult) -> None:
    if operation != "task_evidence":
        return
    texts = [part.text for part in reply.content if part.type == "text"]
    assert texts == [
        json.dumps(
            reply.structured_content,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    ]


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
    result: dict[str, object] = present_repository_evidence(diagnostic, format="text")
    finding = _findings(result)[0]
    assert finding["details"] == record
    assert finding["assertion"] == "producer_claim"
    assert result["source_evidence_identity"] is None
    assert "example-rule" in assert_text(
        result["text"]
    ) and "line one\\nline two" in assert_text(result["text"])
    assert "incomplete" in assert_text(result["text"])
    snapshot = {
        "schema": "hashmarks.repository-intelligence-snapshot.v1",
        "paths": {"a~/b.py": {"member_state": "unknown", "revision": "exact-revision"}},
    }
    projection: dict[str, object] = present_repository_evidence(snapshot)
    rows = _findings(projection)
    assert assert_object(rows[0])["source_refs"] == ["/paths/a~0~1b.py/revision"]
    assert assert_object(rows[1])["details"] == "unknown"
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
    projected: dict[str, object] = present_repository_evidence(packet, format="compact")
    assert (
        assert_object(assert_records(projected["groups"])[0])[
            "omitted_from_presentation"
        ]
        == 5
    )
    omitted = next(
        context
        for context in assert_records(projected["source_context"])
        if context["source_ref"] == "/results/9"
    )
    assert assert_object(omitted["details"])["state"] == "ambiguous"
    assert assert_object(omitted["details"])["negative_evidence"] == "not-admissible"
    row = _findings(projected)[0]
    assert assert_object(row["source_context"])["freshness"] == "unknown"
    assert (
        assert_object(assert_object(row["source_context"])["record_qualification"])[
            "state"
        ]
        == "observed"
    )


def _assert_initial_delivery(
    called: CallToolResult, native: Mapping[str, object], format: str
) -> None:
    assert called.structured_content == native
    text = _content_text(called.content[0])
    display = "text" if format == "none" else format
    projected = present_repository_evidence(native, format=display)
    assert (text if display == "text" else json.loads(text)) == (
        assert_text(projected["text"]) if display == "text" else projected
    )


def _assert_mode_delivery(
    contract: McpToolContract,
    called: CallToolResult,
    native: Mapping[str, object],
    mode: str,
    format: str,
) -> None:
    initial = contract.operation == "task_evidence" and mode == "initial"
    contract.validate_response(
        called.structured_content,
        result_mode=mode,
        presentation="none" if initial else format,
    )
    if initial:
        _assert_initial_delivery(called, native, format)
    else:
        assert called.structured_content == presentation_response(
            contract.operation,
            native,
            format=format,
            result_mode=mode,
        )
        _assert_task_json_mirror(contract.operation, called)
