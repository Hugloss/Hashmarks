from pathlib import Path

from hashmarks.codemap import CodeMap


def test_qualified_reference_beyond_global_short_name_prefix_remains_direct(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src"
    tests = tmp_path / "tests"
    src.mkdir()
    tests.mkdir()
    # More than the 1,024 global reverse-reference safety bound sort before the
    # relevant test reference.  Qualification must not become a lexical-prefix
    # accident merely because every module exports the same short symbol.
    for index in range(1030):
        (src / f"m{index:04d}.py").write_text("def f(): return 1\n", encoding="utf-8")
        (src / f"z{index:04d}.py").write_text(
            f"from .m{index:04d} import f\n", encoding="utf-8"
        )
    (src / "target.py").write_text("def f(): return 1\n", encoding="utf-8")
    (tests / "test_target.py").write_text(
        "from src.target import f\n\ndef test_f(): assert f() == 1\n", encoding="utf-8"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        global_prefix = codemap.store.refs_many(["f"], limit_per_target=1024)["f"]
        assert not any(row["path"] == "tests/test_target.py" for row in global_prefix)
        relevance = codemap.verification_relevance(
            "src/target.py", limit=20, candidate_limit=8
        )

    assert relevance["selected"]["path"] == "tests/test_target.py"
    assert relevance["selected"]["direct_reference"] is True
    assert relevance["selected"]["reference_strength"] == "reachable-symbol-use"
    assert relevance["selected"]["reference_symbols"] == ["f"]


def test_targeted_tail_uses_full_module_identity_when_leaf_names_collide(
    tmp_path: Path, monkeypatch
) -> None:
    for package in ("pkg_a", "pkg_b"):
        directory = tmp_path / package
        directory.mkdir()
        (directory / "__init__.py").write_text("", encoding="utf-8")
        (directory / "target.py").write_text("def run(): return 1\n", encoding="utf-8")
        (directory / "consumer.py").write_text(
            f"from {package}.target import run\n\ndef use(): return run()\n",
            encoding="utf-8",
        )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_target.py").write_text(
        "from pkg_b.target import run\n\ndef test_run(): assert run() == 1\n",
        encoding="utf-8",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observed: list[str] = []
        original = codemap.store.refs_matching_target_suffix

        def recorded(short: str, suffix: str, *, limit: int = 1024):
            observed.append(suffix)
            return original(short, suffix, limit=limit)

        monkeypatch.setattr(codemap.store, "refs_matching_target_suffix", recorded)
        relevance = codemap.verification_relevance(
            "change pkg_b/target.py run behavior", limit=20, candidate_limit=8
        )

    assert "pkg_b.target.run" in observed
    assert "target.run" not in observed
    assert relevance["selected"]["path"] == "tests/test_target.py"
    assert relevance["selected"]["direct_reference"] is True


def test_literal_repository_path_is_not_replaced_by_structural_neighbor(
    tmp_path: Path,
) -> None:
    pkg = tmp_path / "pkg"
    tests = tmp_path / "tests"
    pkg.mkdir()
    tests.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "previous.py").write_text("def run(): return 1\n", encoding="utf-8")
    (pkg / "target.py").write_text(
        "from pkg.previous import run as previous_run\n\ndef run(): return previous_run()\n",
        encoding="utf-8",
    )
    (tests / "test_target.py").write_text(
        "from pkg.target import run\n\ndef test_run(): assert run() == 1\n",
        encoding="utf-8",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("change pkg/target.py run behavior", limit=20)

    assert action["edit"]["path"] == "pkg/target.py"
    assert (
        action["verification_relevance"]["selected"]["path"] == "tests/test_target.py"
    )
    assert action["verification_relevance"]["selected"]["direct_reference"] is True
