"""Repository relationships compose lower evidence without task retrieval."""

import subprocess
import sys
from pathlib import Path

from contract_assertions import assert_records
from test_repository_index_component import index as index
from test_repository_native_component import _native

from hashmarks.codemap.evidence_graph import RepositoryRelationships
from hashmarks.codemap.import_resolution import RepositoryImports
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex


def _relationships(index: RepositoryIndex) -> RepositoryRelationships:
    native = _native(index)
    imports = RepositoryImports(index.files, native.source, native.reads, index.store)
    return RepositoryRelationships(
        native.source, native.reads, index.store, imports, native
    )


def test_relationships_expose_import_reference_and_test_evidence_without_tasks(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): return 1\n")
    (index.workspace / "consumer.py").write_text(
        "from owner import owner\ndef consume(): return owner()\n"
    )
    (index.workspace / "tests").mkdir()
    (index.workspace / "tests/test_owner.py").write_text(
        "from owner import owner\ndef test_owner(): assert owner() == 1\n"
    )
    index.sync()
    relationships = _relationships(index)

    dependencies = relationships.deps("consumer.py")
    imports = [
        row for row in assert_records(dependencies["edges"]) if row["kind"] == "import"
    ]
    assert imports and all(row["resolved_paths"] == ["owner.py"] for row in imports)
    references = assert_records(relationships.refs("owner")["references"])
    assert {row["path"] for row in references} == {"consumer.py", "tests/test_owner.py"}
    impact = relationships.affected("owner.py", max_depth=2)
    assert impact["affected_files"] == ["consumer.py", "tests/test_owner.py"]
    assert relationships.tests("owner.py")["tests"] == ["tests/test_owner.py"]

    # A second independent component reuses durable index authority, not the
    # previous component's cache or any task/selection state.
    assert _relationships(index).affected("owner.py", max_depth=2) == impact


def test_relationships_import_does_not_load_facade_or_retrieval() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.evidence_graph import RepositoryRelationships; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.find_engine' not in sys.modules; assert 'hashmarks.codemap.task_retrieval' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_retired_root_relationship_operations_are_removed() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "projects",
        "deps",
        "refs",
        "affected",
        "tests",
        "_reverse_file_graph",
        "_file_graph",
        "_query_paths",
        "_is_test_path",
        "_invalidate_file_graph_cache",
    ):
        assert not hasattr(CodeMap, name)
