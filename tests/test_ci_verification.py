"""Contract checks for the developer-only CI selector and its fail-closed scope."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "ci_verification.py"
SPEC = importlib.util.spec_from_file_location("ci_verification", MODULE)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _write(root: Path, path: str, content: str) -> None:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content, encoding="utf-8")


@pytest.fixture
def repository(tmp_path: Path) -> tuple[Path, str]:
    _git(tmp_path, "init", "-q")
    _write(tmp_path, "hashmarks/__init__.py", "")
    _write(tmp_path, "hashmarks/worker.py", "def compute():\n    return 1\n")
    _write(
        tmp_path,
        "tests/test_worker.py",
        "from hashmarks.worker import compute\n\n"
        "def test_worker():\n    assert compute() == 1\n",
    )
    _write(tmp_path, "docs/README.md", "Original\n")
    _git(tmp_path, "add", ".")
    _git(
        tmp_path,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "init",
    )
    return tmp_path, _git(tmp_path, "rev-parse", "HEAD")


def _change(root: Path, path: str, content: str) -> None:
    _write(root, path, content)
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "change",
    )


def _unreachable(*args: object) -> None:
    raise AssertionError("CodeMap should not run for this change")


def test_docs_only_runs_baseline_without_scanning(repository: tuple[Path, str]) -> None:
    root, base = repository
    _change(root, "docs/README.md", "Updated\n")
    plan = module.select(root, base, links=_unreachable)
    assert plan["mode"] == "focused"
    assert plan["pytest_paths"] == sorted(
        set(module.BASELINE) | set(module.DOCUMENTATION_CHECKS)
    )
    assert plan["base_sha"] == base
    assert plan["plan_identity"].startswith("sha256:")


def test_changed_test_is_always_selected(repository: tuple[Path, str]) -> None:
    root, base = repository
    _change(root, "tests/test_worker.py", "def test_worker():\n    assert 1 == 1\n")
    plan = module.select(root, base, links=_unreachable)
    assert plan["mode"] == "focused"
    assert "tests/test_worker.py" in plan["pytest_paths"]


def test_source_uses_proven_hashmarks_links(repository: tuple[Path, str]) -> None:
    root, base = repository
    _change(root, "hashmarks/worker.py", "def compute():\n    return 2\n")
    plan = module.select(
        root, base, links=lambda _root, paths: {paths[0]: ("tests/test_worker.py",)}
    )
    assert plan["mode"] == "focused"
    assert "tests/test_worker.py" in plan["pytest_paths"]


def test_actual_codemap_maps_changed_python_to_real_test(
    repository: tuple[Path, str],
) -> None:
    """Exercise the real Hashmarks selection adapter, not an injected fake."""
    root, base = repository
    _change(root, "hashmarks/worker.py", "def compute():\n    return 2\n")
    plan = module.select(root, base)
    if plan["mode"] != "focused":
        from hashmarks.codemap import CodeMap

        with CodeMap(root) as observer:
            observer.index.sync()
            graph = observer.tasks.verification_ownership_graph(
                "Change hashmarks/worker.py", limit=16, candidate_limit=16
            )
            nomination = observer.verification.nomination("tests/test_worker.py")
        pytest.fail(
            json.dumps(
                {
                    "reasons": plan["reasons"],
                    "edit_candidates": graph.get("edit_candidates"),
                    "stale": graph.get("stale"),
                    "qualification": graph.get("verification_qualification"),
                    "owners": [
                        {
                            "path": row.get("path"),
                            "covers": row.get("covers_edit_candidates"),
                            "evidence": row.get("coverage_evidence"),
                        }
                        for row in graph.get("verification_owners", [])
                    ],
                    "nomination_available": nomination.get("available"),
                    "runner": nomination.get("runner_evidence"),
                },
                sort_keys=True,
                default=str,
            )
        )
    assert "tests/test_worker.py" in plan["pytest_paths"]


def test_mixed_documentation_and_test_edits_keep_documentation_proof(
    repository: tuple[Path, str],
) -> None:
    root, base = repository
    _write(root, "docs/README.md", "Updated\n")
    _change(root, "tests/test_worker.py", "def test_worker():\n    assert True\n")
    plan = module.select(root, base, links=_unreachable)
    assert plan["mode"] == "focused"
    assert set(module.DOCUMENTATION_CHECKS).issubset(plan["pytest_paths"])
    assert "tests/test_worker.py" in plan["pytest_paths"]


def test_unknown_source_relevance_runs_entire_suite(
    repository: tuple[Path, str],
) -> None:
    root, base = repository
    _change(root, "hashmarks/worker.py", "def compute():\n    return 3\n")
    plan = module.select(root, base, links=lambda _root, _paths: None)
    assert plan["mode"] == "full"
    assert plan["pytest_paths"] == ["tests"]
    assert "unproven-verification-membership" in plan["reasons"]


def test_empty_source_nominations_are_not_focused(repository: tuple[Path, str]) -> None:
    root, base = repository
    _change(root, "hashmarks/worker.py", "def compute():\n    return 4\n")
    plan = module.select(root, base, links=lambda _root, paths: {paths[0]: ()})
    assert plan["mode"] == "full"
    assert plan["pytest_paths"] == ["tests"]


def test_shared_policy_requires_full_suite(repository: tuple[Path, str]) -> None:
    root, base = repository
    _change(root, "pyproject.toml", "[project]\nname = 'sample'\n")
    plan = module.select(root, base, links=_unreachable)
    assert plan["mode"] == "full"
    assert "broad-authority:pyproject.toml" in plan["reasons"]


@pytest.mark.parametrize(
    "path",
    [
        "hashmarks/codemap/verification_ownership.py",
        "hashmarks/codemap/evidence_verification.py",
        "hashmarks/codemap/engine.py",
        "scripts/release_contract.py",
        "scripts/host_qualification/mcp_gate.py",
    ],
)
def test_verification_and_release_internals_force_full_suite(
    repository: tuple[Path, str], path: str
) -> None:
    root, base = repository
    _change(root, path, "def changed():\n    pass\n")
    plan = module.select(root, base, links=_unreachable)
    assert plan["mode"] == "full"
    assert plan["pytest_paths"] == ["tests"]
    assert f"broad-authority:{path}" in plan["reasons"]


def test_rename_requires_full_suite(repository: tuple[Path, str]) -> None:
    root, base = repository
    _git(root, "mv", "hashmarks/worker.py", "hashmarks/renamed.py")
    _git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "rename",
    )
    plan = module.select(root, base, links=_unreachable)
    assert plan["mode"] == "full"
    assert "unusual-git-change" in plan["reasons"]


def test_uncommitted_local_edits_are_seen(repository: tuple[Path, str]) -> None:
    root, base = repository
    _write(root, "tests/test_worker.py", "def test_worker():\n    assert 2 == 2\n")
    plan = module.select(root, base, worktree=True, links=_unreachable)
    assert plan["mode"] == "focused"
    assert "tests/test_worker.py" in plan["pytest_paths"]
    with pytest.raises(ValueError, match="clean"):
        module.select(root, base, links=_unreachable)


def test_incomplete_graph_cannot_authorize_reduced_suite() -> None:
    graph: dict[str, Any] = {
        "stale": False,
        "edit_candidates": ["hashmarks/worker.py"],
        "verification_qualification": {
            "completeness": "complete",
            "truncation": "complete",
            "negative_evidence_admissible": True,
            "search_bound_reasons": [],
        },
        "verification_owners": [
            {
                "path": "tests/test_worker.py",
                "coverage_evidence": "direct-reference",
                "covers_edit_candidates": ["hashmarks/worker.py"],
            }
        ],
    }
    assert module._qualified_links(graph, "hashmarks/worker.py") == (
        "tests/test_worker.py",
    )
    graph["verification_qualification"]["completeness"] = "incomplete"
    assert module._qualified_links(graph, "hashmarks/worker.py") is None
    graph["verification_qualification"]["completeness"] = "complete"
    graph["verification_qualification"]["search_bound_reasons"] = ["bounded-search"]
    assert module._qualified_links(graph, "hashmarks/worker.py") is None


def test_hosted_cli_emits_nul_delimited_safe_paths(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, base = repository
    _change(root, "docs/README.md", "changed\n")
    output = tmp_path.parent / "ci-plan.json"
    result = subprocess.run(
        [
            sys.executable,
            str(MODULE),
            "--root",
            str(root),
            "--base",
            base,
            "--output",
            str(output),
        ],
        capture_output=True,
        check=True,
    )
    paths = [row.decode() for row in result.stdout.split(b"\0") if row]
    assert paths == sorted(set(module.BASELINE) | set(module.DOCUMENTATION_CHECKS))
    assert json.loads(output.read_text())["pytest_paths"] == paths
