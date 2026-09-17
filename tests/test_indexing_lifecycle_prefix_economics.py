from hashmarks.codemap.indexing_lifecycle import _minimal_path_prefixes, _sorted_paths_under


def test_minimal_path_prefixes_collapses_duplicates_and_descendants_segment_safely() -> None:
    assert _minimal_path_prefixes(
        (
            "src/pkg/a.py",
            "src",
            "src/pkg",
            "src2/a.py",
            "src",
            "tests/unit",
            "tests",
        )
    ) == ("src", "src2/a.py", "tests")


def test_sorted_paths_under_returns_only_exact_path_and_segment_descendants() -> None:
    paths = (
        "src",
        "src/a.py",
        "src/pkg/b.py",
        "src2/a.py",
        "tests/test_a.py",
    )
    assert _sorted_paths_under(paths, "src") == {"src", "src/a.py", "src/pkg/b.py"}
    assert _sorted_paths_under(paths, "src/a.py") == {"src/a.py"}
    assert _sorted_paths_under(paths, "missing") == set()


def test_prefix_helpers_preserve_union_semantics_for_overlapping_requests() -> None:
    discovered = tuple(sorted({
        "src/a.py",
        "src/pkg/b.py",
        "src/pkg/c.py",
        "tests/test_a.py",
    }))
    requested = ("src/pkg", "src", "src/pkg/b.py", "tests/test_a.py")

    old_union: set[str] = set()
    for rel in requested:
        prefix = rel.rstrip("/") + "/"
        old_union.update(path for path in discovered if path == rel or path.startswith(prefix))

    new_union: set[str] = set()
    for rel in _minimal_path_prefixes(requested):
        new_union.update(_sorted_paths_under(discovered, rel))

    assert new_union == old_union

from pathlib import Path

from hashmarks import CodeMap


def test_incremental_sync_overlapping_requested_prefixes_preserves_stale_removal(tmp_path: Path) -> None:
    (tmp_path / "src/pkg").mkdir(parents=True)
    (tmp_path / "src/pkg/a.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "src/pkg/b.py").write_text("VALUE = 2\n", encoding="utf-8")
    (tmp_path / "src/other.py").write_text("VALUE = 3\n", encoding="utf-8")

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        (tmp_path / "src/pkg/a.py").unlink()
        result = codemap.sync(["src/pkg", "src", "src/pkg/a.py", "src/pkg"])

        assert result.removed == 1
        assert "src/pkg/a.py" not in codemap.store.paths()
        assert "src/pkg/b.py" in codemap.store.paths()
        assert "src/other.py" in codemap.store.paths()
