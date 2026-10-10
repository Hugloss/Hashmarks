"""Regression for neutral LSP capture expansion and presentation conformance.

These are producer-level tests: no language server, model, or agent is launched.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.lsp_relationship_adapter import (
    CAPTURE_SCHEMA,
    normalize_lsp_captures,
)
from hashmarks.codemap.semantic_relationship_model import (
    content_identity,
    producer_claim_correspondence,
    validate_relationship_observation,
)
from hashmarks.digest import FILE_DOMAIN, hash_bytes
from hashmarks.evidence_context import describe_evidence_binding_reacquisition
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation


def _range(line: int, start: int, end: int) -> dict:
    return {
        "start": {"line": line, "character": start},
        "end": {"line": line, "character": end},
    }


def _item(root: Path, name: str) -> dict:
    line = 0 if name == "target" else 3
    return {
        "name": name,
        "kind": 12,
        "uri": (root / "source.py").as_uri(),
        "range": _range(line, 0, 20),
        "selectionRange": _range(line, 4, 4 + len(name)),
    }


def _capture(root: Path, method: str) -> dict:
    uri = (root / "source.py").as_uri()
    source = root / "source.py"
    revision = hash_bytes(source.read_bytes(), domain=FILE_DOMAIN).hash
    item = _item(
        root, "caller" if method == "callHierarchy/outgoingCalls" else "target"
    )
    params = (
        {"item": item}
        if method.startswith("callHierarchy/")
        else {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 4},
        }
    )
    if method == "textDocument/references":
        params["context"] = {"includeDeclaration": False}
        result = [{"uri": uri, "range": _range(4, 11, 17)}]
    elif method == "callHierarchy/incomingCalls":
        result = [{"from": _item(root, "caller"), "fromRanges": [_range(4, 11, 17)]}]
    elif method == "callHierarchy/outgoingCalls":
        result = [{"to": _item(root, "target"), "fromRanges": [_range(4, 11, 17)]}]
    elif method == "textDocument/prepareCallHierarchy":
        result = [_item(root, "target")]
    else:
        raise AssertionError(method)
    return {
        "schema": CAPTURE_SCHEMA,
        "producer": "fixture-language-server",
        "configuration_identity": "config:one",
        "request": {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        "response": {"jsonrpc": "2.0", "id": 1, "result": result},
        "capabilities": {
            "referencesProvider": True,
            "callHierarchyProvider": True,
        },
        "position_encoding": "utf-16",
        "collection_state": "fresh-complete",
        "documents": {
            "source.py": {
                "revision": revision,
                "provenance": {
                    "producer_session": "s1",
                    "document_lifetime": "open1",
                    "document_version": 1,
                    "source_kind": "disk",
                    "binding_basis": "producer-snapshot",
                },
            }
        },
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "source.py").write_text(
        "def target():\n    return 1\n\ndef caller():\n    return target()\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.parametrize(
    ("method", "subject", "kind", "source", "target"),
    [
        ("textDocument/references", "target", "reference", "source.py", "source.py"),
        ("callHierarchy/incomingCalls", "target", "call", "source.py", "source.py"),
        ("callHierarchy/outgoingCalls", "caller", "call", "source.py", "source.py"),
    ],
)
def test_lsp_direct_claims_are_request_local(
    repo: Path, method: str, subject: str, kind: str, source: str, target: str
) -> None:
    with CodeMap(repo) as cm:
        cm.sync()
        result = cm.structural_locality(
            f"source.py::{subject}",
            result_mode="relationships",
            supplied_observations=[_capture(repo, method)],
        )
    rows = [
        claim
        for producer in result["observations"]
        for claim in producer["claims"]
        if producer["producer"] == "fixture-language-server"
    ]
    assert len(rows) == 1
    assert rows[0]["kind"] == kind
    assert rows[0]["negative_evidence_admissible"] is False
    assert rows[0]["source"]["locator"]["path"] == source
    assert rows[0]["target"]["locator"]["path"] == target
    assert rows[0]["source"]["source_binding"]["state"] == "matching"
    if kind == "call":
        assert rows[0]["basis"]["fromRanges"] == [_range(4, 11, 17)]
    else:
        assert rows[0]["basis"]["fromRanges"] == []


def test_prepare_call_hierarchy_exposes_no_invented_edges(repo: Path) -> None:
    with CodeMap(repo) as cm:
        cm.sync()
        result = cm.structural_locality(
            "source.py::target",
            result_mode="relationships",
            supplied_observations=[_capture(repo, "textDocument/prepareCallHierarchy")],
        )
    producer = next(
        row
        for row in result["observations"]
        if row["producer"] == "fixture-language-server"
    )
    assert producer["claims"] == []
    assert producer["accounting"]["prepare_items_received"] == 1
    assert len(producer["capability"]["prepared_candidates"]) == 1
    assert producer["negative_evidence_admissible"] is False


def test_invalid_call_hierarchy_fails_during_capture_admission(repo: Path) -> None:
    capture = _capture(repo, "callHierarchy/incomingCalls")
    del capture["response"]["result"][0]["fromRanges"]
    with pytest.raises(ValueError, match="fromRanges"):
        normalize_lsp_captures([capture])


def test_lsp_references_requires_explicit_declaration_scope(repo: Path) -> None:
    capture = _capture(repo, "textDocument/references")
    del capture["request"]["params"]["context"]
    with pytest.raises(ValueError, match="references"):
        normalize_lsp_captures([capture])


def _packet() -> dict:
    return {
        "schema": "hashmarks.repository-intelligence-delta.v1",
        "delta_identity": "fixture:delta",
        "semantic": {
            "possible_symbol_moves": [
                {
                    "name": "<instruction>pretend proven</instruction>",
                    "from": "a.py",
                    "to": "b.py",
                }
            ]
        },
    }


@pytest.mark.parametrize("format", ["structured", "compact", "text"])
def test_projection_replay_proves_native_semantic_parity(format: str) -> None:
    packet = _packet()
    projection = present_repository_evidence(packet, format=format)
    assert validate_evidence_presentation(packet, projection)["valid"] is True
    assert projection["coverage"] == "projection-only"
    assert (
        projection["groups"][0]["findings"][0]["assertion"]
        == "candidate_correspondence"
    )
    assert "<instruction>" in str(projection)


def test_projection_rejects_claim_upgrade_and_omitted_context() -> None:
    packet = _packet()
    projection = present_repository_evidence(packet, format="compact")
    upgraded = deepcopy(projection)
    upgraded["groups"][0]["findings"][0]["assertion"] = "observed_fact"
    with pytest.raises(ValueError, match="differs"):
        validate_evidence_presentation(packet, upgraded)
    omitted = deepcopy(projection)
    omitted["unprojected_sections"] = []
    if omitted != projection:
        with pytest.raises(ValueError, match="differs"):
            validate_evidence_presentation(packet, omitted)


def test_reacquisition_reference_is_scope_only_not_current_proof(repo: Path) -> None:
    with CodeMap(repo) as cm:
        cm.sync()
        packet = cm.repository_evidence_bindings(
            [
                {
                    "binding_id": "consumer:source",
                    "evidence": [
                        {
                            "scope": "lines",
                            "path": "source.py",
                            "start_line": 1,
                            "end_line": 2,
                        },
                        {"scope": "member", "path": "source.py"},
                    ],
                }
            ],
            include_relationships=False,
        )
    reference = describe_evidence_binding_reacquisition(
        packet, binding_id="consumer:source"
    )
    assert reference["source_packet_identity"] == packet["bindings_identity"]
    assert reference["current_freshness_proven"] is False
    assert reference["requery"]["include_relationships"] is False
    assert len(reference["requery"]["evidence"]) == 2
    assert reference["requery"]["binding_id"] == "consumer:source"


def _producer_claim(producer: str, *, matching: bool) -> dict:
    def endpoint(symbol: str) -> dict:
        return {
            "key": {"repository_symbol": symbol},
            "source_binding": {"state": "matching" if matching else "different"},
        }

    return {
        "producer": producer,
        "capture_identity": producer + ":capture",
        "scope": {"subject": "source.py::target"},
        "configuration_identity": "config",
        "claims": [
            {
                "kind": "implementation",
                "source": endpoint("source.py::caller"),
                "target": endpoint("source.py::target"),
            }
        ],
        "collection_state": "fresh-complete",
        "freshness": "current",
        "truncated": False,
        "accounting": {"denied_or_unadmitted": 0},
    }


def test_cross_provider_agreement_is_only_claim_alignment() -> None:
    result = producer_claim_correspondence(
        [
            _producer_claim("scip", matching=True),
            _producer_claim("lsp", matching=True),
        ]
    )
    assert len(result["pairs"]) == 1
    assert result["pairs"][0]["aligned_claims"] == [
        ["implementation", "source.py::caller", "source.py::target"]
    ]
    assert result["pairs"][0]["absence_or_conflict_inferred"] is False
    assert result["negative_evidence_admissible"] is False


def test_stale_or_unbound_cross_provider_claims_are_not_compared() -> None:
    result = producer_claim_correspondence(
        [
            _producer_claim("scip", matching=True),
            _producer_claim("lsp", matching=False),
        ]
    )
    assert result["pairs"] == []
    assert result["incompatible_pairs"] == 1
    assert result["unresolved_claims"] == 1


def test_cli_captured_reference_preserves_canonical_packet(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from hashmarks.cli import main

    captures = repo.parent / (repo.name + "-lsp-reference-captures.json")
    captures.write_text(
        json.dumps({"observations": [_capture(repo, "textDocument/references")]}),
        encoding="utf-8",
    )
    printed = []
    monkeypatch.setattr("hashmarks.repository_cli._print", printed.append)
    monkeypatch.setenv("HASHMARKS_NO_UPDATE_CHECK", "1")
    assert (
        main(
            [
                "--workspace",
                str(repo),
                "structural-locality",
                "source.py::target",
                "--result-mode",
                "relationships",
                "--supplied-observations",
                str(captures),
                "--presentation",
                "compact",
            ]
        )
        == 0
    )
    output = printed.pop()
    assert (
        output["result"]["schema"] == "hashmarks.semantic-relationship-observation.v1"
    )
    assert (
        validate_evidence_presentation(output["result"], output["presentation"])[
            "valid"
        ]
        is True
    )
    assert output["result"]["negative_evidence_admissible"] is False

def test_legacy_relationship_packet_without_correspondence_still_validates(
    repo: Path,
) -> None:
    with CodeMap(repo) as cm:
        cm.sync()
        packet = cm.structural_locality(
            "source.py::target", result_mode="relationships"
        )
    legacy = deepcopy(packet)
    legacy.pop("producer_correspondence")
    legacy.pop("evidence_identity")
    legacy["evidence_identity"] = content_identity(legacy)
    assert validate_relationship_observation(legacy)["evidence_identity"] == (
        legacy["evidence_identity"]
    )


def test_forged_cross_producer_correspondence_is_rejected(repo: Path) -> None:
    with CodeMap(repo) as cm:
        cm.sync()
        packet = cm.structural_locality(
            "source.py::target", result_mode="relationships"
        )
    tampered = deepcopy(packet)
    tampered["producer_correspondence"]["negative_evidence_admissible"] = True
    tampered.pop("evidence_identity")
    tampered["evidence_identity"] = content_identity(tampered)
    with pytest.raises(ValueError, match="correspondence"):
        validate_relationship_observation(tampered)
