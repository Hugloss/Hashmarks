"""A presentation prefix cannot decide test identity over a truncated module."""

from pathlib import Path

from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.codemap import CodeMap


def test_late_relevant_test_declaration_is_not_hidden_by_module_prefix(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend.py").write_text("def execute(): return 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_backend.py").write_text(
        "from backend import execute\n"
        + "".join(f"def test_other_{i}(): assert execute() == 1\n" for i in range(80))
        + "def test_reserved_attribute_warning(): assert execute() == 1\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relevance = codemap.verification_relevance(
            "Fix backend.py execute reserved attribute warning"
        )
    rows = assert_records(relevance["candidates"])
    row = next(row for row in rows if row["path"] == "tests/test_backend.py")
    assert row["test_symbol"] == "test_reserved_attribute_warning"
    assert {"reserved", "attribute", "warning"} <= set(
        assert_array(row["task_anchor_terms"])
    )
    selected = assert_object(relevance["selected"])
    assert selected["test_symbol"] == "test_reserved_attribute_warning"


def test_late_equal_match_preserves_unknown_test_symbol(tmp_path: Path) -> None:
    (tmp_path / "backend.py").write_text("def execute(): return 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_backend.py").write_text(
        "from backend import execute\n"
        "def test_reserved_attribute_warning_first(): assert execute() == 1\n"
        + "".join(f"def test_other_{i}(): assert execute() == 1\n" for i in range(80))
        + "def test_reserved_attribute_warning_last(): assert execute() == 1\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relevance = codemap.verification_relevance(
            "Fix backend.py execute reserved attribute warning"
        )
    rows = assert_records(relevance["candidates"])
    row = next(row for row in rows if row["path"] == "tests/test_backend.py")
    assert row["test_symbol"] is None
    assert assert_object(relevance["selected"])["test_symbol"] is None
