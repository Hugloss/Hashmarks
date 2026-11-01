"""Dependency facts retain Source and producer-neutral authority without CodeMap."""

import subprocess
import sys
from pathlib import Path

from contract_assertions import assert_records
from test_dependency_resolution_evidence import _snapshot_v3
from test_repository_index_component import index as index
from test_repository_source_component import _source

from hashmarks.codemap.evidence_correlation import RepositoryCorrelation
from hashmarks.codemap.evidence_graph import RepositoryRelationships
from hashmarks.codemap.import_resolution import RepositoryImports
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.native_evidence import RepositoryNativeEvidence
from hashmarks.codemap.repository_dependencies import RepositoryDependencies
from hashmarks.codemap.repository_evidence_bindings import RepositoryBindings


def _dependencies(index: RepositoryIndex) -> RepositoryDependencies:
    source = _source(index)
    imports = RepositoryImports(source)
    correlation = RepositoryCorrelation(RepositoryBindings(source))
    relationships = RepositoryRelationships(imports, RepositoryNativeEvidence(source))
    return RepositoryDependencies(source, imports, correlation, relationships)


def test_dependency_inputs_observe_source_revision_without_changing_resolution(
    index: RepositoryIndex,
) -> None:
    member = index.workspace / "dependency.lock"
    member.write_text("before\n")
    dependencies = _dependencies(index)
    snapshot = _snapshot_v3()
    snapshot["repository_inputs"] = [{"path": "dependency.lock"}]
    before = dependencies.observe(snapshot)
    observed = assert_records(before["repository_inputs"])[0]
    source, _ = dependencies.source.member("dependency.lock")
    assert observed["observed_member_revision"] == source["member_revision"]
    member.write_text("after\n")
    after = dependencies.observe(snapshot)
    delta = dependencies.delta(before, after)
    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert delta["selections_changed"] == []
    assert delta["relationships_added"] == []
    assert delta["relationships_removed"] == []


def test_physical_source_kind_cannot_change_dependency_semantic_identity(
    index: RepositoryIndex,
) -> None:
    dependencies = _dependencies(index)
    snapshot = _snapshot_v3()
    before = dependencies.observe(snapshot)
    for row in assert_records(snapshot["evidence_sources"]):
        row["kind"] = "another-physical-source-format"
    after = dependencies.observe(snapshot)
    assert before["definition_identity"] == after["definition_identity"]
    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert before["components"] == after["components"]
    assert before["selections"] == after["selections"]


def test_dependency_component_import_needs_no_root_tasks_or_packets() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.repository_dependencies import RepositoryDependencies; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.repository_tasks' not in sys.modules; assert 'hashmarks.codemap.evidence_packet' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_root_has_no_retired_dependency_operations() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "dependency_codemap",
        "dependency_resolution_evidence",
        "dependency_resolution_queries",
        "dependency_evidence_correlation",
        "dependency_import_correspondence",
        "dependency_resolution_delta",
        "dependency_resolution_derivation_authority",
        "dependency_resolution_explain",
    ):
        assert not hasattr(CodeMap, name)
