"""Bound real Maven/uv captures to manifests replaced in an admitted repository."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from native_evidence_support import (
    assert_projection,
    dependency_capture,
    input_revisions,
    materialize_dependency,
    semantic_dependency_fields,
)

from hashmarks.adapters import maven_dependency_observation
from hashmarks.codemap import CodeMap
from hashmarks.evidence_presentation import FORMATS, present_repository_evidence


def reactor_capture(root: Path, source: Path, paths: list[str]) -> Any:
    contexts = ("alpha", "beta")
    return maven_dependency_observation(
        trees={
            context: (source / "captures" / context / "tree.json").read_bytes()
            for context in contexts
        },
        inventories={
            context: (source / "captures" / context / "list.txt").read_bytes()
            for context in contexts
        },
        complete_tree_contexts=contexts,
        complete_inventory_contexts=contexts,
        repository_inputs=input_revisions(root, paths),
    )


def _maven_capture(root: Path, source: Path, paths: list[str], scenario: str) -> Any:
    if scenario == "multi-module":
        return reactor_capture(root, source, paths)
    return dependency_capture("maven", source, input_revisions(root, paths))


@pytest.mark.parametrize("scenario,count", [("bom-upgrade", 17), ("multi-module", 3)])
def test_maven_manifest_replacement_stale_bindings_and_downstream_transitions(
    tmp_path: Path, scenario: str, count: int, native_dependency_corpus: Path
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    source = native_dependency_corpus / "maven" / scenario / "before"
    original = _maven_capture(
        root, source, materialize_dependency(root, source), scenario
    )
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        before: Any = cm.dependency_resolution_evidence(original)
        after_source = native_dependency_corpus / "maven" / scenario / "after"
        materialize_dependency(root, after_source)
        cm.sync()
        stale: Any = cm.dependency_resolution_evidence(original)
        mismatches = {
            row["path"]
            for row in stale["repository_inputs"]
            if row["source_equivalence"] == "mismatch"
        }
        assert mismatches == (
            {"alpha/pom.xml"} if scenario == "multi-module" else {"pom.xml"}
        )
        raw = _maven_capture(
            root,
            after_source,
            sorted(path.relative_to(root).as_posix() for path in root.rglob("pom.xml")),
            scenario,
        )
        after: Any = cm.dependency_resolution_evidence(raw)
        delta: Any = cm.dependency_resolution_delta(before, after)
        graphs: Any = cm.dependency_resolution_queries(
            after,
            [
                {
                    "operation": "dependencies",
                    "context": row["context"],
                    "node_id": row["node_id"],
                }
                for row in after["roots"]
            ],
        )
        bounded: Any = cm.dependency_resolution_queries(
            after,
            [
                {
                    "operation": "dependencies",
                    "context": after["roots"][0]["context"],
                    "node_id": after["roots"][0]["node_id"],
                    "max_results": 1,
                }
            ],
        )
    assert len(delta["component_selection_transitions"]) == count
    assert delta["change_axes"]["repository_inputs"] == "changed"
    assert all(
        row["source_equivalence"] == "proven" for row in after["repository_inputs"]
    )
    assert all(result["completeness"] == "complete" for result in graphs["results"])
    assert bounded["results"][0]["negative_evidence"] == "not-applicable"
    if scenario == "multi-module":
        assert (
            next(
                row
                for row in after["selections"]
                if row["component_id"] == "com.google.guava:guava"
            )["version"]
            == "33.4.8-jre"
        )
        assert all(
            row["contexts"] == ["alpha", "beta"]
            for row in after["selections"]
            if row["component_id"] == "com.google.guava:guava"
        )
        assert {row["path"] for row in after["repository_inputs"]} == {
            "pom.xml",
            "alpha/pom.xml",
            "beta/pom.xml",
        }
    else:
        assert delta["components_added"] == delta["components_removed"] == []
    assert_projection(delta, "dependency_codemap", "compare")
    for format in FORMATS[1:]:
        projection: Any = present_repository_evidence(delta, format=format)
        group = next(
            group for group in projection["groups"] if group["family"] == "dependency"
        )
        assert group["findings"][0]["kind"] == "change_axes"
        assert group["findings"][1]["kind"] == "component_selection_transitions"
        assert (
            group["findings"][1]["details"]
            == delta["component_selection_transitions"][0]
        )
    with CodeMap(root, state_dir=state) as cm:
        assert semantic_dependency_fields(
            cm.dependency_resolution_evidence(raw)
        ) == semantic_dependency_fields(after)


def test_uv_workspace_changes_observe_selection_and_preserve_unknown_module_ownership(
    tmp_path: Path, native_dependency_corpus: Path
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    previous: Any = None
    old_raw: Any = None
    for name, version, member, orphan in [
        ("before", "1.0.0", "lib", True),
        ("version", "2.0.0", "lib", True),
        ("moved", "2.0.0", "core", True),
        ("removed", "2.0.0", "core", False),
    ]:
        source = native_dependency_corpus / "uv" / "workspace" / name
        paths = materialize_dependency(root, source)
        assert (root / "packages/lib/pyproject.toml").exists() == (member == "lib")
        assert (root / "packages/orphan/pyproject.toml").exists() == orphan
        raw = dependency_capture("uv", source, input_revisions(root, paths))
        with CodeMap(root, state_dir=state) as cm:
            cm.sync()
            current: Any = cm.dependency_resolution_evidence(raw)
            library = next(
                row
                for row in current["selections"]
                if row["component_id"] == "workspace-lib"
            )
            assert library["version"] == version
            assert library["source"] == '{"editable":"packages/' + member + '"}'
            assert current["module_ownership"] == []
            assert all(
                row["source_equivalence"] == "proven"
                for row in current["repository_inputs"]
            )
            assert (
                any(
                    row["component_id"] == "workspace-orphan"
                    for row in current["components"]
                )
                == orphan
            )
            if previous is not None:
                reused: Any = cm.dependency_resolution_evidence(old_raw)
                assert any(
                    row["source_equivalence"] != "proven"
                    for row in reused["repository_inputs"]
                )
                delta: Any = cm.dependency_resolution_delta(previous, current)
                assert delta["change_axes"]["repository_inputs"] == "changed"
                if name == "version":
                    assert len(delta["component_selection_transitions"]) == 1
                if name == "removed":
                    assert delta["components_removed"] == ["workspace-orphan"]
                assert_projection(delta, "dependency_codemap", "compare")
        with CodeMap(root, state_dir=tmp_path / ("fresh-" + name)) as cm:
            cm.sync()
            assert semantic_dependency_fields(
                cm.dependency_resolution_evidence(raw)
            ) == semantic_dependency_fields(current)
        previous, old_raw = current, raw
    source = native_dependency_corpus / "uv" / "workspace" / "rootless"
    paths = materialize_dependency(root, source)
    with pytest.raises(ValueError, match="does not identify a project root"):
        dependency_capture("uv", source, input_revisions(root, paths))
