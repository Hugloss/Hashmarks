from __future__ import annotations

import json
from pathlib import Path

from hashmarks.adapters import (
    maven_dependency_observation,
    uv_lock_dependency_observation,
)
from hashmarks.codemap.engine import CodeMap


def _uv_lock(version: str) -> bytes:
    return f'''version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "dummy-app"
version = "0.1.0"
source = {{ virtual = "." }}
dependencies = [{{ name = "dummy-dep" }}]

[[package]]
name = "dummy-dep"
version = "{version}"
source = {{ directory = "vendor/dummy_dep" }}
'''.encode()


def _maven_tree(version: str) -> bytes:
    return json.dumps(
        {
            "groupId": "example.fixture",
            "artifactId": "dummy-app",
            "version": "0.1.0",
            "type": "jar",
            "scope": "",
            "children": [
                {
                    "groupId": "example.fixture",
                    "artifactId": "dummy-dep",
                    "version": version,
                    "type": "jar",
                    "scope": "compile",
                }
            ],
        }
    ).encode()


def _maven_inventory(version: str) -> bytes:
    return (
        "The following files have been resolved:\n"
        f"   example.fixture:dummy-dep:jar:{version}:compile"
        " -- module dummy.dep (auto)\n"
    ).encode()


def _delta(codemap: CodeMap, before_raw: dict[str, object], after_raw: dict[str, object]):
    before = codemap.dependency_resolution_evidence(before_raw)
    after = codemap.dependency_resolution_evidence(after_raw)
    return before, after, codemap.dependency_resolution_delta(before, after)


def test_uv_and_maven_version_changes_share_dependency_delta_semantics(
    tmp_path: Path,
) -> None:
    contexts = ("compile", "runtime", "test")
    uv_before = uv_lock_dependency_observation(lock=_uv_lock("1.0.0"))
    uv_after = uv_lock_dependency_observation(lock=_uv_lock("2.0.0"))
    maven_before = maven_dependency_observation(
        trees={context: _maven_tree("1.0.0") for context in contexts},
        inventories={context: _maven_inventory("1.0.0") for context in contexts},
    )
    maven_after = maven_dependency_observation(
        trees={context: _maven_tree("2.0.0") for context in contexts},
        inventories={context: _maven_inventory("2.0.0") for context in contexts},
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        uv_b, uv_a, uv_delta = _delta(codemap, uv_before, uv_after)
        mvn_b, mvn_a, mvn_delta = _delta(codemap, maven_before, maven_after)

    for before, after, delta in (
        (uv_b, uv_a, uv_delta),
        (mvn_b, mvn_a, mvn_delta),
    ):
        assert before["definition_identity"] == after["definition_identity"]
        assert delta["comparability"] == "comparable"
        assert delta["components_added"] == []
        assert delta["components_removed"] == []
        assert delta["components_changed"] == []
        assert delta["selections_changed"] == []
        assert len(delta["selections_added"]) == 1
        assert len(delta["selections_removed"]) == 1
        assert delta["causation"] == "not-inferred"

    assert len(uv_delta["inventory_added"]) == 1
    assert len(uv_delta["inventory_removed"]) == 1
    assert len(uv_delta["relationships_added"]) == 1
    assert len(uv_delta["relationships_removed"]) == 1
    assert uv_delta["module_ownership_added"] == []
    assert uv_delta["module_ownership_removed"] == []
    assert uv_delta["module_ownership_changed"] == []

    assert len(mvn_delta["inventory_added"]) == 3
    assert len(mvn_delta["inventory_removed"]) == 3
    assert len(mvn_delta["relationships_added"]) == 3
    assert len(mvn_delta["relationships_removed"]) == 3
    assert mvn_delta["module_ownership_added"] == []
    assert mvn_delta["module_ownership_removed"] == []
    assert len(mvn_delta["module_ownership_changed"]) == 3
