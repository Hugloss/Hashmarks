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
        "repository_freshness": after["freshness"]["state"],
    }
    assert {key: after["semantic_relationships"][key] for key in expected} == expected
    enriched = after["semantic_relationships"]["evidence"]
    assert enriched["claims"][0]["kind"] == "implementation"
    assert enriched["claims"][0]["source"]["source_binding"]["state"] == "unknown"
    assert after["semantic_relationships"]["evidence_refs"]["ownership"] == "/ownership"
    presentation: Any = present_repository_evidence(after, format="structured")
    rows = [
        row
        for group in presentation["groups"]
        for row in group["findings"]
        if row["kind"] == "scip_semantic_discovery"
    ]
    assert len(rows) == 1
    assert rows[0]["assertion"] == "producer_claim"
    assert rows[0]["source_refs"] == ["/semantic_relationships"]


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

