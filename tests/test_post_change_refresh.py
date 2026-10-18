from pathlib import Path

from contract_assertions import assert_integer, assert_object

from hashmarks.codemap.engine import CodeMap
from hashmarks.codemap.post_change import PostChangeOptions


def test_post_change_refresh_is_changed_path_scoped_and_regenerates_packet(
    tmp_path: Path,
) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "tests").mkdir()
    source = tmp_path / "pkg" / "engine.py"
    source.write_text("def target(value: int) -> int:\n    return value\n")
    (tmp_path / "pkg" / "untouched.py").write_text("def stable():\n    return 1\n")
    (tmp_path / "tests" / "test_engine.py").write_text(
        "def test_target():\n    assert True\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.tasks.decision_packet(
            "target implementation test", token_budget=256
        )
        source.write_text("def target(value: int) -> int:\n    return value + 1\n")
        refreshed = codemap.changes.refresh(
            "target implementation test", ["pkg/engine.py"], token_budget=256
        )
    assert refreshed["changed_paths"] == ["pkg/engine.py"]
    assert refreshed["scope"] == "changed-paths-only"
    assert refreshed["consumer_owner"] == "external"
    assert assert_integer(refreshed["generation_after"]) >= assert_integer(
        refreshed["generation_before"]
    )
    assert assert_object(refreshed["sync"])["discovered"] == 1
    assert (
        assert_object(assert_object(refreshed["packet"])["identity"])[
            "decision_generation"
        ]
        != assert_object(before["identity"])["decision_generation"]
    )


def test_refresh_delta_omits_unchanged_action_anchors(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "tests").mkdir()
    source = tmp_path / "pkg" / "engine.py"
    source.write_text("def target(value: int) -> int:\n    return value\n")
    (tmp_path / "tests" / "test_engine.py").write_text(
        "from pkg.engine import target\ndef test_target(): assert target(1) == 2\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        source.write_text("def target(value: int) -> int:\n    return value + 1\n")
        delta = codemap.changes.refresh_delta(
            "target implementation test",
            ["pkg/engine.py"],
            options=PostChangeOptions(
                previous_edit_path="pkg/engine.py",
                previous_verify_path="tests/test_engine.py",
                token_budget=256,
            ),
        )

    assert delta["schema"] == "hashmarks.refresh-delta.v1"
    assert delta["changed_paths"] == ["pkg/engine.py"]
    assert "edit" not in delta
    assert "verify" not in delta
