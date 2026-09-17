from __future__ import annotations

import shutil
from pathlib import Path

from benchmarks.codemap_surface_calibration import _lexical_rows, apply_variant, evaluate
from hashmarks.codemap.engine import CodeMap


def test_benchmark_membership_variant_is_copy_only_and_preserves_source_owner(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "docs").mkdir()
    (workspace / "src" / "lease.py").write_text(
        "class WorkspaceLeaseAuthority:\n    def reassign(self):\n        return 'ok'\n",
        encoding="utf-8",
    )
    (workspace / "docs" / "guide.md").write_text(
        "\n".join(f"WorkspaceLeaseAuthority operational guide line {i}" for i in range(50)) + "\n",
        encoding="utf-8",
    )
    full_state = tmp_path / "full"
    artifacts = tmp_path / "artifacts.sqlite3"
    corpus = [{
        "id": "lease-owner",
        "task": "Change WorkspaceLeaseAuthority reassign behavior.",
        "expected_edit": ["src/lease.py"],
    }]
    with CodeMap(workspace, state_dir=full_state, artifact_db=artifacts) as codemap:
        codemap.sync()
        full = evaluate(codemap, corpus)
    full_rows = _lexical_rows(full_state / "codemap.sqlite3")

    variant_state = tmp_path / "membership"
    shutil.copytree(full_state, variant_state)
    changed = apply_variant(variant_state / "codemap.sqlite3", "membership", surfaces={"docs"})
    with CodeMap(workspace, state_dir=variant_state, artifact_db=artifacts) as codemap:
        membership = evaluate(codemap, corpus)

    assert changed["changed_paths"] == 1
    assert _lexical_rows(variant_state / "codemap.sqlite3") < full_rows
    assert full["exact_edit"] == membership["exact_edit"] == 1
    assert full["false_safe"] == membership["false_safe"] == 0


