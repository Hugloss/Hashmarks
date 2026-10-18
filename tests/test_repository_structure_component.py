"""Bounded structural facts have an owner independent of task policy and CodeMap."""

import subprocess
import sys
from pathlib import Path

from contract_assertions import assert_object, assert_records
from test_repository_index_component import index as index
from test_repository_relationships_component import _relationships

from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.structural_locality import RepositoryStructure


def _structure(index: RepositoryIndex) -> RepositoryStructure:
    relationships = _relationships(index)
    return RepositoryStructure(
        relationships.source,
        relationships.imports,
        relationships.native,
        relationships,
    )


def test_standalone_structure_observes_exact_calls_and_reobserves_changed_source(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): return 1\n")
    consumer = index.workspace / "consumer.py"
    consumer.write_text("from owner import owner\ndef consume(): return owner()\n")
    (index.workspace / "tests").mkdir()
    (index.workspace / "tests/test_consume.py").write_text(
        "from consumer import consume\ndef test_consume(): assert consume() == 1\n"
    )
    index.sync()
    structure = _structure(index)
    before = structure.locality("consumer.py::consume", max_depth=1, refresh=False)
    assert {row["symbol_id"] for row in assert_records(before["nodes"])} == {
        "consumer.py::consume",
        "owner.py::owner",
    }
    assert [row["resolved_symbol_id"] for row in assert_records(before["edges"])] == [
        "owner.py::owner"
    ]
    assert before["verification_paths"] == ["tests/test_consume.py"]
    assert assert_object(before["resource_lifecycle"])["execution_effect"] == "none"

    consumer.write_text("def consume(): return 2\n")
    after = structure.locality("consumer.py::consume", max_depth=1, refresh=True)
    assert after["repository_identity"] != before["repository_identity"]
    assert after["source_identity"] != before["source_identity"]
    assert {row["symbol_id"] for row in assert_records(after["nodes"])} == {
        "consumer.py::consume"
    }
    assert after["edges"] == []


def test_standalone_structure_preserves_competing_import_ambiguity(
    index: RepositoryIndex,
) -> None:
    for module in ("first", "second"):
        (index.workspace / f"{module}.py").write_text("def shared(): return 1\n")
    (index.workspace / "consumer.py").write_text(
        "from first import shared\nfrom second import shared\n"
        "def consume(): return shared()\n"
    )
    index.sync()
    packet = _structure(index).locality("consumer.py::consume", refresh=False)
    unresolved = assert_records(packet["unresolved_calls"])
    assert len(unresolved) == 1
    assert unresolved[0]["resolved_symbol_id"] is None
    assert unresolved[0]["candidate_symbol_ids"] == [
        "first.py::shared",
        "second.py::shared",
    ]
    assert len(assert_records(packet["nodes"])) == 1


def test_structure_and_comparison_imports_have_no_facade_or_task_dependency() -> None:
    for statement in (
        "from hashmarks.codemap.structural_locality import RepositoryStructure",
        "from hashmarks.codemap.structural_locality_delta import structural_locality_delta; assert 'hashmarks.codemap.structural_locality' not in sys.modules",
    ):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; "
                + statement
                + "; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.task_retrieval' not in sys.modules; assert 'hashmarks.codemap.evidence_verification' not in sys.modules",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_retired_root_structural_operations_are_removed() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "structural",
        "structural_locality",
        "_resolve_call_target",
        "_exact_locality_target",
        "_locality_verification_paths",
    ):
        assert not hasattr(CodeMap, name)
