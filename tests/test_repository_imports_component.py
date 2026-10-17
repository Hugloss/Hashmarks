"""Import identity is qualified by its resolver, without a CodeMap facade."""

import subprocess
import sys
from pathlib import Path

from test_repository_index_component import index as index

from hashmarks.codemap.decision_session import DecisionScope
from hashmarks.codemap.import_resolution import RepositoryImports
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.repository_source import RepositorySource


def test_standalone_import_resolver_qualifies_alias_and_reexport(
    index: RepositoryIndex,
) -> None:
    root = index.workspace
    (root / "owner.py").write_text("def target(): pass\n")
    (root / "facade.py").write_text("from owner import target as exported\n")
    (root / "consumer.py").write_text("from facade import exported as selected\n")
    index.sync()
    reads = DecisionScope(index, index.store, index._observation_source)
    source = RepositorySource(index.files, index, reads, index.store, index.file_store)
    imports = RepositoryImports(index.files, source, reads, index.store)
    with reads.session():
        owners, ambiguous = imports._resolve_import_owner_evidence(
            "consumer.py", "facade.exported"
        )
        symbols, symbol_unresolved = imports._resolve_import_symbol_evidence(
            "consumer.py", "facade.exported"
        )
    assert owners == ["facade.py", "owner.py"]
    assert ambiguous is False
    assert symbols == [("owner.py", "target")]
    assert symbol_unresolved is False


def test_import_resolver_does_not_import_the_facade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.import_resolution import RepositoryImports; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.ownership_graph' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_root_has_no_second_import_resolver() -> None:
    from hashmarks.codemap import CodeMap

    assert not hasattr(CodeMap, "_resolve_import_owner_evidence")
    assert not hasattr(CodeMap, "_resolve_import_paths")
