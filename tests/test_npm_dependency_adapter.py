"""Native npm slots provide namespace claims without becoming a Node resolver."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.adapters import npm_lock_dependency_observation


def _lock(packages: dict[str, object], version: int = 3) -> bytes:
    return json.dumps(
        {
            "name": "application",
            "lockfileVersion": version,
            "packages": {"": {"name": "application", "version": "1.0"}, **packages},
        }
    ).encode()


@pytest.mark.parametrize("version", [2, 3])
def test_native_alias_inventory_and_source_authority_do_not_invent_graph_edges(
    tmp_path: Path, version: int
) -> None:
    raw = npm_lock_dependency_observation(
        lock=_lock(
            {
                "node_modules/@scope/alias": {
                    "name": "actual-package",
                    "version": "2.1.0",
                    "resolved": "https://example.invalid/actual-2.1.0.tgz",
                    "integrity": "sha512-caller-supplied",
                    "dependencies": {"unobserved-transitive": "^1.0"},
                }
            },
            version,
        )
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(raw)
        selection = assert_records(observation["selections"])[0]
        queries = codemap.dependencies.queries(
            observation,
            [{"operation": "dependencies", "node_id": selection["node_id"]}],
        )
    assert selection["component_id"] == "actual-package"
    assert selection["version"] == "2.1.0"
    assert json.loads(str(selection["source"])) == {
        "location": "node_modules/@scope/alias",
        "resolved": "https://example.invalid/actual-2.1.0.tgz",
        "integrity": "sha512-caller-supplied",
    }
    ownership = assert_records(observation["module_ownership"])[0]
    assert ownership["module"] == "@scope/alias"
    assert ownership["owners"] == [selection["node_id"]]
    assert ownership["completeness"] == "incomplete"
    assert observation["relationships"] == observation["roots"] == []
    assert len(assert_records(observation["evidence_sources"])) == 1
    source = assert_records(observation["evidence_sources"])[0]
    assert source["authorities"] == [
        "module-ownership",
        "resolved-inventory",
        "selection",
    ]
    assert source["completeness"] == "complete"
    query = assert_records(queries["results"])[0]
    assert query["negative_evidence"] == "not-admissible"
    assert query["completeness"] == "incomplete"


def test_nested_slots_and_aliases_preserve_versions_without_hoisting_inference(
    tmp_path: Path,
) -> None:
    raw = npm_lock_dependency_observation(
        lock=_lock(
            {
                "node_modules/library": {"version": "1.0"},
                "node_modules/parent/node_modules/library": {"version": "2.0"},
                "node_modules/alias": {"name": "library", "version": "1.0"},
            }
        )
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(raw)
    selections = assert_records(observation["selections"])
    assert len({row["node_id"] for row in selections}) == 3
    assert {row["component_id"] for row in selections} == {"library"}
    owners = {
        row["module"]: row for row in assert_records(observation["module_ownership"])
    }
    assert len(assert_array(owners["library"]["owners"])) == 2
    assert len(assert_array(owners["alias"]["owners"])) == 1
    assert owners["library"]["state"] == "resolved-ambiguous"
    assert all(row["contexts"] == ["lock"] for row in selections)


def test_workspace_links_local_sources_and_missing_metadata_keep_coverage_incomplete(
    tmp_path: Path,
) -> None:
    raw = npm_lock_dependency_observation(
        lock=_lock(
            {
                "node_modules/usable": {"version": "1.0"},
                "node_modules/linked": {"link": True, "resolved": "packages/linked"},
                "packages/linked": {"name": "linked", "version": "1.0"},
                "node_modules/local": {
                    "version": "1.0",
                    "resolved": "file:../local.tgz",
                },
                "node_modules/missing": {},
            }
        )
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(raw)
    assert [row["name"] for row in assert_records(observation["components"])] == [
        "usable"
    ]
    assert {
        row["reason"]
        for row in assert_records(assert_object(raw["producer"])["unsupported"])
    } == {
        "linked-package-not-observed",
        "workspace-or-non-install-location-not-observed",
        "local-package-source-not-observed",
        "package-version-unavailable",
    }
    assert all(
        row["completeness"] == "incomplete" for row in assert_records(raw["coverage"])
    )
    assert assert_records(raw["evidence_sources"])[0]["completeness"] == "complete"


def test_semantic_selection_identity_does_not_include_capture_digest(
    tmp_path: Path,
) -> None:
    lock = _lock({"node_modules/library": {"version": "1.0"}})
    first = npm_lock_dependency_observation(lock=lock)
    second = npm_lock_dependency_observation(
        lock=json.dumps(json.loads(lock), indent=2).encode()
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.dependencies.observe(first)
        after = codemap.dependencies.observe(second)
    assert before["selections"] == after["selections"]
    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]


@pytest.mark.parametrize(
    "lock, message",
    [
        (b"[]", "must be an object"),
        (b'{"lockfileVersion":1,"packages":{}}', "lockfileVersion"),
        (b'{"lockfileVersion":true,"packages":{}}', "lockfileVersion"),
        (b'{"lockfileVersion":3,"packages":[],"packages":{}}', "duplicate npm"),
        (b'{"lockfileVersion":3,"packages":{"node_modules/pkg":null}}', "descriptors"),
        (_lock({"../outside": {"version": "1"}}), "must not contain"),
        (_lock({"C:/node_modules/pkg": {"version": "1"}}), "relative to workspace"),
        (_lock({"/node_modules/pkg": {"version": "1"}}), "relative to workspace"),
        (_lock({"./node_modules/pkg": {"version": "1"}}), "canonical relative"),
        (_lock({"node_modules\\pkg": {"version": "1"}}), "canonical relative"),
        (_lock({"node_modules/pkg": {"version": 1}}), "version must be a string"),
        (_lock({"node_modules/pkg": {"version": "1", "link": "true"}}), "boolean"),
        (b" " * 4_194_305, "at most 4194304"),
        (
            _lock({f"node_modules/p{i}": {"version": "1"} for i in range(1000)}),
            "1000 entries",
        ),
    ],
)
def test_native_metadata_must_be_bounded_and_unambiguous(
    lock: bytes, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        npm_lock_dependency_observation(lock=lock)
