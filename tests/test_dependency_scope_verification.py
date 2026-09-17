from pathlib import Path
from unittest.mock import patch

from hashmarks.codemap import CodeMap


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_verification_plan_rejects_pruned_dependency_test_path(tmp_path: Path) -> None:
    owned = tmp_path / "tests" / "test_owned.py"
    dependency = (
        tmp_path
        / ".venv"
        / "lib"
        / "python3.13"
        / "site-packages"
        / "demo_dep"
        / "tests"
        / "test_dep.py"
    )
    _write(owned, "def test_owned():\n    assert True\n")
    _write(dependency, "def test_dependency():\n    assert True\n")
    rel = dependency.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        assert rel not in codemap.store.paths()
        plan = codemap.verification_plan(rel)
        assert plan == {
            "schema": "hashmarks.verification-plan.v1",
            "path": rel,
            "available": False,
            "reason": "path-outside-analysis-scope",
        }
        owned_plan = codemap.verification_plan("tests/test_owned.py")
        assert owned_plan["available"] is True
        assert owned_plan["runner"] == "pytest"


def test_verification_plan_rejects_context_denied_test_path(tmp_path: Path) -> None:
    hidden = tmp_path / "private" / "test_hidden.py"
    _write(hidden, "def test_hidden():\n    assert True\n")
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "private/**"\nindex = false\n',
        encoding="utf-8",
    )
    rel = hidden.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        assert rel not in codemap.store.paths()
        assert codemap.verification_plan(rel)["reason"] == "path-outside-analysis-scope"


def test_pruned_javascript_test_is_rejected_before_source_read(tmp_path: Path) -> None:
    dependency = tmp_path / "node_modules" / "demo" / "tests" / "dep.test.js"
    _write(dependency, 'import test from "node:test";\n')
    rel = dependency.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        with patch("pathlib.Path.read_text", side_effect=AssertionError("dependency source must not be read")):
            plan = codemap.verification_plan(rel)
        assert plan["available"] is False
        assert plan["reason"] == "path-outside-analysis-scope"


def test_verification_scope_pruning_is_segment_aware(tmp_path: Path) -> None:
    owned = tmp_path / "tests" / "node_modules_adapter.py"
    _write(owned, "def test_adapter():\n    assert True\n")
    rel = owned.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        assert rel in codemap.store.paths()
        plan = codemap.verification_plan(rel)
        assert plan["available"] is True
        assert plan["runner"] == "pytest"
