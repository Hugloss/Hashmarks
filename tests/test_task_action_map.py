from __future__ import annotations

import json
from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def test_task_action_map_routes_source_test_contract_without_changing_ranking(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "benchmarks").mkdir()
    (tmp_path / "src" / "widget.py").write_text("class WidgetEngine:\n    pass\n")
    (tmp_path / "tests" / "test_widget.py").write_text(
        "from src.widget import WidgetEngine\n\ndef test_widget():\n    assert WidgetEngine\n"
    )
    (tmp_path / "INVARIANTS.md").write_text("WidgetEngine contract and policy.\n")
    (tmp_path / "benchmarks" / "corpus.json").write_text(
        json.dumps({"note": "WidgetEngine historical corpus"})
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        canonical = codemap.find_task(
            "WidgetEngine implementation test contract", limit=20
        )
        action = codemap.task_action_map(
            "WidgetEngine implementation test contract", limit=20
        )

    assert [row["path"] for row in action["canonical"]] == [
        hit.path for hit in canonical
    ]
    assert action["ranking_effect"] == "none"
    assert action["discovery_effect"] == "none"
    assert action["edit"]["path"] == "src/widget.py"
    assert action["verify"]["path"] == "tests/test_widget.py"
    assert "edit" not in next(
        row for row in action["canonical"] if row["path"] == "tests/test_widget.py"
    ).get("roles", [])


def test_task_action_map_never_uses_benchmark_corpus_as_edit(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "benchmarks").mkdir()
    (tmp_path / "src" / "resolver.py").write_text(
        "def resolve_manifest():\n    return True\n"
    )
    (tmp_path / "benchmarks" / "manifest.json").write_text(
        json.dumps({"resolve_manifest": "answer-like corpus"})
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "resolve_manifest registered manifest implementation", limit=20
        )

    assert action["edit"]["path"] == "src/resolver.py"
    assert all(
        not str(row["path"]).startswith("benchmarks/")
        for row in [action["edit"]]
        if row
    )


def test_task_action_map_generic_build_word_does_not_force_makefile(
    tmp_path: Path,
) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "adapter.py").write_text("class GoImpactAdapter:\n    pass\n")
    (tmp_path / "Makefile").write_text("build:\n\t@echo build\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "GoImpactAdapter build project impact implementation", limit=20
        )

    assert action["edit"]["path"] == "pkg/adapter.py"


def test_source_tree_test_prefixed_module_remains_editable_source(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/tooling").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/tooling/test_batches.py").write_text(
        "def shard_batch_size():\n    return 8\n"
    )
    (tmp_path / "tests/test_batches.py").write_text(
        "from src.tooling.test_batches import shard_batch_size\n\ndef test_batch_size():\n    assert shard_batch_size() == 8\n"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Change shard_batch_size implementation from 8 to 4", limit=20
        )

    assert action["edit"]["path"] == "src/tooling/test_batches.py"


