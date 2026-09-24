from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hashmarks.adapters import maven_dependency_observation
from hashmarks.codemap.engine import CodeMap


def _complete_maven_observation(
    *,
    trees: dict[str, bytes],
    inventories: dict[str, bytes],
    repository_inputs=(),
) -> dict[str, object]:
    return maven_dependency_observation(
        trees=trees,
        inventories=inventories,
        complete_tree_contexts=tuple(trees),
        complete_inventory_contexts=tuple(inventories),
        repository_inputs=repository_inputs,
    )


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


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "trees": {"compile": _tree()},
                "inventories": {},
                "complete_tree_contexts": ("runtime",),
            },
            "complete Maven tree context has no supplied tree: runtime",
        ),
        (
            {
                "trees": {},
                "inventories": {"compile": _inventory()},
                "complete_inventory_contexts": ("runtime",),
            },
            "complete Maven inventory context has no supplied list: runtime",
        ),
    ],
)
def test_maven_complete_context_requires_supplied_artifact(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        maven_dependency_observation(**kwargs)


def test_maven_adapter_does_not_infer_complete_coverage_from_bytes(
    tmp_path: Path,
) -> None:
    raw = maven_dependency_observation(
        trees={"compile": _tree()},
        inventories={"compile": _inventory()},
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)
        missing_component = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "component", "component_id": "missing"}],
        )["results"][0]
        missing_inventory = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "inventory",
                    "node_id": "missing@1",
                    "context": "compile",
                }
            ],
        )["results"][0]

    coverage = {
        row["kind"]: row["completeness"]
        for row in observation["coverage"]
        if row["context"] == "compile"
    }
    assert coverage == {
        "module-ownership": "incomplete",
        "resolution-graph": "incomplete",
        "resolved-inventory": "incomplete",
        "selection": "incomplete",
    }
    assert missing_component["negative_evidence"] == "not-admissible"
    assert missing_inventory["negative_evidence"] == "not-admissible"


