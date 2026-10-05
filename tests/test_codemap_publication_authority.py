from __future__ import annotations

import threading
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap


def _write_repository(root: Path, *, symbol: str) -> Path:
    source = root / "src" / "owner.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        f"def {symbol}():\n    return {symbol!r}\n",
        encoding="utf-8",
    )
    return source


def test_concurrent_sync_writers_serialize_one_publication_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _write_repository(tmp_path, symbol="before_owner")
    state = tmp_path / ".state"
    artifacts = tmp_path / "artifacts.sqlite3"

    with CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as seed:
        initial = seed.sync()

    source.write_text(
        "def after_owner():\n    return 'after'\n",
        encoding="utf-8",
    )
    writer_a = CodeMap(tmp_path, state_dir=state, artifact_db=artifacts)
    writer_b = CodeMap(tmp_path, state_dir=state, artifact_db=artifacts)
    reader = CodeMap(tmp_path, state_dir=state, artifact_db=artifacts)
    a_entered = threading.Event()
    a_release = threading.Event()
    b_entered = threading.Event()
    b_started = threading.Event()
    results: list[object] = []
    errors: list[BaseException] = []

    original_a_begin = writer_a._sync_begin_build
    original_b_begin = writer_b._sync_begin_build

    def block_a(*args, **kwargs):
        value = original_a_begin(*args, **kwargs)
        a_entered.set()
        if not a_release.wait(timeout=5):
            raise TimeoutError("test did not release first CodeMap writer")
        return value

    def observe_b(*args, **kwargs):
        b_entered.set()
        return original_b_begin(*args, **kwargs)

    monkeypatch.setattr(writer_a, "_sync_begin_build", block_a)
    monkeypatch.setattr(writer_b, "_sync_begin_build", observe_b)

    def run(writer: CodeMap, *, started: threading.Event | None = None) -> None:
        if started is not None:
            started.set()
        try:
            results.append(writer.sync())
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    thread_a = threading.Thread(target=run, args=(writer_a,))
    thread_b = threading.Thread(
        target=run, args=(writer_b,), kwargs={"started": b_started}
    )
    try:
        thread_a.start()
        assert a_entered.wait(timeout=5)

        status = reader.status()
        assert status["generation"] == initial.generation
        assert status["build"]["complete"] is True
        assert reader.store.symbol("before_owner")
        assert reader.store.symbol("after_owner") == []

        thread_b.start()
        assert b_started.wait(timeout=2)
        assert not b_entered.wait(timeout=0.1)

        a_release.set()
        thread_a.join(timeout=10)
        thread_b.join(timeout=10)
        assert not thread_a.is_alive()
        assert not thread_b.is_alive()
        assert errors == []
        assert b_entered.is_set()
        assert len(results) == 2
        assert {result.generation for result in results} == {initial.generation + 1}

        assert reader.store.symbol("before_owner") == []
        assert reader.store.symbol("after_owner")
        assert reader.status()["build"]["complete"] is True
        assert reader.store.generation() == initial.generation + 1
    finally:
        a_release.set()
        thread_a.join(timeout=1)
        if thread_b.ident is not None:
            thread_b.join(timeout=1)
        writer_a.close()
        writer_b.close()
        reader.close()


def test_inflight_decision_never_observes_uncommitted_next_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _write_repository(tmp_path, symbol="before_owner")
    state = tmp_path / ".state"
    artifacts = tmp_path / "artifacts.sqlite3"

    with CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as seed:
        initial = seed.sync()

    writer = CodeMap(tmp_path, state_dir=state, artifact_db=artifacts)
    reader = CodeMap(tmp_path, state_dir=state, artifact_db=artifacts)
    source.write_text(
        "def after_owner():\n    return 'after'\n",
        encoding="utf-8",
    )
    staged = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    errors: list[BaseException] = []
    original_finalize = writer._sync_finalize_identity

    def block_before_publication(*args, **kwargs):
        staged.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test did not release staged CodeMap publication")
        return original_finalize(*args, **kwargs)

    monkeypatch.setattr(writer, "_sync_finalize_identity", block_before_publication)

    def run_writer() -> None:
        try:
            writer.sync()
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=run_writer)
    try:
        thread.start()
        assert staged.wait(timeout=5)

        with pytest.raises(
            RuntimeError, match="generation changed during decision session"
        ):
            with reader.decision_session():
                assert reader.store.generation() == initial.generation
                assert reader.store.symbol("before_owner")
                assert reader.store.symbol("after_owner") == []
                release.set()
                assert finished.wait(timeout=5)

        thread.join(timeout=5)
        assert not thread.is_alive()
        assert errors == []
        assert reader.store.generation() == initial.generation + 1
        assert reader.store.symbol("before_owner") == []
        assert reader.store.symbol("after_owner")
    finally:
        release.set()
        thread.join(timeout=1)
        writer.close()
        reader.close()
