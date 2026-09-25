from __future__ import annotations

import json
from pathlib import Path

from hashmarks import CodeMap
from hashmarks.codemap.project_graph import (
    ProjectEdge,
    ProjectGraphEvidence,
    ProjectGraphProvider,
    ProjectNode,
)


class _NativeProjectProvider(ProjectGraphProvider):
    name = "fixture-native-projects"

    def __init__(
        self,
        *,
        include_denied_freshness: bool = False,
    ) -> None:
        super().__init__()
        self.include_denied_freshness = include_denied_freshness

    def detect(self, workspace: Path) -> bool:
        return True

    def collect(self, workspace: Path) -> ProjectGraphEvidence:
        public_metadata: dict[str, object] = {}
        if self.include_denied_freshness:
            public_metadata["freshness_manifests"] = [
                "public/project.meta",
                "private/support.meta",
            ]
        nodes = (
            ProjectNode(
                project_id="fixture:public",
                kind="fixture",
                root="public",
                manifest="public/project.meta",
                producer=self.name,
                metadata=public_metadata,
            ),
            ProjectNode(
                project_id="fixture:private",
                kind="fixture",
                root="private",
                manifest="private/project.meta",
                producer=self.name,
            ),
        )
        edges = (
            ProjectEdge(
                source="fixture:public",
                target="fixture:private",
                kind="dependency",
                confidence="native",
                producer=self.name,
            ),
            ProjectEdge(
                source="fixture:private",
                target="fixture:public",
                kind="dependency",
                confidence="native",
                producer=self.name,
            ),
        )
        return ProjectGraphEvidence(self.name, nodes, edges)


def _deny_private(workspace: Path) -> None:
    (workspace / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "private/**"\nindex = false\n',
        encoding="utf-8",
    )


def test_denied_nested_npm_manifest_is_not_parsed_or_projected(tmp_path: Path) -> None:
    (tmp_path / "packages" / "public").mkdir(parents=True)
    (tmp_path / "packages" / "private").mkdir(parents=True)
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "private": True}),
        encoding="utf-8",
    )
    (tmp_path / "packages" / "public" / "package.json").write_text(
        json.dumps(
            {
                "name": "@hm/public",
                "dependencies": {"@hm/private": "workspace:*"},
            }
        ),
        encoding="utf-8",
    )
    # Deliberately invalid. If the old raw manifest crawler reaches this file,
    # enrichment emits a parse warning containing the denied path.
    (tmp_path / "packages" / "private" / "package.json").write_text(
        "{ this is not json",
        encoding="utf-8",
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "packages/private/**"\nindex = false\n',
        encoding="utf-8",
    )

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        enriched = codemap.enrich_projects(("npm-package-graph",))

    ids = {row["project_id"] for row in enriched["projects"]}
    assert ids == {"npm:root", "npm:@hm/public"}
    assert enriched["edges"] == []
    assert all("packages/private" not in warning for warning in enriched["warnings"])


def test_native_project_nodes_and_edges_are_filtered_by_repository_admission(
    tmp_path: Path,
) -> None:
    (tmp_path / "public").mkdir()
    (tmp_path / "private").mkdir()
    (tmp_path / "public" / "project.meta").write_text("public\n", encoding="utf-8")
    (tmp_path / "private" / "project.meta").write_text(
        "private\n",
        encoding="utf-8",
    )
    _deny_private(tmp_path)

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.project_graph_providers = (_NativeProjectProvider(),)
        enriched = codemap.enrich_projects(("fixture-native-projects",))
        stored_ids = {
            str(row["project_id"])
            for row in codemap.store.project_nodes()
            if row["producer"] == "fixture-native-projects"
        }

    assert {row["project_id"] for row in enriched["projects"]} == {"fixture:public"}
    assert enriched["edges"] == []
    assert stored_ids == {"fixture:public"}
    assert any(
        "filtered project evidence outside repository admission" in warning
        for warning in enriched["warnings"]
    )


