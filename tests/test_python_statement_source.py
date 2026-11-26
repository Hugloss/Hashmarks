import sqlite3
import sys
from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks import CodeMap
from hashmarks.codemap.python_ast import estimate_tokens


def test_unpacked_module_names_restore_source_choices_and_importing_test(
    tmp_path: Path,
) -> None:
    (tmp_path / "settings.py").write_text(
        "ALLOWED_FIELDS, REQUIRED_FIELDS = read_schema()\n"
    )
    (tmp_path / "legacy.py").write_text("ALLOWED_FIELDS = ('old',)\n")
    for module in ("settings", "legacy"):
        (tmp_path / f"test_{module}.py").write_text(
            f"from {module} import ALLOWED_FIELDS\ndef test_fields(): assert ALLOWED_FIELDS\n"
        )
    with CodeMap(tmp_path) as codemap:
        find = codemap.search.packet("ALLOWED_FIELDS")
        assert find["observed_exact_match_count"] == 2
        choice = codemap.source.read("ALLOWED_FIELDS")
        assert choice["ambiguous"]
        assert {row["path"] for row in assert_records(choice["matches"])} == {
            "settings.py",
            "legacy.py",
        }
        current = codemap.source.read("settings.py::ALLOWED_FIELDS")
        assert current["content"] == "ALLOWED_FIELDS, REQUIRED_FIELDS = read_schema()"
        assert current["signature"] == "ALLOWED_FIELDS"
        verification = codemap.verification.changed_set(["settings.py"])
        assert [row["path"] for row in assert_records(verification["targets"])] == [
            "test_settings.py"
        ]
        assert verification["negative_evidence_admissible"] is False


def test_unpacking_indexes_only_lexical_names_and_retains_the_shared_statement(
    tmp_path: Path,
) -> None:
    # Python normalizes identifier keys. Display the target's authored spelling.
    spelling = "cafe\u0301"
    statement = (
        f"entire = ({spelling}, [minimum, *extras], obj.state, table[index]) = unpack()"
    )
    (tmp_path / "config.py").write_text(
        f"prefix = '界'; {statement}; tail = 1\n"
        "def factory():\n    local_a, local_b = pair()\n"
        "class Group:\n    class_a, class_b = pair()\n"
    )
    with CodeMap(tmp_path) as codemap:
        outline = assert_records(codemap.source.outline("config.py")["symbols"])
        bindings = {row["name"]: row for row in outline if row["kind"] == "binding"}
        assert set(bindings) == {
            "prefix",
            "entire",
            "café",
            "minimum",
            "extras",
            "tail",
        }
        assert bindings["entire"]["signature"] == statement
        for name, header in (
            ("café", spelling),
            ("minimum", "minimum"),
            ("extras", "extras"),
        ):
            source = codemap.source.read(f"config.py::{name}")
            assert source["content"] == statement
            assert source["signature"] == header
            assert source["start_byte_column"] == len("prefix = '界'; ".encode())
            assert (
                source["estimated_tokens"]
                == bindings[name]["body_tokens"]
                == estimate_tokens(statement)
            )


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="Type aliases require the native Python 3.12 grammar",
)
def test_shared_line_type_alias_discloses_only_its_statement(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        'message = "界"; type Result = int | str; status = 0\n'
    )
    with CodeMap(tmp_path) as codemap:
        result = codemap.source.read("api.py::Result")
    assert result["content"] == result["signature"] == "type Result = int | str"
    assert result["start_byte_column"] == len('message = "界"; '.encode())


def test_sibling_assignment_does_not_consume_symbol_budget(tmp_path: Path) -> None:
    prefix = 'BANNER = "' + "q" * 8000 + '"; '
    binding = "RETRY_LIMIT = 3"
    (tmp_path / "settings.py").write_text(prefix + binding + "\n")
    with CodeMap(tmp_path) as codemap:
        source = codemap.source.read("settings.py::RETRY_LIMIT", token_budget=32)
        hit = assert_records(codemap.search.packet("RETRY_LIMIT", limit=1)["results"])[
            0
        ]
        symbols = codemap.source.outline("settings.py")["symbols"]
        indexed = next(
            row for row in assert_records(symbols) if row["name"] == "RETRY_LIMIT"
        )
    assert hit["signature"] == source["content"] == source["signature"] == binding
    assert source["too_large"] is False
    assert (
        source["estimated_tokens"] == indexed["body_tokens"] == estimate_tokens(binding)
    )
    assert (source["start_byte_column"], source["end_byte_column"]) == (
        len(prefix.encode()),
        len((prefix + binding).encode()),
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_multiline_bindings_use_utf8_columns_on_both_boundary_lines(
    tmp_path: Path, newline: str
) -> None:
    prefix = 'π = "界"; '
    first, last = "résultat: str = (", '    "réussi")'
    lines = (
        prefix + first,
        last + "; FIN = True",
        "if FIN: visible = 12",
        "normal = 3  # note",
    )
    (tmp_path / "data.py").write_bytes((newline.join(lines) + newline).encode())
    with CodeMap(tmp_path) as codemap:
        value = codemap.source.read("data.py::résultat")
        assert value["signature"] == first and value["content"] == first + "\n" + last
        assert value["lines"] == [1, 2]
        assert [value["start_byte_column"], value["end_byte_column"]] == [
            len(prefix.encode()),
            len(last.encode()),
        ]
        assert codemap.source.read("data.py::π")["content"] == 'π = "界"'
        assert codemap.source.read("data.py::FIN")["content"] == "FIN = True"
        assert codemap.source.read("data.py::visible")["content"] == "visible = 12"
        normal = codemap.source.read("data.py::normal")
        assert normal["content"] == "normal = 3  # note"
        assert "start_byte_column" not in normal and "end_byte_column" not in normal


def test_occurrence_columns_survive_artifact_reuse_and_refresh(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    member = root / "data.py"
    member.write_text("value = 1; value = 2\n")
    state = tmp_path / "state"
    db = tmp_path / "artifacts.sqlite3"
    with CodeMap(root, state_dir=state, artifact_db=db) as codemap:
        codemap.index.sync()
        assert codemap.source.read("data.py::value")["content"] == "value = 1"
    # An older generated workspace schema is disposable. Rebuild its symbol
    # rows from the shared parsed artifact, including the two occurrences.
    with sqlite3.connect(state / "codemap.sqlite3") as connection:
        connection.execute("DROP TABLE symbol")
        connection.execute("CREATE TABLE symbol(path TEXT, qualname TEXT)")
    with CodeMap(root, state_dir=state, artifact_db=db) as codemap:
        assert codemap.index.sync().reused_artifacts == 1
        both = codemap.source.read("data.py::value")
        assert [r["start_byte_column"] for r in assert_records(both["matches"])] == [
            0,
            11,
        ]
        assert codemap.source.read("data.py::value@L1")["content"] == "value = 2"
        member.write_text('value = "界"; value = 3\n')
        updated = codemap.source.read("data.py::value@L1")
        assert updated["start_byte_column"] == len('value = "界"; '.encode())
        assert updated["content"] == "value = 3"