def test_maven_adapter_preserves_inventory_topology_and_module_ambiguity(
    tmp_path: Path,
) -> None:
    raw = _complete_maven_observation(
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
    raw = _complete_maven_observation(
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
    raw = _complete_maven_observation(
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
    raw = _complete_maven_observation(
        trees={"compile": _tree()},
        inventories={"compile": _inventory()},
    )

    assert raw["producer"]["kind"] == "maven-dependency-artifacts"
    assert raw["scope"] == {}
    assert raw["contexts"] == ["compile"]


def test_maven_distinct_same_byte_artifacts_keep_distinct_sources() -> None:
    tree = _tree()
    inventory = _inventory()
    raw = _complete_maven_observation(
        trees={"compile": tree, "runtime": tree},
        inventories={"compile": inventory, "runtime": inventory},
    )

    sources = {row["source_id"]: row for row in raw["evidence_sources"]}
    assert set(sources) == {
        "tree:compile",
        "tree:runtime",
        "list:compile",
        "list:runtime",
    }
    assert (
        sources["tree:compile"]["producer_digest"]
        == sources["tree:runtime"]["producer_digest"]
    )
    assert (
        sources["list:compile"]["producer_digest"]
        == sources["list:runtime"]["producer_digest"]
    )
    assert sources["list:compile"]["authorities"] == [
        "module-ownership",
        "resolved-inventory",
        "selection",
    ]


def test_maven_adapter_relationship_change_is_not_selection_change(
    tmp_path: Path,
) -> None:
    before_raw = _complete_maven_observation(
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
    after_raw = _complete_maven_observation(
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
    raw = _complete_maven_observation(
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
    raw = _complete_maven_observation(
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
    raw = _complete_maven_observation(
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
    raw = _complete_maven_observation(trees={}, inventories={"test": inventory})

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
    raw = _complete_maven_observation(trees={}, inventories={"test": inventory})

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
    raw = _complete_maven_observation(trees={}, inventories={"test": inventory})

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
        _complete_maven_observation(trees={}, inventories={"test": inventory})


def test_maven_adapter_refuses_truncated_inventory_coordinate() -> None:
    inventory = b"""The following files have been resolved:\n   example.libs:valid:jar:3.0:test -- module example.valid\n   example.libs:omitted:jar\n"""

    with pytest.raises(ValueError, match="unparsed Maven dependency-list coordinate"):
        _complete_maven_observation(trees={}, inventories={"test": inventory})


def test_maven_adapter_refuses_short_inventory_coordinate() -> None:
    inventory = b"""The following files have been resolved:\n   example.libs:valid:jar:3.0:test -- module example.valid\n   example.libs:omitted\n"""

    with pytest.raises(ValueError, match="unparsed Maven dependency-list coordinate"):
        _complete_maven_observation(trees={}, inventories={"test": inventory})


@pytest.mark.parametrize(
    "noise",
    [
        "[INFO] Scanning for projects...",
        "[WARNING] Repository mirror: https://repo.example.invalid/maven2",
        "[DEBUG] Dependency collection: complete",
    ],
)
def test_maven_adapter_ignores_colon_bearing_maven_log_noise(noise: str) -> None:
    inventory = (
        "The following files have been resolved:\n"
        f"{noise}\n"
        "   example.libs:valid:jar:3.0:test -- module example.valid\n"
    ).encode()

    raw = _complete_maven_observation(trees={}, inventories={"test": inventory})

    assert [row["node_id"] for row in raw["inventory"]] == [
        "example.libs:valid:jar:3.0"
    ]


def test_maven_adapter_refuses_missing_dependency_metadata_warning() -> None:
    inventory = b"""[WARNING] The POM for example.libs:missing:jar:4.0 is missing, no dependency information available
The following files have been resolved:
   example.libs:valid:jar:3.0:test -- module example.valid
"""

    with pytest.raises(
        ValueError,
        match="Maven dependency list contains incomplete resolution warning",
    ):
        _complete_maven_observation(trees={}, inventories={"test": inventory})


@pytest.mark.parametrize(
    "inventory",
    [
        b"not a Maven dependency list\n",
        b"[INFO] BUILD SUCCESS\n",
        b"example.libs:valid:jar:3.0:test\n",
        b"The following files have been resolved:\n[ERROR] resolution failed\n",
        b"The following files have been resolved:\n   none\n[INFO] BUILD FAILURE\n",
        b"The following files have been resolved:\nresolution incomplete\n",
    ],
)
def test_maven_adapter_rejects_unproved_complete_inventory(
    inventory: bytes,
) -> None:
    with pytest.raises(ValueError):
        _complete_maven_observation(trees={}, inventories={"test": inventory})


def test_maven_header_only_inventory_is_complete_empty_evidence(
    tmp_path: Path,
) -> None:
    raw = _complete_maven_observation(
        trees={}, inventories={"test": b"The following files have been resolved:\n"}
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)
        result = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "inventory", "node_id": "absent", "context": "test"}],
        )["results"][0]
    assert result["result"] == []
    assert result["negative_evidence"] == "admissible-within-declared-scope"
    assert result["producer_authority"] == "caller-claimed"


def test_maven_genuine_none_marker_is_complete_empty_evidence(
    tmp_path: Path,
) -> None:
    raw = _complete_maven_observation(
        trees={},
        inventories={"test": b"The following files have been resolved:\n   none\n"},
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(raw)
    assert observation["inventory"] == []
    assert {
        row["kind"]: row["state"]
        for row in observation["negative_evidence"]
        if row["context"] == "test"
    }["resolved-inventory"] == "admissible-within-declared-scope"


def test_maven_list_strips_producer_ansi_without_changing_source_digest() -> None:
    inventory = (
        b"The following files have been resolved:\n"
        b"   example.libs:valid:jar:3.0:test\x1b[36m -- module valid.name"
        b"\x1b[0;1;33m (auto)\x1b[m\n"
    )
    raw = _complete_maven_observation(trees={}, inventories={"test": inventory})
    assert raw["inventory"][0]["node_id"] == "example.libs:valid:jar:3.0"
    assert raw["module_ownership"][0]["module"] == "valid.name"
    assert raw["evidence_sources"][0]["producer_digest"] == (
        "sha256:" + hashlib.sha256(inventory).hexdigest()
    )


def test_maven_none_marker_cannot_hide_dependency() -> None:
    inventory = (
        b"The following files have been resolved:\n"
        b"   none\n"
        b"   example.libs:valid:jar:3.0:test\n"
    )
    with pytest.raises(ValueError, match="conflicting.*empty marker"):
        _complete_maven_observation(trees={}, inventories={"test": inventory})
