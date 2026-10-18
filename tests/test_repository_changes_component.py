"""Changes borrow repository services and own only scoped observation reuse."""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import ParamSpec, TypeVar

import pytest
from contract_assertions import assert_object
from test_repository_index_component import index as index
from test_repository_tasks_component import tasks as tasks
from test_worktree_overlay import _publish_generation_only

from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.repository_changes import RepositoryChanges
from hashmarks.codemap.repository_tasks import RepositoryTasks

_P = ParamSpec("_P")
_R = TypeVar("_R")


def _publishing_after(
    operation: Callable[_P, _R], index: RepositoryIndex
) -> Callable[_P, _R]:
    def publish_after_observation(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        result = operation(*args, **kwargs)
        _publish_generation_only(index)
        return result

    return publish_after_observation


@pytest.mark.parametrize(
    "surface,dependency",
    [("brief", "task_impact"), ("freshness_map", "task_impact"), ("snapshot", "brief")],
)
def test_composed_changes_reject_publication_between_input_and_projection(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    dependency: str,
) -> None:
    (index.workspace / "owner.py").write_text("def calculate_total(): return 1\n")
    index.sync()
    changes = RepositoryChanges(tasks, tasks.repository_relationships)
    monkeypatch.setattr(
        changes, dependency, _publishing_after(getattr(changes, dependency), index)
    )
    with pytest.raises(RuntimeError, match="generation changed"):
        getattr(changes, surface)("Change owner.calculate_total", ["owner.py"])


def test_independent_changes_reuse_detached_snapshots_only_in_the_same_scope(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
) -> None:
    member = index.workspace / "owner.py"
    member.write_text("def calculate_total(): return 1\n")
    index.sync()
    changes = RepositoryChanges(tasks, tasks.repository_relationships)
    query = "Change owner.calculate_total"
    with changes.reads.session(diagnostics=True):
        first = changes.snapshot(query, ["owner.py"])
        first_scope = changes.reads.scope
        original_identity = first["snapshot_identity"]
        assert_object(assert_object(first["paths"])["owner.py"])["revision"] = (
            "invented"
        )
        second = changes.snapshot(query, ["owner.py"])
        assert (
            assert_object(assert_object(second["paths"])["owner.py"])["revision"]
            != "invented"
        )
        assert second["snapshot_identity"] == original_identity
        assert changes.reads.stats()["snapshot_hit"] == 1
    member.write_text("def calculate_total(): return 2\n")
    index.sync(["owner.py"])
    with changes.reads.session():
        after = changes.snapshot(query, ["owner.py"])
        assert changes.reads.scope is not first_scope
    assert after["snapshot_identity"] != original_identity
    assert (
        assert_object(assert_object(after["paths"])["owner.py"])["revision"]
        != assert_object(assert_object(second["paths"])["owner.py"])["revision"]
    )


def test_refresh_brief_observes_only_reported_changes_at_its_published_generation(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
) -> None:
    owner = index.workspace / "owner.py"
    owner.write_text("def calculate_total(): return 1\n")
    unrelated = index.workspace / "unrelated.py"
    unrelated.write_text("def stable(): return 1\n")
    index.sync()
    changes = RepositoryChanges(tasks, tasks.repository_relationships)
    old_unrelated = index.store.file_row("unrelated.py")
    generation = index.store.generation()
    owner.write_text("def calculate_total(): return 2\n")
    unrelated.write_text("def stable(): return 2\n")

    packet = changes.refresh_brief("Change owner.calculate_total", ["owner.py"])

    assert packet["changed_paths"] == ["owner.py"]
    assert packet["scope"] == "changed-paths-only"
    assert packet["consumer_owner"] == "external"
    assert packet["generation_before"] == generation
    assert packet["generation_after"] == index.store.generation()
    assert index.store.generation() > generation
    assert index.store.file_row("unrelated.py") == old_unrelated
    brief = assert_object(packet["decision_brief"])
    assert brief["schema"] == "hashmarks.task-decision-brief.v1"
    assert (
        assert_object(brief["evidence_receipt"])["codemap_generation"]
        == packet["generation_after"]
    )
    assert (
        brief["decision_generation"]
        == tasks.decision_brief("Change owner.calculate_total")["decision_generation"]
    )
    assert assert_object(brief["edit"])["path"] == "owner.py"


def test_refresh_brief_rejects_publication_during_its_task_observation(
    index: RepositoryIndex,
    tasks: RepositoryTasks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = index.workspace / "owner.py"
    owner.write_text("def calculate_total(): return 1\n")
    index.sync()
    changes = RepositoryChanges(tasks, tasks.repository_relationships)
    owner.write_text("def calculate_total(): return 2\n")
    monkeypatch.setattr(
        tasks, "decision_brief", _publishing_after(tasks.decision_brief, index)
    )

    with pytest.raises(RuntimeError, match="generation changed"):
        changes.refresh_brief("Change owner.calculate_total", ["owner.py"])

    assert changes.reads.scope is None
    assert changes.reads.depth == 0


def test_pure_diagnostic_functions_import_without_live_change_services() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.diagnostic_observation import diagnostic_observation_delta, external_diagnostic_observation; from hashmarks.codemap.diagnostic_source_revision import diagnostic_source_revision_evidence; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.repository_changes' not in sys.modules; assert 'hashmarks.codemap.repository_tasks' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_root_has_no_retired_change_or_diagnostic_alias_operations() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "change_impact",
        "task_change_impact",
        "task_post_change_delta",
        "refresh_after_change",
        "refresh_after_change_brief",
        "refresh_after_change_delta",
        "change_intelligence_brief",
        "evidence_freshness_map",
        "repository_intelligence_snapshot",
        "repository_intelligence_delta",
        "external_observation_freshness",
        "diagnostic_source_revision_evidence",
        "external_diagnostic_observation",
        "diagnostic_observation_delta",
        "verification_relationship_evidence",
    ):
        assert not hasattr(CodeMap, name)
