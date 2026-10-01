from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_domains import (
    RepositoryDomain,
    classify_repository_path,
)


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _owner_corpus(root: Path, directory: str) -> None:
    _write(root, "src/__init__.py", "")
    _write(root, "src/owner.py", "def handle_orbit(): return 'src'\n")
    _write(root, f"{directory}/__init__.py", "")
    _write(root, f"{directory}/owner.py", "def handle_orbit(): return 'other'\n")
    _write(
        root,
        "tests/test_src.py",
        "from src.owner import handle_orbit\ndef test_src(): assert handle_orbit() == 'src'\n",
    )
    _write(
        root,
        f"tests/test_{directory}.py",
        f"from {directory}.owner import handle_orbit\n"
        "def test_other(): assert handle_orbit() == 'other'\n",
    )


@pytest.mark.parametrize("directory", ["archive", "legacy", "deprecated", "vendor"])
def test_directory_spelling_does_not_decide_owner_authority(
    tmp_path: Path, directory: str
) -> None:
    observations = []
    for name in (directory, "history"):
        root = tmp_path / name
        root.mkdir()
        _owner_corpus(root, name)
        with CodeMap(root) as codemap:
            codemap.sync()
            assert {"src/owner.py", f"{name}/owner.py"} <= set(codemap.store.paths())
            vague = codemap.task_action_map("Fix handle_orbit behavior", limit=20)
            explicit = codemap.task_action_map(
                f"Fix {name}/owner.py handle_orbit behavior", limit=20
            )
            graph = codemap.ownership_relation_graph(
                "Fix handle_orbit behavior", f"tests/test_{name}.py", max_depth=3
            )
        assert vague["ambiguity"]["ambiguous"] is True
        assert vague["ownership_authority"]["owner_resolved"] is False
        assert explicit["edit"]["path"] == f"{name}/owner.py"
        assert explicit["ambiguity"]["ambiguous"] is False
        assert graph["selected"] == f"{name}/owner.py"
        observations.append(
            (
                vague["ambiguity"]["reason"],
                explicit["owner_basis"],
                graph["completeness"],
            )
        )
    assert observations[0] == observations[1]


@pytest.mark.parametrize("brand,neutral", [("fastapi", "falconx"), ("goon", "glow")])
def test_project_names_have_no_generic_query_expansion(
    tmp_path: Path, brand: str, neutral: str
) -> None:
    views = []
    paths = []
    for name in (brand, neutral):
        root = tmp_path / name
        root.mkdir()
        _write(root, f"app/{name}.py", f"def {name}_handler(): return 1\n")
        _write(root, "README.md", f"{name} handler reference\n")
        with CodeMap(root) as codemap:
            codemap.sync()
            task = f"Fix {name} handler"
            views.append(codemap.task_query_views(task))
            paths.append(tuple(hit.path for hit in codemap.find_task(task, limit=5)))
    assert {
        key: value.replace(brand, neutral) for key, value in views[0].items()
    } == views[1]
    assert tuple(path.replace(brand, neutral) for path in paths[0]) == paths[1]


def test_goon_filename_does_not_grant_plan_domain() -> None:
    for path in ("goon.yml", "workflow.yml", "templates/goons/work.yml"):
        assert RepositoryDomain.PLAN not in classify_repository_path(path)
        assert RepositoryDomain.CONFIG in classify_repository_path(path)
    assert RepositoryDomain.PLAN in classify_repository_path("plan.yml")
    assert RepositoryDomain.PLAN in classify_repository_path("templates/plans/work.yml")


@pytest.mark.parametrize("directory", ["legacy", "history"])
def test_qualified_reexport_outweighs_unrelated_duplicate(
    tmp_path: Path, directory: str
) -> None:
    _write(tmp_path, "src/__init__.py", "")
    _write(tmp_path, "src/case/__init__.py", "from .engine import handle_orbit\n")
    _write(tmp_path, "src/case/engine.py", "def handle_orbit(): return 'live'\n")
    _write(tmp_path, f"{directory}/owner.py", "def handle_orbit(): return 'other'\n")
    _write(
        tmp_path,
        "tests/test_live.py",
        "from src.case import handle_orbit\n"
        "def test_live(): assert handle_orbit() == 'live'\n",
    )
    _write(
        tmp_path,
        f"tests/test_{directory}.py",
        f"from {directory}.owner import handle_orbit\n"
        "def test_other(): assert handle_orbit() == 'other'\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("Fix src.case.handle_orbit", limit=20)
    assert action["edit"]["path"] == "src/case/engine.py"
    assert action["owner_basis"] == "exact-import-owner"
    assert action["ambiguity"]["ambiguous"] is False


def test_newly_admitted_directory_is_discovered_on_reopen_and_bounded_sync(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "ordinary.py", "def ordinary(): return 1\n")
    _write(tmp_path, ".fastidentity/source.py", "def newly_visible(): return 2\n")
    state_dir = tmp_path / ".state"
    with CodeMap(tmp_path, state_dir=state_dir) as codemap:
        codemap.sync()
        codemap.store.delete_paths([".fastidentity/source.py"])
        codemap.store.set_meta("analysis_scope_conformance_identity", "old-scope")
    with CodeMap(tmp_path, state_dir=state_dir) as codemap:
        assert {hit.path for hit in codemap.find("newly_visible")} == {
            ".fastidentity/source.py"
        }
        codemap.store.delete_paths([".fastidentity/source.py"])
        codemap.store.set_meta("analysis_scope_conformance_identity", "old-scope")
        codemap.sync(["ordinary.py"])
        assert ".fastidentity/source.py" in codemap.store.paths()


def test_configured_fastidentity_state_is_excluded_from_codemap(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/owner.py", "def visible_owner(): return 1\n")
    with CodeMap(tmp_path, state_dir=tmp_path / ".fastidentity") as codemap:
        codemap.sync()
        assert "src/owner.py" in codemap.store.paths()
        assert not any(
            path.startswith(".fastidentity/") for path in codemap.store.paths()
        )
