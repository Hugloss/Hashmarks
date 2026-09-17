from pathlib import Path

from hashmarks.codemap.engine import CodeMap


def test_post_change_refresh_is_changed_path_scoped_and_regenerates_packet(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "tests").mkdir()
    source = tmp_path / "pkg" / "engine.py"
    source.write_text("def target(value: int) -> int:\n    return value\n")
    (tmp_path / "pkg" / "untouched.py").write_text("def stable():\n    return 1\n")
    (tmp_path / "tests" / "test_engine.py").write_text(
        "def test_target():\n    assert True\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.task_decision_packet("target implementation test", token_budget=256)
        source.write_text("def target(value: int) -> int:\n    return value + 1\n")
        refreshed = codemap.refresh_after_change(
            "target implementation test", ["pkg/engine.py"], token_budget=256
        )
    assert refreshed["changed_paths"] == ["pkg/engine.py"]
    assert refreshed["scope"] == "changed-paths-only"
    assert refreshed["consumer_owner"] == "external"
    assert refreshed["generation_after"] >= refreshed["generation_before"]
    assert refreshed["sync"]["discovered"] == 1
    assert refreshed["packet"]["identity"]["decision_generation"] != before["identity"]["decision_generation"]
