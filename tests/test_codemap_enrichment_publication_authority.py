from __future__ import annotations

import json
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap


def _repository(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "owner.py").write_text(
        "def owner():\n    return 1\n",
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        json.dumps({"name": "publication-fixture", "private": True}),
        encoding="utf-8",
    )


def _write_scip(path: Path, *, symbol: str) -> None:
    path.write_text(
        json.dumps(
            {
                "metadata": {
                    "toolInfo": {"name": "scip-python", "version": "publication-test"}
                },
                "documents": [
                    {
                        "relativePath": "src/owner.py",
                        "occurrences": [
                            {
                                "range": [0, 4, 9],
                                "symbol": (
                                    "scip-python python publication 0.0.0 "
                                    f"`src.owner`/{symbol}#"
                                ),
                                "symbolRoles": 1,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _scip_snapshot(codemap: CodeMap) -> str | None:
    return codemap.store.meta("native_evidence:scip:scip-python:publication-test")


def test_scip_rows_and_freshness_snapshot_roll_back_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository(tmp_path)
    scip = tmp_path / "index.json"
    _write_scip(scip, symbol="BeforeOwner")
    state = tmp_path / ".state"
    artifacts = tmp_path / "artifacts.sqlite3"

    with CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as codemap:
        codemap.sync()
        codemap.import_scip(scip)
        before_generation = codemap.store.generation()
        before_snapshot = _scip_snapshot(codemap)
        assert codemap.store.native_definitions("BeforeOwner")

        _write_scip(scip, symbol="AfterOwner")

        def fail_snapshot(*args, **kwargs) -> None:
            raise RuntimeError("injected snapshot publication failure")

        monkeypatch.setattr(codemap, "_record_evidence_snapshot", fail_snapshot)
        with pytest.raises(RuntimeError, match="injected snapshot publication failure"):
            codemap.import_scip(scip)

        assert codemap.store.generation() == before_generation
        assert _scip_snapshot(codemap) == before_snapshot
        assert codemap.store.native_definitions("BeforeOwner")
        assert codemap.store.native_definitions("AfterOwner") == []


def test_project_rows_and_freshness_snapshot_roll_back_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository(tmp_path)
    state = tmp_path / ".state"
    artifacts = tmp_path / "artifacts.sqlite3"

    with CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as codemap:
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph",))
        before_generation = codemap.store.generation()
        before_nodes = codemap.store.project_nodes()
        before_snapshot = codemap.store.meta(
            "native_evidence:project:npm-package-graph"
        )

        (tmp_path / "package.json").write_text(
            json.dumps({"name": "replacement-project", "private": True}),
            encoding="utf-8",
        )

        def fail_snapshot(*args, **kwargs) -> None:
            raise RuntimeError("injected project snapshot publication failure")

        monkeypatch.setattr(codemap, "_record_evidence_snapshot", fail_snapshot)
        with pytest.raises(
            RuntimeError, match="injected project snapshot publication failure"
        ):
            codemap.enrich_projects(("npm-package-graph",))

        assert codemap.store.generation() == before_generation
        assert codemap.store.project_nodes() == before_nodes
        assert (
            codemap.store.meta("native_evidence:project:npm-package-graph")
            == before_snapshot
        )


def test_enrichment_commit_invalidates_inflight_generation_session(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    scip = tmp_path / "index.json"
    _write_scip(scip, symbol="BeforeOwner")
    state = tmp_path / ".state"
    artifacts = tmp_path / "artifacts.sqlite3"

    with CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as seed:
        seed.sync()
        seed.import_scip(scip)

    _write_scip(scip, symbol="AfterOwner")
    with (
        CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as reader,
        CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as writer,
    ):
        before_generation = reader.store.generation()
        with pytest.raises(
            RuntimeError, match="generation changed during decision session"
        ):
            with reader.decision_session():
                assert reader._fresh_native_definitions("BeforeOwner")
                writer.import_scip(scip)
                assert writer.store.generation() == before_generation + 1
                assert reader._fresh_native_definitions("AfterOwner")


def test_enrichment_only_generation_carries_unrelated_scip_binding(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    scip = tmp_path / "index.json"
    _write_scip(scip, symbol="Owner")
    state = tmp_path / ".state"
    artifacts = tmp_path / "artifacts.sqlite3"

    with CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as codemap:
        codemap.sync()
        codemap.import_scip(scip)
        before_generation = codemap.store.generation()
        assert codemap._evidence_fresh("scip", "scip-python:publication-test") == (
            True,
            None,
        )

        result = codemap.enrich_projects(("npm-package-graph",))

        assert result["providers"]
        assert codemap.store.generation() == before_generation + 1
        snapshot = json.loads(_scip_snapshot(codemap) or "{}")
        assert snapshot["generation"] == codemap.store.generation()
        assert codemap._evidence_fresh(
            "scip", "scip-python:publication-test"
        ) == (True, None)
