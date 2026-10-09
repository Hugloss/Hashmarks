from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.lsp_relationship_adapter import CAPTURE_SCHEMA
from hashmarks.codemap.semantic_relationship_delta import semantic_relationship_delta
from hashmarks.codemap.semantic_relationship_model import content_identity
from hashmarks.digest import FILE_DOMAIN, hash_bytes
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.mcp_surface import HashmarksMcpSurface
from hashmarks.repository_intelligence_validation import (
    validate_repository_intelligence_evidence,
)

_INTERFACE = "scip-fixture python example 1 contract/Interface#"
_IMPLEMENTATION = "scip-fixture python example 1 impl/Implementation#"


def _repository(root: Path) -> None:
    (root / "contract.py").write_text("class Interface:\n    pass\n", encoding="utf-8")
    (root / "impl.py").write_text(
        "from contract import Interface\n\nclass Implementation(Interface):\n    pass\n",
        encoding="utf-8",
    )


def _revision(root: Path, path: str) -> str:
    return hash_bytes((root / path).read_bytes(), domain=FILE_DOMAIN).hash


def _provenance(
    version: int | None = 1, *, source_kind: str = "buffer"
) -> dict[str, Any]:
    return {
        "producer_session": "session:1",
        "document_lifetime": "open:1",
        "document_version": version,
        "source_kind": source_kind,
        "binding_basis": "producer-snapshot",
    }


def _capture(
    root: Path, *, method: str = "textDocument/implementation"
) -> dict[str, Any]:
    return {
        "schema": CAPTURE_SCHEMA,
        "producer": "fixture-lsp:1",
        "configuration_identity": "fixture-config:1",
        "request": {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": {
                "textDocument": {"uri": (root / "contract.py").as_uri()},
                "position": {"line": 0, "character": 7},
            },
        },
        "response": {
            "jsonrpc": "2.0",
            "id": 1,
            "result": [
                {
                    "uri": (root / "impl.py").as_uri(),
                    "range": {
                        "start": {"line": 2, "character": 6},
                        "end": {"line": 2, "character": 20},
                    },
                }
            ],
        },
        "capabilities": {
            "implementationProvider": True,
            "typeDefinitionProvider": True,
            "definitionProvider": True,
        },
        "position_encoding": "utf-16",
        "collection_state": "fresh-complete",
        "documents": {
            path: {"revision": _revision(root, path), "provenance": _provenance()}
            for path in ("contract.py", "impl.py")
        },
    }


def _index(root: Path, *, orphan: bool = False) -> Path:
    documents = []
    for path, symbol, name, line, character in (
        ("contract.py", _INTERFACE, "Interface", 0, 6),
        ("impl.py", _IMPLEMENTATION, "Implementation", 2, 6),
    ):
        relationships = (
            []
            if path == "contract.py"
            else [{"symbol": _INTERFACE, "isImplementation": True}]
        )
        documents.append(
            {
                "relativePath": path,
                "positionEncoding": 3,
                "text": (root / path).read_text(),
                "symbols": [
                    {
                        "symbol": symbol,
                        "displayName": name,
                        "kind": "Interface" if name == "Interface" else "Class",
                        "relationships": relationships,
                    }
                ],
                "occurrences": []
                if orphan and path == "impl.py"
                else [
                    {
                        "symbol": symbol,
                        "symbolRoles": 1,
                        "range": [line, character, character + len(name)],
                    }
                ],
            }
        )
    destination = root.parent / f"{root.name}-index.json"
    destination.write_text(
        json.dumps(
            {
                "metadata": {
                    "toolInfo": {"name": "fixture", "version": "1"},
                    "textDocumentEncoding": 1,
                },
                "documents": documents,
            }
        )
    )
    return destination


def _manifest(root: Path) -> dict[str, Any]:
    return {
        "configuration_identity": "fixture-config:1",
        "collection_state": "fresh-complete",
        "capabilities": {"implementation": True},
        "source_revisions": {
            path: _revision(root, path) for path in ("contract.py", "impl.py")
        },
    }


