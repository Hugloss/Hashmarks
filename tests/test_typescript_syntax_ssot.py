"""The TypeScript compiler resolves canonical syntax; it never rediscovers it."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_array, assert_object, assert_records, assert_text

from hashmarks.codemap import CodeMap
from hashmarks.codemap.providers import TreeSitterRangeProvider
from hashmarks.codemap.typescript_resolver import (
    TypeScriptResolution,
    TypeScriptResolverProvider,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


@pytest.fixture
def compiler_workspace(tmp_path: Path) -> Path:
    """Exercise the real Node boundary with a bounded compiler API specimen."""
    if shutil.which("node") is None:
        pytest.skip("native Node executable unavailable")
    module = tmp_path / "node_modules" / "typescript"
    module.mkdir(parents=True)
    (module / "index.js").write_text(
        """
const fs = require('fs');
const path = require('path');
exports.version = 'specimen';
exports.sys = {readFile: file => fs.readFileSync(file, 'utf8')};
exports.readConfigFile = (file, read) => ({config: JSON.parse(read(file))});
exports.parseJsonConfigFileContent = (config, host, base) => {
  const inherited = config.extends ? JSON.parse(host.readFile(path.resolve(base,config.extends))) : {};
  return ({
  fileNames: (config.files || []).map(file => path.resolve(base, file)),
  options: config.compilerOptions || inherited.compilerOptions,
  projectReferences: (config.references || []).map(row => ({path:path.resolve(base,row.path)})),
}); };
exports.resolveProjectReferencePath = row => row.path.endsWith('.json') ? row.path : path.join(row.path,'tsconfig.json');
exports.preProcessFile = () => {throw new Error('duplicate source parser invoked');};
exports.resolveModuleName = (specifier, file, options) => ({
  resolvedModule: options.paths[specifier] && {
    resolvedFileName: path.resolve(options.paths[specifier][0])
  }
});
""",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "value.ts").write_text(
        "export const value = 1;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "caller.ts").write_text(
        "const example = \"import x from 'decoy'\";\n"
        "/* import x from 'decoy'; */\n"
        "import {\n value\n} from '@app/value';\n"
        "export const result = value;\n",
        encoding="utf-8",
    )
    (tmp_path / "tsconfig.json").write_text(
        json.dumps(
            {
                "files": ["src/caller.ts", "src/value.ts"],
                "compilerOptions": {
                    "paths": {
                        "@app/value": ["src/value.ts"],
                        "decoy": ["src/decoy.ts"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_native_resolution_requires_canonical_source_imports(tmp_path: Path) -> None:
    result = TypeScriptResolverProvider(node="must-not-run").collect(tmp_path)
    assert result.edges == ()
    assert result.warnings == ("canonical source imports unavailable",)


def _project_test(root: Path, source: str, *, name: str = "value.test.ts") -> str:
    path = "src/" + name
    (root / path).write_text(source)
    (root / "package.json").write_text('{"devDependencies":{"vitest":"*"}}')
    config = json.loads((root / "tsconfig.json").read_text())
    config["files"].append(path)
    (root / "tsconfig.json").write_text(json.dumps(config))
    return path


@pytest.mark.parametrize("use", ["value();", "const rendered = <Widget />;"])
def test_changed_set_qualifies_used_native_import_identity_without_runtime_claim(
    compiler_workspace: Path, use: str
) -> None:
    (compiler_workspace / "src/value.ts").write_text(
        "export function value() { return 1; }\n"
    )
    path = _project_test(
        compiler_workspace,
        "import { value, value as Widget } from '@app/value';\n" + use,
        name="value.test.tsx",
    )
    with CodeMap(compiler_workspace) as native:
        native.index.sync()
        packet = native.verification.changed_set(("src/value.ts",))
    assert [row["path"] for row in assert_records(packet["targets"])] == [path]
    change = assert_records(packet["changes"])[0]
    evidence = assert_object(
        assert_records(change["relationships"])[0]["reference_evidence"]
    )
    assert evidence["reference_strength"] == "qualified-source-reference"
    source = assert_object(evidence["source_reference_evidence"])
    assert source["runtime_execution"] == "not-established"
    assert assert_records(source["compilers"])[0]["entry_file_sha256"]


@pytest.mark.parametrize(
    "source",
    [
        "import {value} from '@app/value';\nconst unrelated = 1;",
        "import type {value} from '@app/value';\ntype Alias = typeof value;",
        "import {value} from '@app/value';\nfunction check(value) { return value(); }",
        "import {value} from '@app/value';\nvalue = other; value();",
    ],
)
def test_unused_type_only_shadowed_and_reassigned_imports_cannot_become_value_proof(
    compiler_workspace: Path, source: str
) -> None:
    path = _project_test(compiler_workspace, source)
    with CodeMap(compiler_workspace) as native:
        native.index.sync()
        packet = native.verification.changed_set(("src/value.ts",))
    assert path not in {row["path"] for row in assert_records(packet["targets"])}


def test_type_only_static_source_requires_native_project_and_preserves_configuration(
    compiler_workspace: Path,
) -> None:
    path = _project_test(
        compiler_workspace, "export interface Value { name: string }", name="types.ts"
    )
    with CodeMap(compiler_workspace) as native:
        native.index.sync()
        packet = native.verification.changed_set((path,))
    fact = assert_object(
        assert_object(assert_records(packet["changes"])[0]["classification"])[
            "static_project"
        ]
    )
    assert (
        fact["kind"] == "type-only-static-project"
        and fact["qualification"] == "qualified"
    )
    assert assert_records(fact["configuration_inputs"])[0]["member_revision"]
    assert fact["runtime_execution"] == "not-established"


def test_indirect_source_use_preserves_intermediate_and_stops_after_use_removal(
    compiler_workspace: Path,
) -> None:
    config_path = compiler_workspace / "tsconfig.json"
    config = json.loads(config_path.read_text())
    config["compilerOptions"]["paths"]["@caller"] = ["src/caller.ts"]
    config_path.write_text(json.dumps(config))
    path = _project_test(
        compiler_workspace, "import {result} from '@caller';\ncheck(result);"
    )
    with CodeMap(compiler_workspace) as native:
        native.index.sync()
        before = native.verification.changed_set(("src/value.ts",))
        relation = assert_records(
            assert_records(before["changes"])[0]["relationships"]
        )[0]
        evidence = assert_object(relation["reference_evidence"])
        assert evidence["reference_strength"] == "qualified-indirect-source-reference"
        proof = assert_object(evidence["source_reference_evidence"])
        assert proof["via"] == ["src/caller.ts"]
        bindings = assert_object(proof["binding_observations"])
        assert "src/caller.ts" in bindings and path in bindings
        (compiler_workspace / "src/caller.ts").write_text(
            "import {value} from '@app/value';\nexport const result = 1;"
        )
        native.index.sync(("src/caller.ts",))
        after = native.verification.changed_set(("src/value.ts",))
    assert path not in {row["path"] for row in assert_records(after["targets"])}


@pytest.mark.parametrize("form", ["use", "reexport"])
@pytest.mark.parametrize("depth", [7, 8])
def test_source_and_reexport_hop_exhaustion_remains_incomplete(
    compiler_workspace: Path, form: str, depth: int
) -> None:
    config_path = compiler_workspace / "tsconfig.json"
    config = json.loads(config_path.read_text())
    for index in range(depth):
        path = f"src/hop{index}.ts"
        following = f"@hop{index + 1}" if index + 1 < depth else "@app/value"
        source = (
            f"export {{value}} from '{following}';"
            if form == "reexport"
            else f"import {{value as nextValue}} from '{following}';\nexport const value = () => nextValue;"
        )
        (compiler_workspace / path).write_text(source)
        config["files"].append(path)
        config["compilerOptions"]["paths"][f"@hop{index}"] = [path]
    config_path.write_text(json.dumps(config))
    test_path = _project_test(
        compiler_workspace, "import {value} from '@hop0';\ncheck(value);"
    )
    with CodeMap(compiler_workspace) as native:
        native.index.sync()
        packet = native.verification.changed_set(("src/value.ts",))
    targets = {row["path"] for row in assert_records(packet["targets"])}
    assert (test_path in targets) == (depth == 7)
    relevance = assert_object(assert_records(packet["changes"])[0]["relevance"])
    assert relevance["negative_evidence_admissible"] is False
    if depth == 8:
        assert any(
            "hop-bound" in assert_text(reason)
            for reason in assert_array(relevance["search_bound_reasons"])
        )


@pytest.mark.parametrize("name", ["base.options", "base"])
def test_native_non_json_config_closure_is_retained_and_drift_cannot_qualify(
    compiler_workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    config_path = compiler_workspace / "tsconfig.json"
    config = json.loads(config_path.read_text())
    (compiler_workspace / name).write_text(
        json.dumps({"compilerOptions": config.pop("compilerOptions")})
    )
    config["extends"] = "./" + name
    config_path.write_text(json.dumps(config))
    path = _project_test(
        compiler_workspace, "export interface Value { name: string }", name="types.ts"
    )
    with CodeMap(compiler_workspace) as native:
        native.index.sync()
        before = native.verification.changed_set((path,))
        fact = assert_object(
            assert_object(assert_records(before["changes"])[0]["classification"])[
                "static_project"
            ]
        )
        inputs = assert_records(fact["configuration_inputs"])
        assert name in {row["path"] for row in inputs}
        collect = native.native.producers.typescript.collect

        def change(
            workspace: Path,
            imports: Mapping[str, Sequence[str]],
            *,
            config_paths: Sequence[str] = ("tsconfig.json",),
            admitted_paths: Sequence[str] | None = None,
        ) -> TypeScriptResolution:
            result = collect(
                workspace,
                imports,
                config_paths=config_paths,
                admitted_paths=admitted_paths,
            )
            selected = compiler_workspace / name
            selected.write_text(selected.read_text() + "\n")
            return result

        monkeypatch.setattr(native.native.producers.typescript, "collect", change)
        after = native.verification.changed_set((path,))
    assert "static_project" not in assert_object(
        assert_records(after["changes"])[0]["classification"]
    )


def test_native_compiler_resolves_only_supplied_occurrences(
    compiler_workspace: Path,
) -> None:
    # There are no caller bytes left for another source scanner to discover.
    (compiler_workspace / "src" / "caller.ts").unlink()
    result = TypeScriptResolverProvider().collect(
        compiler_workspace,
        {"src/caller.ts": ["@app/value"], "not-in-tsconfig.ts": ["decoy"]},
    )
    assert not result.warnings
    assert [(row.source, row.target, row.specifier) for row in result.edges] == [
        ("src/caller.ts", "src/value.ts", "@app/value")
    ]
    assert result.producer == "typescript-resolver:specimen:canonical-syntax.v2"


def test_native_results_cannot_add_unobserved_source_occurrences() -> None:
    result = TypeScriptResolverProvider._resolution(
        {
            "version": "specimen",
            "edges": [
                {"source": "caller.ts", "target": "a.ts", "specifier": "a"},
                {"source": "caller.ts", "target": "b.ts", "specifier": "b"},
                {"source": "other.ts", "target": "a.ts", "specifier": "a"},
                {"source": "caller.ts", "target": "a.ts"},
            ],
        },
        {"caller.ts": ["a"]},
    )
    assert [(row.source, row.specifier) for row in result.edges] == [("caller.ts", "a")]
    assert result.warnings == (
        "TypeScript resolver discarded 3 unqualified source edges",
    )


@pytest.mark.parametrize(
    "payload", [{}, {"edges": None}, {"edges": {}}, {"edges": "[]"}]
)
def test_missing_or_invalid_native_edges_remain_unavailable(payload: object) -> None:
    result = TypeScriptResolverProvider._resolution(payload, {"caller.ts": ["a"]})
    assert result.edges == ()
    assert result.warnings == ("TypeScript resolver edges unavailable: expected array",)


def test_indexed_native_syntax_is_reused_for_compiler_resolution(
    compiler_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = TreeSitterRangeProvider.auto()
    assert provider.available
    with CodeMap(
        compiler_workspace,
        artifact_db=compiler_workspace / "artifacts.sqlite3",
        range_provider=provider,
    ) as codemap:
        codemap.index.sync()

        def no_reparse(source: bytes, language: str) -> None:
            raise AssertionError("native resolution must reuse indexed source facts")

        monkeypatch.setattr(provider, "syntax_tree", no_reparse)
        result = codemap.native.enrich_projects(("typescript-resolver",))
        assert result["warnings"] == []
        edges = result["native_file_edges"]
        assert isinstance(edges, list)
        assert [(edge["source"], edge["target"]) for edge in edges] == [
            ("src/caller.ts", "src/value.ts")
        ]


@pytest.mark.parametrize(
    "failure", ["missing-parser", "malformed-source", "changed-provider"]
)
def test_compiler_cannot_restore_unqualified_source_syntax(
    compiler_workspace: Path, failure: str
) -> None:
    provider = (
        TreeSitterRangeProvider()
        if failure == "missing-parser"
        else TreeSitterRangeProvider.auto()
    )
    if failure == "malformed-source":
        (compiler_workspace / "src" / "caller.ts").write_text(
            "import { value } from '@app/value';\nfunction broken( {",
            encoding="utf-8",
        )
    with CodeMap(
        compiler_workspace,
        artifact_db=compiler_workspace / "artifacts.sqlite3",
        range_provider=provider,
    ) as codemap:
        codemap.index.sync()
        if failure == "changed-provider":
            codemap.index.range_provider = TreeSitterRangeProvider()
        result = codemap.native.enrich_projects(("typescript-resolver",))
        assert result["native_file_edges"] == []
        warnings = result["warnings"]
        assert isinstance(warnings, list)
        assert "src/caller.ts: canonical source syntax unavailable" in warnings


@pytest.mark.parametrize("changed", ["src/caller.ts", "tsconfig.json"])
def test_source_change_during_native_resolution_discards_new_edges(
    compiler_workspace: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    with CodeMap(
        compiler_workspace, artifact_db=compiler_workspace / "artifacts.sqlite3"
    ) as codemap:
        codemap.index.sync()
        provider = codemap.native.producers.typescript
        collect = provider.collect

        def mutate(
            workspace: Path,
            imports: dict[str, list[str]],
            *,
            config_paths: tuple[str, ...] = ("tsconfig.json",),
            admitted_paths: tuple[str, ...] | None = None,
        ) -> TypeScriptResolution:
            result = collect(
                workspace,
                imports,
                config_paths=config_paths,
                admitted_paths=admitted_paths,
            )
            path = workspace / changed
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            return result

        monkeypatch.setattr(provider, "collect", mutate)
        result = codemap.native.enrich_projects(("typescript-resolver",))
        assert result["native_file_edges"] == []
        warnings = result["warnings"]
        assert isinstance(warnings, list)
        assert (
            f"TypeScript source inputs changed during resolution: {changed}" in warnings
        )


def test_source_change_before_native_resolution_clears_retained_edges(
    compiler_workspace: Path,
) -> None:
    with CodeMap(
        compiler_workspace, artifact_db=compiler_workspace / "artifacts.sqlite3"
    ) as codemap:
        codemap.index.sync()
        original = codemap.native.enrich_projects(("typescript-resolver",))
        assert original["native_file_edges"]
        (compiler_workspace / "src" / "caller.ts").write_text(
            "export const changed = 1;\n", encoding="utf-8"
        )
        result = codemap.native.enrich_projects(("typescript-resolver",))
        assert result["native_file_edges"] == []
        warnings = result["warnings"]
        assert isinstance(warnings, list)
        assert "src/caller.ts: canonical source revision unavailable" in warnings


def test_provider_change_during_native_resolution_discards_new_edges(
    compiler_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    syntax = TreeSitterRangeProvider.auto()
    with CodeMap(
        compiler_workspace,
        artifact_db=compiler_workspace / "artifacts.sqlite3",
        range_provider=syntax,
    ) as codemap:
        codemap.index.sync()
        provider = codemap.native.producers.typescript
        collect = provider.collect

        def mutate_provider(
            workspace: Path,
            imports: dict[str, list[str]],
            *,
            config_paths: tuple[str, ...] = ("tsconfig.json",),
            admitted_paths: tuple[str, ...] | None = None,
        ) -> TypeScriptResolution:
            result = collect(
                workspace,
                imports,
                config_paths=config_paths,
                admitted_paths=admitted_paths,
            )
            assert result.edges
            syntax.version = "changed-after-resolution"
            return result

        monkeypatch.setattr(provider, "collect", mutate_provider)
        result = codemap.native.enrich_projects(("typescript-resolver",))
        assert result["native_file_edges"] == []
        warnings = result["warnings"]
        assert isinstance(warnings, list)
        assert (
            "TypeScript syntax provider changed during resolution: "
            "src/caller.ts, src/value.ts" in warnings
        )
