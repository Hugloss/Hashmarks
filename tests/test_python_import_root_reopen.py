"""Packaging import authority must survive reopening the same native index."""

from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.codemap.repository_file_discovery import RepositoryFiles

_SOURCE = "backend/src/example/feature.py"
_VERIFIER = "backend/tests/test_feature.py"
_MANIFEST = "backend/pyproject.toml"
_PACKAGING = '[tool.setuptools.package-dir]\n"" = "src"\n'
_UNQUALIFIED_METADATA = {
    "malformed": "[tool.setuptools.package-dir\n",
    "unconfigured": '[project]\nname="example"\nversion="0"\n',
    "invalid": '[tool.setuptools.package-dir]\n"" = ["src"]\n',
    "moved": _PACKAGING.replace('"src"', '"lib"'),
}


def _repository(workspace: Path) -> None:
    for rel, text in (
        (_MANIFEST, _PACKAGING),
        (_SOURCE, "def value(): return 42\n"),
        (
            _VERIFIER,
            "from example.feature import value\n"
            "def test_value(): assert value() == 42\n",
        ),
    ):
        path = workspace / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _observation(codemap: CodeMap) -> dict[str, object]:
    return codemap.reads.observe(
        lambda _scope: codemap.tasks.verification_ownership_graph(f"Verify {_SOURCE}")
    )


def _qualified_verifiers(observation: dict[str, object]) -> list[str]:
    return [
        str(row["path"])
        for row in assert_records(observation["verification_owners"])
        if row["covers_edit_candidates"] == [_SOURCE]
        and row["coverage_evidence"] == "direct-reference"
    ]


