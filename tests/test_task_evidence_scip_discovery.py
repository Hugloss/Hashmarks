"""Qualified SCIP evidence discovery on the existing task-evidence surface."""

from __future__ import annotations

import json
from pathlib import Path

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
        "def normalize_widget(value: str) -> str:\n"
        "    return value.strip()\n",
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
                        "symbols": [
                            {"symbol": _SYMBOL, "relationships": relations}
                        ],
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
        before = codemap.task_evidence(_TASK, token_budget=256)
        assert before["ownership"]["status"] == "resolved"
        assert "semantic_relationships" not in before

        codemap.import_scip(index)
        after = codemap.task_evidence(_TASK, token_budget=256)

    assert after["ownership"]["status"] == "resolved"
    assert after["ownership"]["owner"]["path"] == "src/engine.py"
    assert after["verification"]["selected"]["path"] == "tests/test_engine.py"
    assert after["ownership"]["authority_proof_identity"]
    assert after["semantic_relationships"] == {
        "authority": "scip-producer-claim-only",
        "subject": "src/engine.py::normalize_widget",
        "observed_relationship_count": 1,
        "observed_kinds": ["implementation"],
        "producer_bindings": ["scip-python:test"],
        "truncated": False,
        "completeness": "unknown",
        "source_equivalence": "unknown",
        "negative_evidence_admissible": False,
        "detail_surface": "structural_locality",
        "repository_freshness": after["freshness"]["state"],
    }
    presentation = present_repository_evidence(after, format="structured")
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
        observed = codemap.task_evidence(_TASK)
        assert observed["semantic_relationships"]["observed_relationship_count"] == 64
        assert observed["semantic_relationships"]["truncated"] is True
        assert observed["semantic_relationships"]["negative_evidence_admissible"] is False

        (tmp_path / "src" / "engine.py").write_text(
            "def normalize_widget(value: str) -> str:\n"
            "    return value.strip().lower()\n",
            encoding="utf-8",
        )
        codemap.sync(["src/engine.py"])
        stale = codemap.task_evidence(_TASK)
        assert "semantic_relationships" not in stale


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
