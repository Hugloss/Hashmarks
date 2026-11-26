import tokenize
from pathlib import Path

import pytest
from contract_assertions import assert_integer, assert_object, assert_records

from hashmarks import CodeMap


@pytest.mark.parametrize("prefix", ["f", "Rf", "Fr"])
def test_formatted_string_fields_cannot_be_labelled_ordinary_string_text(
    tmp_path: Path, prefix: str
) -> None:
    text = (
        "def fmt(needle, width, r):\n"
        f'    return {prefix}"tag:{{needle!r:>{{width}}}}" + "return" + f"fixed"\n'
    )
    (tmp_path / "value.py").write_text(text)
    with CodeMap(tmp_path) as repository:
        packet = repository.source.scoped_literals(
            ["value.py"], ["needle", "width", "tag:", "r", "return", "fixed", "{needle"]
        )
    hits = assert_records(packet["occurrences"])
    kinds = {
        (hit["line"], hit["column"], hit["literal"]): hit["occurrence_kind"]
        for hit in hits
    }
    first, second = text.splitlines()
    split_tokens = hasattr(tokenize, "FSTRING_MIDDLE")
    for field in ("needle", "width"):
        assert kinds[(1, first.index(field) + 1, field)] == "identifier"
        assert kinds[(2, second.index(field) + 1, field)] == (
            "identifier" if split_tokens else "unknown"
        )
    assert kinds[(2, second.index("tag:") + 1, "tag:")] == (
        "string-literal" if split_tokens else "unknown"
    )
    assert kinds[(2, second.index("!r") + 2, "r")] == "unknown"
    assert kinds[(2, second.index("{needle") + 1, "{needle")] == "unknown"
    assert kinds[(2, second.index("return") + 1, "return")] == "unknown"
    assert kinds[(2, second.rindex("return") + 1, "return")] == "string-literal"
    assert kinds[(2, second.index("fixed") + 1, "fixed")] == "string-literal"


@pytest.mark.skipif(
    not hasattr(tokenize, "TSTRING_MIDDLE"),
    reason="Native template-string tokens required",
)
def test_template_string_text_and_replacement_fields_keep_separate_kinds(
    tmp_path: Path,
) -> None:
    text = 'message = t"label: {item}"\n'
    (tmp_path / "value.py").write_text(text)
    with CodeMap(tmp_path) as repository:
        for literal, expected in (
            ("label:", "string-literal"),
            ("item", "identifier"),
            ("{item", "unknown"),
        ):
            (hit,) = assert_records(
                repository.source.observe("value.py", literal=literal)["occurrences"]
            )
            assert (hit["occurrence_kind"], hit["column"]) == (
                expected,
                text.index(literal) + 1,
            )


@pytest.mark.parametrize("mode", ["member", "scope", "literals"])
def test_literal_owner_contains_the_entire_utf8_span(tmp_path: Path, mode: str) -> None:
    lines = [
        'ALPHA = "é界"; ZULU = ("needle", "needle"); END = 3',
        'LEFT, RIGHT = load_pair("shared")',
        "START = (",
        '    "first"); NEXT = (',
        '    "last")',
    ]
    (tmp_path / "values.py").write_text("\n".join(lines) + "\n")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        for literal, owner in (
            ("needle", "ZULU"),
            ("ZULU", "ZULU"),
            ("shared", None),
            ('"; ZULU', None),
            ("first", "START"),
            ("NEXT", "NEXT"),
            ("last", "NEXT"),
        ):
            if mode == "member":
                packet = repository.source.observe("values.py", literal=literal)
            elif mode == "scope":
                packet = repository.source.scoped_occurrences(["values.py"], literal)
            else:
                packet = repository.source.scoped_literals(
                    ["values.py"], [literal, "missing"]
                )
            hits = assert_records(packet["occurrences"])
            assert (
                len(hits)
                == packet["observed_match_count"]
                == (2 if literal == "needle" else 1)
            )
            for hit in hits:
                assert hit["enclosing_symbol"] == owner
                assert hit["symbol_basis"] == (
                    "indexed-containing-range" if owner else "unknown"
                )
                line, column = (
                    assert_integer(hit["line"]),
                    assert_integer(hit["column"]),
                )
                assert (
                    lines[line - 1][column - 1 : column - 1 + len(literal)] == literal
                )


@pytest.mark.parametrize("path", ["mixed.py", "mixed.PY"])
def test_mixed_newlines_keep_raw_locations_and_python_token_kinds(
    tmp_path: Path,
    path: str,
) -> None:
    text = '# intro\rdef first(): return "needle"\r\nclass Group:\r    def last(self):\n        return "éneedle"  # needle\n'
    (tmp_path / path).write_bytes(text.encode())
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.source.observe(path, literal="needle", context_lines=1)
        limited = repository.source.observe(path, literal="needle", limit=1)
    hits = assert_records(packet["occurrences"])
    assert [(h["line"], h["enclosing_symbol"], h["occurrence_kind"]) for h in hits] == [
        (1, "first", "string-literal"),
        (3, "Group.last", "string-literal"),
        (3, "Group.last", "comment"),
    ]
    for hit in hits:
        line, column = assert_integer(hit["line"]), assert_integer(hit["column"])
        assert text.split("\n")[line - 1][column - 1 :].startswith("needle")
        (excerpt,) = [
            r for r in assert_records(hit["context_excerpt"]) if r["role"] == "match"
        ]
        assert excerpt["line"] == line and excerpt["text"] == text.split("\n")[
            line - 1
        ].removesuffix("\r")
    assert limited["observed_match_count"] == 3 and limited["truncation"] == "truncated"
    assert len(assert_records(limited["occurrences"])) == 1


def test_new_index_publication_cannot_relabel_captured_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    path = root / "value.py"
    path.write_text("def original(): return 'old text'\n")
    state = tmp_path / "state"
    with (
        CodeMap(root, state_dir=state) as reader,
        CodeMap(root, state_dir=state) as writer,
    ):
        reader.index.sync()
        capture = reader.source._bounded_source_observation

        def publish_after_capture(
            relpath: str, max_bytes: int
        ) -> tuple[dict[str, object], bytes | None]:
            observed = capture(relpath, max_bytes)
            path.write_text("def replacement(): return 'new text'\n")
            writer.index.sync()
            return observed

        with monkeypatch.context() as patch:
            patch.setattr(
                reader.source, "_bounded_source_observation", publish_after_capture
            )
            before = reader.source.observe("value.py", literal="old text")
        after = reader.source.observe("value.py", literal="new text")
    (old_hit,) = assert_records(before["occurrences"])
    (new_hit,) = assert_records(after["occurrences"])
    assert old_hit["enclosing_symbol"] is None and old_hit["symbol_basis"] == "unknown"
    assert old_hit["occurrence_kind"] == "string-literal"
    assert (
        old_hit["member_revision"] == assert_object(before["member"])["member_revision"]
    )
    assert new_hit["enclosing_symbol"] == "replacement"
    assert new_hit["member_revision"] != old_hit["member_revision"]
