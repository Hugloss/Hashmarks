from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.project_graph import (
    NpmProjectGraphProvider,
    ProjectGraphEvidence,
    ProjectGraphProvider,
    ProjectNode,
)
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


class _SemanticProjectProvider(ProjectGraphProvider):
    def __init__(self, name: str, *, bind_generation: bool) -> None:
        super().__init__(lambda _filename: ())
        self.name = name
        self.bind_generation = bind_generation

    def detect(self, workspace: Path) -> bool:
        return (workspace / "project.meta").is_file()

    def collect(self, workspace: Path) -> ProjectGraphEvidence:
        del workspace
        node = ProjectNode(
            project_id="semantic:root",
            kind="semantic-test",
            root=".",
            manifest="project.meta",
            producer=self.name,
        )
        return ProjectGraphEvidence(self.name, nodes=(node,))


def test_project_provider_uses_only_injected_manifest_discovery(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "package.json", '{"name":"workspace-root"}\n')
    calls: list[str] = []

    def no_visible_manifests(filename: str) -> tuple[Path, ...]:
        calls.append(filename)
        return ()

    provider = NpmProjectGraphProvider(no_visible_manifests)
    assert provider.detect(tmp_path) is False
    assert calls == ["package.json"]

    def visible_manifests(filename: str) -> tuple[Path, ...]:
        assert filename == "package.json"
        return (tmp_path / "package.json",)

    provider = NpmProjectGraphProvider(visible_manifests)
    assert provider.detect(tmp_path) is True
    evidence = provider.collect(tmp_path)
    assert [node.manifest for node in evidence.nodes] == ["package.json"]


@pytest.mark.parametrize(
    ("provider_name", "bind_generation", "expected_fresh"),
    [
        ("go-list", True, False),
        ("renamed-native-provider", True, False),
        ("manifest-only-provider", False, True),
    ],
)
def test_project_provider_name_does_not_decide_generation_freshness(
    tmp_path: Path,
    provider_name: str,
    bind_generation: bool,
    expected_fresh: bool,
) -> None:
    _write(tmp_path, "project.meta", "semantic project\n")
    _write(tmp_path, "source.py", "VALUE = 1\n")
    provider = _SemanticProjectProvider(provider_name, bind_generation=bind_generation)
    with CodeMap(tmp_path) as codemap:
        codemap.project_graph_providers = (provider,)
        codemap.sync()
        codemap.enrich_projects((provider_name,))
        assert codemap._evidence_fresh("project", provider_name) == (True, None)

        _write(tmp_path, "source.py", "VALUE = 2\n")
        codemap.sync(["source.py"])
        fresh, reason = codemap._evidence_fresh("project", provider_name)

    assert fresh is expected_fresh
    if bind_generation:
        assert reason is not None and reason.startswith("CodeMap generation changed")
    else:
        assert reason is None


@pytest.mark.parametrize(
    "provider_name", ["declared-project-links", "renamed-declared-links"]
)
def test_declared_project_capabilities_survive_provider_rename(
    tmp_path: Path, provider_name: str
) -> None:
    _write(tmp_path, "backend/package.json", '{"name":"backend"}\n')
    _write(tmp_path, "frontend/package.json", '{"name":"frontend"}\n')
    _write(tmp_path, "backend/value.ts", "export const value = 1\n")
    _write(tmp_path, "contract.json", '{"v":1}\n')
    links = (
        "[[shared_input]]\n"
        "path='contract.json'\n"
        "projects=['npm:backend','npm:frontend']\n"
        "kind='contract'\n"
    )
    _write(tmp_path, ".hashmarks-project-links.toml", links)

    with CodeMap(tmp_path) as codemap:
        provider = next(
            candidate
            for candidate in codemap.project_graph_providers
            if candidate.supports_shared_input_freshness_rebind
            and candidate.topology_manifest == ".hashmarks-project-links.toml"
        )
        provider.name = provider_name
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph", provider_name))

        _write(tmp_path, "contract.json", '{"v":2}\n')
        shared = codemap.task_change_impact("contract changed", ["contract.json"])

        _write(
            tmp_path,
            ".hashmarks-project-links.toml",
            links + "[[link]]\n"
            "source='npm:frontend'\n"
            "target='npm:backend'\n"
            "kind='consumer'\n",
        )
        topology = codemap.task_change_impact(
            "declared topology changed", [".hashmarks-project-links.toml"]
        )

    assert shared["project_refresh"]["producer"] == provider_name
    assert shared["project_refresh"]["mode"] == "freshness-rebind"
    assert topology["project_refresh"]["producer"] == provider_name
    assert topology["project_refresh"]["mode"] == "topology-recollect"
