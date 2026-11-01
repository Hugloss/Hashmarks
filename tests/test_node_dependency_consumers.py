"""Static native ECMAScript imports preserve npm metadata uncertainty."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.adapters import npm_lock_dependency_observation
from hashmarks.codemap.providers import TreeSitterRangeProvider
from hashmarks.file_store import UnstableFileError


@pytest.fixture
def native_syntax() -> TreeSitterRangeProvider:
    pytest.importorskip("tree_sitter_language_pack")
    provider = TreeSitterRangeProvider.auto()
    assert provider.available
    return provider


def _snapshot(*, nested: bool = False) -> dict[str, object]:
    packages: dict[str, object] = {
        "": {"name": "application", "version": "1.0"},
        "node_modules/@scope/alias": {"name": "real-package", "version": "1.0"},
    }
    if nested:
        packages["node_modules/parent/node_modules/@scope/alias"] = {
            "name": "real-package",
            "version": "2.0",
        }
    return npm_lock_dependency_observation(
        lock=json.dumps({"lockfileVersion": 3, "packages": packages}).encode()
    )


def _nodes(observation: dict[str, object]) -> list[str]:
    return [str(row["node_id"]) for row in assert_records(observation["selections"])]


def test_native_imports_side_effects_and_reexports_use_declared_alias_ownership(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider
) -> None:
    (tmp_path / "bridge.ts").write_text(
        'import "@scope/alias";\n'
        'import type { Channel } from "@scope/alias/types";\n'
        'export * from "@scope/alias/subpath";\n'
        'import guessed from "real-package";\n'
    )
    (tmp_path / "caller.ts").write_text('import "./bridge";\n')
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        raw = _snapshot()
        assert_object(raw["producer"])["kind"] = "another-native-producer"
        observation = codemap.dependencies.observe(raw)
        result = codemap.dependencies.consumers(
            observation,
            source_paths=["caller.ts", "bridge.ts"],
            node_ids=_nodes(observation),
        )
    rows = assert_records(result["consumers"])
    assert [(row["import_target"], row["type_only"]) for row in rows] == [
        ("@scope/alias", False),
        ("@scope/alias/types", True),
        ("@scope/alias/subpath", False),
    ]
    assert all(row["runtime_resolution"] == "not-observed" for row in rows)
    assert all(row["ecosystem"] == "npm" for row in rows)
    assert all(assert_object(row["syntax_evidence"])["fact_identity"] for row in rows)
    assert all(row["ownership_completeness"] == "incomplete" for row in rows)
    assert result["observed_consumer_count"] == 3
    assert assert_object(result["capability"])["state"] == "supported"
    scope = assert_object(result["consumer_scope"])
    assert scope["negative_evidence"] == "not-admissible"
    assert "typescript-path-mappings-not-resolved" in assert_array(scope["reasons"])
    downstream = assert_object(
        assert_records(result["downstream_relationships"])[0]["relationships"]
    )
    assert "caller.ts" in assert_array(downstream["affected_files"])
    assert (
        result["execution_authority"] == result["certification_authority"] == "external"
    )


def test_nested_selection_ambiguity_is_not_removed_by_caller_selection(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider
) -> None:
    (tmp_path / "consumer.mjs").write_text('import "@scope/alias";\n')
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(_snapshot(nested=True))
        result = codemap.dependencies.consumers(
            observation, source_paths=["consumer.mjs"], node_ids=_nodes(observation)[:1]
        )
    row = assert_records(result["consumers"])[0]
    assert row["distribution_state"] == "resolved-ambiguous"
    assert row["distribution_nodes"] == sorted(_nodes(observation))
    assert row["observed_contexts"] == ["lock"]


def test_supported_and_unsupported_selected_ecosystems_remain_independent(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider
) -> None:
    (tmp_path / "consumer.js").write_text('import "@scope/alias";\n')
    raw = _snapshot()
    assert_array(raw["components"]).append(
        {"component_id": "other", "name": "other", "ecosystem": "maven"}
    )
    assert_array(raw["selections"]).append(
        {
            "node_id": "other:1",
            "component_id": "other",
            "version": "1",
            "contexts": ["lock"],
            "evidence_sources": ["npm:lock"],
        }
    )
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(raw)
        result = codemap.dependencies.consumers(
            observation,
            source_paths=["consumer.js"],
            node_ids=_nodes(observation),
        )
    assert len(assert_records(result["consumers"])) == 1
    assert assert_object(result["capability"])["state"] == "partial"
    assert assert_object(result["capability"])["unsupported_node_ids"] == ["other:1"]
    assert "unsupported-selected-ecosystem" in assert_array(
        assert_object(result["consumer_scope"])["reasons"]
    )


def test_dynamic_commonjs_strings_and_unknown_literal_syntax_do_not_invent_consumers(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider
) -> None:
    (tmp_path / "consumer.ts").write_text(
        '// import "@scope/alias";\n'
        'const text = "import @scope/alias";\n'
        'import("@scope/alias");\n'
        'require("@scope/alias");\n'
        'import "@scope/ali\\u0061s";\n'
        'import "./local";\n'
        'import "#internal";\n'
        'import "node:fs";\n'
    )
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(_snapshot())
        result = codemap.dependencies.consumers(
            observation, source_paths=["consumer.ts"], node_ids=_nodes(observation)
        )
    assert result["consumers"] == []
    source = assert_records(assert_object(result["source_scope"])["observations"])[0]
    assert source["completeness"] == "incomplete"
    assert source["reasons"] == [
        "dynamic-or-commonjs-loading-not-observed",
        "nonliteral-module-declaration-not-observed",
    ]
    assert (
        assert_object(result["consumer_scope"])["negative_evidence"] == "not-admissible"
    )


def test_result_limit_and_native_fact_limit_preserve_incomplete_evidence(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider
) -> None:
    (tmp_path / "consumer.ts").write_text('import "@scope/alias";\n' * 501)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(_snapshot())
        result = codemap.dependencies.consumers(
            observation,
            source_paths=["consumer.ts"],
            node_ids=_nodes(observation),
            limit=2,
        )
    assert len(assert_records(result["consumers"])) == 2
    assert result["observed_consumer_count"] == 500
    assert result["truncation"] == "truncated"
    scope = assert_object(result["source_scope"])
    assert scope["completeness"] == "incomplete"
    assert assert_records(scope["observations"])[0]["truncation"] == "truncated"
    assert (
        assert_object(result["consumer_scope"])["negative_evidence"] == "not-admissible"
    )


def test_native_syntax_unavailable_or_malformed_is_unknown(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider
) -> None:
    (tmp_path / "broken.ts").write_text('import { from "@scope/alias";\n')
    (tmp_path / "consumer.ts").write_text('import "@scope/alias";\n')
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(_snapshot())
        malformed = codemap.dependencies.consumers(
            observation,
            source_paths=["broken.ts", "missing.ts"],
            node_ids=_nodes(observation),
        )
        codemap.index.range_provider = TreeSitterRangeProvider()
        unavailable = codemap.dependencies.consumers(
            observation, source_paths=["consumer.ts"], node_ids=_nodes(observation)
        )
    assert malformed["consumers"] == unavailable["consumers"] == []
    assert assert_object(malformed["source_scope"])["unavailable"] == [
        "broken.ts",
        "missing.ts",
    ]
    source = assert_records(assert_object(unavailable["source_scope"])["observations"])[
        0
    ]
    assert source["reasons"] == ["native-syntax-unavailable"]
    assert source["completeness"] == "unknown"


def test_native_source_drift_during_downstream_observation_is_rejected(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "consumer.ts").write_text('import "@scope/alias";\n')
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(_snapshot())
        original = codemap.relationships.affected

        def mutate(query: str, *, max_depth: int = 12) -> dict[str, object]:
            result = original(query, max_depth=max_depth)
            (tmp_path / "consumer.ts").write_text("export const changed = true;\n")
            return result

        monkeypatch.setattr(codemap.relationships, "affected", mutate)
        with pytest.raises(UnstableFileError, match="source changed"):
            codemap.dependencies.consumers(
                observation, source_paths=["consumer.ts"], node_ids=_nodes(observation)
            )


@pytest.mark.parametrize("nodes", [["unknown"], ["same", "same"]])
def test_unknown_or_duplicate_node_ids_remain_request_errors(
    tmp_path: Path, nodes: list[str]
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(_snapshot())
        with pytest.raises(ValueError, match="unique known dependency selections"):
            codemap.dependencies.consumers(
                observation, source_paths=["missing.ts"], node_ids=nodes
            )
