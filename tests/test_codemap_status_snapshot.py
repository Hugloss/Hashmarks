"""Status observes a committed publication while a separate connection publishes."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks.client import RepositoryObservation
from hashmarks.codemap import CodeMap
from hashmarks.codemap.watch_continuity import (
    WATCH_CONTINUITY_META,
    WatchContinuityRecord,
)
from hashmarks.observation import ObservationState


@pytest.fixture
def maps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[CodeMap, CodeMap]]:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "owner.py").write_text("def owner(): return 1\n", encoding="utf-8")
    state = tmp_path / "state"
    artifacts = tmp_path / "artifacts.sqlite3"
    with CodeMap(workspace, state_dir=state, artifact_db=artifacts) as writer:
        writer.index.sync()
        with CodeMap(workspace, state_dir=state, artifact_db=artifacts) as reader:
            monkeypatch.setattr(reader._observation_source, "observe", lambda: None)
            yield reader, writer


def _publication_facts(packet: dict[str, object]) -> dict[str, object]:
    # Parsed artifacts are a separate shared cache, not this publication's rows.
    return {key: value for key, value in packet.items() if key != "artifact_count"}


def _change_repository(writer: CodeMap) -> None:
    (writer.workspace / "owner.py").write_text(
        "def owner(): return 2\n\ndef added(): return 3\n", encoding="utf-8"
    )
    (writer.workspace / "extra.py").write_text(
        "def extra(): return 4\n", encoding="utf-8"
    )


def test_index_status_keeps_committed_rows_during_concurrent_sync(
    maps: tuple[CodeMap, CodeMap], monkeypatch: pytest.MonkeyPatch
) -> None:
    reader, writer = maps
    before = reader.index.status()
    _change_repository(writer)
    original_meta = reader.store.meta

    def publish_after_metadata(key: str, default: str | None = None) -> str | None:
        value = original_meta(key, default)
        if key == "last_sync_unix":
            monkeypatch.setattr(reader.store, "meta", original_meta)
            writer.index.sync()
        return value

    monkeypatch.setattr(reader.store, "meta", publish_after_metadata)
    assert _publication_facts(reader.index.status()) == _publication_facts(before)

    after = reader.index.status()
    assert after["generation"] == writer.store.generation()
    assert after["generation"] != before["generation"]
    assert after["workspace_fingerprint"] != before["workspace_fingerprint"]
    assert (before["files"], before["symbols"]) == (1, 1)
    assert (after["files"], after["symbols"]) == (2, 3)
    assert after["build"] != before["build"]


def _publish_observer_facts(writer: CodeMap, *, dirty: bool) -> None:
    generation = writer.store.generation()
    paths = ("owner.py",) if dirty else ()
    state = ObservationState.DIRTY if dirty else ObservationState.CLEAN
    record = WatchContinuityRecord(
        owner="status-snapshot-test",
        fence=1,
        pid=os.getpid(),
        heartbeat_unix=1_700_000_000.0,
        active=True,
        codemap_generation=generation,
        observation=RepositoryObservation(
            state=state,
            generation=generation,
            dirty_paths=paths,
            paths_complete=True,
            dirty_path_count=len(paths),
        ),
    )
    with writer.store.publication_transaction():
        writer.store.set_meta(WATCH_CONTINUITY_META, record.to_json())
        writer.native._record_evidence_snapshot(
            "scip", state.value, bind_generation=True
        )


def test_full_status_keeps_index_watcher_and_native_rows_in_one_snapshot(
    maps: tuple[CodeMap, CodeMap], monkeypatch: pytest.MonkeyPatch
) -> None:
    reader, writer = maps
    monkeypatch.setattr(
        "hashmarks.codemap.watch_continuity.time.time", lambda: 1_700_000_000.0
    )
    _publish_observer_facts(writer, dirty=False)
    before = reader.views.status()
    _change_repository(writer)
    original_status = reader.index.status

    def publish_after_index_status() -> dict[str, object]:
        result = original_status()
        monkeypatch.setattr(reader.index, "status", original_status)
        writer.index.sync()
        _publish_observer_facts(writer, dirty=True)
        return result

    monkeypatch.setattr(reader.index, "status", publish_after_index_status)
    assert _publication_facts(reader.views.status()) == _publication_facts(before)

    after = reader.views.status()
    assert after["generation"] == writer.store.generation()
    assert after["generation"] != before["generation"]
    assert before["daemon_generation_changed"] is False
    assert after["daemon_generation_changed"] is True
    assert assert_object(before["watcher"])["state"] == "clean"
    assert assert_object(after["watcher"])["state"] == "dirty"
    assert assert_object(after["watcher"])["codemap_generation"] == after["generation"]
    assert before["native_evidence"] == [
        {"kind": "scip", "producer": "clean", "fresh": True, "reason": None}
    ]
    assert [row["producer"] for row in assert_records(after["native_evidence"])] == [
        "clean",
        "dirty",
    ]


def test_index_status_keeps_warm_sync_metadata_when_generation_does_not_change(
    maps: tuple[CodeMap, CodeMap], monkeypatch: pytest.MonkeyPatch
) -> None:
    reader, writer = maps
    before = reader.index.status()
    original_meta = reader.store.meta

    def publish_after_economics(key: str, default: str | None = None) -> str | None:
        value = original_meta(key, default)
        if key == "sync.economics":
            monkeypatch.setattr(reader.store, "meta", original_meta)
            writer.index.sync()
        return value

    monkeypatch.setattr(reader.store, "meta", publish_after_economics)
    assert _publication_facts(reader.index.status()) == _publication_facts(before)

    after = reader.index.status()
    assert after["generation"] == before["generation"]
    assert after["workspace_fingerprint"] == before["workspace_fingerprint"]
    assert (
        assert_object(after["build"])["build_id"]
        != assert_object(before["build"])["build_id"]
    )
    assert after["last_index_economics"] != before["last_index_economics"]


def test_nested_read_snapshots_preserve_the_outer_committed_snapshot(
    maps: tuple[CodeMap, CodeMap],
) -> None:
    reader, writer = maps
    writer.store.set_meta("snapshot.test", "before")
    with reader.store.read_snapshot():
        assert reader.store.meta("snapshot.test") == "before"
        with reader.store.read_snapshot():
            writer.store.set_meta("snapshot.test", "during-inner")
            assert reader.store.meta("snapshot.test") == "before"
        writer.store.set_meta("snapshot.test", "after-inner")
        assert reader.store.meta("snapshot.test") == "before"
    assert reader.store.meta("snapshot.test") == "after-inner"


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_status_provider_failure_releases_snapshot_and_restores_writes(
    maps: tuple[CodeMap, CodeMap],
    monkeypatch: pytest.MonkeyPatch,
    error: type[BaseException],
) -> None:
    reader, writer = maps
    original_status = reader.native.status

    def fail_native_status() -> list[dict[str, object]]:
        with reader.store.read_snapshot():
            assert reader.store.generation() > 0
            raise error("sentinel status provider")

    monkeypatch.setattr(reader.native, "status", fail_native_status)
    with pytest.raises(error, match="sentinel status provider"):
        reader.views.status()
    monkeypatch.setattr(reader.native, "status", original_status)

    with reader.store.publication_transaction():
        reader.store.set_meta("snapshot.test", "after-error")
    assert writer.store.meta("snapshot.test") == "after-error"
    assert reader.views.status()["generation"] == writer.store.generation()


def test_read_snapshot_rejects_an_unpublished_write_transaction(
    maps: tuple[CodeMap, CodeMap],
) -> None:
    reader, writer = maps
    with reader.store.publication_transaction():
        reader.store.set_meta("snapshot.test", "unpublished")
        with pytest.raises(RuntimeError, match="read snapshot inside a transaction"):
            with reader.store.read_snapshot():
                pytest.fail("a read snapshot must reject unpublished writer state")
        assert writer.store.meta("snapshot.test") is None
        reader.store.set_meta("snapshot.test", "committed")
    assert writer.store.meta("snapshot.test") == "committed"


def test_read_snapshot_rejects_writes_on_its_own_connection(
    maps: tuple[CodeMap, CodeMap],
) -> None:
    reader, writer = maps
    with reader.store.read_snapshot():
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.store.set_meta("snapshot.test", "forbidden")
        assert reader.store.meta("snapshot.test") is None
    reader.store.set_meta("snapshot.test", "after-snapshot")
    assert writer.store.meta("snapshot.test") == "after-snapshot"
