"""Authored manifests retain origins independently from supplied lock evidence."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from hashmarks.adapters import uv_lock_dependency_observation
from hashmarks.codemap import (
    CodeMap,
    PythonUvManifestDeclarations,
    RepositoryDeclarationProviderError,
)
from hashmarks.codemap.python_uv_manifest_declarations import MAX_MANIFEST_BYTES


def _write(root: Path, path: str, source: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


def _observe(root: Path, paths: tuple[str, ...]) -> dict:
    with CodeMap(root) as codemap:
        codemap.index.sync()
        return codemap.declarations.discover([PythonUvManifestDeclarations(paths)])


def _groups(packet: dict, kind: str) -> list[dict]:
    return [
        row
        for row in packet["declarations"]["groups"]
        if row["concept"]["kind"] == kind
    ]


def _value(group: dict) -> dict:
    return group["declarations"][0]["value"]


def _evidence(packet: dict, group: dict) -> list[dict]:
    binding_id = group["declarations"][0]["binding_id"]
    return next(
        row["evidence"]
        for row in packet["declarations"]["repository_evidence"]["bindings"]
        if row["binding_id"] == binding_id
    )


def _project(name: str, requirement: str) -> str:
    return f'[project]\nname = "{name}"\nversion = "0.1.0"\ndependencies = ["{requirement}"]\n'


def _lock() -> bytes:
    return b"""version = 1
