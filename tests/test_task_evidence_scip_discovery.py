"""Qualified SCIP evidence discovery on the existing task-evidence surface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hashmarks.codemap import CodeMap
from hashmarks.evidence_presentation import present_repository_evidence

_SYMBOL = "scip-python python example 0.1.0 `src.engine`/normalize_widget()."
_TARGET = "scip-python python example 0.1.0 `src.types`/Widget#"
_TASK = (
    "Change normalize_widget so it lowercases the trimmed value and verify "
    "normalize_widget semantics."
)


def _repository(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "engine.py").write_text(
        "def normalize_widget(value: str) -> str:\n    return value.strip()\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_engine.py").write_text(
        "from src.engine import normalize_widget\n\n"
        "def test_normalize_widget():\n"
        "    assert normalize_widget('  ABC ') == 'ABC'\n",
        encoding="utf-8",
    )


def _index(root: Path, *, count: int = 1) -> Path:
    path = root.parent / f"{root.name}-semantic-index.json"
    relations = [
        {
            "symbol": _TARGET if index == 0 else f"scip-target-{index}",
            "isImplementation": True,
        }
        for index in range(count)
    ]
    path.write_text(
        json.dumps(
            {
                "metadata": {"toolInfo": {"name": "scip-python", "version": "test"}},
                "documents": [
                    {
                        "relativePath": "src/engine.py",
                        "symbols": [{"symbol": _SYMBOL, "relationships": relations}],
                        "occurrences": [
                            {
                                "symbol": _SYMBOL,
                                "range": [0, 4, 20],
                                "symbolRoles": 1,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_task_evidence_discovers_existing_scip_facts_without_reselecting_owner(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    index = _index(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        before: Any = codemap.task_evidence(_TASK, token_budget=256)
        assert before["ownership"]["status"] == "resolved"
        assert "semantic_relationships" not in before

        codemap.import_scip(index)
        after: Any = codemap.task_evidence(_TASK, token_budget=256)

    assert after["ownership"]["status"] == "resolved"
    assert after["ownership"]["owner"]["path"] == "src/engine.py"
    assert after["verification"]["selected"]["path"] == "tests/test_engine.py"
    assert after["ownership"]["authority_proof_identity"]
    expected = {
        "authority": "scip-producer-claim-only",
        "subject": "src/engine.py::normalize_widget",
        "observation_state": "direct-claims-observed",
        "observed_relationship_count": 1,
        "observed_kinds": ["implementation"],
        "producer_bindings": ["scip-python:test"],
        "truncated": False,
        "completeness": "unknown",
        "source_equivalence": "unknown",
        "repository_revision_observation": "same-as-import-observation",
        "negative_evidence_admissible": False,
        "detail_surface": "structural_locality",
        "detail_arguments": {
            "target": "src/engine.py::normalize_widget",
            "result_mode": "relationships",
        },
        "repository_freshness": after["freshness"]["state"],
        "observed_relationship_count_scope": "exact-owner-scip-definition-outgoing",
        "associated_observed_relationship_count": 1,
        "associated_observed_relationship_count_scope": (
            "explicit-producer-claims-associated-with-owner"
        ),
    }
    assert {key: after["semantic_relationships"][key] for key in expected} == expected
    enriched = after["semantic_relationships"]["evidence"]
    assert enriched["claims"][0]["kind"] == "implementation"
    assert enriched["claims"][0]["source"]["source_binding"]["state"] == "unknown"
    assert after["semantic_relationships"]["evidence_refs"]["ownership"] == "/ownership"
    presentation: Any = present_repository_evidence(after, format="structured")
    assert presentation["source_evidence_identity"] == after["evidence_packet_identity"]
    assert presentation["identity_limitation"] is None
    rows = [
        row
        for group in presentation["groups"]
        for row in group["findings"]
        if row["kind"] == "scip_semantic_discovery"
    ]
    assert len(rows) == 1
    assert rows[0]["assertion"] == "producer_claim"
    assert rows[0]["source_refs"] == ["/semantic_relationships"]


def test_compact_locality_surfaces_scip_claims_before_call_edges(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    code = "def normalize_widget(value: str) -> str:\n"
    code += "".join(f"    helper{i}()\n" for i in range(6))
    code += "    return value.strip()\n"
    code += "".join(f"\ndef helper{i}():\n    return {i}\n" for i in range(6))
    (tmp_path / "src" / "engine.py").write_text(code, encoding="utf-8")
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.import_scip(_index(tmp_path))
        packet = codemap.structural_locality("src/engine.py::normalize_widget")
    for format in ("structured", "compact", "text"):
        projection: Any = present_repository_evidence(packet, format=format)
        group = next(g for g in projection["groups"] if g["family"] == "relationship")
        first = group["findings"][0]
        assert first["kind"] == "native_semantic_relationships"
        assert first["assertion"] == "producer_claim"
        assert first["details"] == packet["native_semantic_relationships"]
        assert first["source_refs"] == ["/native_semantic_relationships"]
        assert group["omitted_from_presentation"] == (
            group["count_observed_in_packet"] - len(group["findings"])
        )
        assert first["details"]["negative_evidence_admissible"] is False


def test_post_change_reports_semantic_freshness_without_comparing_claim_sets(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.import_scip(_index(tmp_path))
        previous = codemap.task_evidence(_TASK)
        noop: Any = codemap.task_post_change_delta(
            _TASK, ["src/engine.py"], previous_evidence=previous
        )
        assert noop["semantic_relationships"]["changed"] is False
        assert "semantic-relationship-evidence" in noop["reused"]
        (tmp_path / "src" / "engine.py").write_text(
            "def normalize_widget(value: str) -> str:\n    return value.strip().lower()\n",
            encoding="utf-8",
        )
        delta: Any = codemap.task_post_change_delta(
            _TASK, ["src/engine.py"], previous_evidence=previous
        )
    evidence: Any = delta["semantic_relationships"]
    assert evidence["changed"] is True
    assert evidence["before"]["evidence"]["qualifications"][0]["freshness"] == "current"
    assert evidence["after"]["evidence"]["qualifications"][0]["freshness"] == "stale"
    assert "semantic-relationship-evidence" in delta["invalidated"]
    assert evidence["claim_set_comparison"] == "not-performed"
    assert evidence["negative_evidence_admissible"] is False
    assert evidence["before"]["claims_omitted_from_summary"] == 1
    assert "claims" not in evidence["before"]["evidence"]
    assert evidence["after"]["detail_arguments"]["result_mode"] == "relationships"
    projection: Any = present_repository_evidence(delta, format="text")
    row = next(
        row
        for group in projection["groups"]
        for row in group["findings"]
        if row["kind"] == "task_semantic_evidence_delta"
    )
    assert row["details"] == evidence
    assert row["source_refs"] == ["/semantic_relationships"]
    assert "claim sets are not compared" in projection["text"]
    assert '"freshness":"stale"' in projection["text"]


def test_post_change_zero_scip_observation_becomes_unavailable_not_absent(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.import_scip(_index(tmp_path, count=0))
        previous = codemap.task_evidence(_TASK)
        (tmp_path / "src" / "engine.py").write_text(
            "def normalize_widget(value: str) -> str:\n    return value.strip().lower()\n",
            encoding="utf-8",
        )
        delta = codemap.task_post_change_delta(
            _TASK, ["src/engine.py"], previous_evidence=previous
        )
    evidence: Any = delta["semantic_relationships"]
    assert (
        evidence["before"]["observation_state"]
        == "definition-observed-no-direct-claims"
    )
    assert evidence["after"] is None
    assert evidence["negative_evidence_admissible"] is False
    projection: Any = present_repository_evidence(delta, format="text")
    assert "after: unavailable in task projection (unknown)" in projection["text"]


def test_task_evidence_scip_discovery_is_bounded_and_stale_fails_closed(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    index = _index(tmp_path, count=65)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.import_scip(index)
        observed: Any = codemap.task_evidence(_TASK)
        assert observed["semantic_relationships"]["observed_relationship_count"] == 64
        assert observed["semantic_relationships"]["truncated"] is True
        assert (
            observed["semantic_relationships"]["negative_evidence_admissible"] is False
        )

        (tmp_path / "src" / "engine.py").write_text(
            "def normalize_widget(value: str) -> str:\n"
            "    return value.strip().lower()\n",
            encoding="utf-8",
        )
        codemap.sync(["src/engine.py"])
        stale: Any = codemap.task_evidence(_TASK)
        assert all(
            row["freshness"] == "stale"
            for row in stale["semantic_relationships"]["evidence"]["qualifications"]
        )
        assert stale["semantic_relationships"]["negative_evidence_admissible"] is False


def test_scip_discovery_does_not_promote_unresolved_or_denied_owners(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    index = _index(tmp_path)
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "src/**"\nvisibility = "deny"\n',
        encoding="utf-8",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.import_scip(index)
        packet = codemap.task_evidence(_TASK)
        assert "semantic_relationships" not in packet


def test_scip_observed_zero_claims_is_not_missing_provider_evidence(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    index = _index(tmp_path, count=0)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        missing = codemap.task_evidence(_TASK, token_budget=256)
        assert "semantic_relationships" not in missing

        codemap.import_scip(index)
        observed = codemap.task_evidence(_TASK, token_budget=256)

    # SCIP import advances the repository generation, so proof identities
    # may legitimately change; the admitted owner and verifier must not.
    assert observed["ownership"]["status"] == missing["ownership"]["status"]
    assert observed["ownership"]["owner"] == missing["ownership"]["owner"]
    assert observed["ownership"]["basis"] == missing["ownership"]["basis"]
    assert observed["verification"]["selected"] == missing["verification"]["selected"]
    assert observed["verification"]["plan"] == missing["verification"]["plan"]
    discovery = observed["semantic_relationships"]
    assert discovery["observation_state"] == "definition-observed-no-direct-claims"
    assert discovery["observed_relationship_count"] == 0
    assert discovery["observed_relationship_count_scope"] == (
        "exact-owner-scip-definition-outgoing"
    )
    assert discovery["associated_observed_relationship_count"] == 0
    assert discovery["observed_kinds"] == []
    assert discovery["producer_bindings"] == ["scip-python:test"]
    assert discovery["completeness"] == "unknown"
    assert discovery["source_equivalence"] == "unknown"
    assert discovery["repository_revision_observation"] == "same-as-import-observation"
    assert discovery["negative_evidence_admissible"] is False

    rendered = present_repository_evidence(observed, format="structured")
    rows = [
        row
        for group in rendered["groups"]
        for row in group["findings"]
        if row["kind"] == "scip_semantic_discovery"
    ]
    assert len(rows) == 1
    assert rows[0]["assertion"] == "producer_claim"
    assert rows[0]["source_refs"] == ["/semantic_relationships"]


def test_scip_empty_observation_invalidated_after_source_edit(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    index = _index(tmp_path, count=0)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.import_scip(index)
        assert (
            codemap.task_evidence(_TASK)["semantic_relationships"]["observation_state"]
            == "definition-observed-no-direct-claims"
        )

        (tmp_path / "src" / "engine.py").write_text(
            "def normalize_widget(value: str) -> str:\n"
            "    return value.strip().lower()\n",
            encoding="utf-8",
        )
        codemap.sync(["src/engine.py"])
        assert "semantic_relationships" not in codemap.task_evidence(_TASK)


def test_incoming_only_scip_claim_is_not_misreported_as_outgoing(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    source = tmp_path / "src" / "engine.py"
    source.write_text(
        source.read_text(encoding="utf-8")
        + "\n\ndef forward_widget(value: str) -> str:\n"
        + "    return normalize_widget(value)\n",
        encoding="utf-8",
    )
    index = _index(tmp_path, count=0)
    native = json.loads(index.read_text(encoding="utf-8"))
    document = native["documents"][0]
    forward = "scip-python python example 0.1.0 `src.engine`/forward_widget()."
    document["symbols"].append(
        {
            "symbol": forward,
            "relationships": [{"symbol": _SYMBOL, "isReference": True}],
        }
    )
    document["occurrences"].append(
        {"symbol": forward, "range": [3, 4, 18], "symbolRoles": 1}
    )
    index.write_text(json.dumps(native), encoding="utf-8")

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.import_scip(index)
        packet: Any = codemap.task_evidence(_TASK, token_budget=256)

    discovery = packet["semantic_relationships"]
    assert packet["ownership"]["owner"]["path"] == "src/engine.py"
    assert packet["ownership"]["owner"]["qualname"] == "normalize_widget"
    assert discovery["observation_state"] == "definition-observed-no-direct-claims"
    assert discovery["observed_relationship_count"] == 0
    assert discovery["observed_relationship_count_scope"] == (
        "exact-owner-scip-definition-outgoing"
    )
    assert discovery["associated_observed_relationship_count"] == 1
    assert discovery["associated_observed_relationship_count_scope"] == (
        "explicit-producer-claims-associated-with-owner"
    )
    claims = discovery["evidence"]["claims"]
    assert len(claims) == 1
    assert claims[0]["kind"] == "reference"
    assert claims[0]["source"]["key"]["symbol"] == forward
    assert claims[0]["target"]["key"]["symbol"] == _SYMBOL
    assert discovery["negative_evidence_admissible"] is False