def test_benchmark_scores_expected_discrimination_for_underspecified_tasks(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.py").write_text("def observer():\n    return 1\n", encoding="utf-8")
    (workspace / "b.py").write_text("def observer_state():\n    return 2\n", encoding="utf-8")
    with CodeMap(workspace, state_dir=tmp_path / "state", artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        result = evaluate(codemap, [{"id": "ambiguous", "task": "Change observer behavior.", "expected_discrimination": True}])
    assert result["discrimination_graded"] == 1
    assert result["discrimination_correct"] in {0, 1}
    assert result["false_safe"] == int(result["discrimination_correct"] == 0)


def test_decision_packet_contract_rejects_wrong_shape(tmp_path: Path) -> None:
    from hashmarks.codemap.decision_contract import DecisionPacketContract

    try:
        DecisionPacketContract.parse({"schema": "hashmarks.task-decision-packet.v2", "action": {"edit": {"path": "a.py"}}})
    except ValueError as exc:
        assert "task" in str(exc)
    else:
        raise AssertionError("malformed decision packet must fail closed")


def test_calibration_manifest_is_deterministic_and_groups_tasks() -> None:
    from benchmarks.codemap_surface_calibration import build_manifest, corpus_group

    corpus = [{"id": f"t{i}", "task": f"Change thing {i}."} for i in range(17)]
    first = build_manifest(corpus, repository_identity="repo-1", generation=7, variant="full", group_size=8)
    second = build_manifest(corpus, repository_identity="repo-1", generation=7, variant="full", group_size=8)
    assert first == second
    assert [len(group) for group in first["groups"]] == [8, 8, 1]
    assert [row["id"] for row in corpus_group(corpus, first, 2)] == ["t16"]


def test_decision_session_reuses_evidence_primitives_without_caching_final_packet(tmp_path: Path) -> None:
    workspace = tmp_path / "repo-session"
    workspace.mkdir()
    (workspace / "owner.py").write_text("class LeaseOwner:\n    def issue(self): return 1\n", encoding="utf-8")
    (workspace / "test_owner.py").write_text("from owner import LeaseOwner\ndef test_issue(): assert LeaseOwner().issue() == 1\n", encoding="utf-8")
    with CodeMap(workspace, state_dir=tmp_path / "state-session", artifact_db=tmp_path / "artifacts-session.sqlite3") as codemap:
        codemap.sync()
        with codemap.decision_session():
            first = codemap.task_decision_packet("Change LeaseOwner issue behavior.")
            second = codemap.task_decision_packet("Add regression coverage for LeaseOwner issue behavior.")
            stats = codemap.decision_session_stats()
        assert first["task"] != second["task"]
        assert first["identity"]["codemap_generation"] == second["identity"]["codemap_generation"]
        assert sum(stats.values()) > 0
        assert first["decision_metrics"]["session_active"] is True


def test_calibration_aggregate_requires_every_matching_group() -> None:
    from benchmarks.codemap_surface_calibration import aggregate_group_results, build_manifest

    corpus = [{"id": f"t{i}", "task": f"Task {i}."} for i in range(9)]
    manifest = build_manifest(corpus, repository_identity="repo", generation=3, variant="full", group_size=4)
    groups = [
        {"manifest_sha256": manifest["manifest_sha256"], "group_index": 0, "complete": True, "decision": {"tasks": 4}},
        {"manifest_sha256": manifest["manifest_sha256"], "group_index": 2, "complete": True, "decision": {"tasks": 1}},
    ]
    partial = aggregate_group_results(manifest, groups)
    assert partial["complete"] is False
    assert partial["missing_groups"] == [1]
    assert partial["tasks_completed"] == 5


def test_decision_scale_ladder_reports_per_task_cost(tmp_path: Path) -> None:
    from benchmarks.codemap_surface_calibration import decision_scale_ladder

    workspace = tmp_path / "repo-scale"
    workspace.mkdir()
    for i in range(12):
        (workspace / f"owner_{i}.py").write_text(f"def unique_owner_{i}():\n    return {i}\n", encoding="utf-8")
    corpus = [{"id": f"t{i}", "task": f"Change unique_owner_{i} behavior.", "expected_edit": [f"owner_{i}.py"]} for i in range(12)]
    with CodeMap(workspace, state_dir=tmp_path / "state-scale", artifact_db=tmp_path / "artifacts-scale.sqlite3") as codemap:
        codemap.sync()
        ladder = decision_scale_ladder(codemap, corpus, sizes=(1, 8, 16))
    assert [row["tasks"] for row in ladder["rows"]] == [1, 8]
    assert all(row["seconds_per_task"] >= 0 for row in ladder["rows"])


def test_scale_point_aggregates_completed_group_evidence() -> None:
    from benchmarks.codemap_surface_calibration import build_manifest, scale_point_from_group_results

    corpus = [{"id": f"t{i}", "task": f"Task {i}."} for i in range(16)]
    manifest = build_manifest(corpus, repository_identity="repo", generation=4, variant="full", group_size=8)
    groups = [
        {"manifest_sha256": manifest["manifest_sha256"], "group_index": 0, "complete": True, "decision": {"tasks": 8, "false_safe": 0, "decision_seconds": {"total": 5.0, "p95": 1.0}}},
        {"manifest_sha256": manifest["manifest_sha256"], "group_index": 1, "complete": True, "decision": {"tasks": 8, "false_safe": 1, "decision_seconds": {"total": 7.0, "p95": 2.0}}},
    ]
    point = scale_point_from_group_results(manifest, groups, 16)
    assert point["total_seconds"] == 12.0
    assert point["seconds_per_task"] == 0.75
    assert point["false_safe"] == 1


def test_weak_generic_contract_anchor_fails_closed_but_identifier_anchor_resolves(tmp_path: Path) -> None:
    workspace = tmp_path / "repo-weak-anchor"
    workspace.mkdir()
    (workspace / "scout_observer_contract.py").write_text(
        "def check_scout_observer_contract():\n    return True\n",
        encoding="utf-8",
    )
    (workspace / "game_tape_observability.py").write_text(
        "def project_observability_receipt():\n    return True\n",
        encoding="utf-8",
    )
    for index in range(9):
        (workspace / f"observer_note_{index}.md").write_text(
            "observer behavior public contract preserving existing\n", encoding="utf-8"
        )
    with CodeMap(workspace, state_dir=tmp_path / "state-weak-anchor", artifact_db=tmp_path / "artifacts-weak-anchor.sqlite3") as codemap:
        codemap.sync()
        generic = codemap.task_action_map("Change the observer behavior while preserving its existing public contract.")
        anchored = codemap.task_action_map("Change the project_observability_receipt behavior while preserving its existing public contract.")
    assert generic["ambiguity"]["ambiguous"] is True
    assert generic["ambiguity"]["reason"] == "weak-task-anchor"
    assert anchored["edit"]["path"] == "game_tape_observability.py"
    assert anchored["ambiguity"]["ambiguous"] is False


def test_repository_domain_classification_is_pure_memoized_evidence() -> None:
    from hashmarks.codemap.repository_domains import classify_repository_path

    classify_repository_path.cache_clear()
    first = classify_repository_path("backend/src/pkg/test_runtime.py")
    before = classify_repository_path.cache_info()
    second = classify_repository_path("backend/src/pkg/test_runtime.py")
    after = classify_repository_path.cache_info()
    assert first == second
    assert after.hits == before.hits + 1


def test_resumable_calibration_reuses_exact_task_receipts_after_interruption(tmp_path: Path) -> None:
    from benchmarks.codemap_surface_calibration import build_manifest, evaluate_resumable

    workspace = tmp_path / "repo-resume"
    workspace.mkdir()
    for index in range(3):
        (workspace / f"owner_{index}.py").write_text(
            f"def unique_resume_owner_{index}():\n    return {index}\n", encoding="utf-8"
        )
    corpus = [
        {"id": f"t{index}", "task": f"Change unique_resume_owner_{index} behavior.", "expected_edit": [f"owner_{index}.py"]}
        for index in range(3)
    ]
    state = tmp_path / "state-resume"
    artifacts = tmp_path / "artifacts-resume.sqlite3"
    receipts = tmp_path / "receipts"
    with CodeMap(workspace, state_dir=state, artifact_db=artifacts) as codemap:
        codemap.sync()
        manifest = build_manifest(corpus, repository_identity=codemap._repository_packet_identity(), generation=codemap.store.generation(), variant="full", group_size=3)
        partial = evaluate_resumable(codemap, corpus[:2], receipt_dir=receipts, manifest_sha256=manifest["manifest_sha256"], group_index=0, expected_task_ids=manifest["groups"][0])
    assert partial["durability"]["created"] == 2
    assert partial["durability"]["reused"] == 0
    assert partial["durability"]["complete"] is False

    with CodeMap(workspace, state_dir=state, artifact_db=artifacts) as codemap:
        resumed = evaluate_resumable(codemap, corpus, receipt_dir=receipts, manifest_sha256=manifest["manifest_sha256"], group_index=0, expected_task_ids=manifest["groups"][0])
    assert resumed["durability"]["created"] == 1
    assert resumed["durability"]["reused"] == 2
    assert resumed["durability"]["performance_comparable"] is False
    assert resumed["tasks"] == 3
    assert resumed["exact_edit"] == 3


def test_resumable_calibration_rejects_receipt_identity_drift(tmp_path: Path) -> None:
    import json
    from benchmarks.codemap_surface_calibration import build_manifest, evaluate_resumable

    workspace = tmp_path / "repo-receipt-drift"
    workspace.mkdir()
    (workspace / "owner.py").write_text("def receipt_owner():\n    return 1\n", encoding="utf-8")
    corpus = [{"id": "t0", "task": "Change receipt_owner behavior.", "expected_edit": ["owner.py"]}]
    state = tmp_path / "state-drift"
    artifacts = tmp_path / "artifacts-drift.sqlite3"
    receipts = tmp_path / "receipts-drift"
    with CodeMap(workspace, state_dir=state, artifact_db=artifacts) as codemap:
        codemap.sync()
        manifest = build_manifest(corpus, repository_identity=codemap._repository_packet_identity(), generation=codemap.store.generation(), variant="full", group_size=1)
        evaluate_resumable(codemap, corpus, receipt_dir=receipts, manifest_sha256=manifest["manifest_sha256"], group_index=0)
    receipt = next(receipts.glob("*.json"))
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["identity"]["task_sha256"] = "drift"
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    with CodeMap(workspace, state_dir=state, artifact_db=artifacts) as codemap:
        try:
            evaluate_resumable(codemap, corpus, receipt_dir=receipts, manifest_sha256=manifest["manifest_sha256"], group_index=0)
        except ValueError as exc:
            assert "receipt identity mismatch" in str(exc)
        else:
            raise AssertionError("identity-drifted task receipt must fail closed")