def test_explicit_test_repair_can_select_test_as_edit_surface(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/lease.py").write_text("class WorkspaceLease:\n    pass\n")
    (tmp_path / "tests/test_lease.py").write_text(
        "from src.lease import WorkspaceLease\n\ndef test_workspace_lease_contract():\n    assert WorkspaceLease\n"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Strengthen the WorkspaceLease regression test to assert the contract",
            limit=20,
        )

    assert action["edit"]["path"] == "tests/test_lease.py"


def test_verify_test_language_does_not_turn_test_into_edit_authority(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "owner.py").write_text(
        "def widget(): return 'old'\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\ndef test_widget(): assert widget() == 'new'\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "change widget implementation and verify widget test", limit=20
        )
    assert action["edit"]["path"] == "src/owner.py"
    assert action["verify"]["path"] == "tests/test_owner.py"


def test_explicit_pytest_shard_tuning_selects_makefile(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/runner.py").write_text("def run_tests():\n    return True\n")
    (tmp_path / "tests/test_runner.py").write_text(
        "def test_runner():\n    assert True\n"
    )
    (tmp_path / "Makefile").write_text("PYTEST_BATCH_SIZE := 8\ntest:\n\tpytest -q\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Change pytest batch shard size from 8 to 4 while keeping the timeout unchanged",
            limit=20,
        )

    assert action["edit"]["path"] == "Makefile"


def test_camelcase_task_anchor_matches_snake_case_owner(tmp_path: Path) -> None:
    (tmp_path / "src/runtime").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/runtime/checkpoint.py").write_text(
        "def candidate_checkpoint_marker():\n    return 'current'\n"
    )
    (tmp_path / "tests/test_checkpoint.py").write_text(
        "from src.runtime.checkpoint import candidate_checkpoint_marker\n\ndef test_marker():\n    assert candidate_checkpoint_marker() == 'current'\n"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix CandidateCheckpoint marker validation in the active implementation",
            limit=20,
        )

    assert action["edit"]["path"] == "src/runtime/checkpoint.py"


def test_close_model_and_runtime_identifier_owners_require_discrimination(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/models").mkdir(parents=True)
    (tmp_path / "src/runtime").mkdir(parents=True)
    (tmp_path / "src/models/workspace_lease.py").write_text(
        "class WorkspaceLease:\n    pass\n"
    )
    (tmp_path / "src/runtime/workspace_lease_runtime.py").write_text(
        "class WorkspaceLeaseRuntime:\n    pass\n"
    )

    task = "Change WorkspaceLease expired behavior before replacement"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)
        packet = codemap.task_decision_packet(task, limit=20)

    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "multiple-identifier-edit-owners"
    assert packet["discrimination"]["needed"] is True


def test_task_action_map_exposes_resolved_ownership_trace_and_authority(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "engine.py").write_text(
        "def apply_widget(value):\n    return value\n"
    )
    (tmp_path / "tests" / "test_engine.py").write_text(
        "from src.engine import apply_widget\ndef test_widget(): assert apply_widget('x') == 'x'\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("apply_widget implementation test", limit=20)

    trace = action["ownership_decision_trace"]
    authority = action["ownership_authority"]
    assert trace["status"] == "resolved"
    assert trace["selected"]["path"] == action["edit"]["path"]
    assert authority["safe_to_edit"] is True
    assert authority["authoritative_edit"] == action["edit"]["path"]


def test_task_action_map_no_edit_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_only.py").write_text("def test_widget():\n    pass\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("widget test verification", limit=20)

    assert action["edit"] is None
    assert action["ownership_decision_trace"]["status"] == "unresolved"
    assert action["ownership_authority"]["safe_to_edit"] is False
    assert action["ownership_authority"]["authoritative_edit"] is None


def test_task_action_map_reuses_primary_structural_owner_for_ambiguity(
    tmp_path: Path, monkeypatch
) -> None:
    """One decision must not rebuild the same ownership graph for ambiguity evidence."""
    from hashmarks.codemap.ownership_graph import OwnershipGraphMixin

    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/widget.py").write_text("class WidgetEngine:\n    pass\n")
    (tmp_path / "tests/test_widget.py").write_text(
        "from src.widget import WidgetEngine\n\ndef test_widget():\n    assert WidgetEngine\n"
    )
    (tmp_path / "INVARIANTS.md").write_text("WidgetEngine contract and policy.\n")

    calls: list[str] = []
    original = OwnershipGraphMixin._structural_owner_candidate

    def counted(self, start_path: str, *, max_depth: int = 2, task: str = ""):
        calls.append(start_path)
        return original(self, start_path, max_depth=max_depth, task=task)

    monkeypatch.setattr(OwnershipGraphMixin, "_structural_owner_candidate", counted)

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "WidgetEngine implementation test contract", limit=20
        )

    assert action["edit"]["path"] == "src/widget.py"
    assert calls.count("tests/test_widget.py") == 1
