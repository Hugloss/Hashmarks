"""Verifier context binds nested declarations without guessing execution roots."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.digest import Digest
from hashmarks.file_store import UnstableFileError
from hashmarks.verification_nomination_validation import (
    validate_verification_nomination,
)


def _write(root: Path, path: str, content: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _context(repository: CodeMap, path: str) -> dict[str, object]:
    return repository.reads.observe(
        lambda _scope: repository.verification._verification_context(path)
    )


def test_nested_python_nomination_binds_nearest_manifest_and_absences(
    tmp_path: Path,
) -> None:
    path = "packages/api/tests/test_total.py"
    _write(tmp_path, path, "def test_total(): pass\n")
    _write(tmp_path, "pyproject.toml", "this is not valid TOML\n")
    _write(tmp_path, "packages/api/pyproject.toml", "[tool.pytest.ini_options]\n")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        nomination = repository.verification.nomination(path, symbol="test_total")
    assert nomination["available"] is True
    assert nomination["confidence"] == "high"
    members = assert_records(nomination["supporting_source_members"])
    assert [row["path"] for row in members] == [
        path,
        "packages/api/tests/pyproject.toml",
        "packages/api/pyproject.toml",
    ]
    assert members[1]["state"] == "known-absent"
    assert validate_verification_nomination(nomination)["valid"] is True
    assert {"argv", "working_directory"}.isdisjoint(nomination)


def test_adding_nearer_manifest_invalidates_retained_nomination(tmp_path: Path) -> None:
    path = "tests/test_total.py"
    _write(tmp_path, path, "def test_total(): pass\n")
    _write(tmp_path, "pyproject.toml", "[tool.pytest.ini_options]\n")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        before = repository.verification.nomination(path)
        _write(tmp_path, "tests/pyproject.toml", "[tool.pytest.ini_options]\n")
        binding = repository.verification.observe_nomination_source_binding(before)
        after = repository.verification.nomination(path)
    assert binding["source_binding_state"] == "mismatch"
    assert "source-mismatch:tests/pyproject.toml" in assert_array(binding["reasons"])
    assert before["nomination_identity"] != after["nomination_identity"]
    assert assert_records(after["supporting_source_members"])[-1]["path"] == (
        "tests/pyproject.toml"
    )


def test_nested_frontend_uses_own_runner_declaration(tmp_path: Path) -> None:
    path = "frontend/tests/example.test.js"
    _write(tmp_path, path, "import test from 'node:test';\n")
    _write(tmp_path, "package.json", '{"devDependencies":{"vitest":"*"}}')
    _write(tmp_path, "frontend/package.json", '{"name":"frontend"}')
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        nomination = repository.verification.nomination(path)
    assert nomination["available"] is True
    assert nomination["runner_evidence"] == "node-test"
    assert [
        row["path"] for row in assert_records(nomination["supporting_source_members"])
    ] == [path, "frontend/tests/package.json", "frontend/package.json"]


def test_nested_vitest_requires_no_installed_tool(tmp_path: Path) -> None:
    path = "frontend/src/example.test.ts"
    _write(tmp_path, path, "export const value = 1;\n")
    _write(tmp_path, "frontend/package.json", '{"devDependencies":{"vitest":"*"}}')
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        nomination = repository.verification.nomination(path)
    assert nomination["available"] is True
    assert nomination["runner_evidence"] == "vitest"
    assert nomination["source_evidence"] == "package-manifest-vitest-declaration"
    assert validate_verification_nomination(nomination)["valid"] is True


def test_nested_typescript_nomination_binds_project_config(tmp_path: Path) -> None:
    path = "frontend/src/example.test.ts"
    _write(tmp_path, path, "export const value = 1;\n")
    _write(tmp_path, "frontend/package.json", '{"name":"frontend"}')
    _write(tmp_path, "frontend/tsconfig.json", '{"compilerOptions":{"strict":true}}')
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        nomination = repository.verification.nomination(path)
    assert nomination["available"] is True
    assert nomination["runner_evidence"] == "typescript-compiler"
    assert nomination["scope"] == "typescript-project"
    assert [
        row["path"] for row in assert_records(nomination["supporting_source_members"])
    ] == [
        path,
        "frontend/src/package.json",
        "frontend/package.json",
        "frontend/src/tsconfig.json",
        "frontend/tsconfig.json",
    ]


def test_current_manifest_does_not_manufacture_native_project_identity(
    tmp_path: Path,
) -> None:
    path = "frontend/example.test.js"
    _write(tmp_path, path, "import test from 'node:test';\n")
    _write(tmp_path, "frontend/package.json", '{"name":"frontend"}')
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        context = _context(repository, path)
    assert assert_records(context["manifests"])[0]["root"] == "frontend"
    project = assert_object(context["project"])
    assert project["state"] == "unknown"
    assert project["freshness"] == "unknown"
    assert project["project_id"] is None
    assert project["completeness"] == "unknown"


def test_duplicate_native_project_names_remain_ambiguous(tmp_path: Path) -> None:
    for folder in ("first", "second"):
        _write(tmp_path, f"{folder}/package.json", '{"name":"duplicate"}')
        _write(tmp_path, f"{folder}/example.test.js", "import test from 'node:test';\n")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        repository.native.enrich_projects(("npm-package-graph",))
        context = _context(repository, "first/example.test.js")
    project = assert_object(context["project"])
    assert project["state"] == "ambiguous"
    assert project["project_id"] is None
    assert project["project_count"] == 1
    assert project["freshness"] == "current"


def test_single_segment_nested_project_is_more_specific_than_workspace(
    tmp_path: Path,
) -> None:
    path = "a/example.test.js"
    _write(tmp_path, path, "import test from 'node:test';\n")
    _write(tmp_path, "package.json", '{"name":"workspace"}')
    _write(tmp_path, "a/package.json", '{"name":"nested"}')
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        repository.native.enrich_projects(("npm-package-graph",))
        context = _context(repository, path)
    project = assert_object(context["project"])
    assert project["state"] == "resolved-unique"
    assert project["project_id"] == "npm:nested"
    assert project["project_count"] == 2


def test_source_refresh_does_not_upgrade_stale_native_project(tmp_path: Path) -> None:
    path = "frontend/example.test.js"
    _write(tmp_path, path, "import test from 'node:test';\n")
    _write(tmp_path, "frontend/package.json", '{"name":"before"}')
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        repository.native.enrich_projects(("npm-package-graph",))
        before = _context(repository, path)
        _write(tmp_path, "frontend/package.json", '{"name":"after"}')
        repository.index.sync(["frontend/package.json"])
        after = _context(repository, path)
    assert assert_object(before["project"])["state"] == "resolved-unique"
    assert assert_object(after["project"])["state"] == "unknown"
    assert assert_records(after["manifests"])[0]["state"] == "known-present"
    assert after["context_identity"] != before["context_identity"]


def test_nested_python_context_reuses_roots_after_reopen(tmp_path: Path) -> None:
    root, state = tmp_path / "repository", tmp_path / "state"
    path = "packages/api/src/catalog/total.py"
    _write(root, path, "def total(): return 1\n")
    _write(
        root,
        "packages/api/pyproject.toml",
        '[tool.setuptools.package-dir]\n"" = "src"\n',
    )
    with CodeMap(root, state_dir=state) as repository:
        repository.index.sync()
        before = _context(repository, path)
    with CodeMap(root, state_dir=state) as repository:
        after = _context(repository, path)
        assert repository.index.python_import_roots == ("packages/api/src",)
    assert before == after
    assert after["python_source_roots"] == ["packages/api/src"]
    assert after["source_root_state"] == "qualified"
    assert assert_records(after["manifests"])[0]["root"] == "packages/api"


def test_denied_nearer_manifest_prevents_ancestor_fallback(tmp_path: Path) -> None:
    path = "frontend/tests/example.test.js"
    _write(tmp_path, path, "import test from 'node:test';\n")
    _write(tmp_path, "package.json", '{"devDependencies":{"vitest":"*"}}')
    _write(tmp_path, "frontend/package.json", '{"privateName":"not-disclosed"}')
    _write(
        tmp_path,
        ".hashmarks-context.toml",
        '[[rule]]\npattern="frontend/package.json"\nvisibility="deny"\n',
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        nomination = repository.verification.nomination(path)
        context = _context(repository, path)
    assert nomination["available"] is False
    assert nomination["reason"] == "source-evidence-unqualified"
    assert context["completeness"] == "incomplete"
    assert context["reasons"] == ["manifest-source-unqualified"]
    assert "not-disclosed" not in json.dumps(context)


def test_python_root_context_requalifies_changed_workspace_membership(
    tmp_path: Path,
) -> None:
    path = "packages/api/src/catalog/total.py"
    _write(tmp_path, path, "def total(): return 1\n")
    _write(
        tmp_path,
        "packages/api/pyproject.toml",
        '[tool.setuptools.package-dir]\n"" = "src"\n',
    )
    _write(tmp_path, "pyproject.toml", '[tool.uv.workspace]\nmembers=["packages/*"]\n')
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        before = _context(repository, path)
        _write(tmp_path, "pyproject.toml", '[tool.uv.workspace]\nmembers=["other"]\n')
        after = _context(repository, path)
    assert before["python_source_roots"] == ["packages/api/src"]
    assert after["python_source_roots"] == []
    assert after["source_root_state"] == "unknown"
    assert after["context_identity"] != before["context_identity"]
    assert "pyproject.toml" in {
        row["path"] for row in assert_records(after["supporting_source_members"])
    }


def test_packaging_reconciliation_rejects_a_competing_generation(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pyproject.toml", '[tool.setuptools.package-dir]\n""="src"\n')
    _write(tmp_path, "src/catalog/total.py", "def total(): return 1\n")
    with CodeMap(tmp_path) as repository:
        first = repository.index.sync()
        _write(tmp_path, "unrelated.py", "value = 1\n")
        repository.index.sync(["unrelated.py"])
        _write(tmp_path, "pyproject.toml", '[tool.setuptools.package-dir]\n""="lib"\n')
        with pytest.raises(RuntimeError, match="changed before expected decision"):
            repository.index.reconcile_path(
                "pyproject.toml", expected_generation=first.generation
            )
        assert repository.index.python_import_roots == ("src",)


def test_packaging_projection_cannot_bind_a_later_manifest_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = '[tool.setuptools.package-dir]\n""="src"\n'
    after = '[tool.setuptools.package-dir]\n""="lib"\n'
    _write(tmp_path, "pyproject.toml", before)
    for folder in ("src", "lib"):
        _write(tmp_path, f"{folder}/catalog/total.py", "def total(): return 1\n")
    with CodeMap(tmp_path) as repository:
        first = repository.index.sync()
        _write(tmp_path, "pyproject.toml", after)
        original = repository.file_store.read_bytes_stable
        intervened = False

        def read_then_change(
            path: str | Path, *, max_attempts: int = 3
        ) -> tuple[bytes, Digest]:
            nonlocal intervened
            result = original(path, max_attempts=max_attempts)
            if Path(path) == tmp_path / "pyproject.toml" and not intervened:
                intervened = True
                _write(tmp_path, "pyproject.toml", before)
            return result

        with monkeypatch.context() as race:
            race.setattr(repository.file_store, "read_bytes_stable", read_then_change)
            with pytest.raises(UnstableFileError, match="import-root input changed"):
                repository.verification.changed_set(["lib/catalog/total.py"])
        assert intervened
        assert repository.index.python_import_roots == ("src",)
        assert repository.store.generation() == first.generation
        assert repository.store.meta("sync.build_state") == "COMPLETE"
        context = _context(repository, "lib/catalog/total.py")
        assert context["python_source_roots"] == []
        assert context["source_root_state"] == "unknown"


def test_context_ancestor_limit_stays_explicit(tmp_path: Path) -> None:
    path = "/".join(["nested"] * 33 + ["test_value.py"])
    _write(tmp_path, path, "def test_value(): pass\n")
    _write(tmp_path, "pyproject.toml", "[tool.pytest.ini_options]\n")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        context = _context(repository, path)
        nomination = repository.verification.nomination(path)
    assert nomination["available"] is False
    assert context["completeness"] == "incomplete"
    assert context["truncation"] == "truncated"
    assert context["reasons"] == ["manifest-ancestor-limit"]
    assert len(assert_records(context["supporting_source_members"])) == 32
