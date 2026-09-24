from __future__ import annotations

import json
from pathlib import Path

import pytest

from hashmarks.adapters import maven_dependency_observation
from hashmarks.codemap.engine import CodeMap


def _tree(*, child_parent: bool = True) -> bytes:
    child = {
        "groupId": "example.libs",
        "artifactId": "shared",
        "version": "2.0",
        "type": "jar",
        "scope": "compile",
        "classifier": "",
        "optional": "false",
    }
    root = {
        "groupId": "example.app",
        "artifactId": "app",
        "version": "1.0",
        "type": "jar",
        "scope": "",
        "classifier": "",
        "optional": "false",
        "children": [child] if child_parent else [],
    }
    return json.dumps(root).encode()


def _inventory() -> bytes:
    return b"""The following files have been resolved:
   example.libs:shared:jar:2.0:compile -- module shared.module
   example.extra:inventory-only:jar:3.0:compile -- module shared.module (auto)
"""


def test_maven_adapter_preserves_inventory_topology_and_module_ambiguity(
    tmp_path: Path,
) -> None:
    raw = maven_dependency_observation(
        trees={"compile": _tree()},
        inventories={"compile": _inventory()},
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)

    inventory = {row["node_id"] for row in observation["inventory"]}
    graph = {
        endpoint
        for row in observation["relationships"]
        for endpoint in (row["source"], row["target"])
    }
    assert "example.extra:inventory-only:jar:3.0" in inventory
    assert "example.extra:inventory-only:jar:3.0" not in graph
    ownership = observation["module_ownership"][0]
    assert ownership["module"] == "shared.module"
    assert ownership["state"] == "resolved-ambiguous"
    assert ownership["owners"] == [
        "example.extra:inventory-only:jar:3.0",
        "example.libs:shared:jar:2.0",
    ]


def test_maven_adapter_keeps_context_separate_from_effective_scope(
    tmp_path: Path,
) -> None:
    runtime_tree = json.loads(_tree())
    runtime_tree["children"][0]["scope"] = "compile"
    raw = maven_dependency_observation(
        trees={"runtime": json.dumps(runtime_tree).encode()},
        inventories={},
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)

    edge = observation["relationships"][0]
    assert edge["context"] == "runtime"
    assert edge["effective_scope"] == "compile"


def test_maven_adapter_preserves_classifier_as_selection_identity(
    tmp_path: Path,
) -> None:
    inventory = b"""The following files have been resolved:
   io.netty:native:jar:linux-x86_64:1.0:runtime -- module native.linux [auto]
   io.netty:native:jar:osx-x86_64:1.0:runtime -- module native.osx [auto]
"""
    raw = maven_dependency_observation(
        trees={},
        inventories={"runtime": inventory},
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)

    assert [row["node_id"] for row in observation["selections"]] == [
        "io.netty:native:jar:linux-x86_64:1.0",
        "io.netty:native:jar:osx-x86_64:1.0",
    ]
    assert {row["component_id"] for row in observation["selections"]} == {
        "io.netty:native"
    }


def test_maven_adapter_is_execution_free(monkeypatch) -> None:
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError("Maven adapter must not execute package tooling")

    monkeypatch.setattr(subprocess, "run", forbidden)
    raw = maven_dependency_observation(
        trees={"compile": _tree()},
        inventories={"compile": _inventory()},
    )

    assert raw["producer"]["kind"] == "maven-dependency-artifacts"
    assert raw["contexts"] == ["compile"]


