"""The TypeScript compiler resolves canonical syntax; it never rediscovers it."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.providers import TreeSitterRangeProvider
from hashmarks.codemap.typescript_resolver import (
    TypeScriptResolution,
    TypeScriptResolverProvider,
)


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
exports.parseJsonConfigFileContent = config => ({
  fileNames: config.files.map(file => path.resolve(file)),
  options: config.compilerOptions,
});
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
    assert result.producer == "typescript-resolver:specimen:canonical-syntax.v1"


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
            workspace: Path, imports: dict[str, list[str]]
        ) -> TypeScriptResolution:
            result = collect(workspace, imports)
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
            workspace: Path, imports: dict[str, list[str]]
        ) -> TypeScriptResolution:
            result = collect(workspace, imports)
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
