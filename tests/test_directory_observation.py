from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

import pytest

from hashmarks import RepositoryIdentity
from hashmarks.digest import Digest
from hashmarks.file_store import FileDigestStore
from hashmarks.observation import UnstableObservationError
from hashmarks.snapshot import InputCounts


def test_directory_contents_and_child_input_roots_keep_native_hash_domains(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "child" / "__pycache__").mkdir(parents=True)
    (root / "child" / "kept").write_bytes(b"yes")
    (root / "child" / "__pycache__" / "ignored").write_bytes(b"physical")
    with RepositoryIdentity(
        root, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        observed = identity.observe_directory(verify=True)
        assert (
            observed.inputs.snapshot.digest
            == identity.snapshot("*", verify=True).digest
        )
    with RepositoryIdentity(
        root / "child", mode="local", state_dir=tmp_path / "child-state"
    ) as identity:
        child = identity.observe_directory(verify=True)
        assert (
            child.inputs.snapshot.digest == identity.snapshot("*", verify=True).digest
        )
    assert observed.inputs.counts == InputCounts(1, 1, 0, 3)
    assert observed.materialization_counts == InputCounts(2, 2, 0, 11)
    assert child.materialization_counts == InputCounts(2, 1, 0, 11)
    assert observed.inputs.members[0].revision != child.inputs.snapshot.hash
    assert observed.inputs.snapshot.hash != child.inputs.snapshot.hash


def test_directory_exclusions_are_literal_and_match_filtered_native_identity(
    tmp_path: Path,
) -> None:
    root, filtered = tmp_path / "repo", tmp_path / "filtered"
    (root / "src" / "generated").mkdir(parents=True)
    (filtered / "src").mkdir(parents=True)
    for base in (root, filtered):
        (base / "src" / "keep").write_bytes(b"yes")
    (root / "src" / "generated" / "private").write_bytes(b"excluded")
    (root / "[literal]").write_bytes(b"excluded")
    (root / "l").write_bytes(b"kept")
    (filtered / "l").write_bytes(b"kept")
    with RepositoryIdentity(
        root, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        observed = identity.observe_directory(
            exclude_paths=("src/generated", "[literal]", "absent"), verify=True
        )
    with RepositoryIdentity(
        filtered, mode="local", state_dir=tmp_path / "filtered-state"
    ) as identity:
        assert (
            observed.inputs.snapshot.digest
            == identity.snapshot("*", verify=True).digest
        )
    assert observed.materialization_counts == InputCounts(2, 1, 0, 7)


def test_physical_counts_do_not_hash_ignored_bytes_or_follow_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    (root / "src" / "__pycache__").mkdir(parents=True)
    (root / "src" / "kept").write_bytes(b"yes")
    (root / "src" / "__pycache__" / "ignored").write_bytes(b"physical")
    (root / "src" / "alias").symlink_to(tmp_path / "missing")
    reads: list[str] = []
    original = FileDigestStore.digest_many_info

    def read(
        owner: FileDigestStore,
        files: Iterable[tuple[Path, str]],
        *,
        workspace: str | Path,
        force: bool = False,
    ) -> dict[str, tuple[Digest, bool]]:
        selected = tuple(files)
        reads.extend(path for _host, path in selected)
        return original(owner, selected, workspace=workspace, force=force)

    monkeypatch.setattr(FileDigestStore, "digest_many_info", read)
    with RepositoryIdentity(
        root, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        observed = identity.observe_directory(verify=True)
    assert reads == ["src/kept"]
    assert observed.materialization_counts == InputCounts(2, 2, 1, 11)


def test_physical_count_mutation_cannot_return_a_complete_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    (root / "src" / "__pycache__").mkdir(parents=True)
    ignored = root / "src" / "__pycache__" / "ignored"
    ignored.write_bytes(b"before")
    (root / "src" / "kept").write_bytes(b"yes")
    original = FileDigestStore.digest_many_info

    def read(
        owner: FileDigestStore,
        files: Iterable[tuple[Path, str]],
        *,
        workspace: str | Path,
        force: bool = False,
    ) -> dict[str, tuple[Digest, bool]]:
        result = original(owner, files, workspace=workspace, force=force)
        if result:
            ignored.write_bytes(b"after")
        return result

    monkeypatch.setattr(FileDigestStore, "digest_many_info", read)
    with RepositoryIdentity(
        root, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        with pytest.raises(
            UnstableObservationError, match="changed during observation"
        ):
            identity.observe_directory(verify=True)


def test_directory_callbacks_and_physical_member_bound_abort_without_partial_results(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "src" / "__pycache__").mkdir(parents=True)
    (root / "src" / "__pycache__" / "ignored").write_bytes(b"physical")
    progress: list[InputCounts] = []

    def check() -> None:
        if progress:
            raise RuntimeError("caller stopped observation")

    with RepositoryIdentity(
        root, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        with pytest.raises(RuntimeError, match="caller stopped"):
            identity.observe_directory(checkpoint=check, progress=progress.append)
        with pytest.raises(ValueError, match="member limit exceeded"):
            identity.observe_directory(max_members=2)
        progress.clear()
        observed = identity.observe_directory(progress=progress.append)
        assert (
            progress[-1] == observed.materialization_counts == InputCounts(1, 2, 0, 8)
        )
    with RepositoryIdentity(
        root, mode="auto", state_dir=tmp_path / "state"
    ) as identity:
        with pytest.raises(ValueError, match="requires mode='local'"):
            identity.observe_directory()


def test_unsupported_ignored_entry_prevents_physical_completeness(
    tmp_path: Path,
) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unavailable")
    root = tmp_path / "repo"
    (root / "src" / "__pycache__").mkdir(parents=True)
    os.mkfifo(root / "src" / "__pycache__" / "pipe")
    with RepositoryIdentity(
        root, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        with pytest.raises(ValueError, match="unsupported selected-input entry"):
            identity.observe_directory()


def test_nested_mandatory_exclusion_is_physical_only_and_redundant_exclusions_collapse(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "src" / ".hashmarks").mkdir(parents=True)
    (root / "src" / ".hashmarks" / "private").write_bytes(b"physical")
    (root / "src" / "keep").write_bytes(b"yes")
    with RepositoryIdentity(
        root, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        observed = identity.observe_directory(verify=True)
        assert observed.inputs.counts == InputCounts(1, 1, 0, 3)
        assert observed.materialization_counts == InputCounts(2, 2, 0, 11)
        filtered = identity.observe_directory(
            exclude_paths=("src/.hashmarks/private", "src/.hashmarks"), verify=True
        )
        assert filtered.inputs.excluded_paths == ("src/.hashmarks",)
        assert filtered.inputs.snapshot.digest == observed.inputs.snapshot.digest
        assert filtered.materialization_counts == InputCounts(1, 1, 0, 3)


def test_default_owned_state_is_omitted_from_directory_observation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "payload").write_bytes(b"yes")
    with RepositoryIdentity(root, mode="local") as identity:
        observed = identity.observe_directory(verify=True)
        assert observed.inputs.manifest.paths == ("payload",)
        assert (
            observed.inputs.counts
            == observed.materialization_counts
            == InputCounts(1, 0, 0, 3)
        )
        assert (
            observed.inputs.snapshot.digest
            == identity.snapshot("payload", verify=True).digest
        )
        assert ".hashmarks" in observed.inputs.internal_excluded_paths
        with pytest.raises(ValueError, match="excluded from identity"):
            identity.observe_inputs(".hashmarks")
        with pytest.raises(ValueError, match="excluded from identity"):
            identity.snapshot(".hashmarks")


def test_nested_owned_state_is_omitted_from_physical_counts(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "payload").write_bytes(b"yes")
    with RepositoryIdentity(
        root, mode="local", state_dir=root / "src" / "state"
    ) as identity:
        observed = identity.observe_directory(verify=True)
        assert (
            observed.inputs.counts
            == observed.materialization_counts
            == InputCounts(1, 1, 0, 3)
        )
        assert tuple(member.path for member in observed.inputs.members) == (
            "src",
            "src/payload",
        )
        with pytest.raises(ValueError, match="excluded from identity"):
            identity.observe_inputs("src/state")


@pytest.mark.parametrize("scope", ["root", "ignored"])
@pytest.mark.parametrize("failure", ["bound", "cancel"])
def test_directory_enumeration_stops_before_exhausting_a_wide_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    failure: str,
) -> None:
    from collections.abc import Iterator
    from contextlib import AbstractContextManager
    from types import SimpleNamespace

    root = tmp_path / "repo"
    (root / "src" / "__pycache__").mkdir(parents=True)
    target = root if scope == "root" else root / "src" / "__pycache__"
    original = os.scandir
    scanned = 0
    closed = False

    class Entries:
        def __enter__(self) -> Entries:
            return self

        def __exit__(self, *_args: object) -> None:
            nonlocal closed
            closed = True

        def __iter__(self) -> Iterator[SimpleNamespace]:
            nonlocal scanned
            for index in range(1000):
                scanned += 1
                yield SimpleNamespace(name=f"entry-{index}")

    def scandir(path: str | Path) -> AbstractContextManager[Iterable[object]]:
        return Entries() if Path(path) == target else original(path)

    def check() -> None:
        if failure == "cancel" and scanned:
            raise RuntimeError("caller cancelled enumeration")

    monkeypatch.setattr(os, "scandir", scandir)
    with RepositoryIdentity(
        root, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        expected = RuntimeError if failure == "cancel" else ValueError
        with pytest.raises(
            expected, match="cancelled enumeration|member limit exceeded"
        ):
            identity.observe_directory(max_members=3, checkpoint=check)
    assert scanned <= 4
    assert closed


def test_excluded_direct_contents_do_not_consume_the_member_budget(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "omit").mkdir(parents=True)
    (root / "omit" / "nested").write_bytes(b"excluded")
    (root / "kept").write_bytes(b"yes")
    with RepositoryIdentity(
        root, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        observed = identity.observe_directory(
            exclude_paths=("omit",), max_members=1, verify=True
        )
    assert observed.inputs.manifest.paths == ("kept",)
    assert observed.materialization_counts == InputCounts(1, 0, 0, 3)
