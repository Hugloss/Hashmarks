from __future__ import annotations

from pathlib import Path

from hashmarks.repository_diagnostics import (
    bounded_top_n_candidate_profile,
    related_query_reuse_receipt,
    repository_query_runtime_diagnostics,
    shared_python_ast_propagation_audit,
)


def _repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "engine.py").write_text(
        "def normalize_widget(value):\n"
        "    return value.strip().lower()\n"
    )
    (root / "tests" / "test_engine.py").write_text(
        "from src.engine import normalize_widget\n"
        "def test_normalize_widget():\n"
        "    assert normalize_widget(' X ') == 'x'\n"
    )


def test_shared_ast_propagation_audit_passes_current_repository() -> None:
    root = Path(__file__).resolve().parents[1]
    result = shared_python_ast_propagation_audit(root)

    assert result["valid"] is True
    assert result["violations"] == []
    assert result["cache_authority"] == "hashmarks.python_ast_cache.read_python_ast"


def test_shared_ast_propagation_audit_detects_direct_file_backed_parse(
    tmp_path: Path,
) -> None:
    package = tmp_path / "hashmarks"
    package.mkdir()
    (package / "bad.py").write_text(
        "import ast\n"
        "from pathlib import Path\n"
        "def bad(path: Path):\n"
        "    source = path.read_text()\n"
        "    return ast.parse(source)\n"
    )
    (package / "python_ast_cache.py").write_text(
        "import ast\n"
        "def allowed(source):\n"
        "    return ast.parse(source)\n"
    )

    result = shared_python_ast_propagation_audit(tmp_path)

    assert result["valid"] is False
    assert len(result["violations"]) == 1
    assert result["violations"][0]["path"].endswith("hashmarks/bad.py")
    assert result["violations"][0]["reason"] == (
        "file-backed-ast-parse-bypasses-shared-cache"
    )


def test_repository_query_runtime_diagnostics_reports_exact_available_metrics(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    result = repository_query_runtime_diagnostics(
        tmp_path,
        query="task_action_map",
        task="normalize_widget implementation test",
        limit=20,
    )

    assert result["schema"] == "hashmarks.repository-query-runtime-diagnostics.v1"
    assert result["repository_scan"]["files"] >= 2
    assert result["repository_scan"]["source_bytes"] > 0
    assert result["query_work"]["wall_time_ns"] > 0
    assert result["query_work"]["candidate_count"] > 0
    assert result["query_work"]["evidence_files"] > 0
    assert result["query_work"]["evidence_bytes"] > 0
    assert result["query_work"]["ast_parses"] >= 0
    assert result["query_work"]["ast_cache_hits"] >= 0
    assert result["query_work"]["graph_nodes_traversed"] is None
    assert result["availability"]["graph_nodes_traversed"] is False
    assert result["boundary"] == "repository-intelligence-only"


def test_related_query_reuse_is_generation_bound_and_semantically_stable(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    result = related_query_reuse_receipt(
        tmp_path,
        task="normalize_widget implementation test",
        limit=20,
    )

    assert result["repository_generation_bound"] is True
    assert result["reuse_observed"] is True
    assert result["stage_deltas"]["task_action_map"]["task_result_hit"] >= 1
    assert result["stage_deltas"]["task_decision_packet"]["task_action_hit"] >= 1
    assert result["boundary"] == "repository-intelligence-only"


def test_bounded_top_n_profile_preserves_prefix_semantics(tmp_path: Path) -> None:
    _repo(tmp_path)
    for index in range(30):
        (tmp_path / "src" / f"related_{index}.py").write_text(
            f"def normalize_widget_{index}(value):\n"
            "    return value.strip().lower()\n"
        )

    result = bounded_top_n_candidate_profile(
        tmp_path,
        task="normalize_widget implementation",
        limits=(3, 7, 12),
    )

    assert result["all_bounds_respected"] is True
    assert result["prefix_semantics_equivalent"] is True
    assert [row["limit"] for row in result["profiles"]] == [3, 7, 12]
    assert all(
        row["result_count"] <= row["limit"]
        for row in result["profiles"]
    )
    assert result["availability"]["sort_operations"] is False


def test_ownership_graph_economics_uses_authoritative_projection(tmp_path: Path) -> None:
    from hashmarks.repository_diagnostics import ownership_graph_economics_receipt

    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "helper.py").write_text(
        "def normalize_widget(value):\n"
        "    return value.strip().lower()\n"
    )
    (tmp_path / "tests" / "test_helper.py").write_text(
        "from src.helper import normalize_widget\n"
        "def test_normalize_widget():\n"
        "    assert normalize_widget(' X ') == 'x'\n"
    )

    result = ownership_graph_economics_receipt(
        tmp_path,
        task="normalize_widget implementation",
        start_path="tests/test_helper.py",
        max_depth=2,
    )

    assert result["graph_nodes_traversed"] >= 1
    assert result["graph_edges_observed"] >= 0
    assert result["availability"]["graph_nodes_traversed"] is True
    assert result["measurement_basis"] == "authoritative-ownership-graph-projection"
    assert result["boundary"] == "repository-intelligence-only"


def test_low_level_operation_counter_decision_is_explicit() -> None:
    from hashmarks.repository_diagnostics import low_level_operation_counter_decision

    result = low_level_operation_counter_decision()
    assert result["decision"] == "do-not-instrument"
    assert result["metrics"]["sort_operations"] is False
    assert result["metrics"]["set_constructions"] is False
    assert result["metrics"]["string_normalizations"] is False


def test_find_task_prefix_is_stable_through_agent_surface(tmp_path: Path) -> None:
    """Prove prefix stability without rebuilding the entire Hashmarks repository.

    Prefix stability is a ranking/limit invariant. Repository scale is not part of
    that contract, so the release-correctness proof uses a bounded representative
    repository instead of coupling every full-suite run to a cold real-repo sync.
    """
    from hashmarks.codemap import CodeMap

    root = tmp_path / "repo"
    root.mkdir()
    for index in range(30):
        (root / f"consumer_{index:02d}.py").write_text(
            f"def consumer_{index:02d}():\n"
            f"    # consumer conformance producer identity qualified shared input {index}\n"
            f"    return {index}\n",
            encoding="utf-8",
        )
    state = tmp_path / "state"
    task = "consumer conformance producer identity qualified shared input"
    with CodeMap(root, state_dir=state, artifact_db=state / "artifacts.sqlite3") as codemap:
        codemap.sync()
        five = [hit.path for hit in codemap.find_task(task, limit=5)]
        ten = [hit.path for hit in codemap.find_task(task, limit=10)]
        twenty = [hit.path for hit in codemap.find_task(task, limit=20)]
    assert five == twenty[:5]
    assert ten == twenty[:10]
