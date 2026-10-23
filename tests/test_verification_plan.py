from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_observation import evidence_identity

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
    assert nomination.pop("nomination_identity") == evidence_identity(
        nomination["schema"], nomination
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
    assert nomination.pop("nomination_identity") == evidence_identity(
        nomination["schema"], nomination
    )
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
    assert (
        first_members[support]["member_revision"]
        != later_members[support]["member_revision"]
    )
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


def test_nomination_identity_binds_source_provenance_without_execution_claims(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    target = tmp_path / "tests/test_demo.py"
    target.write_text("def test_demo(): pass\n", encoding="utf-8")
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        first = codemap.verification.nomination("tests/test_demo.py")
        repeated = codemap.verification.nomination("tests/test_demo.py")
        assert repeated == first
        assert first["available"] is True

        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules/cache.js").write_text("v1", encoding="utf-8")
        runtime_only = codemap.verification.nomination("tests/test_demo.py")
        assert runtime_only["nomination_identity"] == first["nomination_identity"]

        manifest.write_text(
            "[tool.pytest.ini_options]\naddopts = '-q'\n", encoding="utf-8"
        )
        codemap.index.sync()
        after_manifest_change = codemap.verification.nomination("tests/test_demo.py")
        assert (
            after_manifest_change["source_member_revision"]
            == first["source_member_revision"]
        )
        assert (
            after_manifest_change["nomination_identity"] != first["nomination_identity"]
        )

    assert first["execution_authority"] == "external"
    assert {"argv", "working_directory", "executable"}.isdisjoint(first)


def test_nomination_identity_detects_foreign_field_changes(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_demo.py").write_text(
        "def test_demo(): pass\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        original = codemap.verification.nomination("tests/test_demo.py")
    identity = original["nomination_identity"]
    contents = {
        key: value for key, value in original.items() if key != "nomination_identity"
    }
    assert evidence_identity(original["schema"], contents) == identity
    contents["execution_authority"] = "hashmarks"
    assert evidence_identity(original["schema"], contents) != identity


@pytest.mark.parametrize(
    ("manifest", "expected_confidence", "expected_evidence"),
    [
        (
            "[tool.pytest.ini_options]\naddopts = '-q'\n",
            "high",
            "pyproject-pytest-config",
        ),
        (
            "# [tool.pytest.ini_options]\n[project]\nname = 'demo'\n",
            "medium",
            "python-test-domain",
        ),
        (
            "[project]\nname = 'demo'\ndescription = '[tool.pytest.ini_options]'\n",
            "medium",
            "python-test-domain",
        ),
        (
            "[tool.pytest]\nother = true\n",
            "medium",
            "python-test-domain",
        ),
        (
            "[tool.pytest.ini_options]\naddopts = '-q'\n[tool.other]\nactive = true\n",
            "high",
            "pyproject-pytest-config",
        ),
    ],
)
def test_nomination_qualifies_pytest_declaration_from_parsed_toml(
    tmp_path: Path,
    manifest: str,
    expected_confidence: str,
    expected_evidence: str,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_demo.py").write_text(
        "def test_demo(): pass\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(manifest, encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        nomination = codemap.verification.nomination("tests/test_demo.py")
    assert nomination["available"] is True
    assert nomination["confidence"] == expected_confidence
    assert nomination["source_evidence"] == expected_evidence
    assert nomination["supporting_source_members"][1]["path"] == "pyproject.toml"
    assert {"argv", "executable", "working_directory"}.isdisjoint(nomination)


@pytest.mark.parametrize(
    "manifest",
    [
        "[tool.pytest.ini_options]\naddopts = [broken\n",
        "[tool.pytest.ini_options]\naddopts = 'a'\naddopts = 'b'\n",
        "[tool.pytest.ini_options]\ninvalid = \\udcff\n",
    ],
)
def test_nomination_fails_closed_on_invalid_pyproject_toml(
    tmp_path: Path, manifest: str
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_demo.py").write_text(
        "def test_demo(): pass\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        manifest, encoding="utf-8", errors="surrogatepass"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        nomination = codemap.verification.nomination("tests/test_demo.py")
    assert nomination["available"] is False
    assert nomination["reason"] == "source-evidence-unqualified"
    assert nomination["execution_authority"] == "external"


def test_nomination_pytest_confidence_tracks_config_fix_without_source_edit(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_demo.py").write_text(
        "def test_demo(): pass\n", encoding="utf-8"
    )
    config = tmp_path / "pyproject.toml"
    config.write_text("# [tool.pytest.ini_options]\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.verification.nomination("tests/test_demo.py")
        config.write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        codemap.index.sync()
        after = codemap.verification.nomination("tests/test_demo.py")
    assert before["confidence"] == "medium"
    assert after["confidence"] == "high"
    assert before["source_member_revision"] == after["source_member_revision"]
    assert before["nomination_identity"] != after["nomination_identity"]


@pytest.mark.parametrize(
    ("manifest", "expected_runner", "expected_source"),
    [
        (
            '{"devDependencies":{"vitest":"^3.0.0"}}',
            "vitest",
            "package-manifest-vitest-declaration",
        ),
        (
            '{"dependencies":{"vitest":"workspace:*"}}',
            "vitest",
            "package-manifest-vitest-declaration",
        ),
        (
            '{"optionalDependencies":{"vitest":"npm:vitest@^3.0.0"}}',
            "vitest",
            "package-manifest-vitest-declaration",
        ),
        (
            '{"devDependencies":{},"scripts":{"test":"vitest run"}}',
            "node-test",
            "node-test-import-plus-test-file",
        ),
        (
            '{"name":"vitest","devDependencies":{}}',
            "node-test",
            "node-test-import-plus-test-file",
        ),
    ],
)
def test_nomination_qualifies_declared_vitest_spec_not_package_mentions(
    tmp_path: Path, manifest: str, expected_runner: str, expected_source: str
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/widget.test.js").write_text(
        "import test from 'node:test';\n", encoding="utf-8"
    )
    (tmp_path / "package.json").write_text(manifest, encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        nominated = codemap.verification.nomination("tests/widget.test.js")
    assert nominated["available"] is True
    assert nominated["runner_evidence"] == expected_runner
    assert nominated["source_evidence"] == expected_source
    assert nominated["supporting_source_members"][1]["path"] == "package.json"
    assert nominated["execution_authority"] == "external"
    assert {"argv", "working_directory", "executable"}.isdisjoint(nominated)


@pytest.mark.parametrize(
    "manifest",
    [
        '{"devDependencies":{"vitest":null}}',
        '{"devDependencies":{"vitest":false}}',
        '{"devDependencies":{"vitest":7}}',
        '{"devDependencies":{"vitest":{}}}',
        '{"devDependencies":{"vitest":""}}',
        '{"devDependencies":{"vitest":"  "}}',
        '{"devDependencies":null}',
        '{"devDependencies":[]}',
        '{"devDependencies":{"vitest":"^3"},"devDependencies":{"vitest":"^4"}}',
        '{"devDependencies":{"vitest":"^3","vitest":"^4"}}',
        '{"devDependencies":{"vitest":"^3"},"name":"first","name":"second"}',
    ],
)
def test_nomination_rejects_ambiguous_or_invalid_vitest_manifest(
    tmp_path: Path, manifest: str
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/widget.test.js").write_text(
        "import test from 'node:test';\n", encoding="utf-8"
    )
    (tmp_path / "package.json").write_text(manifest, encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        nominated = codemap.verification.nomination("tests/widget.test.js")
    assert nominated["available"] is False
    assert nominated["reason"] == "source-evidence-unqualified"
    assert nominated["execution_authority"] == "external"


def test_nomination_vitest_manifest_repair_changes_only_support_revision(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/widget.test.js").write_text(
        "import test from 'node:test';\n", encoding="utf-8"
    )
    manifest = tmp_path / "package.json"
    manifest.write_text('{"devDependencies":{"vitest":null}}', encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.verification.nomination("tests/widget.test.js")
        manifest.write_text('{"devDependencies":{"vitest":"^3.0.0"}}', encoding="utf-8")
        codemap.index.sync()
        after = codemap.verification.nomination("tests/widget.test.js")
    assert before["available"] is False
    assert after["available"] is True
    assert after["runner_evidence"] == "vitest"
    assert after["supporting_source_members"][0]["path"] == "tests/widget.test.js"
    assert after["supporting_source_members"][1]["path"] == "package.json"
    assert after["nomination_identity"] != before["nomination_identity"]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def test_widget(): pass\n", True),
        ("async def test_widget(): pass\n", True),
        ("# def test_widget(): pass\n", False),
        ("def helper():\n    def test_widget(): pass\n", False),
        ("class TestDemo:\n    def test_widget(self): pass\n", False),
        ("def test_widget(): pass\ndef test_widget(): pass\n", False),
        ("def test_other(): pass\n", False),
        ("def test_widget(\n", False),
    ],
)
def test_nomination_requires_unique_top_level_python_test_node(
    tmp_path: Path, source: str, expected: bool
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_widget.py").write_text(source, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        result = codemap.verification.nomination(
            "tests/test_widget.py", symbol="test_widget"
        )
    assert result["available"] is expected
    assert result["execution_authority"] == "external"
    if expected:
        assert result["scope"] == "test-node"
        assert result["verification_target"]["test_symbol"] == "test_widget"
    else:
        assert result["reason"] == "source-evidence-unqualified"
    assert {"argv", "working_directory", "executable"}.isdisjoint(result)


def test_python_file_level_nomination_remains_available_without_node_claim(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_widget.py").write_text(
        "class TestDemo:\n    def test_widget(self): pass\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.verification.nomination("tests/test_widget.py")
    assert packet["available"] is True
    assert packet["scope"] == "test-file"
    assert packet["verification_target"]["test_symbol"] is None
    assert packet["source_member_revision"]


def test_python_test_node_nomination_tracks_source_edits(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests/test_widget.py"
    test_file.write_text("def test_widget(): pass\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.verification.nomination(
            "tests/test_widget.py", symbol="test_widget"
        )
        test_file.write_text("def test_other(): pass\n", encoding="utf-8")
        codemap.index.sync()
        after = codemap.verification.nomination(
            "tests/test_widget.py", symbol="test_widget"
        )
    assert before["available"] is True
    assert after["available"] is False
    assert before["nomination_identity"] != after["nomination_identity"]
    assert after["execution_authority"] == "external"


@pytest.mark.parametrize(
    ("symbol", "qualname", "expected_scope"),
    [
        ("test_widget", None, "test-node"),
        (None, "test_widget", "test-node"),
        ("test_widget", "test_widget", "test-node"),
        (None, None, "test-file"),
        ("helper", None, "unavailable"),
        (None, "helper", "unavailable"),
        ("", None, "unavailable"),
        (None, "", "unavailable"),
        ("  ", None, "unavailable"),
        (None, "test_widget[case]", "unavailable"),
        ("test widget", None, "unavailable"),
        ("test_widget", 123, "unavailable"),
        (123, None, "unavailable"),
        (None, False, "unavailable"),
        ("test_widget", "test_other", "unavailable"),
        ("helper", "test_widget", "unavailable"),
        ("test_widget", "TestCase.test_widget", "unavailable"),
        ("test_widget", "test_widget.inner", "unavailable"),
        (None, "test_widget.inner", "unavailable"),
        (None, "TestCase.test_widget", "unavailable"),
        ("TestCase.test_widget", None, "unavailable"),
    ],
)
def test_nomination_preserves_explicit_python_source_selection_precision(
    tmp_path: Path,
    symbol: str | None,
    qualname: str | None,
    expected_scope: str,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_widget.py").write_text(
        "def test_widget(): pass\ndef test_other(): pass\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        nomination = codemap.verification.nomination(
            "tests/test_widget.py", symbol=symbol, qualname=qualname
        )
    assert nomination["execution_authority"] == "external"
    assert {"argv", "working_directory", "executable"}.isdisjoint(nomination)
    if expected_scope == "unavailable":
        assert nomination["available"] is False
        assert nomination["reason"] == "source-evidence-unqualified"
    else:
        assert nomination["available"] is True
        assert nomination["scope"] == expected_scope
        assert nomination["verification_target"]["test_symbol"] == (
            "test_widget" if expected_scope == "test-node" else None
        )


def test_legacy_plan_retains_flat_projection_while_nomination_refuses_nested(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_widget.py").write_text(
        "def test_widget(): pass\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        legacy = codemap.verification.plan(
            "tests/test_widget.py", qualname="test_widget.inner"
        )
        exact = codemap.verification.nomination(
            "tests/test_widget.py", qualname="test_widget.inner"
        )
    assert legacy["available"] is True
    assert legacy["verification_target"]["test_symbol"] == "test_widget"
    assert exact["available"] is False
    assert exact["reason"] == "source-evidence-unqualified"


def test_explicit_non_test_selector_cannot_widen_to_file_nomination(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_widget.py").write_text(
        "def helper(): pass\ndef test_widget(): pass\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        original = codemap.verification.nomination("tests/test_widget.py")
        narrowed = codemap.verification.nomination(
            "tests/test_widget.py", symbol="helper"
        )
        legacy = codemap.verification.plan("tests/test_widget.py", symbol="helper")
    assert original["available"] is True
    assert original["scope"] == "test-file"
    assert narrowed["available"] is False
    assert narrowed["reason"] == "source-evidence-unqualified"
    assert narrowed["nomination_identity"] != original["nomination_identity"]
    assert narrowed["execution_authority"] == "external"
    assert legacy["available"] is True
    assert legacy["scope"] == "test-file"


def test_explicit_unsupported_python_selector_never_reads_supporting_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_widget.py").write_text(
        "def test_widget(): pass\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n", encoding="utf-8"
    )

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unqualified node selector inspected config metadata")

    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(
            codemap.verification, "_pytest_manifest_declaration", forbidden
        )
        assert (
            codemap.verification.nomination("tests/test_widget.py", symbol="helper")[
                "reason"
            ]
            == "source-evidence-unqualified"
        )


@pytest.mark.parametrize(
    "case",
    [
        (
            "tests/widget_test.go",
            "package tests\nfunc TestWidget(t *testing.T) {}\n",
            "go.mod",
            "module example.test/widget\n",
        ),
        (
            "tests/widget.test.js",
            "import test from 'node:test';\n",
            "package.json",
            '{"devDependencies":{"vitest":"^3.0.0"}}',
        ),
        (
            "tests/widget.test.ts",
            "export const widget = 1\n",
            "tsconfig.json",
            "{}",
        ),
    ],
)
@pytest.mark.parametrize(
    ("symbol", "qualname"),
    [
        ("test_widget", None),
        (None, "test_widget"),
        ("test_widget", "test_widget"),
        ("", None),
    ],
)
def test_polyglot_explicit_node_selector_cannot_widen_to_file_or_package(
    tmp_path: Path,
    case: tuple[str, str, str, str],
    symbol: str | None,
    qualname: str | None,
) -> None:
    filename, test_source, manifest_name, manifest_source = case
    (tmp_path / "tests").mkdir()
    (tmp_path / filename).write_text(test_source, encoding="utf-8")
    (tmp_path / manifest_name).write_text(manifest_source, encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        file_scope = codemap.verification.nomination(filename)
        requested_node = codemap.verification.nomination(
            filename, symbol=symbol, qualname=qualname
        )
    assert file_scope["available"] is True
    assert file_scope["verification_target"]["test_symbol"] is None
    assert file_scope["scope"] in {"go-package", "test-file", "typescript-project"}
    assert requested_node["available"] is False
    assert requested_node["reason"] == "source-evidence-unqualified"
    assert requested_node["nomination_identity"] != file_scope["nomination_identity"]
    assert requested_node["execution_authority"] == "external"
    assert {"argv", "working_directory", "executable"}.isdisjoint(requested_node)


def test_polyglot_explicit_selector_rejection_precedes_native_manifest_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/widget.test.js").write_text(
        "import test from 'node:test';\n", encoding="utf-8"
    )
    (tmp_path / "package.json").write_text(
        '{"devDependencies":{"vitest":"^3.0.0"}}', encoding="utf-8"
    )

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unsupported node selector inspected verifier manifests")

    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(codemap.verification, "_vitest_declared", forbidden)
        rejection = codemap.verification.nomination(
            "tests/widget.test.js", symbol="test_widget"
        )
    assert rejection["available"] is False
    assert rejection["reason"] == "source-evidence-unqualified"
