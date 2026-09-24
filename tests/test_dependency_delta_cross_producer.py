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


def _delta(
    codemap: CodeMap, before_raw: dict[str, object], after_raw: dict[str, object]
):
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


def _uv_lock_with_source(version: str, source: str, *, marker: str = "") -> bytes:
    marker_field = f", marker = {json.dumps(marker)}" if marker else ""
    return f'''version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "dummy-app"
version = "0.1.0"
source = {{ virtual = "." }}
dependencies = [{{ name = "dummy-dep"{marker_field} }}]

[[package]]
name = "dummy-dep"
version = "{version}"
source = {source}
'''.encode()


def _maven_tree_variant(
    version: str,
    *,
    packaging: str = "jar",
    classifier: str = "",
    scope: str = "compile",
) -> bytes:
    child = {
        "groupId": "example.fixture",
        "artifactId": "dummy-dep",
        "version": version,
        "type": packaging,
        "scope": scope,
    }
    if classifier:
        child["classifier"] = classifier
    return json.dumps(
        {
            "groupId": "example.fixture",
            "artifactId": "dummy-app",
            "version": "0.1.0",
            "type": "jar",
            "scope": "",
            "children": [child],
        }
    ).encode()


def _maven_inventory_variant(
    version: str,
    *,
    packaging: str = "jar",
    classifier: str = "",
    scope: str = "compile",
) -> bytes:
    variant = f":{classifier}" if classifier else ""
    return (
        "The following files have been resolved:\n"
        f"   example.fixture:dummy-dep:{packaging}{variant}:{version}:{scope}"
        " -- module dummy.dep (auto)\n"
    ).encode()


