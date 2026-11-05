"""Quoted source/data extents preserve syntax without interpreting execution."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from hashmarks.codemap import (
    CodeMap,
    MakeShellDeclarations,
    RepositoryDeclarationProviderError,
)
from hashmarks.codemap.make_shell_declarations import MAX_STATEMENT_CHARS


def _observe(root: Path, source: str) -> dict:
    (root / "demo.sh").write_text(source, encoding="utf-8", newline="")
    with CodeMap(root) as native:
        native.index.sync()
        packet = native.declarations.discover(
            [MakeShellDeclarations(shell_paths=("demo.sh",), layout="file")]
        )
    declarations = packet["declarations"]
    assert isinstance(declarations, dict)
    groups = declarations["groups"]
    assert isinstance(groups, list)
    rows = groups[0]["declarations"]
    assert isinstance(rows, list)
    return rows[0]["value"]


def _commands(value: dict) -> list[dict]:
    return [
        row["value"]
        for row in value["facts"]
        if row["kind"] == "shell-command-expression"
    ]


def _assert_native_bash_syntax_when_available(source: str) -> None:
    bash = shutil.which("bash")
    if bash is not None:
        result = subprocess.run(
            [bash, "-n"],
            input=source.encode("utf-8"),
            capture_output=True,
            timeout=5,
        )
        assert result.returncode == 0 and result.stderr == b""


@pytest.mark.parametrize("suffix", ["\r", "\u2028", "\u00a0"])
def test_non_shell_whitespace_cannot_shorten_a_quoted_delimiter_and_expose_data(
    tmp_path: Path, suffix: str
) -> None:
    source = f"cat <<'D'{suffix}\nD\ncommand_like_payload\nD{suffix}\n"
    _assert_native_bash_syntax_when_available(source)
    value = _observe(tmp_path, source)
    assert value["facts_completeness"] == "incomplete"
    assert _commands(value) == []
    assert value["negative_evidence_admissible"] is False


def test_non_shell_whitespace_inside_a_comment_does_not_change_the_delimiter(
    tmp_path: Path,
) -> None:
    source = "cat <<'D' # comment\r\npayload\nD\necho resumed\n"
    _assert_native_bash_syntax_when_available(source)
    value = _observe(tmp_path, source)
    assert value["facts_completeness"] == "complete-supported-subset"
    assert [row["literal_argv"] for row in _commands(value)] == [["echo", "resumed"]]


def test_file_evidence_uses_physical_lf_extent_for_unicode_quoted_data(
    tmp_path: Path,
) -> None:
    source = "echo 'one\u2028two'\necho after\n"
    _observe(tmp_path, source)
    with CodeMap(tmp_path) as native:
        native.index.sync()
        packet = native.declarations.discover(
            [MakeShellDeclarations(shell_paths=("demo.sh",), layout="file")]
        )
    declarations = packet["declarations"]
    assert isinstance(declarations, dict)
    evidence = declarations["repository_evidence"]["bindings"][0]["evidence"][0]
    assert evidence["start_line"] == 1 and evidence["end_line"] == 2


@pytest.mark.parametrize("quote", ["'", '"'])
def test_multiline_literal_word_is_one_native_source_word(
    tmp_path: Path, quote: str
) -> None:
    literal = "before\nfi; commandlike payload\nafter"
    value = _observe(tmp_path, f"printf '%s' {quote}{literal}{quote}\necho resumed\n")
    first, second = _commands(value)
    assert first["literal_argv"] == ["printf", "%s", literal]
    assert second["literal_argv"] == ["echo", "resumed"]
    assert value["facts"][0]["start_line"] == 1 and value["facts"][0]["end_line"] == 3
    assert first["context"] == second["context"] == []
    assert value["negative_evidence_admissible"] is False


def test_shell_tabs_and_backslashes_inside_multiline_single_quotes_are_data(
    tmp_path: Path,
) -> None:
    value = _observe(tmp_path, "\tprintf '%s' 'before\\\n\tafter'\necho resumed\n")
    assert _commands(value)[0]["literal_argv"] == ["printf", "%s", "before\\\n\tafter"]


def test_comments_cannot_open_a_quote_or_splice_a_later_statement(
    tmp_path: Path,
) -> None:
    value = _observe(
        tmp_path, "# \"unclosed \\\necho first; # 'unclosed \\\necho second\n"
    )
    assert [row["literal_argv"] for row in _commands(value)] == [
        ["echo", "first"],
        ["echo", "second"],
    ]


@pytest.mark.parametrize("quote", ["'", '"'])
def test_quoted_heredoc_body_is_opaque_and_has_exact_utf8_source_range(
    tmp_path: Path, quote: str
) -> None:
    header = f"cat <<{quote}PAYLOAD{quote}\n"
    body = "fi\n{ malformed '\" λ\ndata\u2028PAYLOAD\nrunner --wipe\n# commandlike comment\n"
    terminator = "PAYLOAD\n"
    source = header + body + terminator + "echo resumed\n"
    value = _observe(tmp_path, source)
    assert [row["literal_argv"] for row in _commands(value)] == [["echo", "resumed"]]
    data = next(
        row["value"] for row in value["facts"] if row["kind"] == "shell-heredoc-data"
    )
    start, end = len(header.encode()), len((header + body).encode())
    assert data["body_source_range"] == {"start_byte": start, "end_byte": end}
    assert source.encode()[start:end] == body.encode()
    assert data["terminator_source_range"] == {
        "start_byte": end,
        "end_byte": end + len(terminator),
    }
    assert data["body_observation"] == "uninterpreted-data"
    assert data["state"] == "source-extent-observed"
    assert data["execution"] == "not-established"
    assert value["facts_completeness"] == "complete-supported-subset"


def test_heredoc_keywords_do_not_close_the_real_function_or_control_scope(
    tmp_path: Path,
) -> None:
    source = "run() {\nif inspect <<'BODY'; then\n}\nfi\nBODY\necho inside\nfi\n}\nrun\necho outside\n"
    value = _observe(tmp_path, source)
    inside, invocation, outside = _commands(value)
    assert inside["literal_argv"] == ["echo", "inside"]
    assert inside["context"] == ["function:run:1", "conditional-or-loop:2"]
    assert invocation["literal_argv"] == ["run"]
    assert outside["context"] == []


@pytest.mark.parametrize(
    "redirection", ["<<BODY", '<<"$DYNAMIC"', "<<-'BODY'", "<<'ONE' <<'TWO'"]
)
def test_unsupported_heredoc_delimiters_keep_remaining_source_unobserved(
    tmp_path: Path, redirection: str
) -> None:
    value = _observe(
        tmp_path, f"cat {redirection}\ncommandlike data\nBODY\necho later\n"
    )
    assert value["facts_completeness"] == "incomplete"
    assert value["remaining_source"] == "not-observed"
    assert _commands(value) == []
    assert value["negative_evidence_admissible"] is False


def test_missing_heredoc_terminator_is_incomplete_even_when_body_looks_like_code(
    tmp_path: Path,
) -> None:
    value = _observe(tmp_path, "cat <<'BODY'\nfi\n}\necho payload\n")
    data = next(
        row["value"] for row in value["facts"] if row["kind"] == "shell-heredoc-data"
    )
    assert data["state"] == "unterminated"
    assert data["terminator_source_range"] is None
    assert value["facts_completeness"] == "incomplete"
    assert _commands(value) == []


def test_here_string_is_uninterpreted_same_line_input_without_hiding_later_source(
    tmp_path: Path,
) -> None:
    value = _observe(tmp_path, 'IFS="|" read -r name <<<"$INPUT"\necho resumed\n')
    assert value["facts_completeness"] == "complete-supported-subset"
    assert [row["literal_argv"] for row in _commands(value)] == [["echo", "resumed"]]
    assert not any(row["kind"] == "shell-heredoc-data" for row in value["facts"])
    unresolved = value["facts"][0]["value"]
    assert "<<<" in unresolved["token_expressions"]
    assert unresolved["execution"] == "not-established"


@pytest.mark.parametrize(
    "source",
    [
        "echo 'never\nclosed\n",
        "echo '" + "a\n" * (MAX_STATEMENT_CHARS // 2) + "'\n",
        "cat <<'BODY'\n" + "x" * (MAX_STATEMENT_CHARS + 1) + "\nBODY\n",
    ],
)
def test_unclosed_or_oversized_capture_never_returns_an_apparently_complete_prefix(
    tmp_path: Path, source: str
) -> None:
    with pytest.raises(RepositoryDeclarationProviderError):
        _observe(tmp_path, source)
