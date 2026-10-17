"""External claims are compared to Source without Tasks or CodeMap callbacks."""

import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from contract_assertions import assert_array, assert_object, assert_records
from test_repository_index_component import index as index
from test_repository_source_component import _source

from hashmarks.codemap.evidence_correlation import RepositoryCorrelation
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.repository_evidence_bindings import RepositoryBindings


def _bundle(anchor: Mapping[str, object]) -> list[dict[str, object]]:
    return [
        {
            "bundle_id": "external",
            "producer": {"kind": "test"},
            "scope": {},
            "completeness": "complete",
            "truncation": "complete",
            "anchors": [anchor],
        }
    ]


def _anchor(packet: Mapping[str, object]) -> dict[str, object]:
    return assert_object(
        assert_array(assert_object(assert_array(packet["bundles"])[0])["anchors"])[0]
    )


def test_correlation_rejects_old_member_equivalence_after_edit(
    index: RepositoryIndex,
) -> None:
    member = index.workspace / "owner.py"
    member.write_text("VALUE = 1\n")
    index.sync()
    source = _source(index)
    correlation = RepositoryCorrelation(source, RepositoryBindings(source))
    observation, _ = source.member("owner.py")
    original_revision = observation["member_revision"]
    claim = _bundle(
        {
            "anchor_id": "runtime",
            "path": "owner.py",
            "member_revision": original_revision,
        }
    )
    before = correlation.observe(claim, include_relationships=False)
    assert assert_object(_anchor(before)["source_equivalence"])["state"] == "proven"
    member.write_text("VALUE = 2\n")
    index.sync(["owner.py"])
    after = correlation.observe(
        claim, include_relationships=False, previous_correlation=before
    )
    assert assert_object(_anchor(after)["source_equivalence"])["state"] == "mismatch"
    assert "delta_from_previous" in after


def test_correlation_preserves_same_named_symbol_ambiguity(
    index: RepositoryIndex,
) -> None:
    for name in ("left", "right"):
        (index.workspace / f"{name}.py").write_text("def duplicate(): pass\n")
    index.sync()
    source = _source(index)
    correlation = RepositoryCorrelation(source, RepositoryBindings(source))
    packet = correlation.observe(
        _bundle({"anchor_id": "symbol", "symbol": "duplicate"}),
        include_relationships=False,
    )
    resolution = assert_object(_anchor(packet)["resolution"])
    assert resolution["state"] == "resolved-ambiguous"
    assert [row["path"] for row in assert_records(resolution["candidates"])] == [
        "left.py",
        "right.py",
    ]


def test_correlation_import_has_no_facade_task_or_packet_dependency() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.evidence_correlation import RepositoryCorrelation; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.repository_tasks' not in sys.modules; assert 'hashmarks.codemap.evidence_packet' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_root_has_no_retired_correlation_operations() -> None:
    from hashmarks.codemap import CodeMap

    for name in ("correlate_evidence", "evidence_correlation_delta"):
        assert not hasattr(CodeMap, name)
