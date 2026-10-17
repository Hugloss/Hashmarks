"""Bindings preserve Source facts without constructing higher repository services."""

from pathlib import Path

from contract_assertions import assert_object, assert_records
from test_repository_index_component import index as index
from test_repository_source_component import _source

from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.repository_evidence_bindings import RepositoryBindings


def test_binding_and_source_share_unindexed_member_revision(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "contract.proto").write_text("message Contract {}\n")
    source = _source(index)
    bindings = RepositoryBindings(source)
    packet = bindings.observe(
        [
            {
                "binding_id": "contract",
                "evidence": [{"path": "contract.proto", "scope": "member"}],
            }
        ],
        include_relationships=False,
    )
    row = assert_records(assert_records(packet["bindings"])[0]["evidence"])[0]
    member, _ = source.member("contract.proto")
    assert row["state"] == member["state"] == "known-present"
    assert row["member_revision"] == member["member_revision"]
    assert index.store.file_row("contract.proto") is None


def test_binding_delta_preserves_range_identity_across_an_unrelated_edit(
    index: RepositoryIndex,
) -> None:
    member = index.workspace / "owner.py"
    member.write_text("first = 1\nsecond = 2\n")
    index.sync()
    bindings = RepositoryBindings(_source(index))
    declaration = [
        {
            "binding_id": "second",
            "evidence": [{"path": "owner.py", "start_line": 2, "end_line": 2}],
        }
    ]
    before = bindings.observe(declaration, include_relationships=False)
    member.write_text("first = 9\nsecond = 2\n")
    index.sync(["owner.py"])
    after = bindings.observe(declaration, include_relationships=False)
    old = assert_records(assert_records(before["bindings"])[0]["evidence"])[0]
    new = assert_records(assert_records(after["bindings"])[0]["evidence"])[0]
    assert old["span_identity"] == new["span_identity"]
    assert old["member_revision"] != new["member_revision"]
    delta = bindings.delta(before, after)
    coverage = bindings.coverage(
        after,
        changed_paths=["owner.py"],
        change_set_complete=True,
        binding_delta=delta,
        binding_delta_before=before,
    )
    classification = assert_object(coverage["classification"])
    assert classification["changed_inside_bound_evidence"] == []
    assert classification["changed_elsewhere_in_bound_member"] == ["owner.py"]


def test_root_has_no_retired_binding_operations(tmp_path: Path) -> None:
    from hashmarks.codemap import CodeMap

    with CodeMap(tmp_path) as repository:
        assert isinstance(repository.bindings, RepositoryBindings)
        for name in (
            "repository_evidence_bindings",
            "repository_evidence_binding_delta",
            "repository_evidence_coverage",
        ):
            assert not hasattr(repository, name)
