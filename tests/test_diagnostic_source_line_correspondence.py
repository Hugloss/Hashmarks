from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.repository_delta import (
    RepositoryDeltaMixin,
    RepositoryGenerationBinding,
)

if TYPE_CHECKING:
    from pathlib import Path


def _diagnostics(
    generation: int,
    line: int,
    *,
    column: int = 12,
    collection: str = "fresh-complete",
) -> dict[str, object]:
    return RepositoryDeltaMixin.external_diagnostic_observation(
        producer="pyright",
        binding=RepositoryGenerationBinding("repository:fixture", generation),
        environment_identity="pyright:fixture",
        scope_paths=["src.py"],
        collection_state=collection,
        outcome="fail",
        diagnostics=[
            {
                "tool": "pyright",
                "rule": "unknown-name",
                "path": "src.py",
                "symbol": "example",
                "line": line,
                "column": column,
                "message": "undefined name",
            }
        ],
    )


def _capture(
    tmp_path: Path,
    *,
    old: str,
    new: str,
    old_line: int,
    new_line: int,
    columns: tuple[int, int] = (12, 12),
) -> dict[str, object]:
    file = tmp_path / "src.py"
    file.write_text(old, encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before_source = codemap.source_observation("src.py", lines=[old_line])
        before = _diagnostics(
            int(before_source["generation"]), old_line, column=columns[0]
        )
        file.write_text(new, encoding="utf-8")
        codemap.sync()
        after_source = codemap.source_observation("src.py", lines=[new_line])
        after = _diagnostics(
            int(after_source["generation"]), new_line, column=columns[1]
        )
    return RepositoryDeltaMixin.diagnostic_observation_delta(
        before, after, before_source=before_source, after_source=after_source
    )


def test_source_backed_unique_moved_line_preserves_raw_diagnostic_identities(
    tmp_path: Path,
) -> None:
    delta = _capture(
        tmp_path,
        old="def example():\n    print(missing)\n",
        new="def example():\n    other = 1\n    print(missing)\n",
        old_line=2,
        new_line=3,
    )
    assert len(delta["diagnostics"]["added"]) == 1
    assert len(delta["diagnostics"]["removed"]) == 1
    proof = delta["diagnostics"]["source_correspondence"]
    assert len(proof["supported"]) == 1
    assert proof["unresolved"] == []
    moved = proof["supported"][0]
    assert moved["state"] == "source-line-correspondence"
    assert moved["before_line"] == 2
    assert moved["after_line"] == 3
    assert moved["diagnostic_identity_authority"] is False
    assert moved["before_member_revision"] != moved["after_member_revision"]
    assert proof["diagnostic_identity_authority"] is False


@pytest.mark.parametrize("endpoint", ["before", "after"])
@pytest.mark.parametrize("claim", ["matching", "different", "malformed"])
def test_source_line_correspondence_respects_explicit_producer_revisions(
    tmp_path: Path, endpoint: str, claim: str
) -> None:
    file = tmp_path / "src.py"
    file.write_text("def example():\n    print(missing)\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before_source = codemap.source_observation("src.py", lines=[2])
        before = _diagnostics(int(before_source["generation"]), 2)
        file.write_text(
            "def example():\n    other = 1\n    print(missing)\n", encoding="utf-8"
        )
        codemap.sync()
        after_source = codemap.source_observation("src.py", lines=[3])
        after = _diagnostics(int(after_source["generation"]), 3)
    packet, source = (
        (before, before_source) if endpoint == "before" else (after, after_source)
    )
    packet["source_revisions"] = {
        "src.py": source["member"]["member_revision"]
        if claim == "matching"
        else "a" * 64
    }
    if claim == "malformed":
        packet["source_revisions"] = {"outside.py": "not-a-revision"}
        with pytest.raises(ValueError):
            RepositoryDeltaMixin.diagnostic_observation_delta(
                before, after, before_source=before_source, after_source=after_source
            )
        return
    delta = RepositoryDeltaMixin.diagnostic_observation_delta(
        before, after, before_source=before_source, after_source=after_source
    )
    correspondence = delta["diagnostics"]["source_correspondence"]
    if claim == "matching":
        assert len(correspondence["supported"]) == 1
        assert correspondence["unresolved"] == []
    else:
        assert correspondence["supported"] == []
        assert correspondence["unresolved"][0]["reason"] == (
            "diagnostic-source-revision-mismatch"
        )


@pytest.mark.parametrize(
    ("old", "new", "reason"),
    [
        (
            "def example():\n    print(missing)\n",
            "def example():\n    other = 1\n    print(changed)\n",
            "source-line-bytes-changed",
        ),
        (
            "def example():\n    print(missing)\n    print(missing)\n",
            "def example():\n    x = 1\n    print(missing)\n    print(missing)\n",
            "source-line-not-unique",
        ),
    ],
)
def test_changed_or_duplicate_source_lines_do_not_prove_correspondence(
    tmp_path: Path, old: str, new: str, reason: str
) -> None:
    delta = _capture(tmp_path, old=old, new=new, old_line=2, new_line=3)
    result = delta["diagnostics"]["source_correspondence"]
    assert result["supported"] == []
    assert result["unresolved"][0]["reason"] == reason


def test_changed_diagnostic_column_does_not_prove_correspondence(
    tmp_path: Path,
) -> None:
    result = _capture(
        tmp_path,
        old="def example():\n    print(missing)\n",
        new="def example():\n    y = 1\n    print(missing)\n",
        old_line=2,
        new_line=3,
        columns=(12, 14),
    )["diagnostics"]["source_correspondence"]
    assert result["supported"] == []
    assert result["unresolved"][0]["reason"] == "diagnostic-column-not-preserved"


def test_missing_or_blank_line_anchor_fails_closed(tmp_path: Path) -> None:
    file = tmp_path / "src.py"
    file.write_text("x = 1\n\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.source_observation("src.py", lines=[2, 500])
    assert packet["availability"] == "observed"
    assert packet["line_coverage"] == "unknown"
    assert [row["state"] for row in packet["line_anchors"]] == ["unknown", "unknown"]


def test_source_line_anchor_is_exact_revision_bound_and_unique(tmp_path: Path) -> None:
    path = tmp_path / "src.py"
    path.write_bytes(b"a = 1\r\nb = 2\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.source_observation("src.py", lines=[1, 2])
    assert packet["line_coverage"] == "complete"
    assert packet["completeness"] == "complete"
    assert len(packet["line_anchors"]) == 2
    assert all(row["matching_physical_lines"] == 1 for row in packet["line_anchors"])
    assert all(
        row["member_revision"] == packet["member"]["member_revision"]
        for row in packet["line_anchors"]
    )
    assert (
        packet["line_anchors"][0]["line_sha256"]
        != packet["line_anchors"][1]["line_sha256"]
    )


@pytest.mark.parametrize("lines", [[0], [-1], [True], [1] * 33])
def test_source_line_scope_is_rejected_before_read(
    tmp_path: Path, lines: list[int]
) -> None:
    with CodeMap(tmp_path) as codemap:
        with pytest.raises(ValueError, match="lines"):
            codemap.source_observation("src.py", lines=lines)


def test_unsupported_or_stale_member_has_no_source_anchors(tmp_path: Path) -> None:
    path = tmp_path / "src.py"
    path.write_text("original = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.source_observation("src.py", lines=[1])
        path.write_text("replaced = 1\n", encoding="utf-8")
        stale = codemap.source_observation("src.py", lines=[1])
        denied = codemap.source_observation(".env", lines=[1])
    assert len(before["line_anchors"]) == 1
    assert stale["line_anchors"] == []
    assert stale["line_coverage"] == "unknown"
    assert denied["line_anchors"] == []


def test_source_correspondence_requires_both_snapshots() -> None:
    before = _diagnostics(1, 2)
    after = _diagnostics(2, 3)
    with pytest.raises(ValueError, match="both endpoint"):
        RepositoryDeltaMixin.diagnostic_observation_delta(
            before, after, before_source={}
        )


def test_mismatched_source_generation_never_supports_correspondence(
    tmp_path: Path,
) -> None:
    delta = _capture(
        tmp_path,
        old="def example():\n    print(missing)\n",
        new="def example():\n    other = 1\n    print(missing)\n",
        old_line=2,
        new_line=3,
    )
    before = _diagnostics(987654, 2)
    after = _diagnostics(987655, 3)
    source_pair = delta["diagnostics"]["source_correspondence"]
    assert len(source_pair["supported"]) == 1
    result = RepositoryDeltaMixin.diagnostic_observation_delta(
        before,
        after,
        before_source={"schema": "hashmarks.source-observation.v1"},
        after_source={"schema": "hashmarks.source-observation.v1"},
    )["diagnostics"]["source_correspondence"]
    assert result["supported"] == []
    assert result["unresolved"][0]["reason"] == "missing-canonical-member"


def test_same_generation_unadmitted_source_change_cannot_prove_movement() -> None:
    from hashmarks.codemap.source_line_correspondence import _source_pair_reason

    before = _diagnostics(5, 2)
    after = _diagnostics(5, 3)
    source_before = {
        "schema": "hashmarks.source-observation.v1",
        "availability": "observed",
        "freshness": "unknown",
        "line_coverage": "complete",
        "completeness": "complete",
        "observation_identity": "sha256:fixture",
        "generation": 5,
        "member": {
            "path": "src.py",
            "state": "known-present",
            "member_revision": "first",
        },
    }
    source_after = {
        **source_before,
        "member": {**source_before["member"], "member_revision": "second"},
    }
    assert (
        _source_pair_reason(before, after, source_before, source_after)
        == "source-change-not-generation-bound"
    )
