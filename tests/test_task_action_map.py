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


def test_unique_exact_identifier_outweighs_close_nonexact_runtime_name(
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

    assert action["edit"]["path"] == "src/models/workspace_lease.py"
    assert action["owner_basis"] in {"exact-symbol", "unique-exact-symbol"}
    assert action["ambiguity"]["ambiguous"] is False
    assert action["ownership_authority"]["owner_resolved"] is True


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
    assert authority["owner_resolved"] is True
    assert authority["resolved_owner"] == action["edit"]["path"]


def test_task_action_map_no_edit_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_only.py").write_text("def test_widget():\n    pass\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("widget test verification", limit=20)

    assert action["edit"] is None
    assert action["ownership_decision_trace"]["status"] == "unresolved"
    assert action["ownership_authority"]["owner_resolved"] is False
    assert action["ownership_authority"]["resolved_owner"] is None


def test_task_action_map_skips_structural_owner_after_exact_resolution(
    tmp_path: Path, monkeypatch
) -> None:
    """A stronger exact owner must terminate before weaker structural traversal."""
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
    assert action["owner_basis"] in {"exact-symbol", "unique-exact-symbol"}
    assert calls == []


def test_qualified_module_function_target_wins_over_lexically_stronger_sibling(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/repository_understanding_policy.py").write_text(
        "from src._repository_understanding_policy_primitives import prepare\n\n"
        "def evaluate(value):\n"
        "    return prepare(value)\n",
        encoding="utf-8",
    )
    (tmp_path / "src/_repository_understanding_policy_primitives.py").write_text(
        "def prepare(value):\n"
        "    return value\n\n"
        "def refactor_repository_understanding_policy_evaluate_without_changing_behavior():\n"
        "    return True\n",
        encoding="utf-8",
    )

    task = "Refactor repository_understanding_policy.evaluate without changing behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)

    assert action["edit"]["path"] == "src/repository_understanding_policy.py"
    assert action["edit"]["name"] == "evaluate"
    assert action["edit"]["exact_identifier_projection"] is True


def test_qualified_module_function_target_stays_ambiguous_across_duplicate_modules(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/a").mkdir(parents=True)
    (tmp_path / "src/b").mkdir(parents=True)
    for package in ("a", "b"):
        (tmp_path / f"src/{package}/repository_understanding_policy.py").write_text(
            "def evaluate(value):\n    return value\n",
            encoding="utf-8",
        )

    task = "Refactor repository_understanding_policy.evaluate without changing behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)

    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "multiple-exact-identifier-edit-owners"
    assert action["ownership_authority"]["owner_resolved"] is False


def test_qualified_module_function_does_not_match_wrong_module(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/policy.py").write_text(
        "def evaluate(value):\n    return value\n",
        encoding="utf-8",
    )

    task = "Refactor missing_policy.evaluate without changing behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        context = codemap._task_action_map_context(task, 20)
        candidates = codemap._task_action_exact_identifier_edit_candidates(
            task, context.rows, context.failed
        )

    assert candidates == []


def test_qualified_target_recovers_from_index_when_canonical_limit_excludes_source(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src/test_batches.py").write_text(
        "from src.test_batch_receipts import receipt_identity\n\n"
        "def main() -> int:\n"
        "    return receipt_identity()\n",
        encoding="utf-8",
    )
    (tmp_path / "src/test_batch_receipts.py").write_text(
        "def receipt_identity() -> int:\n    return 0\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_test_batches.py").write_text(
        "from src import test_batches\n\n"
        "def test_batches_main_behavior():\n"
        "    assert test_batches.main() == 0\n",
        encoding="utf-8",
    )

    task = "Refactor test_batches.main without changing behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=1, per_role=1)

    assert [row["path"] for row in action["canonical"]] == [
        "tests/test_test_batches.py"
    ]
    assert action["edit"]["path"] == "src/test_batches.py"
    assert action["edit"]["name"] == "main"
    assert action["edit"]["exact_identifier_projection"] is True
    assert action["edit"]["qualified_identifier_index_projection"] is True
    assert action["ambiguity"]["ambiguous"] is False


def test_structural_owner_projection_preserves_unique_qualified_symbol_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src/capability.py").write_text(
        "class UnrelatedError(RuntimeError):\n"
        "    pass\n\n"
        "def target(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_capability.py").write_text(
        "from src import capability\n\n"
        "def test_target():\n"
        "    assert capability.target('x') == 'x'\n",
        encoding="utf-8",
    )

    task = "Refactor capability.target without changing behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)
        evidence = codemap.task_evidence(task, limit=20)

    assert action["edit"]["path"] == "src/capability.py"
    assert action["edit"]["name"] == "target"
    assert action["edit"]["qualname"] == "target"
    assert action["edit"]["exact_identifier_projection"] is True
    ownership = evidence["ownership"]
    assert ownership["candidate"]["path"] == "src/capability.py"
    assert ownership["source_evidence"]["symbol"] == "target"
    assert ownership["source_evidence"]["content"].startswith("def target(value):")
    assert "UnrelatedError" not in ownership["source_evidence"]["content"]


def test_qualified_identifier_does_not_inherit_plain_same_name_ambiguity(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/bootstrap.py").write_text(
        "def _require_regular(path):\n    return path\n",
        encoding="utf-8",
    )
    (tmp_path / "src/qualification.py").write_text(
        "def _require_regular(path):\n    return path\n",
        encoding="utf-8",
    )

    task = "Refactor bootstrap._require_regular without changing behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)

    assert action["edit"]["path"] == "src/bootstrap.py"
    assert action["edit"]["name"] == "_require_regular"
    assert action["edit"]["exact_identifier_projection"] is True
    assert action["ambiguity"]["ambiguous"] is False
    assert action["ownership_authority"]["owner_resolved"] is True


def test_exact_identifier_authority_is_invariant_across_presentation_limits(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src/target.py").write_text(
        "def globally_unique_owner(value):\n    return value\n",
        encoding="utf-8",
    )
    for index in range(12):
        (tmp_path / "tests" / f"test_noise_{index}.py").write_text(
            f"def test_globally_unique_owner_noise_{index}():\n    assert True\n",
            encoding="utf-8",
        )

    task = "Refactor target.globally_unique_owner without changing behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        results = [
            codemap.task_action_map(task, limit=limit, per_role=1)
            for limit in (1, 10, 100)
        ]

    assert {row["edit"]["path"] for row in results} == {"src/target.py"}
    assert {row["owner_basis"] for row in results} == {"qualified-symbol"}
    assert {row["ownership_authority"]["resolved_owner"] for row in results} == {
        "src/target.py"
    }
    assert {
        row["ownership_authority"]["authority_proof_identity"] for row in results
    } == {results[0]["ownership_authority"]["authority_proof_identity"]}
    assert all(
        row["ownership_authority"]["proof_scope"] == "repository-global-symbol-identity"
        for row in results
    )
    assert all(row["ownership_authority"]["proof_scope_complete"] for row in results)


