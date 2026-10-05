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


class _PublicationHarness:
    def __init__(self, root: Path) -> None:
        self.source = _write_repository(root, symbol="before_owner")
        self.state = root / ".state"
        self.artifacts = root / "artifacts.sqlite3"
        with CodeMap(root, state_dir=self.state, artifact_db=self.artifacts) as seed:
            self.initial = seed.sync()
        self.source.write_text(
            "def after_owner():\n    return 'after'\n",
            encoding="utf-8",
        )
        self.writer_a = CodeMap(root, state_dir=self.state, artifact_db=self.artifacts)
        self.writer_b = CodeMap(root, state_dir=self.state, artifact_db=self.artifacts)
        self.reader = CodeMap(root, state_dir=self.state, artifact_db=self.artifacts)
        self.a_entered = threading.Event()
        self.a_release = threading.Event()
        self.b_entered = threading.Event()
        self.b_started = threading.Event()
        self.staged = threading.Event()
        self.finished = threading.Event()
        self.results: list[object] = []
        self.errors: list[BaseException] = []

    def install_writer_serialization_hooks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original_a_begin = self.writer_a._sync_begin_build
        original_b_begin = self.writer_b._sync_begin_build

        def block_a(*args, **kwargs):
            value = original_a_begin(*args, **kwargs)
            self.a_entered.set()
            if not self.a_release.wait(timeout=5):
                raise TimeoutError("test did not release first CodeMap writer")
            return value

        def observe_b(*args, **kwargs):
            self.b_entered.set()
            return original_b_begin(*args, **kwargs)

        monkeypatch.setattr(self.writer_a, "_sync_begin_build", block_a)
        monkeypatch.setattr(self.writer_b, "_sync_begin_build", observe_b)

    def install_staged_finalize_hook(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original_finalize = self.writer_a._sync_finalize_identity

        def block_before_publication(*args, **kwargs):
            self.staged.set()
            if not self.a_release.wait(timeout=5):
                raise TimeoutError("test did not release staged CodeMap publication")
            return original_finalize(*args, **kwargs)

        monkeypatch.setattr(
            self.writer_a, "_sync_finalize_identity", block_before_publication
        )

    def run(self, writer: CodeMap, *, started: threading.Event | None = None) -> None:
        if started is not None:
            started.set()
        try:
            self.results.append(writer.sync())
        except BaseException as exc:  # pragma: no cover - surfaced below
            self.errors.append(exc)

    def run_and_finish(self) -> None:
        try:
            self.run(self.writer_a)
        finally:
            self.finished.set()

    def close(self) -> None:
        self.a_release.set()
        self.writer_a.close()
        self.writer_b.close()
        self.reader.close()


def test_concurrent_sync_writers_serialize_one_publication_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _PublicationHarness(tmp_path)
    harness.install_writer_serialization_hooks(monkeypatch)
    thread_a = threading.Thread(target=harness.run, args=(harness.writer_a,))
    thread_b = threading.Thread(
        target=harness.run,
        args=(harness.writer_b,),
        kwargs={"started": harness.b_started},
    )
    try:
        thread_a.start()
        assert harness.a_entered.wait(timeout=5)

        status = harness.reader.status()
        assert status["generation"] == harness.initial.generation
        assert status["build"]["complete"] is True
        assert harness.reader.store.symbol("before_owner")
        assert harness.reader.store.symbol("after_owner") == []

        thread_b.start()
        assert harness.b_started.wait(timeout=2)
        assert not harness.b_entered.wait(timeout=0.1)

        harness.a_release.set()
        thread_a.join(timeout=10)
        thread_b.join(timeout=10)
        assert not thread_a.is_alive()
        assert not thread_b.is_alive()
        assert harness.errors == []
        assert harness.b_entered.is_set()
        assert len(harness.results) == 2
        assert {result.generation for result in harness.results} == {
            harness.initial.generation + 1
        }

        assert harness.reader.store.symbol("before_owner") == []
        assert harness.reader.store.symbol("after_owner")
        assert harness.reader.status()["build"]["complete"] is True
        assert harness.reader.store.generation() == harness.initial.generation + 1
    finally:
        harness.a_release.set()
        thread_a.join(timeout=1)
        if thread_b.ident is not None:
            thread_b.join(timeout=1)
        harness.close()


def test_inflight_decision_never_observes_uncommitted_next_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _PublicationHarness(tmp_path)
    harness.install_staged_finalize_hook(monkeypatch)
    thread = threading.Thread(target=harness.run_and_finish)
    try:
        thread.start()
        assert harness.staged.wait(timeout=5)

        with pytest.raises(
            RuntimeError, match="generation changed during decision session"
        ):
            with harness.reader.decision_session():
                assert harness.reader.store.generation() == harness.initial.generation
                assert harness.reader.store.symbol("before_owner")
                assert harness.reader.store.symbol("after_owner") == []
                harness.a_release.set()
                assert harness.finished.wait(timeout=5)

        thread.join(timeout=5)
        assert not thread.is_alive()
        assert harness.errors == []
        assert harness.reader.store.generation() == harness.initial.generation + 1
        assert harness.reader.store.symbol("before_owner") == []
        assert harness.reader.store.symbol("after_owner")
    finally:
        harness.a_release.set()
        thread.join(timeout=1)
        harness.close()


def test_public_symbol_fails_instead_of_mixing_committed_generations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _PublicationHarness(tmp_path)
    evidence_read = threading.Event()
    writer_finished = threading.Event()
    original_symbol = harness.reader.store.symbol

    def block_after_symbol_read(query: str):
        rows = original_symbol(query)
        if query == "before_owner":
            evidence_read.set()
            if not writer_finished.wait(timeout=5):
                raise TimeoutError("writer did not publish the competing generation")
        return rows

    monkeypatch.setattr(harness.reader.store, "symbol", block_after_symbol_read)

    def publish_next_generation() -> None:
        if not evidence_read.wait(timeout=5):
            harness.errors.append(TimeoutError("reader did not reach symbol evidence"))
            return
        try:
            harness.writer_a.sync()
        except BaseException as exc:  # pragma: no cover - surfaced below
            harness.errors.append(exc)
        finally:
            writer_finished.set()

    thread = threading.Thread(target=publish_next_generation)
    try:
        thread.start()
        with pytest.raises(
            RuntimeError, match="generation changed during decision session"
        ):
            harness.reader.symbol("before_owner")
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert harness.errors == []
        assert harness.reader.store.generation() == harness.initial.generation + 1
    finally:
        writer_finished.set()
        thread.join(timeout=1)
        harness.close()


class _LazyRefreshHarness:
    def __init__(self, root: Path) -> None:
        source = _write_repository(root, symbol="before_owner")
        self.state = root / ".state"
        self.artifacts = root / "artifacts.sqlite3"
        with CodeMap(root, state_dir=self.state, artifact_db=self.artifacts) as seed:
            self.initial = seed.sync()
            self.initial_fingerprint = seed.store.meta("workspace_fingerprint")
        self.reader = CodeMap(root, state_dir=self.state, artifact_db=self.artifacts)
        self.observer = CodeMap(root, state_dir=self.state, artifact_db=self.artifacts)
        source.write_text(
            "def after_owner():\n    return 'after'\n",
            encoding="utf-8",
        )
        self.staged = threading.Event()
        self.release = threading.Event()
        self.results: list[dict[str, object]] = []
        self.errors: list[BaseException] = []

    def install_staged_row_hook(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original_set_file = self.reader.store.set_file

        def block_after_staged_row(*args, **kwargs):
            value = original_set_file(*args, **kwargs)
            self.staged.set()
            if not self.release.wait(timeout=5):
                raise TimeoutError("test did not release staged path refresh")
            return value

        monkeypatch.setattr(self.reader.store, "set_file", block_after_staged_row)

    def run_outline(self) -> None:
        try:
            self.results.append(self.reader.outline("src/owner.py"))
        except BaseException as exc:  # pragma: no cover - surfaced below
            self.errors.append(exc)

    def close(self) -> None:
        self.release.set()
        self.reader.close()
        self.observer.close()


def test_lazy_path_refresh_publishes_row_generation_and_fingerprint_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _LazyRefreshHarness(tmp_path)
    harness.install_staged_row_hook(monkeypatch)
    thread = threading.Thread(target=harness.run_outline)
    try:
        thread.start()
        assert harness.staged.wait(timeout=5)

        assert harness.observer.store.generation() == harness.initial.generation
        assert harness.observer.store.symbol("before_owner")
        assert harness.observer.store.symbol("after_owner") == []
        assert (
            harness.observer.store.meta("workspace_fingerprint")
            == harness.initial_fingerprint
        )

        harness.release.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert harness.errors == []
        assert len(harness.results) == 1
        assert harness.results[0]["generation"] == harness.initial.generation + 1
        assert "after_owner" in str(harness.results[0]["outline"])
        assert harness.observer.store.generation() == harness.initial.generation + 1
        assert harness.observer.store.symbol("before_owner") == []
        assert harness.observer.store.symbol("after_owner")
        assert (
            harness.observer.store.meta("workspace_fingerprint")
            != harness.initial_fingerprint
        )
    finally:
        harness.release.set()
        thread.join(timeout=1)
        harness.close()
