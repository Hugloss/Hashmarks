from __future__ import annotations

import json
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.decision_session import DecisionRefreshRequired
from hashmarks.repository_retry import is_transient_repository_race


def _repository(root: Path) -> Path:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    source = root / "src" / "feature.py"
    source.write_text("def flare041(value):\n    return value + 1\n")
    (root / "tests" / "test_feature.py").write_text(
        "from src.feature import flare041\n"
        "def test_flare041(): assert flare041(1) == 2\n"
    )
    return source


@pytest.mark.parametrize("operation", ["evidence", "task_impact"])
def test_staged_observation_reconciles_source_drift_before_restarting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    source = _repository(tmp_path)
    with CodeMap(
        tmp_path, state_dir=tmp_path / ".state", artifact_db=tmp_path / "artifacts.db"
    ) as repository:
        repository.index.sync()
        generation = repository.store.generation()
        original = repository.source.ensure_current
        changed = False

        def edit_before_read(path: str) -> None:
            nonlocal changed
            if path == "src/feature.py" and not changed:
                changed = True
                source.write_text("def flare041(value):\n    return value + 999\n")
            original(path)

        monkeypatch.setattr(repository.source, "ensure_current", edit_before_read)
        task = "change flare041 behavior and verify it"
        if operation == "evidence":
            result = repository.tasks.evidence(task)
        else:
            result = repository.changes.task_impact(task, ["src/feature.py"])

        assert changed, "the operation must encounter the controlled source edit"
        assert repository.reads.depth == 0
        assert repository.store.generation() > generation
        assert not repository.index.needs_reconcile("src/feature.py")
        assert "return value + 1\\n" not in json.dumps(result)


def test_nested_observation_leaves_refresh_to_the_outer_read_owner(
    tmp_path: Path,
) -> None:
    source = _repository(tmp_path)
    with CodeMap(
        tmp_path, state_dir=tmp_path / ".state", artifact_db=tmp_path / "artifacts.db"
    ) as repository:
        repository.index.sync()
        with repository.reads.session():
            source.write_text("def flare041(value):\n    return value + 999\n")
            with pytest.raises(DecisionRefreshRequired):
                repository.tasks.evidence("change flare041 behavior")
            assert repository.reads.depth == 1


def test_repeated_source_drift_stops_after_one_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _repository(tmp_path)
    with CodeMap(
        tmp_path, state_dir=tmp_path / ".state", artifact_db=tmp_path / "artifacts.db"
    ) as repository:
        repository.index.sync()
        original = repository.source.ensure_current
        edits = 0

        def edit_before_read(path: str) -> None:
            nonlocal edits
            if path == "src/feature.py":
                edits += 1
                source.write_text(f"def flare041(value): return value + {edits + 1}\n")
            original(path)

        monkeypatch.setattr(repository.source, "ensure_current", edit_before_read)
        with pytest.raises(
            RuntimeError, match="path remained stale after refresh"
        ) as failure:
            repository.tasks.evidence("change flare041 behavior and verify it")
        assert edits == 2
        assert repository.reads.depth == 0
        assert is_transient_repository_race(failure.value)


@pytest.mark.parametrize(
    "operation", ["task_delta", "refresh", "refresh_brief", "refresh_delta"]
)
def test_post_change_recomputation_preserves_the_original_before_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    source = _repository(tmp_path)
    with CodeMap(
        tmp_path, state_dir=tmp_path / ".state", artifact_db=tmp_path / "artifacts.db"
    ) as repository:
        repository.index.sync()
        task = "change flare041 behavior and verify it"
        previous = repository.tasks.evidence(task)
        before = repository.store.generation()
        row = repository.store.file_row("src/feature.py")
        assert row is not None
        before_revision = row["file_digest"]
        source.write_text("def flare041(value):\n    return value + 2\n")
        original = repository.source.ensure_current
        changed = False

        def edit_before_read(path: str) -> None:
            nonlocal changed
            if path == "src/feature.py" and not changed:
                changed = True
                source.write_text("def flare041(value):\n    return value + 999\n")
            original(path)

        monkeypatch.setattr(repository.source, "ensure_current", edit_before_read)
        if operation == "task_delta":
            result = assert_object(
                repository.changes.task_delta(
                    task, ["src/feature.py"], previous_evidence=previous
                )
            )
        else:
            result = assert_object(
                getattr(repository.changes, operation)(task, ["src/feature.py"])
            )
        assert changed
        assert repository.reads.depth == 0
        assert not repository.index.needs_reconcile("src/feature.py")
        generation_key = (
            "generation" if operation == "refresh_delta" else "generation_after"
        )
        assert result[generation_key] == repository.store.generation()
        if operation != "refresh_delta":
            assert result["generation_before"] == before
        if operation == "task_delta":
            changes = assert_records(result["path_changes"])
            assert changes[0]["state"] == "changed"
            assert changes[0]["revision"] != before_revision
        elif operation == "refresh":
            assert assert_object(result["sync"])["indexed"] == 1
