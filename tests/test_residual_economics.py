from pathlib import Path

from hashmarks.residual_economics import (
    changed_impact_economics_receipt,
    residual_repository_economics_report,
)


def _repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "engine.py").write_text(
        "def normalize_widget(value):\n    return value.strip().lower()\n"
    )
    (root / "tests" / "test_engine.py").write_text(
        "from src.engine import normalize_widget\n"
        "def test_normalize_widget(): assert normalize_widget(' X ') == 'x'\n"
    )


def test_changed_impact_economics_is_measurement_only(tmp_path: Path) -> None:
    _repo(tmp_path)
    result = changed_impact_economics_receipt(
        tmp_path,
        task="normalize_widget implementation test",
        changed_paths=("src/engine.py",),
    )
    assert result["wall_time_ns"] >= 0
    assert result["repository_scan_files"] >= 2
    assert result["authority"] == "repository-intelligence-economics-only"
    assert result["execution_layout"] == "external"
    forbidden = {"workers", "timeout", "retry", "subprocess", "certification"}
    assert forbidden.isdisjoint(result)


def test_residual_report_composes_reuse_candidates_scale_and_impact(tmp_path: Path) -> None:
    _repo(tmp_path)
    result = residual_repository_economics_report(
        tmp_path,
        task="normalize_widget implementation test",
        changed_paths=("src/engine.py",),
        limit=10,
    )
    assert result["scale"]["class"] == "tiny"
    assert set(result["isolated_queries"]) == {
        "find_task", "task_action_map", "task_decision_packet"
    }
    assert result["isolated_query_totals"]["candidate_count"] >= 0
    assert result["related_query_reuse"]["semantic_equivalent"] is True
    assert result["bounded_top_n"]["all_bounds_respected"] is True
    assert result["changed_impact"]["changed_paths"] == ["src/engine.py"]
    assert result["boundary"] == "repository-intelligence-economics-only"
    assert result["execution_authority"] == "external"
    assert result["result_authority"] == "external"
    assert result["certification_authority"] == "external"


def test_residual_report_can_include_qualification_classification(tmp_path: Path) -> None:
    _repo(tmp_path)
    root = Path(__file__).resolve().parents[1]
    result = residual_repository_economics_report(
        tmp_path,
        task="normalize_widget implementation test",
        qualification_root=root,
        limit=5,
    )
    qualification = result["qualification_classification"]
    assert qualification["exact_total_membership_preserved"] is True
    assert qualification["ordinary_correctness_members_avoided"] == (
        qualification["process_sensitive_members"] + qualification["empirical_benchmark_members"]
    )
