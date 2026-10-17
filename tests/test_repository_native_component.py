"""Native publication and qualification need only their repository inputs."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from contract_assertions import assert_records
from test_repository_index_component import index as index

from hashmarks.codemap.decision_session import DecisionScope
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.native_evidence import RepositoryNativeEvidence
from hashmarks.codemap.repository_source import RepositorySource


def _native(index: RepositoryIndex) -> RepositoryNativeEvidence:
    reads = DecisionScope(index, index.store, index._observation_source)
    source = RepositorySource(index.files, index, reads, index.store, index.file_store)
    return RepositoryNativeEvidence(index.files, source, reads, index.store)


def test_project_evidence_is_disqualified_on_manifest_drift_without_publication(
    index: RepositoryIndex,
) -> None:
    manifest = index.workspace / "package.json"
    manifest.write_text(json.dumps({"name": "original", "private": True}))
    index.sync()
    native = _native(index)
    result = native.enrich_projects(("npm-package-graph",))
    assert assert_records(result["projects"])[0]["project_id"] == "npm:original"
    assert native.status() == [
        {
            "kind": "project",
            "producer": "npm-package-graph",
            "fresh": True,
            "reason": None,
        }
    ]
    generation = index.store.generation()
    published = index.store.project_nodes()

    manifest.write_text(json.dumps({"name": "replacement", "private": True}))

    assert index.store.generation() == generation
    assert index.store.project_nodes() == published
    assert native._fresh_project_nodes() == []
    assert native.status() == [
        {
            "kind": "project",
            "producer": "npm-package-graph",
            "fresh": False,
            "reason": "manifest changed: package.json",
        }
    ]


def test_failed_native_publication_rolls_back_rows_binding_and_generation(
    index: RepositoryIndex,
) -> None:
    manifest = index.workspace / "package.json"
    manifest.write_text(json.dumps({"name": "original", "private": True}))
    index.sync()
    native = _native(index)
    native.enrich_projects(("npm-package-graph",))
    before = (
        index.store.generation(),
        index.store.project_nodes(),
        index.store.meta_items(),
    )
    index.store._db.execute(
        "CREATE TRIGGER reject_native_snapshot BEFORE UPDATE ON meta "
        "WHEN NEW.key LIKE 'native_evidence:%' "
        "BEGIN SELECT RAISE(ABORT, 'reject native snapshot'); END"
    )
    index.store._db.commit()
    manifest.write_text(json.dumps({"name": "replacement", "private": True}))

    with pytest.raises(sqlite3.IntegrityError, match="reject native snapshot"):
        native.enrich_projects(("npm-package-graph",))

    assert (
        index.store.generation(),
        index.store.project_nodes(),
        index.store.meta_items(),
    ) == before


def test_native_component_import_does_not_load_facade_or_upper_composition() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.native_evidence import RepositoryNativeEvidence; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.evidence_graph' not in sys.modules; assert 'hashmarks.codemap.task_retrieval' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_root_has_no_retired_native_publication_or_qualification_operations() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "import_scip",
        "enrich_projects",
        "_native_evidence_status",
        "_fresh_native_refs",
        "_fresh_native_file_edges",
        "_fresh_project_nodes",
    ):
        assert not hasattr(CodeMap, name)
