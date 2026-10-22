from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

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
        plan = codemap.verification.plan("tests/test_widget.py", symbol="test_widget")
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
        plan = codemap.verification.plan("src/widget.py")
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
        plan = codemap.verification.plan("tests/widget_test.go")
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
        plan = codemap.verification.plan("tests/widget.test.ts")
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
        plan = codemap.verification.plan("tests/widget.test.js")
    assert plan["available"] is True
    assert "runner" in plan
    assert plan["runner"] == "node-test"
    assert "argv" in plan
    assert plan["argv"] == ["node", "--test", "tests/widget.test.js"]
    assert "scope" in plan
    assert plan["scope"] == "test-file"


def test_verification_nomination_excludes_native_command_for_python(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_widget.py").write_text(
        "def test_widget(): pass\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        legacy = codemap.verification.plan("tests/test_widget.py", symbol="test_widget")
        member, _ = codemap.source.member("tests/test_widget.py")
        config, _ = codemap.source.member("pyproject.toml")
        nomination = codemap.verification.nomination(
            "tests/test_widget.py", symbol="test_widget"
        )
    assert nomination == {
        "schema": "hashmarks.verification-nomination.v1",
        "available": True,
        "verification_target": legacy["verification_target"],
        "source_member_revision": member["member_revision"],
        "supporting_source_members": [
            {
                "path": "tests/test_widget.py",
                "state": "known-present",
                "member_revision": member["member_revision"],
            },
            {
                "path": "pyproject.toml",
                "state": "known-present",
                "member_revision": config["member_revision"],
            },
        ],
        "scope": "test-node",
        "runner_evidence": "pytest",
        "source_evidence": "pyproject-pytest-config",
        "confidence": "high",
        "authority": "repository-evidence-only",
        "execution_authority": "external",
    }
    assert {"argv", "working_directory", "command", "executable", "safe"}.isdisjoint(
        nomination
    )


def test_verification_nomination_preserves_unavailable_scope(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/widget.py").write_text("x = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        nomination = codemap.verification.nomination("src/widget.py")
    assert nomination == {
        "schema": "hashmarks.verification-nomination.v1",
        "available": False,
        "path": "src/widget.py",
        "reason": "path-is-not-test-domain",
        "authority": "repository-evidence-only",
        "execution_authority": "external",
    }


def test_verification_nomination_never_promotes_polyglot_argv(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "go.mod").write_text("module example.test/widget\n", encoding="utf-8")
    (tmp_path / "tests/widget_test.go").write_text(
        "package tests\nfunc TestWidget(t *testing.T) {}\n", encoding="utf-8"
    )
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tests/widget.test.ts").write_text(
        "export const widget = 1\n", encoding="utf-8"
    )
    (tmp_path / "tests/widget.test.js").write_text(
        "import test from 'node:test';\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        for rel in (
            "tests/widget_test.go",
            "tests/widget.test.ts",
            "tests/widget.test.js",
        ):
            planned = codemap.verification.plan(rel)
            nominated = codemap.verification.nomination(rel)
            assert planned["available"] is True
            assert nominated["verification_target"] == planned["verification_target"]
            assert nominated["runner_evidence"] == planned["runner"]
            assert nominated["execution_authority"] == "external"
            assert {"argv", "working_directory", "command"}.isdisjoint(nominated)


def test_nomination_never_calls_legacy_plan_or_native_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_example.py").write_text(
        "def test_example(): pass\n", encoding="utf-8"
    )
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tests/example.test.ts").write_text(
        "export const example = 1\n", encoding="utf-8"
    )

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("evidence-only nomination consulted executable authority")

    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(codemap.verification, "plan", fail_if_called)
        monkeypatch.setattr(codemap.verification, "_vitest_runner", fail_if_called)
        assert (
            codemap.verification.nomination("tests/test_example.py")["available"]
            is True
        )
        assert (
            codemap.verification.nomination("tests/example.test.ts")["runner_evidence"]
            == "typescript-compiler"
        )