def test_denied_support_manifest_prevents_project_evidence_persistence(
    tmp_path: Path,
) -> None:
    (tmp_path / "public").mkdir()
    (tmp_path / "private").mkdir()
    (tmp_path / "public" / "project.meta").write_text("public\n", encoding="utf-8")
    (tmp_path / "private" / "project.meta").write_text(
        "private\n",
        encoding="utf-8",
    )
    (tmp_path / "private" / "support.meta").write_text(
        "support\n",
        encoding="utf-8",
    )
    _deny_private(tmp_path)

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.project_graph_providers = (
            _NativeProjectProvider(include_denied_freshness=True),
        )
        enriched = codemap.enrich_projects(("fixture-native-projects",))
        stored = [
            row
            for row in codemap.store.project_nodes()
            if row["producer"] == "fixture-native-projects"
        ]

    assert enriched["projects"] == []
    assert enriched["edges"] == []
    assert stored == []


def test_project_graph_allow_to_deny_converges_without_denied_residue(
    tmp_path: Path,
) -> None:
    (tmp_path / "packages" / "a").mkdir(parents=True)
    (tmp_path / "packages" / "b").mkdir(parents=True)
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "private": True}),
        encoding="utf-8",
    )
    (tmp_path / "packages" / "a" / "package.json").write_text(
        json.dumps(
            {
                "name": "@hm/a",
                "dependencies": {"@hm/b": "workspace:*"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "packages" / "b" / "package.json").write_text(
        json.dumps({"name": "@hm/b"}),
        encoding="utf-8",
    )

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        before = codemap.enrich_projects(("npm-package-graph",))
        assert {row["project_id"] for row in before["projects"]} == {
            "npm:root",
            "npm:@hm/a",
            "npm:@hm/b",
        }

        (tmp_path / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern = "packages/b/**"\nindex = false\n',
            encoding="utf-8",
        )

        # Query-time policy reconciliation must stop exposing the old graph
        # before enrichment has a chance to rebuild the producer evidence.
        assert codemap.projects()["projects"] == []

        after = codemap.enrich_projects(("npm-package-graph",))

    assert {row["project_id"] for row in after["projects"]} == {
        "npm:root",
        "npm:@hm/a",
    }
    assert all(
        edge["target"] != "npm:@hm/b" and edge["source"] != "npm:@hm/b"
        for edge in after["edges"]
    )



def test_denied_declared_project_links_do_not_activate_or_parse(
    tmp_path: Path,
) -> None:
    (tmp_path / ".hashmarks-project-links.toml").write_text(
        "[[link]\nthis is deliberately invalid toml",
        encoding="utf-8",
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = ".hashmarks-project-links.toml"\nindex = false\n',
        encoding="utf-8",
    )

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        enriched = codemap.enrich_projects(("declared-project-links",))

    assert enriched["projects"] == []
    assert enriched["edges"] == []
    assert all(".hashmarks-project-links.toml" not in warning for warning in enriched["warnings"])


def test_targeted_python_import_root_refresh_ignores_denied_pyproject(
    tmp_path: Path,
) -> None:
    package = tmp_path / "nested" / "src" / "pkg"
    package.mkdir(parents=True)
    (tmp_path / "nested" / "pyproject.toml").write_text(
        '[tool.setuptools.package-dir]\n"" = "src"\n',
        encoding="utf-8",
    )
    (package / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        before = codemap.store.file_row("nested/src/pkg/mod.py")
        assert before is not None
        assert before["module_name"] == "pkg.mod"

        (tmp_path / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern = "nested/pyproject.toml"\nvisibility = "deny"\n',
            encoding="utf-8",
        )
        codemap.sync(["nested/pyproject.toml"])
        after = codemap.store.file_row("nested/src/pkg/mod.py")

    assert after is not None
    assert after["module_name"] == "nested.src.pkg.mod"