def _observe(
    cm: CodeMap, captures: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return cm.structural_locality(
        "contract.py::Interface",
        result_mode="relationships",
        supplied_observations=captures,
        refresh=False,
    )


def _claims(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        claim
        for observation in packet["observations"]
        for claim in observation["claims"]
    ]


def test_interface_query_preserves_explicit_incoming_scip_direction_and_source_bindings(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        cm.import_scip(_index(tmp_path), provenance=_manifest(tmp_path))
        packet = _observe(cm)
    claim = _claims(packet)[0]
    assert claim["source"]["key"]["symbol"] == _IMPLEMENTATION
    assert claim["target"]["key"]["symbol"] == _INTERFACE
    assert claim["source"]["source_binding"]["state"] == "matching"
    assert claim["source"]["declaration"]["kind"] == "Class"
    assert (
        claim["target"]["resolution"]["candidates"][0]["declaration"]["kind"]
        == "Interface"
    )
    assert claim["target"]["resolution"]["state"] == "unique-candidate"
    assert (
        claim["target"]["resolution"]["candidates"][0]["source_binding"]["state"]
        == "matching"
    )
    assert packet["negative_evidence_admissible"] is False
    assert validate_repository_intelligence_evidence(packet)["valid"] is True


def test_task_lsp_projection_preserves_owner_verifier_and_request_locality(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    task = "Change Interface in contract.py to document its behavior."
    with CodeMap(tmp_path) as cm:
        cm.sync()
        before: Any = cm.task_evidence(task)
        captured: Any = cm.task_evidence(
            task, supplied_observations=[_capture(tmp_path)]
        )
        after: Any = cm.task_evidence(task)
    assert captured["ownership"] == before["ownership"] == after["ownership"]
    assert captured["verification"] == before["verification"] == after["verification"]
    assert (
        "semantic_relationships" not in before and "semantic_relationships" not in after
    )
    relationships = captured["semantic_relationships"]
    assert captured["supplied_observation_accounting"]["retained"] == 1
    assert relationships["evidence"]["claims"]
    for pointer in relationships["evidence_refs"].values():
        value = captured
        for key in pointer.strip("/").split("/"):
            value = value[key]
        assert value is not None


def test_task_captures_without_an_admitted_owner_keep_exclusion_accounting(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet: Any = cm.task_evidence(
            "Investigate unknownxyz behavior",
            supplied_observations=[_capture(tmp_path)],
        )
    assert "semantic_relationships" not in packet
    assert packet["supplied_observation_accounting"]["received"] == 1
    assert packet["supplied_observation_accounting"]["omitted"] == 1
    assert (
        packet["supplied_observation_accounting"]["reason"]
        == "task-owner-or-freshness-not-qualified"
    )


def test_cli_relationship_capture_and_comparison_use_the_same_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hashmarks.cli import main

    _repository(tmp_path)
    captures = tmp_path.parent / f"{tmp_path.name}-captures.json"
    captures.write_text(json.dumps({"observations": [_capture(tmp_path)]}))
    printed = []
    monkeypatch.setattr("hashmarks.repository_cli._print", printed.append)
    monkeypatch.setenv("HASHMARKS_NO_UPDATE_CHECK", "1")
    assert (
        main(
            [
                "--workspace",
                str(tmp_path),
                "structural-locality",
                "contract.py::Interface",
                "--result-mode",
                "relationships",
                "--supplied-observations",
                str(captures),
            ]
        )
        == 0
    )
    packet = printed.pop()
    assert len(_claims(packet)) == 1
    endpoint = tmp_path.parent / f"{tmp_path.name}-endpoint.json"
    endpoint.write_text(json.dumps(packet))
    assert (
        main(
            [
                "structural-locality-delta",
                "--result-mode",
                "relationships",
                "--before",
                str(endpoint),
                "--after",
                str(endpoint),
            ]
        )
        == 0
    )
    assert printed.pop() == semantic_relationship_delta(packet, packet)


def test_warm_service_client_and_dispatch_preserve_supplied_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hashmarks.codemap.service import PROTOCOL, CodeMapService, CodeMapServiceClient

    _repository(tmp_path)
    service = CodeMapService(tmp_path)
    client = CodeMapServiceClient(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        monkeypatch.setattr(service, "_map", lambda: cm)
        monkeypatch.setattr(
            client,
            "request",
            lambda op, **payload: service.dispatch(
                {"protocol": PROTOCOL, "op": op, **payload}
            ),
        )
        task = "Change Interface in contract.py to document its behavior."
        result = client.task_evidence(task, supplied_observations=[_capture(tmp_path)])
    assert result["semantic_relationships"]["evidence"]["claims"]


@pytest.mark.host_mcp_sdk
def test_sdk_relationship_modes_and_supplied_captures_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("mcp.server")
    from hashmarks.mcp_server import build_server

    _repository(tmp_path)
    server: Any = build_server(tmp_path, state_dir=tmp_path / "state")

    async def exercise() -> None:
        response = await server.call_tool(
            "structural_locality",
            {
                "target": "contract.py::Interface",
                "result_mode": "relationships",
                "supplied_observations": [_capture(tmp_path)],
            },
        )
        assert response.is_error is not True
        packet = response.structured_content
        assert _claims(packet)
        response = await server.call_tool(
            "evidence_comparison",
            {
                "before": packet,
                "after": packet,
                "result_mode": "relationships",
                "presentation": "compact",
            },
        )
        assert response.is_error is not True
        assert response.structured_content["result"] == semantic_relationship_delta(
            packet, packet
        )

    try:
        asyncio.run(exercise())
    finally:
        server._hashmarks_surface.close()


def test_orphan_scip_claim_is_retained_without_fabricating_a_definition(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        imported = cm.import_scip(_index(tmp_path, orphan=True))
        packet = _observe(cm)
        assert (
            cm.store.native_definitions_for_symbol(
                _IMPLEMENTATION, producer="fixture:1"
            )
            == []
        )
    assert imported["unlocated_relationship_claims"] == 1
    claim = _claims(packet)[0]
    assert claim["source"]["definition_observed"] is False
    assert claim["source"]["locator"] is None
    assert claim["source"]["resolution"]["state"] == "unresolved"


def test_import_time_current_revision_cannot_hide_an_older_scip_source(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    index = _index(tmp_path)
    (tmp_path / "impl.py").write_text(
        (tmp_path / "impl.py").read_text() + "# changed after indexing\n"
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        cm.import_scip(index)
        packet = _observe(cm)
    binding = _claims(packet)[0]["source"]["source_binding"]
    assert binding["state"] == "different"
    assert binding["observed_at_import"] == binding["observed_revision"]
    assert binding["claimed_revision"] != binding["observed_revision"]


def test_scip_claims_and_qualifications_survive_reopen(tmp_path: Path) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        cm.import_scip(_index(tmp_path), provenance=_manifest(tmp_path))
        before = _observe(cm)
    with CodeMap(tmp_path) as cm:
        after = _observe(cm)
    assert after == before


def test_captured_lsp_response_is_request_local_and_preserves_both_snapshots(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    capture = _capture(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        before = _observe(cm)
        packet = _observe(cm, [capture])
        after = _observe(cm)
    assert before == after
    claim = _claims(packet)[0]
    assert claim["basis"]["direction"] == "result-to-query"
    assert claim["source"]["key"]["repository_symbol"] == "impl.py::Implementation"
    assert claim["target"]["source_binding"]["provenance"]["document_version"] == 1
    assert all(
        binding["state"] == "matching"
        for binding in packet["observations"][0]["source_bindings"]
    )
    assert validate_repository_intelligence_evidence(packet)["valid"] is True


@pytest.mark.parametrize(
    "method", ["textDocument/typeDefinition", "textDocument/definition"]
)
def test_lsp_query_to_result_relationship_kinds(tmp_path: Path, method: str) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet = _observe(cm, [_capture(tmp_path, method=method)])
    assert _claims(packet)[0]["basis"]["direction"] == "query-to-result"
    assert _claims(packet)[0]["kind"] == (
        "type_definition" if method.endswith("typeDefinition") else "definition"
    )


def test_lsp_buffer_mismatch_is_preserved_and_blocks_repository_resolution(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    capture = _capture(tmp_path)
    capture["documents"]["impl.py"] = {
        "text": "class DifferentBuffer: pass\n",
        "revision_kind": "utf8-document-text",
        "provenance": _provenance(),
    }
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet = _observe(cm, [capture])
    claim = _claims(packet)[0]
    assert claim["source"]["source_binding"]["state"] == "different"
    assert claim["source"]["resolution"]["state"] == "unresolved"
    assert claim["source"]["resolution"]["candidates"]


def test_lsp_unadmitted_document_snapshots_remain_explicitly_accounted(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    capture = _capture(tmp_path)
    capture["documents"]["ignored.py"] = {
        "revision": "a" * 64,
        "provenance": _provenance(),
    }
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet = _observe(cm, [capture])
    observation = packet["observations"][0]
    assert observation["accounting"]["documents_received"] == 3
    assert observation["accounting"]["documents_unadmitted"] == 1
    ignored = next(
        row for row in observation["source_bindings"] if row["path"] == "ignored.py"
    )
    assert ignored["state"] == "unknown"
    assert ignored["reason"] == "member-not-present"
    assert validate_repository_intelligence_evidence(packet)["valid"] is True


def test_lsp_document_version_changes_are_a_separate_delta_axis(tmp_path: Path) -> None:
    _repository(tmp_path)
    capture = _capture(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        before = _observe(cm, [capture])
        capture["documents"]["contract.py"]["provenance"]["document_version"] = 2
        after = _observe(cm, [capture])
    delta = semantic_relationship_delta(before, after)
    assert delta["comparable"] is True
    changes = delta["producer_deltas"][0]
    assert changes["facts"]["added"] == changes["facts"]["removed"] == []
    assert changes["facts"]["unchanged_count"] == 1
    assert changes["source_bindings"]["changed"] is True
    assert changes["capture"]["changed"] is True
    assert changes["claim_evidence_changes"]
    assert validate_repository_intelligence_evidence(delta)["valid"] is True


def test_lsp_null_error_partial_duplicate_and_unobserved_target_snapshots_are_visible(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    capture = _capture(tmp_path)
    location = capture["response"]["result"][0]
    capture["partial_results"] = [[location, location]]
    capture["response"]["result"] = None
    capture["collection_state"] = "fresh-partial"
    capture["documents"].pop("impl.py")
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet = _observe(cm, [capture])
        complete_capture = {**capture, "collection_state": "fresh-complete"}
        complete_packet = _observe(cm, [complete_capture])
        error = deepcopy(capture)
        error["response"] = {"id": 1, "error": {"code": -32800, "message": "cancelled"}}
        error["partial_results"] = []
        failed = _observe(cm, [error])
    observation = packet["observations"][0]
    assert observation["accounting"]["duplicates"] == 1
    assert observation["collection_state"] == "fresh-partial"
    assert _claims(packet)[0]["source"]["source_binding"]["state"] == "unknown"
    assert failed["observations"][0]["capability"]["response_error"]["code"] == -32800
    assert failed["observations"][0]["source_bindings"]
    assert _claims(failed) == []
    assert failed["negative_evidence_admissible"] is False
    complete_delta = semantic_relationship_delta(complete_packet, complete_packet)
    assert complete_delta["comparable"] is False
    assert (
        "before-source-correspondence-unproven"
        in complete_delta["incomparability_reasons"]
    )


@pytest.mark.parametrize(
    "mutation",
    ["request_id", "method", "encoding", "scope", "count", "revision", "range"],
)
def test_invalid_capture_fails_before_repository_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    _repository(tmp_path)
    capture = _capture(tmp_path)
    if mutation == "request_id":
        capture["response"]["id"] = "wrong"
    elif mutation == "method":
        capture["request"]["method"] = "textDocument/hover"
    elif mutation == "encoding":
        capture["position_encoding"] = "unknown"
    elif mutation == "scope":
        capture["documents"]["../escape.py"] = capture["documents"]["impl.py"]
    elif mutation == "count":
        capture["documents"] = {
            f"x{index}.py": capture["documents"]["impl.py"] for index in range(33)
        }
    elif mutation == "revision":
        capture["documents"]["impl.py"]["revision"] = "wrong"
    else:
        capture["response"]["result"][0]["range"]["start"]["character"] = -1
    with CodeMap(tmp_path) as cm:
        monkeypatch.setattr(
            cm,
            "sync",
            lambda *args, **kwargs: pytest.fail("invalid input reached sync"),
        )
        with pytest.raises(ValueError):
            cm.structural_locality(
                "contract.py::Interface",
                result_mode="relationships",
                supplied_observations=[capture],
            )


@pytest.mark.parametrize("format", ["structured", "compact", "text"])
def test_mcp_comparison_and_presentations_preserve_relationship_endpoints(
    tmp_path: Path, format: str
) -> None:
    _repository(tmp_path)
    surface = HashmarksMcpSurface(str(tmp_path), state_dir=str(tmp_path / "state"))
    try:
        before = surface.structural_locality(
            "contract.py::Interface",
            result_mode="relationships",
            supplied_observations=[_capture(tmp_path)],
        )
        capture = _capture(tmp_path)
        capture["response"]["result"] = None
        after = surface.structural_locality(
            "contract.py::Interface",
            result_mode="relationships",
            supplied_observations=[capture],
        )
        delta = surface.evidence_comparison(before, after, result_mode="relationships")
    finally:
        surface.close()
    projection: Any = present_repository_evidence(delta, format=format)
    findings = [row for group in projection["groups"] for row in group["findings"]]
    assert any(row["kind"] == "semantic_relationship_delta" for row in findings)
    assert any(row["kind"] == "relationship_source_binding" for row in findings)
    assert delta == semantic_relationship_delta(before, after)
    assert validate_repository_intelligence_evidence(delta)["valid"] is True


def test_relationship_tampering_is_rejected_and_delta_is_reproved(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet = _observe(cm, [_capture(tmp_path)])
    tampered = deepcopy(packet)
    tampered["observations"][0]["claims"][0]["kind"] = "definition"
    assert validate_repository_intelligence_evidence(tampered)["valid"] is False
    delta = semantic_relationship_delta(packet, packet)
    delta["producer_deltas"][0]["facts"]["unchanged_count"] = 0
    delta["evidence_identity"] = content_identity(
        {key: value for key, value in delta.items() if key != "evidence_identity"}
    )
    assert validate_repository_intelligence_evidence(delta)["valid"] is False


def test_incoming_query_does_not_expand_to_other_explicit_or_transitive_claims(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    index = _index(tmp_path)
    data = json.loads(index.read_text())
    data["documents"][1]["symbols"][0]["relationships"].append(
        {"symbol": "unrelated-symbol", "isTypeDefinition": True}
    )
    index.write_text(json.dumps(data))
    with CodeMap(tmp_path) as cm:
        cm.sync()
        cm.import_scip(index, provenance=_manifest(tmp_path))
        incoming = _observe(cm)
        direct = cm.structural_locality(
            "impl.py::Implementation", result_mode="relationships", refresh=False
        )
    assert [claim["target"]["key"]["symbol"] for claim in _claims(incoming)] == [
        _INTERFACE
    ]
    assert len(_claims(direct)) == 2


def test_scip_local_symbols_never_resolve_across_documents(tmp_path: Path) -> None:
    _repository(tmp_path)
    index = _index(tmp_path)
    data = json.loads(
        index.read_text()
        .replace(_INTERFACE, "local 0")
        .replace(_IMPLEMENTATION, "local 1")
    )
    index.write_text(json.dumps(data))
    with CodeMap(tmp_path) as cm:
        cm.sync()
        cm.import_scip(index, provenance=_manifest(tmp_path))
        assert _claims(_observe(cm)) == []
        packet = cm.structural_locality(
            "impl.py::Implementation", result_mode="relationships", refresh=False
        )
    target = _claims(packet)[0]["target"]
    assert target["key"]["document"] == "impl.py"
    assert target["resolution"]["candidates"] == []


def test_scip_line_movement_changes_locators_not_fact_identity(tmp_path: Path) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        cm.import_scip(_index(tmp_path), provenance=_manifest(tmp_path))
        before = _observe(cm)
        file = tmp_path / "impl.py"
        file.write_text("# moved declaration\n" + file.read_text())
        cm.sync()
        index = _index(tmp_path)
        data = json.loads(index.read_text())
        data["documents"][1]["occurrences"][0]["range"][0] += 1
        index.write_text(json.dumps(data))
        cm.import_scip(index, provenance=_manifest(tmp_path))
        after = _observe(cm)
    delta = semantic_relationship_delta(before, after)
    assert delta["comparable"] is True
    row = delta["producer_deltas"][0]
    assert row["facts"]["added"] == row["facts"]["removed"] == []
    assert row["facts"]["unchanged_count"] == 1
    assert len(row["locators"]) == 1
    assert row["source_bindings"]["changed"] is True


@pytest.mark.parametrize(
    "change", ["partial", "configuration", "target_snapshot", "ambiguous_capture"]
)
def test_incompatible_observations_preserve_delivered_changes_without_fact_removals(
    tmp_path: Path, change: str
) -> None:
    _repository(tmp_path)
    capture = _capture(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        before = _observe(cm, [capture])
        capture["response"]["result"] = None
        captures = [capture]
        if change == "partial":
            capture["collection_state"] = "fresh-partial"
        elif change == "configuration":
            capture["configuration_identity"] = "other-config"
        elif change == "target_snapshot":
            capture["documents"]["impl.py"]["revision"] = "a" * 64
        else:
            captures.append(deepcopy(capture))
        after = _observe(cm, captures)
    delta = semantic_relationship_delta(before, after)
    assert delta["comparable"] is False
    assert all(not row["facts"]["removed"] for row in delta["producer_deltas"])
    assert delta["before"] == before and delta["after"] == after
    assert validate_repository_intelligence_evidence(delta)["valid"] is True


@pytest.mark.parametrize(
    "encoding,units,expected",
    [
        ("utf-8", 4, 1),
        ("utf-8", 1, None),
        ("utf-16-le", 2, 1),
        ("utf-16-le", 1, None),
        ("utf-32", 1, 1),
    ],
)
def test_unicode_position_units_preserve_boundaries(
    encoding: str, units: int, expected: int | None
) -> None:
    from hashmarks.codemap.semantic_relationship_source import character_offset

    assert character_offset("𐐀Interface", units, encoding) == expected


def test_relationship_qualification_reuses_one_stable_read_per_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository(tmp_path)
    captures = [
        _capture(tmp_path),
        _capture(tmp_path, method="textDocument/definition"),
    ]
    with CodeMap(tmp_path) as cm:
        cm.sync()
        read = cm._bounded_source_observation
        observed = []

        def count(path: str, bound: int):
            observed.append(path)
            return read(path, bound)

        monkeypatch.setattr(cm, "_bounded_source_observation", count)
        packet = _observe(cm, captures)
    assert sorted(observed) == ["contract.py", "impl.py"]
    assert len(_claims(packet)) == 2


@pytest.mark.parametrize(
    "character,expected", [(6, "unique-candidate"), (21, "unresolved")]
)
def test_lsp_location_links_require_the_declaration_token_not_only_its_line(
    tmp_path: Path, character: int, expected: str
) -> None:
    _repository(tmp_path)
    capture = _capture(tmp_path)
    selection = {
        "start": {"line": 2, "character": character},
        "end": {"line": 2, "character": character + 1},
    }
    link = {
        "targetUri": (tmp_path / "impl.py").as_uri(),
        "targetRange": {
            "start": {"line": 2, "character": 0},
            "end": {"line": 3, "character": 8},
        },
        "targetSelectionRange": selection,
        "originSelectionRange": {
            "start": {"line": 0, "character": 6},
            "end": {"line": 0, "character": 15},
        },
    }
    capture["response"]["result"] = [link]
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet = _observe(cm, [capture])
    claim = _claims(packet)[0]
    assert claim["source"]["resolution"]["state"] == expected
    assert (
        claim["basis"]["captured_location"]["origin_range"]
        == link["originSelectionRange"]
    )
    assert claim["basis"]["captured_location"]["target_range"] == link["targetRange"]


def test_compact_relationship_evidence_accounts_for_claim_and_byte_bounds(
    tmp_path: Path,
) -> None:
    from hashmarks.codemap.semantic_relationship_model import compact_relationships

    _repository(tmp_path)
    capture = _capture(tmp_path)
    location = capture["response"]["result"][0]
    capture["response"]["result"] = [
        {
            **location,
            "range": {
                "start": {"line": 2, "character": index},
                "end": {"line": 2, "character": index + 1},
            },
        }
        for index in range(140)
    ]
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet = _observe(cm, [capture])
    observation = packet["observations"][0]
    assert observation["accounting"]["received"] == 140
    retained = observation["accounting"]["retained"]
    assert retained <= 128
    assert (
        retained
        + observation["accounting"]["omitted_locations"]
        + observation["accounting"].get("packet_byte_omitted_claims", 0)
        == 140
    )
    assert observation["accounting"]["omitted_locations"] == 12
    assert observation["truncated"] is True
    compact = compact_relationships(packet)
    assert len(compact["claims"]) == 8
    assert compact["omitted_from_presentation"] == retained - 8
    assert compact["qualifications"][0]["source_bindings"]
    assert validate_repository_intelligence_evidence(packet)["valid"] is True
