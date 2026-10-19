from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from hashmarks import Directory, File, Glob, RepositoryIdentity
from hashmarks.snapshot import InputCounts


@pytest.fixture
def identity(tmp_path: Path) -> Iterator[RepositoryIdentity]:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    with RepositoryIdentity(
        workspace, mode="local", state_dir=tmp_path / "state"
    ) as selected:
        yield selected


def test_identity_and_members_share_equivalent_resolved_selections(
    identity: RepositoryIdentity,
) -> None:
    source = identity.workspace / "src"
    (source / "empty").mkdir(parents=True)
    (source / "a.py").write_bytes(b"a = 1\n")
    (source / "b.bin").write_bytes(b"\x00\xff\x80")
    (identity.workspace / "config.txt").write_bytes(b"config")

    first = identity.observe_inputs(Directory("src"), File("config.txt"))
    reordered = identity.observe_inputs("config.txt", "src/a.py", "src", "src")
    native = identity.snapshot("src", "config.txt")

    assert first.snapshot.digest == reordered.snapshot.digest == native.digest
    assert first.manifest == reordered.manifest
    assert first.snapshot.manifest_fingerprint == native.manifest_fingerprint
    assert first.members == reordered.members
    assert first.counts == InputCounts(3, 2, 0, 15)
    assert first.snapshot.digest.size != first.counts.regular_file_bytes
    assert [member.path for member in first.members] == [
        "config.txt",
        "src",
        "src/a.py",
        "src/b.bin",
        "src/empty",
    ]


def test_exclusions_use_the_same_canonical_directory_encoding(
    identity: RepositoryIdentity, tmp_path: Path
) -> None:
    source = identity.workspace / "src"
    source.mkdir()
    (source / "keep").write_bytes(b"yes")
    (source / "omit").write_bytes(b"no")
    filtered_root = tmp_path / "filtered"
    (filtered_root / "src").mkdir(parents=True)
    (filtered_root / "src" / "keep").write_bytes(b"yes")

    unfiltered = identity.snapshot("src")
    filtered = identity.observe_inputs("src", exclude=("src/omit",))
    with RepositoryIdentity(
        filtered_root, mode="local", state_dir=tmp_path / "filtered-state"
    ) as expected:
        assert filtered.snapshot.digest == expected.snapshot("src").digest
    assert filtered.snapshot.digest != unfiltered.digest
    assert identity.snapshot("src").digest == unfiltered.digest
    assert filtered.excluded_paths == ("src/omit",)
    assert filtered.counts == InputCounts(1, 1, 0, 3)


def test_excluded_changes_do_not_change_selected_identity_or_inventory(
    identity: RepositoryIdentity,
) -> None:
    source = identity.workspace / "src"
    (source / "generated").mkdir(parents=True)
    (source / "keep").write_bytes(b"keep")
    (source / "generated" / "old").write_bytes(b"old")
    first = identity.observe_inputs("src", exclude=("src/generated", "src/later"))

    (source / "generated" / "old").unlink()
    (source / "generated" / "new").write_bytes(b"changed")
    (source / "later").write_bytes(b"new excluded path")
    second = identity.observe_inputs(
        "src",
        exclude=("src/later", "src/generated/old", "src/generated"),
    )

    assert first.snapshot.digest == second.snapshot.digest
    assert first.members == second.members
    assert first.excluded_paths == second.excluded_paths
    assert first.counts == second.counts == InputCounts(1, 1, 0, 4)


@pytest.mark.parametrize("mutation", ["add", "delete", "rename", "content"])
def test_selected_membership_or_content_change_changes_identity(
    identity: RepositoryIdentity, mutation: str
) -> None:
    source = identity.workspace / "src"
    source.mkdir()
    target = source / "a"
    target.write_bytes(b"old")
    first = identity.observe_inputs("src")
    if mutation == "add":
        (source / "b").write_bytes(b"new")
    elif mutation == "delete":
        target.unlink()
    elif mutation == "rename":
        target.rename(source / "b")
    else:
        target.write_bytes(b"replacement")

    second = identity.observe_inputs("src")

    assert second.snapshot.digest != first.snapshot.digest
    assert second.members != first.members
    assert second.snapshot.digest == identity.snapshot("src").digest


def test_file_execute_bit_is_inventory_and_selected_identity_evidence(
    identity: RepositoryIdentity,
) -> None:
    if os.name == "nt":
        pytest.skip("POSIX executable bit semantics")
    target = identity.workspace / "script"
    target.write_bytes(b"echo yes\n")
    target.chmod(0o644)
    first = identity.observe_inputs("script")
    target.chmod(0o755)
    second = identity.observe_inputs("script")

    assert first.members[0].revision == second.members[0].revision
    assert first.members[0].executable is False
    assert second.members[0].executable is True
    assert first.snapshot.digest != second.snapshot.digest


