from __future__ import annotations

import ast
from pathlib import Path


_IMPORT_RESOLUTION_METHODS = {
    "_python_reexport_targets",
    "_python_export_binding",
    "_python_star_export_authority",
    "_resolve_import_owner_evidence",
    "_resolve_import_owner_paths",
    "_python_import_module_candidates",
    "_resolve_python_import_paths",
    "_python_import_identity_ambiguous",
    "_resolve_js_import_paths",
    "_resolve_go_import_paths",
    "_resolve_import_paths",
}


def _class_methods(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    return {node.name for node in owner.body if isinstance(node, ast.FunctionDef)}


def test_import_resolution_has_one_explicit_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    resolver = _class_methods(root / "hashmarks/codemap/import_resolution.py", "ImportResolutionMixin")
    graph = _class_methods(root / "hashmarks/codemap/evidence_graph.py", "EvidenceGraphMixin")
    ownership = _class_methods(root / "hashmarks/codemap/ownership_graph.py", "OwnershipGraphMixin")

    assert _IMPORT_RESOLUTION_METHODS <= resolver
    assert not (_IMPORT_RESOLUTION_METHODS & graph)
    assert not (_IMPORT_RESOLUTION_METHODS & ownership)
