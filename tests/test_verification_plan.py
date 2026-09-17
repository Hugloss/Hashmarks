from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def test_verification_plan_derives_pytest_argv_without_shell_guess(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_widget.py").write_text("def test_widget():\n    pass\n")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        plan = codemap.verification_plan("tests/test_widget.py", symbol="test_widget")
    assert plan["available"] is True
    assert plan["runner"] == "pytest"
    assert plan["argv"] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_widget.py::test_widget",
    ]
    assert plan["scope"] == "test-node"
    assert plan["confidence"] == "high"


def test_verification_plan_refuses_non_test_source(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "widget.py").write_text("def widget():\n    pass\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        plan = codemap.verification_plan("src/widget.py")
    assert plan["available"] is False
    assert plan["reason"] == "path-is-not-test-domain"
