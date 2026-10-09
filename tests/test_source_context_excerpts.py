"""Regression contracts for Hermes-inspired source match context.

Source excerpts are a bounded projection over the same stable admitted bytes,
not a repository-wide grep/read endpoint or an independent evidence authority.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from hashmarks import CodeMap
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError


def test_context_is_opt_in_and_does_not_change_location_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "sample.py").write_text(
        "def f():\n    value = 'needle'\n    return value\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        legacy = codemap.source_observation("sample.py", literal="needle")
        explicit_zero = codemap.source_observation(
            "sample.py", literal="needle", context_lines=0
        )
        contextual = codemap.source_observation(
            "sample.py", literal="needle", context_lines=1
        )
    assert legacy == explicit_zero
    assert "context_lines" not in legacy["limits"]
    assert "context_excerpt" not in legacy["occurrences"][0]
    assert contextual["limits"]["context_lines"] == 1
    assert (
        contextual["occurrences"][0]["evidence_identity"]
        == (legacy["occurrences"][0]["evidence_identity"])
    )
    assert contextual["occurrences"][0]["column"] == legacy["occurrences"][0]["column"]
    assert contextual["observation_identity"] != legacy["observation_identity"]
    excerpt = contextual["occurrences"][0]["context_excerpt"]
    assert [(row["line"], row["role"]) for row in excerpt] == [
        (1, "context"),
        (2, "match"),
        (3, "context"),
    ]
    assert [row["text"] for row in excerpt] == [
        "def f():",
        "    value = 'needle'",
        "    return value",
    ]
    assert all(row["start_column"] == 1 for row in excerpt)
    assert all(
        row["truncated_left"] is False and row["truncated_right"] is False
        for row in excerpt
    )


def test_long_physical_lines_clip_without_losing_match_or_unicode_columns(
    tmp_path: Path,
) -> None:
    path = tmp_path / "example.py"
    path.write_text(
        "prefix\n" + "ö" * 2000 + "needle" + "z" * 3000 + "\nsuffix\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.source_observation(
            "example.py", literal="needle", context_lines=1
        )
    hit = packet["occurrences"][0]
    assert hit["column"] == 2001  # Unicode codepoints, not UTF-8 bytes
    rows = hit["context_excerpt"]
    assert len(rows) == 3
    match = rows[1]
    assert match["start_column"] > 1
    assert match["truncated_left"] is True
    assert match["truncated_right"] is True
    assert len(match["text"]) <= 320
    assert "needle" in match["text"]
    assert match["text"].index("needle") + match["start_column"] == hit["column"]
    assert packet["observed_match_count"] == 1
    assert packet["completeness"] == "complete"


def test_crlf_boundary_and_first_last_lines_do_not_invent_extra_lines(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_bytes(b"needle\r\nother\r\nneedle\r\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.source_observation("a.py", literal="needle", context_lines=1)
    first, last = packet["occurrences"]
    assert [x["line"] for x in first["context_excerpt"]] == [1, 2]
    assert [x["line"] for x in last["context_excerpt"]] == [2, 3]
    assert first["context_excerpt"][0]["text"] == "needle"
    assert last["context_excerpt"][-1]["text"] == "needle"
    assert all(
        not row["text"].endswith("\r")
        for hit in (first, last)
        for row in hit["context_excerpt"]
    )


def test_scoped_context_reuses_member_admission_and_preserves_native_counts(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("one\nneedle\ntwo\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("three\nneedle\nfour\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        original = codemap.scoped_source_occurrences(["a.py", "b.py"], "needle")
        contextual = codemap.scoped_source_occurrences(
            ["a.py", "b.py"], "needle", context_lines=1
        )
    assert original["observed_match_count"] == contextual["observed_match_count"] == 2
    assert original["source_coverage"] == contextual["source_coverage"]
    assert original["negative_evidence"] == contextual["negative_evidence"]
    assert "context_lines" not in original["limits"]
    assert contextual["limits"]["context_lines"] == 1
    assert [row["path"] for row in contextual["occurrences"]] == ["a.py", "b.py"]
    assert all("context_excerpt" in row for row in contextual["occurrences"])
    assert [row["evidence_identity"] for row in contextual["occurrences"]] == [
        row["evidence_identity"] for row in original["occurrences"]
    ]


def test_context_never_escapes_denied_oversized_or_unreconciled_members(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text("SECRET=needle\n", encoding="utf-8")
    path = tmp_path / "sample.py"
    path.write_text("value = 'needle'\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        denied = codemap.source_observation(".env", literal="needle", context_lines=1)
        oversized = codemap.source_observation(
            "sample.py", literal="needle", context_lines=1, max_bytes=2
        )
        path.write_text("value = 'changed'\n", encoding="utf-8")
        stale = codemap.source_observation(
            "sample.py", literal="needle", context_lines=1
        )
    for result in (denied, oversized, stale):
        assert result["occurrences"] == []
        assert result["negative_evidence"] == "not-admissible"
        assert result["observed_match_count"] is None


@pytest.mark.parametrize("bad", [-1, 2, True, 0.5, "1", None])
def test_invalid_context_fails_before_source_observation(
    tmp_path: Path, bad: object
) -> None:
    (tmp_path / "sample.py").write_text("needle\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="context_lines"):
            codemap.source_observation(
                "sample.py",
                literal="needle",
                context_lines=bad,  # type: ignore[arg-type]
            )
        with pytest.raises(ValueError, match="context_lines"):
            codemap.scoped_source_occurrences(
                ["sample.py"],
                "needle",
                context_lines=bad,  # type: ignore[arg-type]
            )



def test_source_line_keywords_remain_supported_but_typos_fail_early(
    tmp_path: Path,
) -> None:
    (tmp_path / "sample.py").write_text("needle\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(TypeError, match="unexpected source observation keyword"):
            codemap.source_observation(
                "sample.py", literal="needle", context_line=1  # type: ignore[call-arg]
            )
        observed = codemap.source_observation(
            "sample.py", literal="needle", lines=(1,), context_lines=1
        )
    assert observed["requested_lines"] == [1]
    assert observed["line_coverage"] == "complete"
    assert observed["occurrences"][0]["context_excerpt"][0]["role"] == "match"


def test_context_requires_literal_and_does_not_read_file_for_preview(
    tmp_path: Path,
) -> None:
    path = tmp_path / "a.py"
    path.write_text("x = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="requires a literal"):
            codemap.source_observation("a.py", context_lines=1)


def test_mcp_context_is_bounded_and_structured_projection_keeps_source_pointer(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("above\nneedle\nbelow\n", encoding="utf-8")
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        raw = surface.source_observation(["a.py"], literal="needle", context_lines=1)
        scope = surface.source_observation(
            ["a.py"], literal="needle", context_lines=1, result_mode="scope"
        )
        assert raw["occurrences"][0]["context_excerpt"][1]["text"] == "needle"
        assert scope["occurrences"][0]["context_excerpt"][1]["text"] == "needle"
        original = deepcopy(raw)
        projected = present_repository_evidence(raw, format="compact")
        source = next(g for g in projected["groups"] if g["family"] == "source")
        occurrence = next(
            row for row in source["findings"] if row["kind"] == "occurrences"
        )
        assert occurrence["source_refs"] == ["/occurrences/0"]
        assert occurrence["details"]["context_excerpt"][1]["role"] == "match"
        assert raw == original
        for bad in (2, -1, True, "1"):
            with pytest.raises(McpSurfaceError, match="context_lines"):
                surface.source_observation(
                    ["a.py"],
                    literal="needle",
                    context_lines=bad,  # type: ignore[arg-type]
                )
        with pytest.raises(McpSurfaceError, match="requires a literal"):
            surface.source_observation(["a.py"], context_lines=1)
    finally:
        surface.close()
