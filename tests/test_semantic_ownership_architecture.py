from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODEMAP = ROOT / "hashmarks" / "codemap"


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_repository_member_observation_has_one_semantic_owner() -> None:
    definitions: list[str] = []
    for path in sorted(CODEMAP.glob("*.py")):
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.FunctionDef) and node.name == "_repository_member_observation":
                definitions.append(f"{path.name}:{node.lineno}")
    assert len(definitions) == 1
    assert definitions[0].startswith("repository_delta.py:")


def test_evidence_binding_projection_does_not_read_repository_bytes_directly() -> None:
    path = CODEMAP / "repository_evidence_bindings.py"
    violations: list[str] = []
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in {"read_bytes", "read_text"}:
            violations.append(f"{path.name}:{node.lineno}:{node.func.attr}")
    assert violations == [], (
        "repository evidence bindings must consume canonical member observation "
        "rather than create another repository byte-read authority: "
        + ", ".join(violations)
    )


def test_canonical_freshness_vocabulary_is_owned_once() -> None:
    owner = (CODEMAP / "evidence_freshness.py").read_text(encoding="utf-8")
    state_doc = (ROOT / "docs" / "reference" / "STATE_AND_SEMANTIC_OWNERS.md").read_text(
        encoding="utf-8"
    )
    assert 'FRESHNESS_STATES = frozenset({"current", "stale", "unknown"})' in owner
    assert "current" in state_doc and "stale" in state_doc and "unknown" in state_doc

    freshness_map = (CODEMAP / "freshness_map.py").read_text(encoding="utf-8")
    context = (ROOT / "hashmarks" / "evidence_context.py").read_text(encoding="utf-8")
    assert '"invalidated"' not in freshness_map
    assert 'frozenset({"unknown", "current", "stale"})' in context


def test_binding_modules_are_projection_owners_not_second_change_authorities() -> None:
    bindings = (CODEMAP / "repository_evidence_bindings.py").read_text(
        encoding="utf-8"
    )
    delta = (CODEMAP / "repository_evidence_binding_delta.py").read_text(
        encoding="utf-8"
    )
    coverage = (CODEMAP / "repository_evidence_coverage.py").read_text(
        encoding="utf-8"
    )
    assert "_repository_member_observation(" in bindings
    assert "binding_definition_identity" in bindings
    assert "binding_observation_identity" in bindings
    assert "declared_dependencies" in delta
    assert "semantic_dependencies" not in delta
    assert '"source": "repository-observer"' in coverage
    assert '"source": "caller-asserted"' in coverage
