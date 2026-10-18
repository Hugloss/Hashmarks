"""Same-named admitted packages remain distinct without guessing dependency targets."""

from __future__ import annotations

import json
from pathlib import Path

from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.codemap import CodeMap


def _package(
    root: Path, path: str, name: str, dependencies: dict[str, str] | None = None
) -> None:
    directory = root / path
    directory.mkdir(parents=True)
    (directory / "package.json").write_text(
        json.dumps({"name": name, "dependencies": dependencies or {}})
    )
    (directory / "value.ts").write_text("export const value = 1;\n")


def test_duplicate_package_names_publish_distinct_declarations_and_unknown_targets(
    tmp_path: Path,
) -> None:
    _package(tmp_path, "first", "duplicate", {"unique": "*"})
    _package(tmp_path, "second", "duplicate", {"unique": "*"})
    _package(tmp_path, "unique", "unique")
    _package(tmp_path, "caller", "caller", {"duplicate": "*"})
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as repository:
        repository.index.sync()
        result = repository.native.enrich_projects(("npm-package-graph",))
        nodes = assert_records(result["projects"])
        by_root = {row["root"]: row for row in nodes}
        assert len(nodes) == len({row["project_id"] for row in nodes}) == 4
        assert by_root["first"]["project_id"] != by_root["second"]["project_id"]
        assert by_root["unique"]["project_id"] == "npm:unique"
        assert by_root["caller"]["project_id"] == "npm:caller"
        assert (
            assert_object(by_root["first"]["metadata"])["name_resolution"]
            == "ambiguous"
        )
        assert (
            assert_object(by_root["second"]["metadata"])["name_resolution"]
            == "ambiguous"
        )
        edges = assert_records(result["edges"])
        assert {(row["source"], row["target"]) for row in edges} == {
            (by_root["first"]["project_id"], "npm:unique"),
            (by_root["second"]["project_id"], "npm:unique"),
        }
        assert any(
            "ambiguous" in str(warning) and "duplicate" in str(warning)
            for warning in assert_array(result["warnings"])
        )
        first_ids = {row["manifest"]: row["project_id"] for row in nodes}
        repeated = repository.native.enrich_projects(("npm-package-graph",))
        assert {
            row["manifest"]: row["project_id"]
            for row in assert_records(repeated["projects"])
        } == first_ids


def test_denied_duplicate_does_not_displace_a_visible_unique_name(
    tmp_path: Path,
) -> None:
    _package(tmp_path, "visible", "duplicate")
    _package(tmp_path, "hidden", "duplicate")
    _package(tmp_path, "caller", "caller", {"duplicate": "*"})
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "hidden/**"\nindex = false\n'
    )
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as repository:
        repository.index.sync()
        result = repository.native.enrich_projects(("npm-package-graph",))
    assert {row["project_id"] for row in assert_records(result["projects"])} == {
        "npm:duplicate",
        "npm:caller",
    }
    assert {
        (row["source"], row["target"]) for row in assert_records(result["edges"])
    } == {("npm:caller", "npm:duplicate")}
    assert not any(
        "hidden" in str(warning) for warning in assert_array(result["warnings"])
    )


def test_ambiguous_declaration_ids_cannot_collide_with_literal_package_names(
    tmp_path: Path,
) -> None:
    _package(tmp_path, "first", "duplicate")
    _package(tmp_path, "second", "duplicate")
    conflicting_name = 'declaration:["duplicate","first/package.json"]'
    _package(tmp_path, "literal", conflicting_name)
    _package(tmp_path, "caller", "caller", {conflicting_name: "*"})
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as repository:
        repository.index.sync()
        result = repository.native.enrich_projects(("npm-package-graph",))
    nodes = assert_records(result["projects"])
    by_root = {row["root"]: row for row in nodes}
    assert len({row["project_id"] for row in nodes}) == 4
    assert by_root["literal"]["project_id"] != by_root["first"]["project_id"]
    assert {
        (row["source"], row["target"]) for row in assert_records(result["edges"])
    } == {("npm:caller", by_root["literal"]["project_id"])}


def test_reopened_graph_resolves_a_name_only_after_its_duplicate_is_removed(
    tmp_path: Path,
) -> None:
    _package(tmp_path, "first", "duplicate")
    _package(tmp_path, "second", "duplicate")
    _package(tmp_path, "caller", "caller", {"duplicate": "*"})
    state = tmp_path / ".state"
    with CodeMap(tmp_path, state_dir=state) as repository:
        repository.index.sync()
        before = repository.native.enrich_projects(("npm-package-graph",))
        assert before["edges"] == []
    (tmp_path / "second/package.json").write_text(json.dumps({"name": "renamed"}))
    with CodeMap(tmp_path, state_dir=state) as repository:
        repository.index.sync()
        after = repository.native.enrich_projects(("npm-package-graph",))
    assert {row["project_id"] for row in assert_records(after["projects"])} == {
        "npm:duplicate",
        "npm:renamed",
        "npm:caller",
    }
    assert {
        (row["source"], row["target"]) for row in assert_records(after["edges"])
    } == {("npm:caller", "npm:duplicate")}
    assert not any(
        "ambiguous" in str(warning) for warning in assert_array(after["warnings"])
    )
