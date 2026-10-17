"""Reverse relationship reuse must converge with a fresh admitted repository."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap


def _repository(root: Path) -> None:
    root.mkdir()
    (root / "owner.ts").write_text("export function owner() {}\n")
    (root / "other.ts").write_text("export function other() {}\n")
    (root / "consumer.ts").write_text("import { owner } from './owner';\n")


@pytest.mark.parametrize("transition", ["modify", "add", "delete", "rename", "deny"])
def test_reverse_relationship_cache_matches_fresh_after_transition(
    tmp_path: Path, transition: str
) -> None:
    workspace = tmp_path / "repo"
    _repository(workspace)
    with CodeMap(
        workspace,
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        assert codemap.affected("owner.ts")["affected_files"] == ["consumer.ts"]
        if transition == "modify":
            (workspace / "consumer.ts").write_text("import { other } from './other';\n")
        elif transition == "add":
            (workspace / "added.ts").write_text("import { owner } from './owner';\n")
        elif transition == "delete":
            (workspace / "consumer.ts").unlink()
        elif transition == "rename":
            (workspace / "consumer.ts").rename(workspace / "renamed.ts")
        else:
            (workspace / ".hashmarks-context.toml").write_text(
                "[[rule]]\npattern = 'consumer.ts'\nindex = false\n"
            )
        codemap.index.sync()
        actual = codemap.affected("owner.ts")["affected_files"]
        with CodeMap(
            workspace,
            state_dir=tmp_path / "fresh",
            artifact_db=tmp_path / "fresh-artifacts.sqlite3",
        ) as fresh:
            fresh.index.sync()
            expected = fresh.affected("owner.ts")["affected_files"]
        assert actual == expected
        assert actual == (
            {"add": ["added.ts", "consumer.ts"], "rename": ["renamed.ts"]}.get(
                transition, []
            )
        )


def test_reverse_queries_reuse_graph_and_no_change_sync_revalidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "repo"
    _repository(workspace)
    with CodeMap(
        workspace,
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        build = codemap._file_graph
        builds = 0

        def measured_graph(
            *, native_edges: Sequence[Mapping[str, object]]
        ) -> dict[str, set[str]]:
            nonlocal builds
            builds += 1
            return build(native_edges=native_edges)

        monkeypatch.setattr(codemap, "_file_graph", measured_graph)
        first = codemap.affected("owner.ts")
        second = codemap.affected("owner.ts")
        assert first["affected_files"] == second["affected_files"] == ["consumer.ts"]
        assert builds == 1
        codemap.index.sync()
        assert codemap.affected("owner.ts")["affected_files"] == ["consumer.ts"]
        assert builds == 1


def test_native_qualification_changes_revalidate_without_index_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "repo"
    _repository(workspace)
    (workspace / "consumer.ts").write_text("export function consumer() {}\n")
    qualified_edges = [{"source": "consumer.ts", "target": "owner.ts"}]
    with CodeMap(
        workspace,
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        generation = codemap.store.generation()
        monkeypatch.setattr(
            codemap, "_fresh_native_file_edges", lambda: qualified_edges
        )
        assert codemap.affected("owner.ts")["affected_files"] == ["consumer.ts"]
        qualified_edges.clear()
        assert codemap.affected("owner.ts")["affected_files"] == []
        assert codemap.store.generation() == generation


def test_clear_and_rebuild_cannot_reuse_old_relationship_authority(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    _repository(workspace)
    with CodeMap(
        workspace,
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        assert codemap.affected("owner.ts")["affected_files"] == ["consumer.ts"]
        generation = codemap.store.generation()
        codemap.index.clean()
        (workspace / "consumer.ts").write_text("import { other } from './other';\n")
        codemap.index.sync()
        assert codemap.affected("owner.ts")["affected_files"] == []
        assert codemap.store.generation() > generation
