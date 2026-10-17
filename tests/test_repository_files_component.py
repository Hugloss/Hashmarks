"""The admission component owns state and works without a CodeMap or database."""

import subprocess
import sys
from pathlib import Path

import pytest

from hashmarks.codemap.model import EvidenceVisibility
from hashmarks.codemap.repository_file_discovery import RepositoryFiles


def test_files_component_import_does_not_load_the_facade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.repository_file_discovery import RepositoryFiles; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.repository_index_store' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_standalone_files_component_owns_admission_and_format_neutral_traversal(
    tmp_path: Path,
) -> None:
    for name in (
        "src/owner.py",
        "src/contract.proto",
        "cache/result.py",
        "cache2/kept.py",
        ".venv/foreign.py",
        "nested/.git/config",
        "nested/private.py",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n")
    (tmp_path / "linked.py").symlink_to(tmp_path / "src/owner.py")
    files = RepositoryFiles(tmp_path, internal_state_path="cache")
    assert {item.rel for item in files.iter_files()} == {
        "src/owner.py",
        "src/contract.proto",
        "cache2/kept.py",
    }
    assert files.visible_file("src/contract.proto") is not None
    assert files.is_internal("cache/result.py")
    assert not files.is_internal("cache2/kept.py")
    assert not hasattr(files, "store")
    assert not hasattr(files, "codemap")
    assert not (tmp_path / ".hashmarks").exists()


def test_component_policy_reload_owns_semantic_change_and_invalid_input(
    tmp_path: Path,
) -> None:
    source = tmp_path / "owner.py"
    source.write_text("def owner(): pass\n")
    policy = tmp_path / ".hashmarks-context.toml"
    files = RepositoryFiles(tmp_path)
    before = files.policy_fingerprint()
    assert files.visible_file("owner.py") is not None
    policy.write_text("[[rule]]\npattern='owner.py'\nvisibility='outline'\n")
    assert files.refresh_policy()
    assert files.policy_fingerprint() != before
    assert files.decide("owner.py").evidence_visibility is EvidenceVisibility.OUTLINE
    policy.write_text("[[rule]]\npattern = 'owner.py'\nvisibility = 'outline'\n")
    assert not files.refresh_policy()
    policy.write_text("[[rule]]\npattern='owner.py'\nindex=false\n")
    assert files.refresh_policy()
    assert files.visible_file("owner.py") is None
    policy.write_text("this is not valid TOML")
    with pytest.raises(ValueError):
        files.refresh_policy()


def test_relative_workspace_and_policy_stay_bound_after_chdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    (workspace / "owner.py").write_text("def owner(): pass\n")
    (workspace / "policy.toml").write_text(
        "[[rule]]\npattern='owner.py'\nvisibility='outline'\n"
    )
    monkeypatch.chdir(tmp_path)
    files = RepositoryFiles(Path("repository"), policy_path=Path("policy.toml"))
    monkeypatch.chdir(workspace)

    admitted = files.visible_file("owner.py")
    assert admitted is not None
    assert admitted.path == workspace / "owner.py"
    assert admitted.visibility is EvidenceVisibility.OUTLINE
    assert not files.refresh_policy()


def test_workspace_alias_is_canonical_but_member_symlinks_remain_excluded(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    (workspace / "owner.py").write_text("def owner(): pass\n")
    (workspace / "linked.py").symlink_to(workspace / "owner.py")
    alias = tmp_path / "alias"
    alias.symlink_to(workspace, target_is_directory=True)
    files = RepositoryFiles(alias)

    admitted = files.visible_file("owner.py")
    assert admitted is not None
    assert admitted.path == workspace / "owner.py"
    assert {item.rel for item in files.iter_files()} == {"owner.py"}
    assert files.visible_file("linked.py") is None


def test_facade_files_reference_is_read_only(tmp_path: Path) -> None:
    from hashmarks.codemap import CodeMap

    with CodeMap(
        tmp_path,
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as repository:
        files = repository.files
        with pytest.raises(AttributeError):
            object.__setattr__(repository, "files", RepositoryFiles(tmp_path))
        assert repository.files is files


@pytest.mark.parametrize(
    "path", ["../outside.py", "/outside.py", "src/../../outside.py"]
)
def test_component_rejects_paths_outside_repository_scope(
    tmp_path: Path, path: str
) -> None:
    with pytest.raises(ValueError):
        RepositoryFiles(tmp_path).is_admitted(path)


def test_facade_does_not_keep_retired_admission_aliases() -> None:
    from hashmarks.codemap import CodeMap

    assert not hasattr(CodeMap, "_path_admitted_for_analysis")
    assert not hasattr(CodeMap, "_iter_admitted_repository_files")
    assert not hasattr(CodeMap, "_visible_repository_manifests")