revision = 3
[[package]]
name = "demo-app"
version = "0.1.0"
source = {virtual = "."}
dependencies = [{name = "shared-lib"}]
[[package]]
name = "shared-lib"
version = "2.0.0"
source = {registry = "https://example.invalid/simple"}
"""


def test_dependency_origins_scripts_groups_and_dynamic_metadata_remain_distinct(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        """[project]
name = "demo-app"
dynamic = ["version"]
requires-python = ">=3.11"
dependencies = ["shared-lib>=1; python_version >= '3.11'", "shared-lib<3"]
[project.optional-dependencies]
image = ["image-lib>=2"]
[project.scripts]
demo = "demo_package.cli:main"
[dependency-groups]
test = ["test-lib>=1"]
check = [{include-group = "test"}, "check-lib", {include-group = "missing"}]
cycle = [{include-group = "cycle"}]
[build-system]
requires = ["build-lib>=1"]
build-backend = "build_lib.api"
backend-path = ["."]
[tool.uv.sources]
shared-lib = [{path = "libs/shared", editable = true, marker = "sys_platform == 'linux'"}, {index = "internal"}]
""",
    )
    packet = _observe(tmp_path, ("pyproject.toml",))
    dependencies = _groups(packet, "python-dependency-declarations")
    by_key = {tuple(row["scope"]["toml_key"]): _value(row) for row in dependencies}
    root = by_key[("project", "dependencies")]["entries"]
    assert [row["raw_requirement"] for row in root] == [
        "shared-lib>=1; python_version >= '3.11'",
        "shared-lib<3",
    ]
    check = by_key[("dependency-groups", "check")]["entries"]
    assert check[0]["include_group"] == "test"
    assert check[0]["target_declared_in_this_manifest"] is True
    assert check[2]["target_declared_in_this_manifest"] is False
    assert check[0]["effective_requirements"] == "not-expanded"
    assert (
        by_key[("dependency-groups", "cycle")]["entries"][0]["effective_requirements"]
        == "not-expanded"
    )
    script = _value(_groups(packet, "python-script-entrypoint-declaration")[0])
    assert (script["name"], script["target"]) == ("demo", "demo_package.cli:main")
    assert script["runtime_importability"] == "not-established"
    project = _value(_groups(packet, "python-project-declaration")[0])
    assert project["dynamic"] == ["version"]
    assert "version" not in project["declared"]
    alternatives = _value(_groups(packet, "uv-source-declaration")[0])["alternatives"]
    assert alternatives[0]["declared"]["editable"] is True
    assert alternatives[0]["effective_source"] == "not-established"
    for group in packet["declarations"]["groups"]:
        assert group["absence"]["state"] == "unknown"
        assert group["correspondence"]["state"] == "unresolved"
        evidence = _evidence(packet, group)[0]
        assert evidence["scope"] == "member"
        assert (
            evidence["member_revision"]
            == packet["providers"][0]["inputs"][0]["member_revision"]
        )


def test_nominated_workspace_matches_exclusions_and_multiple_origins(
    tmp_path: Path,
) -> None:
    root = "repo/pyproject.toml"
    member = "repo/packages/one/pyproject.toml"
    excluded = "repo/packages/excluded/pyproject.toml"
    outside = "other/pyproject.toml"
    _write(
        tmp_path,
        root,
        _project("demo-app", "shared-lib>=1")
        + (
            '[tool.uv.workspace]\nmembers = ["packages/*"]\nexclude = ["packages/excluded"]\n'
        ),
    )
    for path, constraint in (
        (member, "shared-lib<2"),
        (excluded, "shared-lib>=3"),
        (outside, "shared-lib==9"),
    ):
        _write(tmp_path, path, _project("same-declared-name", constraint))
    packet = _observe(tmp_path, (root, member, excluded, outside))
    workspace = _groups(packet, "uv-workspace-declaration")[0]
    value = _value(workspace)
    assert {
        row["manifest_path"]: row["matches_declared_patterns"]
        for row in value["static_candidate_matches"]
    } == {
        root: True,
        member: True,
        excluded: False,
        outside: False,
    }
    assert value["effective_workspace_membership"] == "not-established"
    assert value["candidate_scope"] == "selected-present-manifests-only"
    assert {
        row["scope"]["manifest_path"]
        for row in _groups(packet, "python-dependency-declarations")
    } == {root, member, excluded, outside}
    assert {row["path"] for row in _evidence(packet, workspace)} == {
        root,
        member,
        excluded,
        outside,
    }


def test_member_script_change_updates_binding_with_unchanged_root_and_lock(
    tmp_path: Path,
) -> None:
    member = "packages/tool/pyproject.toml"
    _write(tmp_path, "pyproject.toml", _project("demo-app", "shared-lib>=1"))
    _write(
        tmp_path,
        member,
        _project("tool", "shared-lib<3") + '[project.scripts]\ntool="pkg:before"\n',
    )
    (tmp_path / "uv.lock").write_bytes(_lock())
    provider = PythonUvManifestDeclarations(("pyproject.toml", member))
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = cast("dict", codemap.declarations.discover([provider]))
        _write(
            tmp_path,
            member,
            _project("tool", "shared-lib<3") + '[project.scripts]\ntool="pkg:after"\n',
        )
        with pytest.raises(RepositoryDeclarationProviderError):
            codemap.declarations.discover([provider])
        codemap.index.sync([member])
        after = cast(
            "dict",
            codemap.declarations.discover([provider], previous_observation=before),
        )
    before_inputs = {
        row["path"]: row["member_revision"] for row in before["providers"][0]["inputs"]
    }
    after_inputs = {
        row["path"]: row["member_revision"] for row in after["providers"][0]["inputs"]
    }
    assert before_inputs["pyproject.toml"] == after_inputs["pyproject.toml"]
    assert before_inputs[member] != after_inputs[member]
    assert (tmp_path / "uv.lock").read_bytes() == _lock()
    assert before["observation_identity"] != after["observation_identity"]
    assert (
        _value(_groups(after, "python-script-entrypoint-declaration")[0])["target"]
        == "pkg:after"
    )
    delta = after["delta_from_previous"]["declarations"]
    changed = [
        row for row in delta["changed_groups"] if row["value_changed_declaration_ids"]
    ]
    assert len(changed) == 1


def test_lock_evidence_uses_existing_adapter_and_explicit_manifest_correspondence(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pyproject.toml", _project("demo-app", "shared-lib>=1"))
    (tmp_path / "uv.lock").write_bytes(_lock())
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        declarations = cast(
            "dict",
            codemap.declarations.discover(
                [PythonUvManifestDeclarations(("pyproject.toml",))]
            ),
        )
        member, raw = codemap.source.member("uv.lock", include_bytes=True)
        assert raw is not None
        inputs = [
            {"path": row["path"], "member_revision": row["member_revision"]}
            for row in declarations["providers"][0]["inputs"]
        ]
        inputs.append({"path": "uv.lock", "member_revision": member["member_revision"]})
        dependencies = cast(
            "dict",
            codemap.dependencies.observe(
                uv_lock_dependency_observation(
                    lock=raw,
                    repository_inputs=inputs,
                )
            ),
        )
    assert all(
        row["source_equivalence"] == "proven"
        for row in dependencies["repository_inputs"]
    )
    external = next(
        row for row in dependencies["selections"] if row["component_id"] == "shared-lib"
    )
    assert external["version"] == "2.0.0"
    declaration = _value(_groups(declarations, "python-dependency-declarations")[0])
    assert declaration["entries"][0]["raw_requirement"] == "shared-lib>=1"
    assert declaration["selected_versions"] == "not-established"
    assert dependencies["roots"][0]["node_id"].startswith("demo-app:")


def test_missing_lock_is_independent_and_missing_manifests_are_not_negative_evidence(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pyproject.toml", _project("demo-app", "shared-lib>=1"))
    packet = _observe(tmp_path, ("pyproject.toml", "missing/pyproject.toml"))
    assert packet["providers"][0]["provenance"]["missing_selected_paths"] == [
        "missing/pyproject.toml"
    ]
    assert not (tmp_path / "uv.lock").exists()
    missing = _observe(tmp_path, ("missing/pyproject.toml",))
    assert missing["declarations"]["groups"] == []
    assert (
        missing["providers"][0]["provenance"]["negative_evidence_admissible"] is False
    )


def test_comment_only_edit_preserves_manifest_semantic_value(tmp_path: Path) -> None:
    source = _project("demo-app", "shared-lib>=1")
    _write(tmp_path, "pyproject.toml", source)
    before = _observe(tmp_path, ("pyproject.toml",))
    _write(tmp_path, "pyproject.toml", "# comment\n" + source)
    after = _observe(tmp_path, ("pyproject.toml",))
    assert [_value(row) for row in before["declarations"]["groups"]] == [
        _value(row) for row in after["declarations"]["groups"]
    ]
    assert before["observation_identity"] != after["observation_identity"]


def test_workspace_without_declared_members_does_not_invent_empty_membership(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pyproject.toml", '[tool.uv.workspace]\nexclude=["excluded"]\n')
    packet = _observe(tmp_path, ("pyproject.toml",))
    workspace = _value(_groups(packet, "uv-workspace-declaration")[0])
    assert workspace["members_declared"] is False
    assert workspace["static_candidate_matches"][0]["matches_declared_patterns"] is None


@pytest.mark.parametrize(
    "source",
    [
        '[project]\nname="demo"\nname="duplicate"\n',
        '[project]\ndependencies=[{invalid="form"}]\n',
        '[dependency-groups]\nbad=[{unknown="group"}]\n',
        "[project.scripts]\ndemo=42\n",
        '[tool.uv.workspace]\nmembers="packages/*"\n',
        "#" * (MAX_MANIFEST_BYTES + 1),
    ],
)
def test_invalid_or_oversized_manifests_fail_closed(
    tmp_path: Path, source: str
) -> None:
    _write(tmp_path, "pyproject.toml", source)
    with pytest.raises(RepositoryDeclarationProviderError):
        _observe(tmp_path, ("pyproject.toml",))


@pytest.mark.parametrize(
    "paths",
    [(), ("uv.lock",), ("../pyproject.toml",), ("pyproject.toml", "pyproject.toml")],
)
def test_explicit_manifest_selection_rejects_invalid_scope(
    paths: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        PythonUvManifestDeclarations(paths)
