"""Shared evidence contracts survive projection and untrusted JSON transport."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.ownership_candidates import OwnershipCandidatesMixin
from hashmarks.codemap.ownership_relation_types import (
    OwnershipRelationGraph,
    StructuralOwnerCandidate,
)
from hashmarks.codemap.service import CodeMapServiceClient
from hashmarks.codemap.task_evidence_contract import (
    read_initial_projection,
    read_ownership_relation_graph,
    read_post_change_delta,
    read_task_action_map,
    read_task_evidence,
)
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_packet,
    encode_initial_packet,
)
from hashmarks.codemap.task_evidence_types import (
    InitialTaskEvidenceEnvelope,
    TaskActionMap,
    TaskEvidencePacket,
    TaskPostChangeDelta,
)

_TASK = "Change owner.py widget behavior and verify widget test"


@dataclass(frozen=True)
class _Samples:
    graph: OwnershipRelationGraph
    action: TaskActionMap
    packet: TaskEvidencePacket
    initial: InitialTaskEvidenceEnvelope
    delta: TaskPostChangeDelta


@pytest.fixture(scope="module")
def samples(tmp_path_factory: pytest.TempPathFactory) -> _Samples:
    root = tmp_path_factory.mktemp("task-contract")
    _repo(root)
    with _codemap(root) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence(_TASK)
        return _Samples(
            graph=codemap.ownership.relations(_TASK, "tests/test_owner.py"),
            action=codemap.tasks.action_map(_TASK),
            packet=packet,
            initial=codemap.tasks.evidence(_TASK, result_mode="initial"),
            delta=codemap.changes.task_delta(
                _TASK, ["owner.py"], previous_evidence=packet
            ),
        )


def _repo(root: Path) -> None:
    (root / "owner.py").write_text("def widget(value): return value.strip()\n")
    (root / "tests").mkdir()
    (root / "tests/test_owner.py").write_text(
        "from owner import widget\ndef test_widget(): assert widget(' a ') == 'a'\n"
    )
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n"
    )


def _codemap(root: Path) -> CodeMap:
    return CodeMap(
        root, state_dir=root / ".hashmarks", artifact_db=root / "artifacts.sqlite"
    )


_READERS: tuple[tuple[str, Callable[[object], Mapping[str, object]]], ...] = (
    ("graph", read_ownership_relation_graph),
    ("action", read_task_action_map),
    ("packet", read_task_evidence),
    ("delta", read_post_change_delta),
)


@pytest.mark.parametrize(("name", "reader"), _READERS)
def test_readers_preserve_json_values_and_extension_evidence(
    samples: _Samples, name: str, reader: Callable[[object], Mapping[str, object]]
) -> None:
    payload: dict[str, object] = json.loads(json.dumps(getattr(samples, name)))
    payload["producer_extension"] = {
        "state": "unknown",
        "observations": [None, False, "é"],
    }
    before = deepcopy(payload)
    result = reader(payload)
    assert result is payload
    assert result == before


@pytest.mark.parametrize(
    ("name", "reader", "path", "invalid"),
    [
        ("graph", read_ownership_relation_graph, ("owner_path",), ["owner.py"]),
        ("graph", read_ownership_relation_graph, ("owner_path", 0, "relation"), 5),
        ("graph", read_ownership_relation_graph, ("edges", 0, "cycle"), "false"),
        ("action", read_task_action_map, ("action_discrimination", "needed"), "false"),
        (
            "action",
            read_task_action_map,
            ("exact_identifier_search", "bound_reasons"),
            [False],
        ),
        (
            "action",
            read_task_action_map,
            ("ownership_decision_trace", "evidence_state", "proven"),
            "true",
        ),
        (
            "action",
            read_task_action_map,
            ("ownership_authority", "evidence_state", "proven"),
            "true",
        ),
        ("action", read_task_action_map, ("edit", "start_line"), False),
        (
            "action",
            read_task_action_map,
            ("verification_relevance", "verifier_identity_ambiguous"),
            1,
        ),
        (
            "action",
            read_task_action_map,
            ("verification_relevance", "verifier_identity_ambiguous"),
            0,
        ),
        (
            "packet",
            read_task_evidence,
            ("verification", "relevance", "verifier_identity_ambiguous"),
            "true",
        ),
        (
            "packet",
            read_task_evidence,
            ("verification", "relevance", "verifier_identity_ambiguous"),
            1.0,
        ),
        (
            "packet",
            read_task_evidence,
            ("ownership", "source_budget", "complete"),
            "false",
        ),
        (
            "packet",
            read_task_evidence,
            ("ownership", "source_budget", "estimated_tokens"),
            True,
        ),
        ("packet", read_task_evidence, ("verification", "plan", "argv"), ["pytest", 7]),
        ("packet", read_task_evidence, ("provenance", "context_identity"), None),
        ("packet", read_task_evidence, ("retrieval", "results", 0, "path"), False),
        ("delta", read_post_change_delta, ("generation_after",), True),
        ("delta", read_post_change_delta, ("path_changes", 0, "state"), None),
    ],
)
def test_readers_reject_malformed_nested_fields(
    samples: _Samples,
    name: str,
    reader: Callable[[object], Mapping[str, object]],
    path: tuple[str | int, ...],
    invalid: object,
) -> None:
    payload: dict[str, object] = json.loads(json.dumps(getattr(samples, name)))
    _replace(payload, path, invalid)
    with pytest.raises(RuntimeError, match="invalid .*"):
        reader(payload)


def _replace(
    value: dict[str, object], path: tuple[str | int, ...], item: object
) -> None:
    cursor: object = value
    for key in path[:-1]:
        cursor = _descend(cursor, key)
    key = path[-1]
    if isinstance(key, int):
        assert isinstance(cursor, list)
        cursor[key] = item
    else:
        assert isinstance(cursor, dict)
        cursor[key] = item


def test_reader_distinguishes_missing_required_fields_from_null(
    samples: _Samples,
) -> None:
    packet = deepcopy(samples.packet)
    packet["explicit_target"]["symbol"] = None
    assert read_task_evidence(packet) is packet
    raw: dict[str, object] = json.loads(json.dumps(packet))
    del raw["freshness"]
    with pytest.raises(RuntimeError, match="task_evidence.freshness"):
        read_task_evidence(raw)


def test_reader_checks_changed_role_replacements(samples: _Samples) -> None:
    delta: dict[str, object] = json.loads(json.dumps(samples.delta))
    delta["replacement"] = {
        "ownership": {**samples.packet["ownership"], "source_budget": {}}
    }
    with pytest.raises(RuntimeError, match="replacement.ownership.source_budget"):
        read_post_change_delta(delta)


def test_initial_projection_reader_preserves_encoded_candidates_and_omissions(
    samples: _Samples,
) -> None:
    decoded = decode_initial_packet(samples.initial)
    before = deepcopy(decoded)
    initial = read_initial_projection(decoded)
    assert initial == before
    assert (
        initial["source_evidence_identity"]
        == samples.packet["evidence_packet_identity"]
    )
    assert "related" not in initial
    counts = initial["initial_projection"]["omissions"]["collections"]
    assert counts["/verification/relevance/candidates"]["omitted"] == 0
    if initial["ownership"]["source_evidence"] is not None:
        assert "content" not in initial["ownership"]["source_evidence"]


@pytest.mark.parametrize("missing", ["encoding", "columns"])
def test_initial_projection_reader_rejects_malformed_candidate_tables(
    samples: _Samples, missing: str
) -> None:
    decoded = decode_initial_packet(samples.initial)
    relevance = decoded["verification"]["relevance"]
    relevance["candidates_encoding"] = {"kind": "columns-rows.v1", "columns": ["path"]}
    relevance["candidates"] = [["tests/test_owner.py"]]
    if missing == "columns":
        del relevance["candidates_encoding"]["columns"]
    else:
        relevance["candidates_encoding"]["kind"] = "unknown"
    with pytest.raises(RuntimeError, match="initial.verification.relevance.candidates"):
        read_initial_projection(decoded)


def test_service_client_uses_checked_shared_contracts(
    samples: _Samples, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses: dict[str, dict[str, object]] = {
        "task_action_map": {"action_map": samples.action},
        "ownership_relation_graph": {"ownership_relation_graph": samples.graph},
        "task_evidence": {"task_evidence": samples.packet},
        "task_post_change_delta": {"post_change_delta": samples.delta},
    }

    def request(op: str, **payload: object) -> dict[str, object]:
        return responses[op]

    client = CodeMapServiceClient(tmp_path)
    monkeypatch.setattr(client, "request", request)
    assert client.task_action_map(_TASK) == samples.action
    assert (
        client.ownership_relation_graph(_TASK, "tests/test_owner.py") == samples.graph
    )
    assert client.task_evidence(_TASK) == samples.packet
    assert (
        client.task_post_change_delta(
            _TASK, ["owner.py"], previous_evidence=samples.packet
        )
        == samples.delta
    )
    responses["task_evidence"] = {
        "task_evidence": {**samples.packet, "freshness": "current"}
    }
    with pytest.raises(RuntimeError, match="task_evidence.freshness"):
        client.task_evidence(_TASK)


def test_dictionary_input_contract_rejects_read_only_mapping_before_sync(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with _codemap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence(_TASK)
        proxy = MappingProxyType(packet)
        (tmp_path / "owner.py").write_text("def widget(value): return value.lower()\n")
        generation = codemap.store.generation()
        # Exercise a malformed runtime caller; static consumers use the exact API.
        with pytest.raises(ValueError, match="hashmarks.task-evidence.v5 packet"):
            _call_with_previous(codemap.changes.task_delta, proxy)
        assert codemap.store.generation() == generation
        result = codemap.changes.task_delta(
            _TASK, ["owner.py"], previous_evidence=dict(proxy)
        )
        assert result["change"] == "changed"


def _call_with_previous(operation: Callable[..., object], previous: object) -> object:
    """Model an untyped runtime caller without weakening valid static examples."""
    return operation(_TASK, ["owner.py"], previous_evidence=previous)


def _descend(value: object, key: str | int) -> object:
    if isinstance(key, int):
        assert isinstance(value, list)
        return value[key]
    assert isinstance(value, dict)
    return value[key]


@pytest.mark.parametrize(
    ("source", "hop_from", "hop_to", "relation", "corroboration", "expected"),
    [
        (
            "route.ts",
            "route.ts",
            "owner.ts",
            "imports",
            ["exact-module-resolution"],
            True,
        ),
        (
            "route.js",
            "route.js",
            "owner.ts",
            "imports",
            ["exact-module-resolution"],
            True,
        ),
        (
            "route.go",
            "route.go",
            "owner.ts",
            "imports",
            ["exact-module-resolution"],
            True,
        ),
        (
            "route.py",
            "route.py",
            "owner.ts",
            "imports",
            ["exact-module-resolution"],
            False,
        ),
        (
            "route.ts",
            "other.ts",
            "owner.ts",
            "imports",
            ["exact-module-resolution"],
            False,
        ),
        (
            "route.ts",
            "route.ts",
            "other.ts",
            "imports",
            ["exact-module-resolution"],
            False,
        ),
        (
            "route.ts",
            "route.ts",
            "owner.ts",
            "calls",
            ["exact-module-resolution"],
            False,
        ),
        ("route.ts", "route.ts", "owner.ts", "imports", [], False),
    ],
)
def test_polyglot_owner_proof_requires_the_exact_import_hop(
    source: str,
    hop_from: str,
    hop_to: str,
    relation: str,
    corroboration: list[str],
    expected: bool,
) -> None:
    resolved: StructuralOwnerCandidate = {
        "path": "owner.ts",
        "depth": 1,
        "via": "import",
        "source_path": source,
        "owner_path": [{"from": hop_from, "to": hop_to, "relation": relation}],
        "corroboration": corroboration,
        "cycle_count": 0,
        "revisit_count": 0,
        "relation_graph_schema": "hashmarks.ownership-relation-graph.v1",
        "relation_graph_completeness": "complete",
        "relation_graph_truncation": "complete",
        "relation_graph_search_bound_reasons": [],
    }
    assert (
        OwnershipCandidatesMixin._task_action_polyglot_import_proves_owner(
            resolved, source, "owner.ts"
        )
        is expected
    )
    resolved["owner_path"] = []
    assert (
        OwnershipCandidatesMixin._task_action_polyglot_import_proves_owner(
            resolved, source, "owner.ts"
        )
        is False
    )


@pytest.mark.parametrize(
    "field", ["schema", "source_evidence_identity", "evidence_packet_identity"]
)
def test_initial_encoder_rejects_non_string_headers(field: str) -> None:
    raw: dict[str, object] = {
        "schema": "hashmarks.task-evidence-initial.v2",
        "source_evidence_identity": "sha256:source",
        "evidence_packet_identity": "sha256:initial",
    }
    raw[field] = False
    with pytest.raises(ValueError, match=f"initial packet header: {field}"):
        encode_initial_packet(raw)
