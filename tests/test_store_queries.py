from pathlib import Path

from hashmarks.codemap import CodeMap


def test_refs_many_high_frequency_symbol_keeps_deterministic_bounded_prefix(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    for i in range(1100):
        (src / f"m{i:04d}.py").write_text(
            "from shared import f\n" + f"def local_{i}():\n    return f()\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        rows = codemap.store.refs_many(["shared.f", "other.f"], limit_per_target=1024)
        assert len(rows["shared.f"]) == 1024
        assert rows["shared.f"] == rows["other.f"]
        ordered = [(row["path"], row["line"]) for row in rows["shared.f"]]
        assert ordered == sorted(ordered)
        assert ordered[:4] == [
            ("src/m0000.py", 1),
            ("src/m0000.py", 3),
            ("src/m0001.py", 1),
            ("src/m0001.py", 3),
        ]


def test_paths_under_is_segment_safe_for_exact_and_descendant_ranges(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/pkg").mkdir(parents=True)
    (tmp_path / "src2").mkdir()
    (tmp_path / "src0").mkdir()
    (tmp_path / "src/a.py").write_text("VALUE = 1\n")
    (tmp_path / "src/pkg/b.py").write_text("VALUE = 2\n")
    (tmp_path / "src/å.py").write_text("VALUE = 3\n")
    (tmp_path / "src2/not_child.py").write_text("VALUE = 4\n")
    (tmp_path / "src0/not_child.py").write_text("VALUE = 5\n")

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.index.sync()
        assert codemap.store.paths_under("src") == {
            "src/a.py",
            "src/pkg/b.py",
            "src/å.py",
        }
        assert codemap.store.paths_under("src/a.py") == {"src/a.py"}
        assert codemap.store.paths_under("src2") == {"src2/not_child.py"}
        assert codemap.store.paths_under("missing") == set()


def test_has_files_is_exact_and_independent_of_other_surface_counts(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("VALUE = 1\n")
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        assert codemap.store.has_files() is False
        codemap.index.sync()
        assert codemap.store.has_files() is True
        codemap.store.delete_paths(["src/a.py"])
        assert codemap.store.has_files() is False


def test_search_candidates_match_repository_fields_in_stable_order(
    tmp_path: Path,
) -> None:
    (tmp_path / "z_path_needle.py").write_text(
        "def transform():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text(
        "def needle_second():\n    return 2\n",
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text(
        "def needle_first():\n    return 1\n\n"
        "def transform(value: NeedleType):\n    return value\n",
        encoding="utf-8",
    )

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.index.sync()
        first = codemap.store.search_candidates("needle", limit=20)
        second = codemap.store.search_candidates("needle", limit=20)

    assert first == second

    symbols = [row for row in first if row["row_type"] == "symbol"]
    symbol_order = [
        (row["path"], row["start_line"], row["qualname"]) for row in symbols
    ]
    assert symbol_order == sorted(symbol_order)
    assert any(row["name"] == "needle_first" for row in symbols)
    assert any(row["name"] == "needle_second" for row in symbols)
    assert any(row["name"] == "transform" and row["path"] == "a.py" for row in symbols)
    assert any(row["path"] == "z_path_needle.py" for row in symbols)

    files = [row for row in first if row["row_type"] == "file"]
    assert [row["path"] for row in files] == ["z_path_needle.py"]


def test_scoped_references_filter_paths_before_row_bound(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "noise.py").write_text(
        "from owner import Thing\n" + "Thing()\n" * 12
    )
    target = "tests/test_thing.py"
    (tmp_path / target).write_text(
        "from owner import Thing\ndef test_thing(): Thing()\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        raw = codemap.store.refs_many(["Thing"], limit_per_target=2)["Thing"]
        assert all(row["path"] != target for row in raw)
        scoped = codemap.store.refs_many_for_paths(
            ["owner.Thing", "other.Thing"], [target], limit_per_target=2
        )
        assert len(scoped["owner.Thing"]) == 2
        assert scoped["owner.Thing"] == scoped["other.Thing"]
        assert all(row["path"] == target for row in scoped["owner.Thing"])
        assert codemap.store.refs_many_for_paths(["Thing"], [], limit_per_target=2) == {
            "Thing": []
        }


def test_reference_priority_preserves_capacity_and_independent_cached_orders(
    tmp_path: Path,
) -> None:
    (tmp_path / "a_source.py").write_text("from owner import Thing\n" + "Thing()\n" * 8)
    (tmp_path / "tests").mkdir()
    preferred = "tests/test_thing.py"
    (tmp_path / preferred).write_text("from owner import Thing\nThing()\n")
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as repository:
        repository.index.sync()
        with repository.reads.session():
            original = repository.reads.refs_many(["Thing"], limit_per_target=4)
            prioritized = repository.reads.refs_many(
                ["Thing"], limit_per_target=4, preferred_paths=[preferred]
            )
            narrow = repository.reads.refs_many(
                ["other.Thing"],
                limit_per_target=1,
                preferred_paths=[preferred, preferred],
            )
            assert len(prioritized["Thing"]) == 4
            assert [row["path"] for row in prioritized["Thing"]] == [
                preferred,
                preferred,
                "a_source.py",
                "a_source.py",
            ]
            assert narrow["other.Thing"] == prioritized["Thing"][:1]
            narrow["other.Thing"][0]["path"] = "mutated.py"
            repeated = repository.reads.refs_many(
                ["Thing"], limit_per_target=1, preferred_paths=[preferred]
            )
            assert repeated["Thing"] == prioritized["Thing"][:1]
            assert repository.reads.refs_many(["Thing"], limit_per_target=4) == original
            assert all(row["path"] == "a_source.py" for row in original["Thing"])


def test_preferred_reference_window_keeps_its_truncation_lookahead(
    tmp_path: Path,
) -> None:
    (tmp_path / "a_source.py").write_text("from owner import Thing\nThing()\n")
    (tmp_path / "tests").mkdir()
    preferred = "tests/test_thing.py"
    (tmp_path / preferred).write_text("from owner import Thing\n" + "Thing()\n" * 1030)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as repository:
        repository.index.sync()
        with repository.reads.session():
            prefix = repository.reads.refs_many(
                ["Thing"], limit_per_target=1024, preferred_paths=[preferred]
            )["Thing"]
            lookahead = repository.reads.refs_many(
                ["Thing"], limit_per_target=1025, preferred_paths=[preferred]
            )["Thing"]
    assert len(prefix) == 1024
    assert len(lookahead) == 1025
    assert prefix == lookahead[:1024]
    assert all(row["path"] == preferred for row in lookahead)