def test_uv_source_change_is_a_selection_change_without_component_change(
    tmp_path: Path,
) -> None:
    before_raw = uv_lock_dependency_observation(
        lock=_uv_lock_with_source("1.0.0", '{ directory = "vendor/dummy_dep" }')
    )
    after_raw = uv_lock_dependency_observation(
        lock=_uv_lock_with_source(
            "1.0.0", '{ registry = "https://example.invalid/simple" }'
        )
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        _before, _after, delta = _delta(codemap, before_raw, after_raw)

    assert delta["comparability"] == "comparable"
    assert delta["components_added"] == []
    assert delta["components_removed"] == []
    assert delta["components_changed"] == []
    assert delta["selections_changed"] == []
    assert len(delta["selections_added"]) == 1
    assert len(delta["selections_removed"]) == 1
    assert len(delta["inventory_added"]) == 1
    assert len(delta["inventory_removed"]) == 1
    assert len(delta["relationships_added"]) == 1
    assert len(delta["relationships_removed"]) == 1


def test_uv_marker_change_is_relationship_only_delta(tmp_path: Path) -> None:
    before_raw = uv_lock_dependency_observation(
        lock=_uv_lock_with_source("1.0.0", '{ directory = "vendor/dummy_dep" }')
    )
    after_raw = uv_lock_dependency_observation(
        lock=_uv_lock_with_source(
            "1.0.0",
            '{ directory = "vendor/dummy_dep" }',
            marker='python_version >= "3.12"',
        )
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        _before, _after, delta = _delta(codemap, before_raw, after_raw)

    assert delta["selections_added"] == []
    assert delta["selections_removed"] == []
    assert delta["selections_changed"] == []
    assert delta["inventory_added"] == []
    assert delta["inventory_removed"] == []
    assert len(delta["relationships_added"]) == 1
    assert len(delta["relationships_removed"]) == 1


def test_maven_classifier_change_is_selection_change_without_component_change(
    tmp_path: Path,
) -> None:
    before_raw = maven_dependency_observation(
        trees={"compile": _maven_tree_variant("1.0.0")},
        inventories={"compile": _maven_inventory_variant("1.0.0")},
    )
    after_raw = maven_dependency_observation(
        trees={"compile": _maven_tree_variant("1.0.0", classifier="tests")},
        inventories={"compile": _maven_inventory_variant("1.0.0", classifier="tests")},
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        _before, _after, delta = _delta(codemap, before_raw, after_raw)

    assert delta["components_added"] == []
    assert delta["components_removed"] == []
    assert delta["components_changed"] == []
    assert delta["selections_changed"] == []
    assert len(delta["selections_added"]) == 1
    assert len(delta["selections_removed"]) == 1
    assert len(delta["inventory_added"]) == 1
    assert len(delta["inventory_removed"]) == 1
    assert len(delta["relationships_added"]) == 1
    assert len(delta["relationships_removed"]) == 1
    assert delta["module_ownership_added"] == []
    assert delta["module_ownership_removed"] == []
    assert delta["module_ownership_changed"] == ["dummy.dep|compile"]


def test_maven_effective_scope_change_is_relationship_only_delta(
    tmp_path: Path,
) -> None:
    before_raw = maven_dependency_observation(
        trees={"test": _maven_tree_variant("1.0.0", scope="compile")},
        inventories={"test": _maven_inventory_variant("1.0.0", scope="compile")},
    )
    after_raw = maven_dependency_observation(
        trees={"test": _maven_tree_variant("1.0.0", scope="runtime")},
        inventories={"test": _maven_inventory_variant("1.0.0", scope="runtime")},
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        _before, _after, delta = _delta(codemap, before_raw, after_raw)

    assert delta["selections_added"] == []
    assert delta["selections_removed"] == []
    assert delta["selections_changed"] == []
    assert delta["inventory_added"] == []
    assert delta["inventory_removed"] == []
    assert len(delta["relationships_added"]) == 1
    assert len(delta["relationships_removed"]) == 1
    assert delta["module_ownership_changed"] == []


def test_maven_context_membership_change_is_selection_and_inventory_delta(
    tmp_path: Path,
) -> None:
    before_raw = maven_dependency_observation(
        trees={"compile": _maven_tree_variant("1.0.0")},
        inventories={"compile": _maven_inventory_variant("1.0.0")},
    )
    after_raw = maven_dependency_observation(
        trees={
            "compile": _maven_tree_variant("1.0.0"),
            "runtime": _maven_tree_variant("1.0.0"),
        },
        inventories={
            "compile": _maven_inventory_variant("1.0.0"),
            "runtime": _maven_inventory_variant("1.0.0"),
        },
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(before_raw)
        after = codemap.dependency_resolution_evidence(after_raw)
        delta = codemap.dependency_resolution_delta(before, after)

    assert delta["comparability"] == "not-comparable"
    assert delta["reason"] == "definition-changed"


def _uv_lock_optional_dependency(*, include: bool) -> bytes:
    dependency = 'dependencies = [{ name = "dummy-dep" }]\n' if include else ""
    package = (
        """
[[package]]
name = "dummy-dep"
version = "1.0.0"
source = { directory = "vendor/dummy_dep" }
"""
        if include
        else ""
    )
    return f"""version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "dummy-app"
version = "0.1.0"
source = {{ virtual = "." }}
{dependency}{package}""".encode()


def _maven_tree_optional_dependency(*, include: bool) -> bytes:
    root = {
        "groupId": "example.fixture",
        "artifactId": "dummy-app",
        "version": "0.1.0",
        "type": "jar",
        "scope": "",
        "children": [],
    }
    if include:
        root["children"] = [
            {
                "groupId": "example.fixture",
                "artifactId": "dummy-dep",
                "version": "1.0.0",
                "type": "jar",
                "scope": "compile",
            }
        ]
    return json.dumps(root).encode()


def test_uv_and_maven_dependency_addition_share_delta_semantics(tmp_path: Path) -> None:
    uv_before = uv_lock_dependency_observation(
        lock=_uv_lock_optional_dependency(include=False)
    )
    uv_after = uv_lock_dependency_observation(
        lock=_uv_lock_optional_dependency(include=True)
    )
    maven_before = maven_dependency_observation(
        trees={"compile": _maven_tree_optional_dependency(include=False)},
        inventories={"compile": b"The following files have been resolved:\n"},
    )
    maven_after = maven_dependency_observation(
        trees={"compile": _maven_tree_optional_dependency(include=True)},
        inventories={"compile": _maven_inventory_variant("1.0.0")},
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        _uv_b, _uv_a, uv_delta = _delta(codemap, uv_before, uv_after)
        _mv_b, _mv_a, maven_delta = _delta(codemap, maven_before, maven_after)

    for delta in (uv_delta, maven_delta):
        assert delta["comparability"] == "comparable"
        assert len(delta["components_added"]) == 1
        assert delta["components_removed"] == []
        assert delta["components_changed"] == []
        assert len(delta["selections_added"]) == 1
        assert delta["selections_removed"] == []
        assert delta["selections_changed"] == []
        assert len(delta["inventory_added"]) == 1
        assert delta["inventory_removed"] == []
        assert len(delta["relationships_added"]) == 1
        assert delta["relationships_removed"] == []


def test_uv_and_maven_dependency_removal_share_delta_semantics(tmp_path: Path) -> None:
    uv_before = uv_lock_dependency_observation(
        lock=_uv_lock_optional_dependency(include=True)
    )
    uv_after = uv_lock_dependency_observation(
        lock=_uv_lock_optional_dependency(include=False)
    )
    maven_before = maven_dependency_observation(
        trees={"compile": _maven_tree_optional_dependency(include=True)},
        inventories={"compile": _maven_inventory_variant("1.0.0")},
    )
    maven_after = maven_dependency_observation(
        trees={"compile": _maven_tree_optional_dependency(include=False)},
        inventories={"compile": b"The following files have been resolved:\n"},
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        _uv_b, _uv_a, uv_delta = _delta(codemap, uv_before, uv_after)
        _mv_b, _mv_a, maven_delta = _delta(codemap, maven_before, maven_after)

    for delta in (uv_delta, maven_delta):
        assert delta["comparability"] == "comparable"
        assert delta["components_added"] == []
        assert len(delta["components_removed"]) == 1
        assert delta["components_changed"] == []
        assert delta["selections_added"] == []
        assert len(delta["selections_removed"]) == 1
        assert delta["selections_changed"] == []
        assert delta["inventory_added"] == []
        assert len(delta["inventory_removed"]) == 1
        assert delta["relationships_added"] == []
        assert len(delta["relationships_removed"]) == 1


def test_uv_simultaneous_versions_preserve_independent_selection_delta(
    tmp_path: Path,
) -> None:
    before_lock = b"""version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "dummy-app"
version = "0.1.0"
source = { virtual = "." }
dependencies = [
    { name = "shared", version = "1.0.0" },
    { name = "shared", version = "2.0.0" },
]

[[package]]
name = "shared"
version = "1.0.0"
source = { registry = "https://example.invalid/simple" }

[[package]]
name = "shared"
version = "2.0.0"
source = { registry = "https://example.invalid/simple" }
"""
    after_lock = before_lock.replace(b'version = "2.0.0"', b'version = "3.0.0"')
    after_lock = after_lock.replace(
        b'{ name = "shared", version = "2.0.0" }',
        b'{ name = "shared", version = "3.0.0" }',
    )
    before_raw = uv_lock_dependency_observation(lock=before_lock)
    after_raw = uv_lock_dependency_observation(lock=after_lock)

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before, after, delta = _delta(codemap, before_raw, after_raw)

    shared_before = [
        row for row in before["selections"] if row["component_id"] == "shared"
    ]
    shared_after = [
        row for row in after["selections"] if row["component_id"] == "shared"
    ]
    assert len(shared_before) == 2
    assert len(shared_after) == 2
    assert {row["version"] for row in shared_before} == {"1.0.0", "2.0.0"}
    assert {row["version"] for row in shared_after} == {"1.0.0", "3.0.0"}
    assert len(delta["selections_added"]) == 1
    assert len(delta["selections_removed"]) == 1
    assert delta["selections_changed"] == []


def test_maven_simultaneous_variants_preserve_independent_selection_delta(
    tmp_path: Path,
) -> None:
    before_inventory = (
        "The following files have been resolved:\n"
        "   example.fixture:dummy-dep:jar:linux:1.0.0:runtime"
        " -- module dummy.linux (auto)\n"
        "   example.fixture:dummy-dep:jar:osx:1.0.0:runtime"
        " -- module dummy.osx (auto)\n"
    ).encode()
    after_inventory = before_inventory.replace(
        b":osx:1.0.0:", b":windows:1.0.0:"
    ).replace(b"dummy.osx", b"dummy.windows")
    before_raw = maven_dependency_observation(
        trees={}, inventories={"runtime": before_inventory}
    )
    after_raw = maven_dependency_observation(
        trees={}, inventories={"runtime": after_inventory}
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before, after, delta = _delta(codemap, before_raw, after_raw)

    assert len(before["selections"]) == 2
    assert len(after["selections"]) == 2
    assert len(delta["selections_added"]) == 1
    assert len(delta["selections_removed"]) == 1
    assert delta["selections_changed"] == []
    assert delta["module_ownership_added"] == ["dummy.windows|runtime"]
    assert delta["module_ownership_removed"] == ["dummy.osx|runtime"]


def test_uv_repository_input_change_preserves_resolution_delta(
    tmp_path: Path,
) -> None:
    lock = _uv_lock("1.0.0")
    before_raw = uv_lock_dependency_observation(
        lock=lock,
        repository_inputs=[
            {"path": "uv.lock", "member_revision": "a" * 64},
        ],
    )
    after_raw = uv_lock_dependency_observation(
        lock=lock,
        repository_inputs=[
            {"path": "uv.lock", "member_revision": "b" * 64},
        ],
    )
    with CodeMap(tmp_path) as codemap:
        (tmp_path / "uv.lock").write_bytes(lock)
        codemap.sync()
        before, after, delta = _delta(codemap, before_raw, after_raw)

    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert delta["comparability"] == "comparable"
    assert delta["components_added"] == []
    assert delta["components_removed"] == []
    assert delta["selections_added"] == []
    assert delta["selections_removed"] == []
    assert delta["inventory_added"] == []
    assert delta["inventory_removed"] == []
    assert delta["relationships_added"] == []
    assert delta["relationships_removed"] == []


def test_maven_module_ownership_change_does_not_change_resolution_identity(
    tmp_path: Path,
) -> None:
    tree = _maven_tree_variant("1.0.0")
    before_raw = maven_dependency_observation(
        trees={"compile": tree},
        inventories={
            "compile": (
                "The following files have been resolved:\n"
                "   example.fixture:dummy-dep:jar:1.0.0:compile"
                " -- module dummy.old (auto)\n"
            ).encode()
        },
    )
    after_raw = maven_dependency_observation(
        trees={"compile": tree},
        inventories={
            "compile": (
                "The following files have been resolved:\n"
                "   example.fixture:dummy-dep:jar:1.0.0:compile"
                " -- module dummy.new (auto)\n"
            ).encode()
        },
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before, after, delta = _delta(codemap, before_raw, after_raw)

    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert delta["selections_added"] == []
    assert delta["selections_removed"] == []
    assert delta["inventory_added"] == []
    assert delta["inventory_removed"] == []
    assert delta["relationships_added"] == []
    assert delta["relationships_removed"] == []
    assert delta["module_ownership_added"] == ["dummy.new|compile"]
    assert delta["module_ownership_removed"] == ["dummy.old|compile"]
    assert delta["module_ownership_changed"] == []


def test_maven_same_module_owner_change_is_observation_delta_only(
    tmp_path: Path,
) -> None:
    before_raw = maven_dependency_observation(
        trees={},
        inventories={
            "runtime": (
                "The following files have been resolved:\n"
                "   example.fixture:dummy-dep:jar:linux:1.0.0:runtime"
                " -- module dummy.dep (auto)\n"
            ).encode()
        },
    )
    after_raw = maven_dependency_observation(
        trees={},
        inventories={
            "runtime": (
                "The following files have been resolved:\n"
                "   example.fixture:dummy-dep:jar:windows:1.0.0:runtime"
                " -- module dummy.dep (auto)\n"
            ).encode()
        },
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before, after, delta = _delta(codemap, before_raw, after_raw)

    assert before["resolution_identity"] != after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert len(delta["selections_added"]) == 1
    assert len(delta["selections_removed"]) == 1
    assert delta["module_ownership_added"] == []
    assert delta["module_ownership_removed"] == []
    assert delta["module_ownership_changed"] == ["dummy.dep|runtime"]