def test_reopened_native_index_preserves_nested_packaging_verifier_relationship(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "repository"
    _repository(workspace)
    state = tmp_path / "state"
    with CodeMap(workspace, state_dir=state) as cold:
        cold.index.sync()
        before = _observation(cold)
        assert _qualified_verifiers(before) == [_VERIFIER]
        generation = cold.index.status()["generation"]
    # Reopening an already indexed workspace restores its manifest candidates;
    # it must not add a second full filesystem discovery before the next sync.
    with monkeypatch.context() as construction:
        construction.setattr(
            RepositoryFiles,
            "iter_files",
            lambda *_args, **_kwargs: pytest.fail("reopen rediscovered the workspace"),
        )
        reopened = CodeMap(workspace, state_dir=state)
    with reopened:
        after = _observation(reopened)
        assert _qualified_verifiers(after) == [_VERIFIER]
        assert after["edit_candidates"] == before["edit_candidates"]
        assert assert_object(after["verification_qualification"]) == assert_object(
            before["verification_qualification"]
        )
        assert reopened.index.status()["generation"] == generation


@pytest.mark.parametrize(
    "change",
    [
        "deleted",
        "malformed",
        "unconfigured",
        "invalid",
        "moved",
        "denied",
        "unindexed",
        "symlink",
    ],
)
def test_reopen_revokes_changed_or_unadmitted_nested_packaging_authority(
    tmp_path: Path, change: str
) -> None:
    workspace = tmp_path / "repository"
    _repository(workspace)
    state = tmp_path / "state"
    with CodeMap(workspace, state_dir=state) as cold:
        cold.index.sync()
        assert _qualified_verifiers(_observation(cold)) == [_VERIFIER]
    manifest = workspace / _MANIFEST
    policy = workspace / ".hashmarks-context.toml"
    if change in _UNQUALIFIED_METADATA:
        manifest.write_text(_UNQUALIFIED_METADATA[change], encoding="utf-8")
    elif change == "deleted":
        manifest.unlink()
    elif change in {"denied", "unindexed"}:
        setting = "visibility='deny'" if change == "denied" else "index=false"
        policy.write_text(
            f"[[rule]]\npattern='backend/pyproject.toml'\n{setting}\n",
            encoding="utf-8",
        )
    else:
        outside = tmp_path / "outside.toml"
        outside.write_text(_PACKAGING, encoding="utf-8")
        manifest.unlink()
        manifest.symlink_to(outside)
    with CodeMap(workspace, state_dir=state) as reopened:
        assert _qualified_verifiers(_observation(reopened)) == []
        if manifest.is_symlink():
            manifest.unlink()
        manifest.write_text(_PACKAGING, encoding="utf-8")
        if policy.exists():
            policy.unlink()
        reopened.index.sync([_MANIFEST])
        assert _qualified_verifiers(_observation(reopened)) == [_VERIFIER]


def test_added_nested_manifest_is_discovered_by_native_sync_after_reopen(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repository"
    _repository(workspace)
    (workspace / _MANIFEST).unlink()
    state = tmp_path / "state"
    with CodeMap(workspace, state_dir=state) as cold:
        cold.index.sync()
        assert _qualified_verifiers(_observation(cold)) == []
    (workspace / _MANIFEST).write_text(_PACKAGING, encoding="utf-8")
    with CodeMap(workspace, state_dir=state) as reopened:
        reopened.index.sync([_MANIFEST])
        assert _qualified_verifiers(_observation(reopened)) == [_VERIFIER]
    with CodeMap(workspace, state_dir=state) as reopened_again:
        assert _qualified_verifiers(_observation(reopened_again)) == [_VERIFIER]


def test_reopened_workspace_keeps_native_member_exclusion_and_refreshes_changes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repository"
    _repository(workspace)
    root_manifest = workspace / "pyproject.toml"
    root_manifest.write_text(
        '[tool.uv.workspace]\nmembers=["backend"]\n', encoding="utf-8"
    )
    other = workspace / "other/src/example"
    other.mkdir(parents=True)
    (other / "feature.py").write_text("def value(): return 21\n", encoding="utf-8")
    (workspace / "other/pyproject.toml").write_text(_PACKAGING, encoding="utf-8")
    state = tmp_path / "state"
    with CodeMap(workspace, state_dir=state) as cold:
        cold.index.sync()
        assert _qualified_verifiers(_observation(cold)) == [_VERIFIER]
    with CodeMap(workspace, state_dir=state) as reopened:
        assert _qualified_verifiers(_observation(reopened)) == [_VERIFIER]
    root_manifest.write_text(
        '[tool.uv.workspace]\nmembers=["other"]\n', encoding="utf-8"
    )
    with CodeMap(workspace, state_dir=state) as reopened:
        assert _qualified_verifiers(_observation(reopened)) == []
        root_manifest.write_text(
            '[tool.uv.workspace]\nmembers=["backend"]\n', encoding="utf-8"
        )
        reopened.index.sync(["pyproject.toml"])
        assert _qualified_verifiers(_observation(reopened)) == [_VERIFIER]


def test_reopened_nested_projects_keep_ambiguous_import_ownership_unqualified(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repository"
    _repository(workspace)
    state = tmp_path / "state"
    with CodeMap(workspace, state_dir=state) as cold:
        cold.index.sync()
        assert _qualified_verifiers(_observation(cold)) == [_VERIFIER]
    other = workspace / "other/src/example"
    other.mkdir(parents=True)
    (other / "feature.py").write_text("def value(): return 21\n", encoding="utf-8")
    (workspace / "other/pyproject.toml").write_text(_PACKAGING, encoding="utf-8")
    with CodeMap(workspace, state_dir=state) as reopened:
        reopened.index.sync(["other/pyproject.toml"])
        observation = _observation(reopened)
        assert _qualified_verifiers(observation) == []
        assert (
            assert_object(observation["verification_qualification"])[
                "verifier_identity_ambiguous"
            ]
            is True
        )
    with CodeMap(workspace, state_dir=state) as reopened_again:
        observation = _observation(reopened_again)
        assert _qualified_verifiers(observation) == []
        assert (
            assert_object(observation["verification_qualification"])[
                "negative_evidence_admissible"
            ]
            is False
        )