def test_symlink_targets_are_literal_and_never_followed(
    identity: RepositoryIdentity, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.write_bytes(b"first")
    link = identity.workspace / "link"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    first = identity.observe_inputs("link")
    outside.write_bytes(b"changed target bytes")
    second = identity.observe_inputs("link")
    assert first.members == second.members
    assert first.snapshot.digest == second.snapshot.digest
    assert first.counts == InputCounts(0, 0, 1, 0)
    assert first.members[0].link_target == str(outside)
    link.unlink()
    link.symlink_to("missing")
    missing = identity.observe_inputs("link")
    assert missing.members[0].link_target == "missing"
    assert missing.members[0].revision != first.members[0].revision
    assert missing.snapshot.digest == identity.snapshot("link").digest


def test_hardlink_paths_each_contribute_file_bytes(
    identity: RepositoryIdentity,
) -> None:
    original = identity.workspace / "a"
    original.write_bytes(b"same")
    try:
        (identity.workspace / "b").hardlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("hardlinks unavailable")
    observed = identity.observe_inputs("b", "a")
    assert observed.counts == InputCounts(2, 0, 0, 8)
    assert observed.members[0].revision == observed.members[1].revision


def test_empty_scope_is_complete_for_resolved_roots_only(
    identity: RepositoryIdentity,
) -> None:
    (identity.workspace / "unselected").write_bytes(b"exists")
    empty = identity.observe_inputs(Glob("missing*"), require_matches=False)
    assert empty.snapshot.digest == identity.snapshot().digest
    assert empty.manifest.paths == ()
    assert empty.members == ()
    assert empty.counts == InputCounts(0, 0, 0, 0)
    assert empty.completeness == "complete"
    assert empty.freshness == "current"
    with pytest.raises(FileNotFoundError, match="matched nothing"):
        identity.observe_inputs("missing")
    excluded = identity.observe_inputs("unselected", exclude=("unselected",))
    assert excluded.snapshot.digest == empty.snapshot.digest
    assert excluded.manifest.paths == ()


def test_globs_are_resolved_once_into_explicit_scope(
    identity: RepositoryIdentity,
) -> None:
    source = identity.workspace / "src"
    source.mkdir()
    (source / "a.py").write_bytes(b"a")
    (source / "b.py").write_bytes(b"b")
    (source / "c.txt").write_bytes(b"c")
    observed = identity.observe_inputs(Glob("src/*"), exclude=(Glob("src/b.*"),))
    assert observed.manifest.paths == ("src/a.py", "src/c.txt")
    assert observed.excluded_paths == ("src/b.py",)
    assert [member.path for member in observed.members] == ["src/a.py", "src/c.txt"]
    assert observed.snapshot.digest == identity.snapshot("src/a.py", "src/c.txt").digest


def test_policy_exclusions_and_explicit_ignored_roots_remain_canonical(
    identity: RepositoryIdentity,
) -> None:
    source = identity.workspace / "src"
    for ignored in (".git", ".hashmarks", "__pycache__"):
        (source / ignored).mkdir(parents=True)
        (source / ignored / "entry").write_bytes(b"ignored")
    (source / "keep").write_bytes(b"kept")
    observed = identity.observe_inputs("src")
    assert observed.counts == InputCounts(1, 1, 0, 4)
    assert ".hashmarks" in observed.mandatory_exclude_names
    assert ".git" in observed.walk_ignore_names
    explicit = identity.observe_inputs("src/__pycache__")
    assert explicit.counts == InputCounts(1, 1, 0, 7)
    assert explicit.snapshot.digest == identity.snapshot("src/__pycache__").digest
    with pytest.raises(ValueError, match="excluded from identity"):
        identity.observe_inputs("src/.hashmarks")


def test_wire_observation_exposes_scope_counts_and_authority(
    identity: RepositoryIdentity,
) -> None:
    (identity.workspace / "empty").mkdir()
    observation = identity.observe_inputs("empty", exclude=("absent",))
    wire = json.loads(json.dumps(observation.as_dict()))
    assert wire["schema"] == "hashmarks.input-observation.v1"
    assert wire["snapshot"] == observation.snapshot.as_dict()
    assert wire["scope"]["roots"] == ["empty"]
    assert wire["scope"]["excluded_paths"] == ["absent"]
    assert wire["counts"]["entry_count"] == 1
    assert wire["counts"]["regular_file_bytes"] == 0
    assert wire["completeness"] == "complete"
    assert wire["freshness"] == "current"
    assert wire["authority"] == "repository-evidence-only"
    assert wire["execution_effect"] == "none"
