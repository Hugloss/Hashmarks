from __future__ import annotations

import ast
from pathlib import Path

_FRESHNESS_METHODS = {
    "_evidence_key",
    "_manifest_digest",
    "_record_evidence_snapshot",
    "_evidence_snapshot",
    "_evidence_manifest_changes",
    "_declared_project_shared_input",
    "_rebind_declared_project_freshness",
    "_evidence_fresh",
    "_fresh_native_file_edges",
    "_fresh_native_file_edges_from",
    "_fresh_native_definitions",
    "_fresh_native_refs",
    "_fresh_native_edges_from",
    "_fresh_project_nodes",
    "_fresh_project_edges",
    "_fresh_projects_for_path",
    "_fresh_project_dependents",
    "_fresh_project_dependents_with_provenance",
    "_native_evidence_status",
}


def _class_methods(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return {node.name for node in owner.body if isinstance(node, ast.FunctionDef)}


def test_evidence_freshness_has_one_explicit_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    freshness = _class_methods(
        root / "hashmarks/codemap/evidence_freshness.py", "EvidenceFreshnessMixin"
    )
    graph = _class_methods(
        root / "hashmarks/codemap/evidence_graph.py", "EvidenceGraphMixin"
    )

    assert freshness >= _FRESHNESS_METHODS
    assert not (_FRESHNESS_METHODS & graph)