def test_maven_adapter_relationship_change_is_not_selection_change(
    tmp_path: Path,
) -> None:
    before_raw = maven_dependency_observation(
        trees={"compile": _tree()},
        inventories={"compile": _inventory()},
    )
    changed_tree = json.loads(_tree())
    child = changed_tree["children"].pop()
    changed_tree["children"] = [
        {
            "groupId": "example.bridge",
            "artifactId": "bridge",
            "version": "1.0",
            "type": "jar",
            "scope": "compile",
            "classifier": "",
            "optional": "false",
            "children": [child],
        }
    ]
    after_raw = maven_dependency_observation(
        trees={"compile": json.dumps(changed_tree).encode()},
        inventories={"compile": _inventory()},
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(before_raw)
        after = codemap.dependency_resolution_evidence(after_raw)
        delta = codemap.dependency_resolution_delta(before, after)

    assert "example.libs:shared:jar:2.0" not in delta["selections_added"]
    assert "example.libs:shared:jar:2.0" not in delta["selections_removed"]
    assert delta["relationships_added"]
    assert delta["relationships_removed"]


def test_maven_adapter_preserves_inventory_without_module_metadata(
    tmp_path: Path,
) -> None:
    inventory = b"""The following files have been resolved:
   example.scala:scala-module_2.13:jar:2.0:test
   example.root:parent:pom:1.0:compile
   example.libs:owned:jar:3.0:test -- module example.owned
"""
    raw = maven_dependency_observation(
        trees={},
        inventories={"test": inventory},
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)

    assert [row["node_id"] for row in observation["inventory"]] == [
        "example.libs:owned:jar:3.0",
        "example.root:parent:pom:1.0",
        "example.scala:scala-module_2.13:jar:2.0",
    ]
    assert [row["module"] for row in observation["module_ownership"]] == [
        "example.owned"
    ]


def test_maven_adapter_does_not_overclaim_module_ownership_completeness(
    tmp_path: Path,
) -> None:
    inventory = b"""The following files have been resolved:
   example.libs:owned:jar:3.0:test -- module example.owned
   example.libs:unannotated:jar:4.0:test
"""
    raw = maven_dependency_observation(
        trees={},
        inventories={"test": inventory},
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)

    coverage = {
        row["kind"]: row for row in observation["coverage"] if row["context"] == "test"
    }
    assert coverage["resolved-inventory"]["completeness"] == "complete"
    assert coverage["module-ownership"]["completeness"] == "incomplete"
    negative = {
        row["kind"]: row
        for row in observation["negative_evidence"]
        if row["context"] == "test"
    }
    assert negative["resolved-inventory"]["state"] == "admissible-within-declared-scope"
    assert negative["module-ownership"]["state"] == "not-admissible"
    assert observation["module_ownership"][0]["completeness"] == "incomplete"


def test_maven_pom_inventory_does_not_make_module_coverage_incomplete(
    tmp_path: Path,
) -> None:
    inventory = b"""The following files have been resolved:
   example.root:parent:pom:1.0:compile
   example.libs:owned:jar:3.0:compile -- module example.owned
"""
    raw = maven_dependency_observation(
        trees={},
        inventories={"compile": inventory},
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)

    coverage = {
        row["kind"]: row
        for row in observation["coverage"]
        if row["context"] == "compile"
    }
    assert coverage["resolved-inventory"]["completeness"] == "complete"
    assert coverage["module-ownership"]["completeness"] == "complete"
    assert observation["module_ownership"][0]["completeness"] == "complete"


def test_maven_duplicate_inventory_rows_do_not_overclaim_module_completeness(
    tmp_path: Path,
) -> None:
    inventory = b"""The following files have been resolved:
   example.libs:owned:jar:3.0:test -- module example.owned
   example.libs:owned:jar:3.0:test -- module example.owned
"""
    raw = maven_dependency_observation(trees={}, inventories={"test": inventory})

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)

    coverage = {
        row["kind"]: row for row in observation["coverage"] if row["context"] == "test"
    }
    assert len(observation["inventory"]) == 1
    assert coverage["module-ownership"]["completeness"] == "complete"


def test_maven_duplicate_module_annotation_cannot_hide_unannotated_inventory(
    tmp_path: Path,
) -> None:
    inventory = b"""The following files have been resolved:
   example.libs:owned:jar:3.0:test -- module example.owned
   example.libs:owned:jar:3.0:test -- module example.owned
   example.libs:missing:jar:4.0:test
"""
    raw = maven_dependency_observation(trees={}, inventories={"test": inventory})

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)

    coverage = {
        row["kind"]: row for row in observation["coverage"] if row["context"] == "test"
    }
    assert len(observation["inventory"]) == 2
    assert coverage["module-ownership"]["completeness"] == "incomplete"


def test_maven_conflicting_duplicate_module_annotations_preserve_ambiguity(
    tmp_path: Path,
) -> None:
    inventory = b"""The following files have been resolved:
   example.libs:owned:jar:3.0:test -- module example.one
   example.libs:owned:jar:3.0:test -- module example.two
"""
    raw = maven_dependency_observation(trees={}, inventories={"test": inventory})

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)

    ownership = {
        row["module"]: row["owners"] for row in observation["module_ownership"]
    }
    coverage = {
        row["kind"]: row for row in observation["coverage"] if row["context"] == "test"
    }
    assert ownership == {
        "example.one": ["example.libs:owned:jar:3.0"],
        "example.two": ["example.libs:owned:jar:3.0"],
    }
    assert coverage["module-ownership"]["completeness"] == "complete"


def test_maven_adapter_refuses_unparsed_inventory_coordinate() -> None:
    inventory = b"""The following files have been resolved:\n   example.libs:valid:jar:3.0:test -- module example.valid\n   example.libs:omitted:jar:4.0\n"""

    with pytest.raises(ValueError, match="unparsed Maven dependency-list coordinate"):
        maven_dependency_observation(trees={}, inventories={"test": inventory})


def test_maven_adapter_refuses_truncated_inventory_coordinate() -> None:
    inventory = b"""The following files have been resolved:\n   example.libs:valid:jar:3.0:test -- module example.valid\n   example.libs:omitted:jar\n"""

    with pytest.raises(ValueError, match="unparsed Maven dependency-list coordinate"):
        maven_dependency_observation(trees={}, inventories={"test": inventory})


def test_maven_adapter_refuses_short_inventory_coordinate() -> None:
    inventory = b"""The following files have been resolved:\n   example.libs:valid:jar:3.0:test -- module example.valid\n   example.libs:omitted\n"""

    with pytest.raises(ValueError, match="unparsed Maven dependency-list coordinate"):
        maven_dependency_observation(trees={}, inventories={"test": inventory})


@pytest.mark.parametrize(
    "noise",
    [
        "[INFO] Scanning for projects...",
        "[WARNING] Repository mirror: https://repo.example.invalid/maven2",
        "[ERROR] Example diagnostic: retained as non-coordinate noise",
        "[DEBUG] Dependency collection: complete",
    ],
)
def test_maven_adapter_ignores_colon_bearing_maven_log_noise(noise: str) -> None:
    inventory = (
        "The following files have been resolved:\n"
        f"{noise}\n"
        "   example.libs:valid:jar:3.0:test -- module example.valid\n"
    ).encode()

    raw = maven_dependency_observation(trees={}, inventories={"test": inventory})

    assert [row["node_id"] for row in raw["inventory"]] == [
        "example.libs:valid:jar:3.0"
    ]
