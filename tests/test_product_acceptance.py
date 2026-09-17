from __future__ import annotations

from pathlib import Path

from hashmarks.product_acceptance import (
    executable_acceptance_suite,
    observability_capabilities,
    scale_class_contract,
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


def test_scale_class_contract_is_explicit_and_monotonic() -> None:
    assert scale_class_contract(files=10, source_bytes=1_000)["class"] == "tiny"
    assert scale_class_contract(files=5_000, source_bytes=50_000_000)["class"] == "small"
    assert scale_class_contract(files=50_000, source_bytes=500_000_000)["class"] == "medium"
    assert scale_class_contract(files=500_000, source_bytes=5_000_000_000)["class"] == "large"


def test_observability_capabilities_are_bounded() -> None:
    result = observability_capabilities()
    assert result["values"]["executable_acceptance_suite"] is True
    assert result["values"]["symbolic_identity_nomination"] is True
    assert result["values"]["ownership_graph_economics_receipt"] is True
    assert result["values"]["producer_implementation_identity"] is True
    assert result["values"]["same_version_implementation_drift_detection"] is True
    assert result["values"]["qualification_classification_identity"] is True
    assert result["values"]["qualification_coverage_validation"] is True
    assert result["values"]["qualification_classification_economics"] is True
    assert result["values"]["native_qualification_handoff"] is True
    assert result["values"]["graph_nodes_traversed_exact"] is False
    assert result["values"]["sort_operations_exact"] is False
    assert result["boundary"] == "repository-intelligence-only"


def test_executable_acceptance_suite_passes_small_repository(tmp_path: Path) -> None:
    _repo(tmp_path)
    result = executable_acceptance_suite(
        tmp_path,
        task="normalize_widget implementation test",
        limit=20,
    )

    assert result["passed"] is True
    assert result["checks"]["identity_present"] is True
    assert result["checks"]["ownership_fail_closed"] is True
    assert result["checks"]["selection_envelope_valid"] is True
    assert result["checks"]["downstream_boundary_external"] is True
    assert result["checks"]["symbolic_nomination_non_authoritative"] is True
    assert result["checks"]["deterministic_repeated_query"] is True
    assert result["checks"]["cold_warm_semantic_equivalence"] is True
    assert result["boundary"] == "repository-intelligence-only"
