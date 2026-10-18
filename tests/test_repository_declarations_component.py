"""Current provider claims are observed without a facade or replay state."""

import subprocess
import sys
from pathlib import Path

from contract_assertions import assert_object, assert_records
from test_repository_declaration_correspondence_persistence import _SourceProvider
from test_repository_declarations import _declaration, _group
from test_repository_index_component import index as index
from test_repository_source_component import _source

from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.repository_declarations import RepositoryDeclarations
from hashmarks.codemap.repository_evidence_bindings import RepositoryBindings


def test_declarations_bind_provider_values_to_the_shared_source_revision(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "config.txt").write_text("version: 1\n")
    (index.workspace / "other.txt").write_text("version: 1\n")
    source = _source(index)
    declarations = RepositoryDeclarations(RepositoryBindings(source))
    packet = declarations.observe(
        [
            _group(
                [
                    _declaration("version", "config.txt", "1"),
                    _declaration("other", "other.txt", "1"),
                ]
            )
        ]
    )
    assert (
        assert_object(assert_records(packet["groups"])[0]["comparison"])["state"]
        == "equivalent"
    )
    evidence = assert_object(packet["repository_evidence"])
    observed = assert_records(assert_records(evidence["bindings"])[0]["evidence"])[0]
    member, _ = source.member("config.txt")
    assert observed["member_revision"] == member["member_revision"]
    assert packet["semantic_value_authority"] == "provider-claimed"


def test_previous_discovery_cannot_hydrate_later_provider_membership(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.txt").write_text("owner: accounts\n")
    source = _source(index)
    bindings = RepositoryBindings(source)
    declarations = RepositoryDeclarations(bindings)
    before = declarations.discover([_SourceProvider("provider-a", "owner.txt")])
    assert assert_records(assert_object(before["declarations"])["groups"])
    comparison = declarations.discover([], previous_observation=before)
    assert assert_object(comparison["declarations"])["groups"] == []
    later = RepositoryDeclarations(bindings).discover([])
    assert assert_object(later["declarations"])["groups"] == []
    assert later["providers"] == []
    assert "delta_from_previous" not in later


def test_declaration_component_import_needs_no_root_tasks_or_packets() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.repository_declarations import RepositoryDeclarations; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.repository_tasks' not in sys.modules; assert 'hashmarks.codemap.evidence_packet' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_root_has_no_retired_declaration_operations() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "repository_declarations",
        "discover_repository_declarations",
        "repository_declarations_operation",
        "repository_declaration_derivation_authority",
        "repository_declaration_explain",
    ):
        assert not hasattr(CodeMap, name)
