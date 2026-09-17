from pathlib import Path

from hashmarks.codemap import CodeMap


def _rewrite_without_observer(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    source = repo / "src" / "app.py"
    source.write_text("def old_owner():\n    return 1\n", encoding="utf-8")
    state = repo / ".state"
    with CodeMap(repo, state_dir=state) as codemap:
        codemap.sync()
    source.write_text("def new_owner():\n    return 2\n", encoding="utf-8")
    return repo, state


def test_symbol_exposes_unknown_freshness_after_unsignaled_rewrite(tmp_path: Path) -> None:
    repo, state = _rewrite_without_observer(tmp_path)
    with CodeMap(repo, state_dir=state) as codemap:
        assert codemap.status()["daemon_generation_changed"] is None
        value = codemap.symbol("old_owner")
    assert value["stale"] is None
    assert value["generation"] >= 1
    assert value["identity_generation"] is None
    assert value["matches"][0]["name"] == "old_owner"


def test_structured_persisted_queries_share_freshness_authority(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("from .b import target\ndef caller():\n    return target()\n", encoding="utf-8")
    (repo / "src" / "b.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    state = repo / ".state"
    with CodeMap(repo, state_dir=state) as codemap:
        codemap.sync()
        values = [
            codemap.symbol("target"),
            codemap.deps("caller"),
            codemap.refs("target"),
            codemap.affected("src/b.py"),
            codemap.tests("src/b.py"),
            codemap.projects(),
            codemap.repository_instruction_scope("src/b.py"),
            codemap.change_impact("src/b.py"),
        ]
    for value in values:
        assert {"generation", "identity_generation", "stale"} <= value.keys()
        assert value["stale"] is None


def test_exact_outline_still_revalidates_path_without_global_observer(tmp_path: Path) -> None:
    repo, state = _rewrite_without_observer(tmp_path)
    with CodeMap(repo, state_dir=state) as codemap:
        value = codemap.outline("src/app.py")
    assert value["symbols"][0]["name"] == "new_owner"
    assert value["stale"] is None
