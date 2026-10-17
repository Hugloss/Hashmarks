from pathlib import Path

from hashmarks.codemap import CodeMap


def test_sql_is_indexed_as_editable_source_evidence(tmp_path: Path) -> None:
    (tmp_path / "queries").mkdir()
    (tmp_path / "queries" / "ember_731.sql").write_text(
        "SELECT 'old-ember-731' AS label;\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ember_731.py").write_text(
        "def test_ember_731():\n    pass\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as c:
        c.index.sync()
        action = c.task_action_map("Change ember_731 SQL label")
    assert action["edit"] is not None
    assert action["edit"]["path"] == "queries/ember_731.sql"


def test_lexical_file_candidates_count_distinct_terms_not_occurrences(
    tmp_path: Path,
) -> None:
    (tmp_path / "many.txt").write_text("alpha alpha alpha beta\n", encoding="utf-8")
    (tmp_path / "one.txt").write_text("alpha\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        rows = codemap.store.lexical_file_candidates(["alpha", "beta"], limit=10)
    by_path = {str(row["path"]): int(row["matches"]) for row in rows}
    assert by_path["many.txt"] == 2
    assert by_path["one.txt"] == 1
    assert [str(row["path"]) for row in rows[:2]] == ["many.txt", "one.txt"]


def test_lexical_scope_is_preserved_before_bounds_and_across_session_cache(
    tmp_path: Path,
) -> None:
    (tmp_path / "first.txt").write_text("cleanup\n")
    (tmp_path / "second.txt").write_text("cleanup\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with codemap.reads.session():
            unscoped = codemap.reads.lexical_file_candidates(["cleanup"], limit=1)
            second = codemap.reads.lexical_file_candidates(
                ["cleanup"], limit=1, paths=["second.txt"]
            )
            empty = codemap.reads.lexical_file_candidates(
                ["cleanup"], limit=1, paths=[]
            )
            first = codemap.reads.lexical_file_candidates(
                ["cleanup"], limit=1, paths=["first.txt"]
            )
    assert [row["path"] for row in unscoped] == ["first.txt"]
    assert [row["path"] for row in second] == ["second.txt"]
    assert empty == []
    assert [row["path"] for row in first] == ["first.txt"]
