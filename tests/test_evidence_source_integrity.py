"""Adversarial regressions for source-bound LSP sites and neutral packet references."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records, assert_text

from hashmarks import CodeMap
from hashmarks.codemap.semantic_relationship_model import (
    content_identity,
    validate_relationship_observation,
)
from hashmarks.digest import FILE_DOMAIN, hash_bytes
from hashmarks.evidence_context import describe_evidence_binding_reacquisition
from hashmarks.evidence_reacquisition_integrity import (
    compare_reacquisition_observation,
    validate_reacquisition_descriptor,
)


def _range(start_line: int, start: int, end_line: int, end: int) -> dict:
    return {
        "start": {"line": start_line, "character": start},
        "end": {"line": end_line, "character": end},
    }


def _item(path: Path, name: str) -> dict:
    target = name == "target"
    return {
        "name": name,
        "kind": 12,
        "uri": path.as_uri(),
        "range": _range(0, 0, 1, 12) if target else _range(3, 0, 4, 20),
        "selectionRange": _range(0, 4, 0, 10) if target else _range(3, 4, 3, 10),
    }


def _capture(path: Path, *, method: str, revision: str | None = None) -> dict:
    identity = revision or hash_bytes(path.read_bytes(), domain=FILE_DOMAIN).hash
    query = _item(path, "target" if method.endswith("incomingCalls") else "caller")
    result_item = _item(
        path, "caller" if method.endswith("incomingCalls") else "target"
    )
    key = "from" if method.endswith("incomingCalls") else "to"
    return {
        "schema": "hashmarks.lsp-relationship-capture.v1",
        "producer": "fixture-lsp",
        "configuration_identity": "config",
        "request": {
            "id": 7,
            "method": method,
            "params": {"item": query},
        },
        "response": {
            "id": 7,
            "result": [{key: result_item, "fromRanges": [_range(4, 11, 4, 17)]}],
        },
        "capabilities": {"callHierarchyProvider": True},
        "position_encoding": "utf-16",
        "collection_state": "fresh-complete",
        "documents": {
            path.name: {
                "revision": identity,
                "provenance": {
                    "producer_session": "fixture",
                    "document_lifetime": "opened",
                    "document_version": 1,
                    "source_kind": "disk",
                    "binding_basis": "producer-snapshot",
                },
            }
        },
    }


def _claim(root: Path, capture: dict, *, subject: str) -> tuple[dict, dict]:
    with CodeMap(root) as codemap:
        codemap.index.sync()
        packet = codemap.structure.locality(
            f"src.py::{subject}",
            result_mode="relationships",
            supplied_observations=[capture],
        )
    rows = [
        claim
        for observation in assert_records(packet["observations"])
        if observation["producer"] == "fixture-lsp"
        for claim in assert_records(observation["claims"])
    ]
    assert len(rows) == 1
    return packet, rows[0]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src.py").write_text(
        "def target():\n    return 1\n\ndef caller():\n    return target()\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.parametrize(
    ("method", "subject"),
    [
        ("callHierarchy/incomingCalls", "target"),
        ("callHierarchy/outgoingCalls", "caller"),
    ],
)
def test_call_site_range_matches_exact_caller_snapshot(
    repo: Path,
    method: str,
    subject: str,
) -> None:
    _packet, claim = _claim(
        repo, _capture(repo / "src.py", method=method), subject=subject
    )
    site = claim["basis"]["call_site_source"]
    assert site["path"] == "src.py"
    assert site["source_binding"]["state"] == "matching"
    assert site["state"] == "source-range-matching"
    assert site["negative_evidence_admissible"] is False
    assert site["ranges"] == claim["basis"]["fromRanges"]


def test_empty_call_site_result_cannot_claim_range_correspondence(
    repo: Path,
) -> None:
    capture = _capture(repo / "src.py", method="callHierarchy/incomingCalls")
    capture["response"]["result"][0]["fromRanges"] = []
    _packet, claim = _claim(repo, capture, subject="target")
    assert claim["basis"]["call_site_source"]["state"] == "empty-call-sites"
    assert claim["basis"]["call_site_source"]["negative_evidence_admissible"] is False


def test_stale_source_does_not_become_qualified_call_site(repo: Path) -> None:
    capture = _capture(
        repo / "src.py", method="callHierarchy/incomingCalls", revision="0" * 64
    )
    _packet, claim = _claim(repo, capture, subject="target")
    site = claim["basis"]["call_site_source"]
    assert site["state"] == "revision-different"
    assert site["source_binding"]["state"] == "different"
    assert "declaration_context" not in site


def test_range_outside_caller_is_not_a_current_call_site(repo: Path) -> None:
    capture = _capture(repo / "src.py", method="callHierarchy/incomingCalls")
    capture["response"]["result"][0]["fromRanges"] = [_range(1, 4, 1, 10)]
    _packet, claim = _claim(repo, capture, subject="target")
    assert claim["basis"]["call_site_source"]["state"] == "outside-caller-item"


def test_short_producer_item_preserves_independent_source_declaration_context(
    repo: Path,
) -> None:
    capture = _capture(repo / "src.py", method="callHierarchy/incomingCalls")
    item = capture["response"]["result"][0]["from"]
    item["range"] = item["selectionRange"]
    _packet, claim = _claim(repo, capture, subject="target")
    site = claim["basis"]["call_site_source"]
    assert site["state"] == "outside-caller-item"
    context = site["declaration_context"]
    assert context["state"] == "within-declaration-range"
    assert context["symbol_id"] == "src.py::caller"
    assert context["authority"] == "indexed-lexical-range-correspondence-only"
    assert context["negative_evidence_admissible"] is False
    assert claim["basis"]["captured_location"]["item"]["range"] == item["range"]


def test_source_declaration_context_does_not_accept_another_function_body(
    repo: Path,
) -> None:
    capture = _capture(repo / "src.py", method="callHierarchy/incomingCalls")
    capture["response"]["result"][0]["fromRanges"] = [_range(1, 4, 1, 10)]
    _packet, claim = _claim(repo, capture, subject="target")
    site = claim["basis"]["call_site_source"]
    assert site["state"] == "outside-caller-item"
    assert site["declaration_context"]["state"] == "outside-declaration-range"


def test_out_of_bounds_position_is_not_qualified(repo: Path) -> None:
    capture = _capture(repo / "src.py", method="callHierarchy/incomingCalls")
    capture["response"]["result"][0]["from"]["range"]["end"] = {
        "line": 90,
        "character": 1,
    }
    capture["response"]["result"][0]["fromRanges"] = [_range(4, 11, 4, 900)]
    _packet, claim = _claim(repo, capture, subject="target")
    assert claim["basis"]["call_site_source"]["state"] == "invalid-position"


def test_source_site_authority_cannot_be_forged_with_recomputed_digests(
    repo: Path,
) -> None:
    packet, _claim_row = _claim(
        repo,
        _capture(repo / "src.py", method="callHierarchy/incomingCalls"),
        subject="target",
    )
    forged = deepcopy(packet)
    observation = next(
        row for row in forged["observations"] if row["producer"] == "fixture-lsp"
    )
    claim = observation["claims"][0]
    claim["basis"]["call_site_source"]["negative_evidence_admissible"] = True
    claim["identity"] = content_identity(
        {
            "producer": claim["producer"],
            "kind": claim["kind"],
            "source": claim["source"]["key"],
            "target": claim["target"]["key"],
        }
    )
    observation["observation_identity"] = content_identity(
        {k: v for k, v in observation.items() if k != "observation_identity"}
    )
    forged["evidence_identity"] = content_identity(
        {k: v for k, v in forged.items() if k != "evidence_identity"}
    )
    with pytest.raises(ValueError, match="call-site"):
        validate_relationship_observation(forged)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authority", "exact-runtime-caller"),
        ("negative_evidence_admissible", True),
        ("state", "outside-declaration-range"),
        ("symbol_id", "elsewhere.py::caller"),
        (
            "declaration_range",
            {
                "start": {"line": True, "character": 0},
                "end": {"line": 8, "character": 0},
            },
        ),
    ],
)
def test_declaration_context_cannot_be_strengthened_by_rehashing(
    repo: Path, field: str, value: object
) -> None:
    packet, _ = _claim(
        repo,
        _capture(repo / "src.py", method="callHierarchy/incomingCalls"),
        subject="target",
    )
    forged = deepcopy(packet)
    observation = next(
        row for row in forged["observations"] if row["producer"] == "fixture-lsp"
    )
    site = observation["claims"][0]["basis"]["call_site_source"]
    site["declaration_context"][field] = value
    observation["observation_identity"] = content_identity(
        {
            key: item
            for key, item in observation.items()
            if key != "observation_identity"
        }
    )
    forged["evidence_identity"] = content_identity(
        {key: item for key, item in forged.items() if key != "evidence_identity"}
    )
    with pytest.raises(ValueError):
        validate_relationship_observation(forged)


def _source_binding(root: Path, *, include_relationships: bool = False) -> dict:
    with CodeMap(root) as codemap:
        codemap.index.sync()
        return codemap.bindings.observe(
            [
                {
                    "binding_id": "source:entry",
                    "evidence": [
                        {
                            "scope": "lines",
                            "path": "src.py",
                            "start_line": 1,
                            "end_line": 1,
                        }
                    ],
                }
            ],
            include_relationships=include_relationships,
        )


def test_reacquisition_descriptor_preserves_exact_scope_and_identity(
    repo: Path,
) -> None:
    packet = _source_binding(repo)
    desc = describe_evidence_binding_reacquisition(packet, binding_id="source:entry")
    assert validate_reacquisition_descriptor(desc) == desc
    assert assert_text(desc["descriptor_identity"]).startswith("sha256:")
    assert desc["current_freshness_proven"] is False
    comparison = compare_reacquisition_observation(desc, packet)
    assert comparison["definition_correspondence"] == "matching-claim"
    assert comparison["observation_correspondence"] == "matching-claim"
    assert comparison["current_freshness_proven"] is False


def test_modified_reacquisition_selector_is_rejected(repo: Path) -> None:
    desc = describe_evidence_binding_reacquisition(
        _source_binding(repo), binding_id="source:entry"
    )
    forged = deepcopy(desc)
    assert_records(assert_object(forged["requery"])["evidence"])[0]["end_line"] = 2
    with pytest.raises(ValueError, match="identity"):
        validate_reacquisition_descriptor(forged)


def test_reacquisition_does_not_claim_current_on_changed_member(repo: Path) -> None:
    before = _source_binding(repo)
    desc = describe_evidence_binding_reacquisition(before, binding_id="source:entry")
    (repo / "src.py").write_text(
        "def target():  # changed\n    return 1\n\ndef caller():\n    return target()\n",
        encoding="utf-8",
    )
    after = _source_binding(repo)
    comparison = compare_reacquisition_observation(desc, after)
    assert comparison["definition_correspondence"] == "matching-claim"
    assert comparison["observation_correspondence"] == "different-or-unknown"
    assert comparison["current_freshness_proven"] is False


def test_reacquisition_rejects_unknown_authority(repo: Path) -> None:
    desc = describe_evidence_binding_reacquisition(
        _source_binding(repo), binding_id="source:entry"
    )
    desc["current_freshness_proven"] = True
    with pytest.raises(ValueError, match="authority"):
        validate_reacquisition_descriptor(desc)
