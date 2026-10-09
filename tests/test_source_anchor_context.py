"""Bounded explicit-line context for diagnostic investigation, without source rereads."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from hashmarks import CodeMap
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError


def test_opt_in_line_context_preserves_legacy_anchors_and_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "example.py").write_bytes(b"before\r\nneedle\r\nafter\r\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        old = codemap.source_observation("example.py", lines=(2,))
        zero = codemap.source_observation(
            "example.py", lines=(2,), anchor_context_lines=0
        )
        new = codemap.source_observation(
            "example.py", lines=(2,), anchor_context_lines=1
        )
    assert old == zero
    assert old["line_anchors"][0]["state"] == "observed"
    assert "context_excerpt" not in old["line_anchors"][0]
    assert (
        old["line_anchors"][0]["line_sha256"] == new["line_anchors"][0]["line_sha256"]
    )
    assert new["limits"]["anchor_context_lines"] == 1
    assert "anchor_context_lines" not in old["limits"]
    assert new["observation_identity"] != old["observation_identity"]
    assert new["source_shape"] == old["source_shape"]
    assert new["line_coverage"] == old["line_coverage"] == "complete"
    rows = new["line_anchors"][0]["context_excerpt"]
    assert [(row["line"], row["role"]) for row in rows] == [
        (1, "context"),
        (2, "anchor"),
        (3, "context"),
    ]
    assert [row["text"] for row in rows] == ["before", "needle", "after"]
    assert all(row["start_column"] == 1 for row in rows)
    assert all(not row["truncated_right"] for row in rows)


def test_line_context_clips_long_unicode_lines_without_changing_byte_anchor(
    tmp_path: Path,
) -> None:
    (tmp_path / "example.py").write_text(
        "before\n" + "ö" * 400 + "needle\n" + "after\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.source_observation(
            "example.py", lines=(2,), anchor_context_lines=1
        )
    anchor = packet["line_anchors"][0]
    assert anchor["state"] == "observed"
    excerpt = anchor["context_excerpt"][1]
    assert excerpt["role"] == "anchor"
    assert excerpt["start_column"] == 1
    assert excerpt["text"] == "ö" * 320
    assert excerpt["truncated_left"] is False
    assert excerpt["truncated_right"] is True
    assert packet["source_shape"]["maximum_physical_line_bytes"] > 400


def test_unknown_blank_and_out_of_range_lines_never_get_excerpts(
    tmp_path: Path,
) -> None:
    (tmp_path / "example.py").write_text("head\n\nfoot\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.source_observation(
            "example.py", lines=(2, 4, 3), anchor_context_lines=1
        )
    assert [row["line"] for row in packet["line_anchors"]] == [2, 3, 4]
    assert [row["state"] for row in packet["line_anchors"]] == [
        "unknown",
        "observed",
        "unknown",
    ]
    assert "context_excerpt" not in packet["line_anchors"][0]
    assert "context_excerpt" not in packet["line_anchors"][2]
    assert packet["line_coverage"] == "unknown"


def test_denied_unreconciled_oversized_and_invalid_utf8_never_expose_context(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text("PRIVATE=sensitive\n", encoding="utf-8")
    path = tmp_path / "sample.py"
    path.write_text("needle\n", encoding="utf-8")
    (tmp_path / "bad.py").write_bytes(b"invalid=\xff\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        denied = codemap.source_observation(".env", lines=(1,), anchor_context_lines=1)
        oversized = codemap.source_observation(
            "sample.py", lines=(1,), anchor_context_lines=1, max_bytes=1
        )
        invalid = codemap.source_observation(
            "bad.py", lines=(1,), anchor_context_lines=1
        )
        path.write_text("different\n", encoding="utf-8")
        stale = codemap.source_observation(
            "sample.py", lines=(1,), anchor_context_lines=1
        )
    for packet in (denied, oversized, invalid, stale):
        assert packet["line_anchors"] == []
        assert packet["line_coverage"] == "unknown"
        assert packet["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize("bad", [-1, 2, True, None, "1", 0.5])
def test_invalid_native_line_context_fails_before_source_read(
    tmp_path: Path, bad: object
) -> None:
    with CodeMap(tmp_path) as codemap:
        with pytest.raises(ValueError, match="anchor_context_lines"):
            codemap.source_observation(
                "not-present.py",
                lines=(1,),
                anchor_context_lines=bad,  # type: ignore[arg-type]
            )


def test_line_context_requires_explicit_bounded_lines(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        with pytest.raises(ValueError, match="requires 1 to 8"):
            codemap.source_observation("not-present.py", anchor_context_lines=1)
        with pytest.raises(ValueError, match="requires 1 to 8"):
            codemap.source_observation(
                "not-present.py", lines=tuple(range(1, 10)), anchor_context_lines=1
            )


def test_mcp_line_context_transports_without_changing_literal_context(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("before\nneedle\nafter\n", encoding="utf-8")
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        source = surface.source_observation(
            ["a.py"], context_lines={"lines": [2], "radius": 1}
        )
        original = deepcopy(source)
        projected = present_repository_evidence(source, format="compact")
        group = next(g for g in projected["groups"] if g["family"] == "source")
        anchor = next(row for row in group["findings"] if row["kind"] == "line_anchors")
        assert anchor["source_refs"] == ["/line_anchors/0"]
        assert anchor["details"]["context_excerpt"][1]["text"] == "needle"
        assert anchor["details"]["context_excerpt"][1]["role"] == "anchor"
        assert source == original
        literal = surface.source_observation(
            ["a.py"], literal="needle", context_lines=1
        )
        assert literal["occurrences"][0]["context_excerpt"][1]["role"] == "match"
    finally:
        surface.close()


@pytest.mark.parametrize(
    "context",
    [
        {"lines": [], "radius": 1},
        {"lines": [1, 1], "radius": 1},
        {"lines": [0], "radius": 1},
        {"lines": [True], "radius": 1},
        {"lines": list(range(1, 10)), "radius": 1},
        {"lines": [1], "radius": 2},
        {"lines": [1], "radius": True},
        {"lines": [1], "radius": "1"},
        {"lines": "1", "radius": 1},
        {"lines": [1]},
        {"lines": [1], "radius": 1, "other": 0},
    ],
)
def test_mcp_invalid_line_requests_fail_before_source_sync(
    tmp_path: Path, context: dict[str, object]
) -> None:
    surface = HashmarksMcpSurface(str(tmp_path), state_dir=str(tmp_path / "state"))
    try:
        with pytest.raises(McpSurfaceError, match="line|context_lines"):
            surface.source_observation(["unreadable.py"], context_lines=context)
        with pytest.raises(McpSurfaceError, match="line context"):
            surface.source_observation(
                ["unreadable.py"],
                literal="needle",
                context_lines={"lines": [1], "radius": 1},
            )
        with pytest.raises(McpSurfaceError, match="line context"):
            surface.source_observation(
                ["unreadable.py"],
                result_mode="scope",
                literal="needle",
                context_lines={"lines": [1], "radius": 1},
            )
    finally:
        surface.close()