def test_nomination_uses_authored_vitest_manifest_without_installation(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/example.test.ts").write_text(
        "export const example = 1\n", encoding="utf-8"
    )
    (tmp_path / "package.json").write_text(
        '{"devDependencies":{"vitest":"^3.0.0"}}', encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        first = codemap.verification.nomination("tests/example.test.ts")
        assert first["available"] is True
        assert first["runner_evidence"] == "vitest"
        assert first["source_evidence"] == "package-manifest-vitest-declaration"
        assert {"argv", "working_directory", "executable"}.isdisjoint(first)
        (tmp_path / "node_modules/.bin").mkdir(parents=True)
        (tmp_path / "node_modules/.bin/vitest").write_text(
            "untrusted", encoding="utf-8"
        )
        second = codemap.verification.nomination("tests/example.test.ts")
    assert second == first


def test_nomination_revision_tracks_source_not_runtime_materialization(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    selected = tmp_path / "tests/test_example.py"
    selected.write_text("def test_example(): pass\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.verification.nomination("tests/test_example.py")
        assert before["available"] is True
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules/dependency.js").write_text("v1", encoding="utf-8")
        after_runtime_only = codemap.verification.nomination("tests/test_example.py")
        assert (
            after_runtime_only["source_member_revision"]
            == before["source_member_revision"]
        )
        selected.write_text("def test_example(): assert True\n", encoding="utf-8")
        codemap.index.sync()
        after_source_edit = codemap.verification.nomination("tests/test_example.py")
    assert after_source_edit["available"] is True
    assert (
        after_source_edit["source_member_revision"] != before["source_member_revision"]
    )


def test_nomination_rejects_unqualified_native_source_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_example.py").write_text(
        "def test_example(): pass\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()

        def unknown_member(
            _path: str, *, include_bytes: bool = False
        ) -> tuple[dict[str, object], None]:
            return (
                {
                    "state": "unknown",
                    "reason": "member-revision-mismatch",
                },
                None,
            )

        monkeypatch.setattr(codemap.source, "member", unknown_member)
        nomination = codemap.verification.nomination("tests/test_example.py")
    assert nomination["available"] is False
    assert nomination["reason"] == "source-evidence-unqualified"
    assert nomination["execution_authority"] == "external"


def test_nomination_cannot_promote_nonexistent_test_source(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        result = codemap.verification.nomination("tests/test_missing.py")
    assert result["available"] is False
    assert result["reason"] == "source-file-unavailable"
    assert result["execution_authority"] == "external"


def test_nomination_does_not_treat_installed_tool_as_repository_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/example.test.js").write_text(
        "export const example = 1\n", encoding="utf-8"
    )
    (tmp_path / "node_modules/.bin").mkdir(parents=True)
    (tmp_path / "node_modules/.bin/vitest").write_text("fake tool", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        nomination = codemap.verification.nomination("tests/example.test.js")
    assert nomination["available"] is False
    assert nomination["reason"] == "unsupported-repository-verification-source"


@pytest.mark.parametrize(
    ("support", "test_file", "test_source", "before", "after"),
    [
        (
            "pyproject.toml",
            "tests/test_demo.py",
            "def test_demo(): pass\n",
            "[tool.pytest.ini_options]\n",
            "[tool.pytest.ini_options]\naddopts = '-q'\n",
        ),
        (
            "go.mod",
            "tests/demo_test.go",
            "package tests\n",
            "module example.test/first\n",
            "module example.test/second\n",
        ),
        (
            "package.json",
            "tests/demo.test.ts",
            "export const demo = 1\n",
            '{"devDependencies":{"vitest":"^3.0.0"}}',
            '{"devDependencies":{"vitest":"^4.0.0"}}',
        ),
        (
            "tsconfig.json",
            "tests/demo.test.ts",
            "export const demo = 1\n",
            "{}",
            '{"compilerOptions":{"strict":true}}',
        ),
    ],
)
def test_nomination_binds_exact_supporting_manifest_revision(
    tmp_path: Path,
    support: str,
    test_file: str,
    test_source: str,
    before: str,
    after: str,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / test_file).write_text(test_source, encoding="utf-8")
    (tmp_path / support).write_text(before, encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        original = codemap.verification.nomination(test_file)
        assert original["available"] is True
        (tmp_path / support).write_text(after, encoding="utf-8")
        codemap.index.sync()
        updated = codemap.verification.nomination(test_file)
    assert updated["available"] is True
    first_members = {
        member["path"]: member for member in original["supporting_source_members"]
    }
    later_members = {
        member["path"]: member for member in updated["supporting_source_members"]
    }
    assert set(first_members) == set(later_members)
    assert first_members[support]["member_revision"] != later_members[support][
        "member_revision"
    ]
    assert first_members[test_file] == later_members[test_file]


def test_nomination_rejects_denied_package_metadata_without_fallback(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/example.test.js").write_text(
        "import test from 'node:test';\n", encoding="utf-8"
    )
    (tmp_path / "package.json").write_text(
        '{"devDependencies":{"vitest":"^3.0.0"}}', encoding="utf-8"
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "package.json"\nindex = false\n',
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        nomination = codemap.verification.nomination("tests/example.test.js")
    assert nomination["available"] is False
    assert nomination["reason"] == "source-evidence-unqualified"


def test_nomination_rejects_invalid_declared_package_metadata(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/example.test.js").write_text(
        "import test from 'node:test';\n", encoding="utf-8"
    )
    (tmp_path / "package.json").write_text("{bad json", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        nomination = codemap.verification.nomination("tests/example.test.js")
    assert nomination["available"] is False
    assert nomination["reason"] == "source-evidence-unqualified"


def test_nomination_qualifies_missing_metadata_as_observed_absence(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_demo.py").write_text(
        "def test_demo(): pass\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        nomination = codemap.verification.nomination("tests/test_demo.py")
    assert nomination["available"] is True
    assert nomination["supporting_source_members"][1] == {
        "path": "pyproject.toml",
        "state": "known-absent",
    }
    assert nomination["confidence"] == "medium"
