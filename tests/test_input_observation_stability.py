from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import cast

import pytest

from hashmarks import RepositoryIdentity
from hashmarks.digest import Digest
from hashmarks.file_store import FileDigestStore
from hashmarks.inputs import ResolvedInputScope
from hashmarks.merkle import MerkleTree
from hashmarks.observation import UnstableObservationError


def _identity(tmp_path: Path) -> RepositoryIdentity:
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a").write_bytes(b"a")
    return RepositoryIdentity(workspace, mode="local", state_dir=tmp_path / "state")


def _mutate_after_native_read(
    monkeypatch: pytest.MonkeyPatch, mutation: Callable[[], object]
) -> None:
    original = FileDigestStore.digest_many_info
    changed = False

    def mutate(
        owner: FileDigestStore,
        files: Iterable[tuple[Path, str]],
        *,
        workspace: str | Path,
        force: bool = False,
    ) -> dict[str, tuple[Digest, bool]]:
        nonlocal changed
        result = original(owner, files, workspace=workspace, force=force)
        if result and not changed:
            changed = True
            mutation()
        return result

    monkeypatch.setattr(FileDigestStore, "digest_many_info", mutate)


def test_mutation_cannot_pair_old_counts_with_a_new_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _identity(tmp_path) as identity:
        target = identity.workspace / "src" / "a"
        _mutate_after_native_read(monkeypatch, lambda: target.write_bytes(b"bbbb"))
        with pytest.raises(
            UnstableObservationError, match="changed during observation"
        ):
            identity.observe_inputs("src")
        stable = identity.observe_inputs("src")
        assert stable.counts.regular_file_bytes == 4
        assert stable.snapshot.digest == identity.snapshot("src").digest


def test_directory_addition_during_capture_is_unstable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _identity(tmp_path) as identity:
        target = identity.workspace / "src" / "new"
        _mutate_after_native_read(monkeypatch, lambda: target.write_bytes(b"new"))
        with pytest.raises(
            UnstableObservationError, match="changed during observation"
        ):
            identity.observe_inputs("src")


def test_selected_disappearance_during_capture_is_unstable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _identity(tmp_path) as identity:
        target = identity.workspace / "src" / "a"
        _mutate_after_native_read(monkeypatch, target.unlink)
        with pytest.raises(UnstableObservationError):
            identity.observe_inputs("src")


def test_excluded_addition_during_capture_does_not_enter_selected_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _identity(tmp_path) as identity:
        target = identity.workspace / "src" / "excluded"
        before = identity.observe_inputs("src", exclude=("src/excluded",))
        _mutate_after_native_read(monkeypatch, lambda: target.write_bytes(b"new"))
        after = identity.observe_inputs("src", exclude=("src/excluded",))
        assert after.members == before.members
        assert after.snapshot.digest == before.snapshot.digest
        assert after.counts == before.counts


@pytest.mark.parametrize(
    ("selection", "exclusions"),
    [("src/*", ()), ("src", ("src/*.tmp",)), ("src/*.tmp", ())],
)
def test_glob_scope_drift_between_resolution_and_capture_is_unstable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selection: str,
    exclusions: tuple[str, ...],
) -> None:
    with _identity(tmp_path) as identity:
        original = ResolvedInputScope.resolve
        changed = False

        def resolve(
            _cls: type[ResolvedInputScope],
            workspace: str | Path,
            patterns: Iterable[str],
            exclude: Iterable[str],
            *,
            require_matches: bool = True,
        ) -> ResolvedInputScope:
            nonlocal changed
            scope = original(
                workspace, patterns, exclude, require_matches=require_matches
            )
            if not changed:
                changed = True
                (identity.workspace / "src" / "new.tmp").write_bytes(b"new")
            return scope

        monkeypatch.setattr(ResolvedInputScope, "resolve", classmethod(resolve))
        with pytest.raises(UnstableObservationError, match="selection changed"):
            identity.observe_inputs(
                selection, exclude=exclusions, require_matches=False
            )


def test_permission_failure_never_returns_complete_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(_path: Path) -> list[os.DirEntry[str]]:
        raise PermissionError("cannot list selected directory")

    with _identity(tmp_path) as identity:
        monkeypatch.setattr(MerkleTree, "_sorted_scandir", staticmethod(denied))
        with pytest.raises(PermissionError, match="cannot list"):
            identity.observe_inputs("src")


def test_unsupported_fifo_is_rejected_before_reading(
    tmp_path: Path,
) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unavailable")
    with _identity(tmp_path) as identity:
        os.mkfifo(identity.workspace / "src" / "pipe")
        with pytest.raises(ValueError, match="unsupported selected-input entry"):
            identity.observe_inputs("src")


def test_symlink_ancestor_cannot_claim_a_physical_inventory(
    tmp_path: Path,
) -> None:
    with _identity(tmp_path) as identity:
        try:
            (identity.workspace / "alias").symlink_to("src", target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("directory symlinks unavailable")
        with pytest.raises(ValueError, match="symlink ancestor"):
            identity.observe_inputs("alias/a")


def test_member_bound_fails_without_a_partial_complete_result(tmp_path: Path) -> None:
    with _identity(tmp_path) as identity:
        with pytest.raises(ValueError, match="member limit exceeded"):
            identity.observe_inputs("src", max_members=1)
        assert identity.observe_inputs("src", max_members=2).counts.entry_count == 2


@pytest.mark.parametrize("maximum", [0, -1, True, 1.5])
def test_member_bound_requires_a_positive_integer(
    tmp_path: Path, maximum: object
) -> None:
    with _identity(tmp_path) as identity:
        with pytest.raises(ValueError, match="positive integer"):
            identity.observe_inputs("src", max_members=cast(int, maximum))


@pytest.mark.parametrize("selector", ["ref", "revision"])
def test_git_ref_authority_is_not_supported_by_live_input_observation(
    tmp_path: Path, selector: str
) -> None:
    with _identity(tmp_path) as identity:
        observe = cast(Callable[..., object], identity.observe_inputs)
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            observe("src", **{selector: "HEAD"})


def test_identity_inventory_does_not_import_codemap(tmp_path: Path) -> None:
    code = """
import sys
from pathlib import Path
from hashmarks import RepositoryIdentity
root = Path(sys.argv[1])
(root / 'repo').mkdir()
(root / 'repo' / 'entry').write_bytes(b'entry')
with RepositoryIdentity(root / 'repo', mode='local', state_dir=root / 'state') as identity:
    assert identity.observe_inputs('entry').counts.regular_file_bytes == 5
assert not any(name == 'hashmarks.codemap' or name.startswith('hashmarks.codemap.') for name in sys.modules)
"""
    subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=True)