def test_duplicate_exact_identifier_stays_ambiguous_across_presentation_limits(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/a").mkdir(parents=True)
    (tmp_path / "src/b").mkdir(parents=True)
    for package in ("a", "b"):
        (tmp_path / f"src/{package}/policy.py").write_text(
            "def evaluate(value):\n    return value\n",
            encoding="utf-8",
        )

    task = "Refactor evaluate without changing behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        results = [
            codemap.task_action_map(task, limit=limit, per_role=1)
            for limit in (1, 10, 100)
        ]

    assert all(row["ambiguity"]["ambiguous"] for row in results)
    assert all(
        row["ambiguity"]["reason"] == "multiple-exact-identifier-edit-owners"
        for row in results
    )
    assert all(not row["ownership_authority"]["owner_resolved"] for row in results)
    assert all(row["ownership_authority"]["resolved_owner"] is None for row in results)


def test_literal_path_authority_is_invariant_across_presentation_limits(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/owner.py").write_text(
        "def owner(value):\n    return value\n",
        encoding="utf-8",
    )
    task = "Change src/owner.py owner behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        results = [
            codemap.task_action_map(task, limit=limit, per_role=1)
            for limit in (1, 10, 100)
        ]

    assert {row["edit"]["path"] for row in results} == {"src/owner.py"}
    assert {row["owner_basis"] for row in results} == {"literal-path"}
    assert {
        row["ownership_authority"]["authority_proof_identity"] for row in results
    } == {results[0]["ownership_authority"]["authority_proof_identity"]}
    assert all(
        row["ownership_authority"]["proof_scope"] == "repository-global-path-identity"
        for row in results
    )


def test_authority_proof_identity_ignores_per_role_presentation_bounds(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    for name in ("a", "b", "c", "d"):
        (tmp_path / "src" / f"{name}.py").write_text(
            "def duplicate_owner(value):\n    return value\n", encoding="utf-8"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        results = [
            codemap.task_action_map("Fix duplicate_owner", limit=20, per_role=per_role)
            for per_role in (1, 2, 4)
        ]

    proof_ids = {
        row["ownership_authority"]["authority_proof_identity"] for row in results
    }
    presentation_ids = {
        row["authority_non_interference"]["presentation_identity"] for row in results
    }
    assert len(proof_ids) == 1
    assert len(presentation_ids) == 3
    assert all(row["ambiguity"]["ambiguous"] for row in results)
    assert all(not row["ownership_authority"]["owner_resolved"] for row in results)
    assert [len(row["ambiguity"]["alternatives"]) for row in results] == [1, 2, 4]
    assert {
        row["authority_non_interference"]["total_candidates"] for row in results
    } == {4}
    assert [
        row["authority_non_interference"]["returned_candidates"] for row in results
    ] == [1, 2, 4]
    assert [
        row["authority_non_interference"]["complete"] for row in results
    ] == [False, False, True]


def test_resolved_authority_proof_identity_ignores_per_role_bounds(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/owner.py").write_text(
        "def unique_owner(value):\n    return value\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        results = [
            codemap.task_action_map(
                "Refactor owner.unique_owner without changing behavior",
                limit=20,
                per_role=per_role,
            )
            for per_role in (1, 2, 4)
        ]

    assert {row["ownership_authority"]["resolved_owner"] for row in results} == {
        "src/owner.py"
    }
    assert len(
        {
            row["ownership_authority"]["authority_proof_identity"]
            for row in results
        }
    ) == 1
    assert len(
        {
            row["authority_non_interference"]["presentation_identity"]
            for row in results
        }
    ) == 3
