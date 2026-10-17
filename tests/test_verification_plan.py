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
        codemap.index.sync()
        plan = codemap.verification_plan("tests/test_widget.py", symbol="test_widget")
    assert plan["available"] is True
    assert "runner" in plan
    assert plan["runner"] == "pytest"
    assert "argv" in plan
    assert plan["argv"] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_widget.py::test_widget",
    ]
    assert "scope" in plan
    assert plan["scope"] == "test-node"
    assert "confidence" in plan
    assert plan["confidence"] == "high"


def test_verification_plan_refuses_non_test_source(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "widget.py").write_text("def widget():\n    pass\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        plan = codemap.verification_plan("src/widget.py")
    assert plan["available"] is False
    assert "reason" in plan
    assert plan["reason"] == "path-is-not-test-domain"


def test_verification_plan_derives_go_package_argv(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "go.mod").write_text("module example.com/widget\n", encoding="utf-8")
    (tmp_path / "tests" / "widget_test.go").write_text(
        "package tests\nfunc TestWidget(t *testing.T) {}\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        plan = codemap.verification_plan("tests/widget_test.go")
    assert plan["available"] is True
    assert "runner" in plan
    assert plan["runner"] == "go-test"
    assert "argv" in plan
    assert plan["argv"] == ["go", "test", "./tests"]
    assert "confidence" in plan
    assert plan["confidence"] == "high"


def test_verification_plan_derives_typescript_project_argv(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"strict":true}}\n',
        encoding="utf-8",
    )
    (tmp_path / "tests" / "widget.test.ts").write_text(
        "export const widget = 1\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        plan = codemap.verification_plan("tests/widget.test.ts")
    assert plan["available"] is True
    assert "runner" in plan
    assert plan["runner"] == "typescript-compiler"
    assert "argv" in plan
    assert plan["argv"] == ["tsc", "--noEmit", "-p", "tsconfig.json"]
    assert "scope" in plan
    assert plan["scope"] == "typescript-project"


def test_verification_plan_derives_native_node_test_argv(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "widget.test.js").write_text(
        "import test from 'node:test';\ntest('widget', () => {});\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        plan = codemap.verification_plan("tests/widget.test.js")
    assert plan["available"] is True
    assert "runner" in plan
    assert plan["runner"] == "node-test"
    assert "argv" in plan
    assert plan["argv"] == ["node", "--test", "tests/widget.test.js"]
    assert "scope" in plan
    assert plan["scope"] == "test-file"
