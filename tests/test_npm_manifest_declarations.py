"""Selected npm syntax does not become package or execution authority."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hashmarks.codemap import (
    CodeMap,
    NpmManifestDeclarations,
    RepositoryDeclarationProviderError,
)
from hashmarks.codemap.npm_manifest_declarations import MAX_NPM_ENTRIES


def _write(root: Path, name: str, value: object) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _observe(root: Path, *paths: str) -> dict:
    with CodeMap(root) as repository:
        repository.index.sync()
        return repository.declarations.discover([NpmManifestDeclarations(paths)])


def _values(packet: dict) -> dict[str, dict]:
    return {
        group["scope"]["manifest_path"]: group["declarations"][0]["value"]
        for group in packet["declarations"]["groups"]
    }


def test_scripts_and_dependency_declarations_remain_authored_fields(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "frontend/package.json",
        {
            "scripts": {
                "verify": "npm run build && runner test",
                "build": "vite build",
            },
            "dependencies": {"runner": "npm:other-package@^1"},
            "devDependencies": {"vite": "^2"},
            "optionalDependencies": {"optional": "*"},
            "bin": "./cli.js",
        },
    )
    packet = _observe(tmp_path, "frontend/package.json")
    value = _values(packet)["frontend/package.json"]
    assert value["scripts"]["verify"] == "npm run build && runner test"
    assert value["dependency_declarations"]["dependencies"] == {
        "runner": "npm:other-package@^1"
    }
    assert value["bin"] == "./cli.js"
    assert value["native_interpretation"] == "not-established"
    assert value["installation"] == "not-observed"
    assert value["execution"] == "not-established"
    assert value["negative_evidence_admissible"] is False
    assert packet["providers"][0]["inputs"][0]["path"] == "frontend/package.json"


def test_lock_bin_slots_retain_ambiguity_nested_locations_and_string_shape(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "package-lock.json",
        {
            "lockfileVersion": 3,
            "packages": {
                "": {"bin": "cli.js"},
                "node_modules/runner-a": {
                    "version": "1",
                    "bin": {"runner": "cli.js"},
                    "integrity": "sha512-a",
                },
                "node_modules/runner-b": {"version": "2", "bin": {"runner": "bin.js"}},
                "node_modules/outer/node_modules/runner-c": {
                    "version": "3",
                    "bin": "runner.js",
                },
                "node_modules/linked": {"link": True, "bin": {"runner": "linked.js"}},
                "node_modules/no-bin": {"version": "4"},
            },
        },
    )
    value = _values(_observe(tmp_path, "package-lock.json"))["package-lock.json"]
    bins = value["bin_declarations"]
    assert len(bins) == 5
    assert [row["bin"] for row in bins].count({"runner": "cli.js"}) == 1
    assert bins[0] == {"package_location": "", "bin": "cli.js"}
    assert any(
        row["package_location"] == "node_modules/outer/node_modules/runner-c"
        and row["bin"] == "runner.js"
        for row in bins
    )
    assert value["effective_bin_names"] == "not-established"
    assert value["dependency_resolution"] == "native-npm-owned"
    assert value["negative_evidence_admissible"] is False


def test_reopen_and_changed_source_keep_revision_bound_declarations(
    tmp_path: Path,
) -> None:
    path = "package.json"
    _write(tmp_path, path, {"scripts": {"verify": "first-tool"}})
    before = _observe(tmp_path, path)
    assert _observe(tmp_path, path) == before
    _write(tmp_path, path, {"scripts": {"verify": "second-tool"}})
    after = _observe(tmp_path, path)
    assert _values(before)[path]["scripts"]["verify"] == "first-tool"
    assert _values(after)[path]["scripts"]["verify"] == "second-tool"
    assert before["providers"][0]["inputs"] != after["providers"][0]["inputs"]


def test_empty_omitted_and_missing_inputs_do_not_establish_absence(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "empty/package.json", {"scripts": {}})
    _write(tmp_path, "omitted/package.json", {})
    packet = _observe(
        tmp_path, "empty/package.json", "omitted/package.json", "missing/package.json"
    )
    values = _values(packet)
    assert values["empty/package.json"]["declared_fields"] == ["scripts"]
    assert values["omitted/package.json"]["declared_fields"] == []
    assert packet["providers"][0]["provenance"]["missing_selected_paths"] == [
        "missing/package.json"
    ]
    assert all(
        value["negative_evidence_admissible"] is False for value in values.values()
    )
    assert all(
        group["coverage"]["state"] == "incomplete"
        for group in packet["declarations"]["groups"]
    )


@pytest.mark.parametrize(
    "text",
    [
        '{"scripts":{},"scripts":{"verify":"tool"}}',
        '{"scripts":{"verify":42}}',
        '{"dependencies":{"tool":null}}',
        '{"bin":42}',
        '{"scripts":NaN}',
        "[]",
        "{",
    ],
)
def test_malformed_or_ambiguous_selected_json_fails_closed(
    tmp_path: Path, text: str
) -> None:
    (tmp_path / "package.json").write_text(text, encoding="utf-8")
    with pytest.raises(RepositoryDeclarationProviderError):
        _observe(tmp_path, "package.json")


def test_excessive_supported_fields_fail_without_partial_declarations(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "package.json",
        {"scripts": {f"script-{n}": "tool" for n in range(MAX_NPM_ENTRIES + 1)}},
    )
    with pytest.raises(RepositoryDeclarationProviderError):
        _observe(tmp_path, "package.json")


def test_explicit_custom_fields_are_opaque_transport_without_implicit_disclosure(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "package.json",
        {"consumerPolicy": {"selected": "candidate"}, "privateExtra": "excluded"},
    )
    assert (
        _values(_observe(tmp_path, "package.json"))["package.json"]["selected_fields"]
        == {}
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.declarations.discover(
            [NpmManifestDeclarations(("package.json",), fields=("consumerPolicy",))]
        )
    value = _values(packet)["package.json"]
    assert value["selected_fields"] == {"consumerPolicy": {"selected": "candidate"}}
    assert "privateExtra" not in value
    assert value["native_interpretation"] == "not-established"


@pytest.mark.parametrize(
    "paths", [(), ("uv.lock",), ("../package.json",), ("package.json", "package.json")]
)
def test_selection_requires_explicit_canonical_npm_paths(
    paths: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        NpmManifestDeclarations(paths)
