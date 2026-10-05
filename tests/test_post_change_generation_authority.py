from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap


def _repo(root: Path) -> tuple[Path, Path, str]:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    source = root / "src" / "owner.py"
    other = root / "src" / "other.py"
    source.write_text("def widget(): return 'old'\n", encoding="utf-8")
    other.write_text("def other(): return 'old'\n", encoding="utf-8")
    (root / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\ndef test_widget(): assert widget() == 'new'\n",
        encoding="utf-8",
    )
    return source, other, "change widget implementation and verify widget test"


def _install_competing_writer(
    reader: CodeMap,
    writer: CodeMap,
    other: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_sync = reader.sync

    def racing_sync(paths=None):
        result = original_sync(paths)
        other.write_text("def other(): return 'new'\n", encoding="utf-8")
        writer.sync(["src/other.py"])
        return result

    monkeypatch.setattr(reader, "sync", racing_sync)


@pytest.mark.parametrize(
    "method_name",
    [
        "task_change_impact",
        "refresh_after_change",
        "refresh_after_change_brief",
        "refresh_after_change_delta",
    ],
)
def test_post_sync_composition_rejects_competing_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
) -> None:
    source, other, task = _repo(tmp_path)
    state = tmp_path / ".state"
    artifacts = tmp_path / "artifacts.sqlite3"
    with (
        CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as reader,
        CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as writer,
    ):
        reader.sync()
        source.write_text("def widget(): return 'new'\n", encoding="utf-8")
        _install_competing_writer(reader, writer, other, monkeypatch)

        operation = getattr(reader, method_name)
        with pytest.raises(
            RuntimeError,
            match="CodeMap generation changed before expected decision session",
        ):
            operation(task, ["src/owner.py"])


def test_post_change_delta_rejects_competing_generation_after_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, other, task = _repo(tmp_path)
    state = tmp_path / ".state"
    artifacts = tmp_path / "artifacts.sqlite3"
    with (
        CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as reader,
        CodeMap(tmp_path, state_dir=state, artifact_db=artifacts) as writer,
    ):
        reader.sync()
        previous = reader.task_evidence(task)
        source.write_text("def widget(): return 'new'\n", encoding="utf-8")
        _install_competing_writer(reader, writer, other, monkeypatch)

        with pytest.raises(
            RuntimeError,
            match="CodeMap generation changed before expected decision session",
        ):
            reader.task_post_change_delta(
                task,
                ["src/owner.py"],
                previous_evidence=previous,
            )
