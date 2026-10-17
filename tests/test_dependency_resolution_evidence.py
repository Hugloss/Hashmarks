from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_number, assert_object, assert_text

from hashmarks.codemap.engine import CodeMap


def _without_source_refs(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_source_refs(item)
            for key, item in value.items()
            if key != "evidence_sources"
        }
    if isinstance(value, list):
        return [_without_source_refs(item) for item in value]
    return value


def _snapshot_v3() -> dict[str, object]:
    return {
        "schema": "hashmarks.dependency-resolution.v3",
        "producer": {
            "kind": "neutral-resolver",
            "schema_version": "1",
            "adapter_semantics": "test.neutral-dependency-adapter.v1",
        },
        "scope": {"environment": "test"},
        "contexts": ["compile", "runtime"],
        "roots": [
            {
                "node_id": "app@1",
                "context": "compile",
                "evidence_sources": ["tree:compile"],
            },
            {
                "node_id": "app@1",
                "context": "runtime",
                "evidence_sources": ["tree:runtime"],
            },
        ],
        "evidence_sources": [
            {
                "source_id": "tree:compile",
                "kind": "test-resolution-source",
                "authorities": ["resolution-graph", "selection"],
                "context": "compile",
                "completeness": "complete",
                "truncation": "complete",
            },
            {
                "source_id": "tree:runtime",
                "kind": "test-resolution-source",
                "authorities": ["resolution-graph", "selection"],
                "context": "runtime",
                "completeness": "complete",
                "truncation": "complete",
            },
            {
                "source_id": "list:compile",
                "kind": "test-inventory-source",
                "authorities": ["module-ownership", "resolved-inventory", "selection"],
                "context": "compile",
                "completeness": "complete",
                "truncation": "complete",
            },
        ],
        "components": [
            {"component_id": "app", "name": "app", "ecosystem": "test"},
            {"component_id": "library", "name": "library", "ecosystem": "test"},
            {
                "component_id": "inventory-only",
                "name": "inventory-only",
                "ecosystem": "test",
            },
        ],
        "selections": [
            {
                "node_id": "app@1",
                "component_id": "app",
                "version": "1",
                "source": "workspace",
                "contexts": ["compile", "runtime"],
                "evidence_sources": ["tree:compile", "tree:runtime"],
            },
            {
                "node_id": "library@1",
                "component_id": "library",
                "version": "1",
                "source": "registry",
                "contexts": ["compile", "runtime"],
                "evidence_sources": ["tree:compile", "tree:runtime"],
            },
            {
                "node_id": "inventory-only@1",
                "component_id": "inventory-only",
                "version": "1",
                "source": "registry",
                "contexts": ["compile"],
                "evidence_sources": ["list:compile"],
            },
        ],
        "inventory": [
            {
                "node_id": "app@1",
                "context": "compile",
                "evidence_sources": ["list:compile"],
            },
            {
                "node_id": "library@1",
                "context": "compile",
                "evidence_sources": ["list:compile"],
            },
            {
                "node_id": "inventory-only@1",
                "context": "compile",
                "evidence_sources": ["list:compile"],
            },
        ],
        "relationships": [
            {
                "source": "app@1",
                "target": "library@1",
                "kind": "dependency",
                "context": "compile",
                "effective_scope": "compile",
                "evidence_sources": ["tree:compile"],
            },
            {
                "source": "app@1",
                "target": "library@1",
                "kind": "dependency",
                "context": "runtime",
                "effective_scope": "runtime",
                "evidence_sources": ["tree:runtime"],
            },
        ],
        "coverage": [
            {
                "context": "compile",
                "kind": "resolution-graph",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["tree:compile"],
            },
            {
                "context": "runtime",
                "kind": "resolution-graph",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["tree:runtime"],
            },
            {
                "context": "compile",
                "kind": "resolved-inventory",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["list:compile"],
            },
            {
                "context": "compile",
                "kind": "selection",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["list:compile", "tree:compile"],
            },
            {
                "context": "runtime",
                "kind": "selection",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["tree:runtime"],
            },
        ],
        "repository_inputs": [],
        "module_ownership": [],
    }


def test_v3_refuses_obsolete_v2_schema(tmp_path: Path) -> None:
    snapshot = _snapshot_v3()
    snapshot["schema"] = "hashmarks.dependency-resolution.v2"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="dependency resolution schema must be hashmarks.dependency-resolution.v3",
        ):
            codemap.dependency_resolution_evidence(snapshot)


@pytest.mark.parametrize("kind", ["depends-on", "conflicts-with"])
def test_v3_rejects_non_dependency_relationship_kind(tmp_path: Path, kind: str) -> None:
    snapshot = _snapshot_v3()
    assert_object(assert_array(snapshot["relationships"])[0])["kind"] = kind

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError, match=f"unsupported dependency relationship kind: {kind}"
        ):
            codemap.dependency_resolution_evidence(snapshot)


def test_v3_replay_rejects_non_dependency_relationship_kind(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        tampered = copy.deepcopy(observation)
        assert_object(assert_array(tampered["relationships"])[0])["kind"] = (
            "conflicts-with"
        )

        with pytest.raises(
            ValueError, match="unsupported dependency relationship kind"
        ):
            codemap.dependency_resolution_queries(
                tampered, [{"operation": "inventory"}]
            )
        with pytest.raises(
            ValueError, match="unsupported dependency relationship kind"
        ):
            codemap.dependency_resolution_delta(observation, tampered)


def test_v3_distinguishes_inventory_membership_from_graph_reachability(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(_snapshot_v3())

    inventory_nodes = {
        assert_object(row)["node_id"] for row in assert_array(packet["inventory"])
    }
    graph_nodes = {
        endpoint
        for row in assert_array(packet["relationships"])
        for endpoint in (assert_object(row)["source"], assert_object(row)["target"])
    }
    assert "inventory-only@1" in inventory_nodes
    assert "inventory-only@1" not in graph_nodes


def test_v3_separates_component_selection_and_observation_identity(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.dependency_resolution_evidence(_snapshot_v3())
        changed = _snapshot_v3()
        changed["module_ownership"] = [
            {
                "module": "library.module",
                "context": "compile",
                "owners": ["library@1"],
                "completeness": "complete",
                "evidence_sources": ["list:compile"],
            }
        ]
        second = codemap.dependency_resolution_evidence(changed)

    assert first["resolution_identity"] == second["resolution_identity"]
    assert first["observation_identity"] != second["observation_identity"]


def test_v3_public_consumers_revalidate_qualified_observation(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        assert observation["root_evidence"]
        reopened = json.loads(json.dumps(observation))
        assert (
            codemap.dependency_resolution_queries(
                reopened, [{"operation": "inventory", "node_id": "missing"}]
            )["observation_identity"]
            == observation["observation_identity"]
        )
        tampered = copy.deepcopy(observation)
        assert_object(tampered["producer"])["kind"] = "changed-after-qualification"

        consumers = (
            lambda: codemap.dependency_resolution_queries(
                tampered, [{"operation": "inventory", "node_id": "missing"}]
            ),
            lambda: codemap.dependency_resolution_delta(observation, tampered),
            lambda: codemap.dependency_import_correspondence(
                tampered, source_path="app.py", import_target="library"
            ),
            lambda: codemap.dependency_evidence_correlation(
                tampered, {"correlations": []}
            ),
        )
        for consume in consumers:
            with pytest.raises(ValueError, match="content identity mismatch"):
                consume()


def test_v3_queries_reject_foreign_repository_observation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    consumer = tmp_path / "consumer"
    source.mkdir()
    consumer.mkdir()
    with CodeMap(source) as source_map:
        source_map.sync()
        observation = source_map.dependency_resolution_evidence(_snapshot_v3())

    with CodeMap(consumer) as consumer_map:
        consumer_map.sync()
        with pytest.raises(ValueError, match="repository binding mismatch"):
            consumer_map.dependency_resolution_queries(
                observation, [{"operation": "inventory"}]
            )


def test_v3_queries_reject_stale_repository_generation(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        (tmp_path / "new.py").write_text("VALUE = 1\n", encoding="utf-8")
        codemap.sync(["new.py"])
        with pytest.raises(ValueError, match="repository binding mismatch"):
            codemap.dependency_resolution_queries(
                observation, [{"operation": "inventory"}]
            )


def test_v3_revalidation_rejects_unqualified_coverage_claim(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        tampered = copy.deepcopy(observation)
        assert_array(tampered["coverage"]).append(
            {
                "context": "runtime",
                "kind": "resolved-inventory",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["invented-source"],
            }
        )
        with pytest.raises(ValueError, match="dangling coverage evidence source"):
            codemap.dependency_resolution_queries(
                tampered, [{"operation": "inventory", "node_id": "missing"}]
            )


def test_v3_revalidation_binds_root_evidence_sources(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        tampered = copy.deepcopy(observation)
        assert_object(assert_array(tampered["root_evidence"])[0])[
            "evidence_sources"
        ] = ["list:compile"]
        with pytest.raises(ValueError, match="root requires resolution-graph"):
            codemap.dependency_resolution_queries(
                tampered, [{"operation": "inventory", "node_id": "missing"}]
            )


def test_v3_identity_separates_semantics_from_producer_provenance(
    tmp_path: Path,
) -> None:
    base = _snapshot_v3()
    provenance = copy.deepcopy(base)
    provenance["producer"] = {"kind": "other-resolver", "schema_version": "9"}
    for source in assert_array(provenance["evidence_sources"]):
        assert_object(source)["kind"] = "other-source-format"
        assert_object(source)["producer_digest"] = "sha256:other"
    semantic_scope = copy.deepcopy(base)
    semantic_scope["scope"] = {"environment": "production"}
    changed_resolution = copy.deepcopy(base)
    assert_object(assert_array(changed_resolution["selections"])[1])["version"] = "2"
    changed_coverage = copy.deepcopy(base)
    assert_object(assert_array(changed_coverage["coverage"])[0])["completeness"] = (
        "incomplete"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        original = codemap.dependency_resolution_evidence(base)
        other_producer = codemap.dependency_resolution_evidence(provenance)
        other_scope = codemap.dependency_resolution_evidence(semantic_scope)
        other_resolution = codemap.dependency_resolution_evidence(changed_resolution)
        other_coverage = codemap.dependency_resolution_evidence(changed_coverage)
        delta = codemap.dependency_resolution_delta(original, other_producer)
        scope_delta = codemap.dependency_resolution_delta(original, other_scope)

    assert original["definition_identity"] == other_producer["definition_identity"]
    assert original["resolution_identity"] == other_producer["resolution_identity"]
    assert original["observation_identity"] != other_producer["observation_identity"]
    assert delta["comparability"] == "comparable"
    assert delta["selections_changed"] == []
    assert original["definition_identity"] != other_scope["definition_identity"]
    assert original["resolution_identity"] != other_scope["resolution_identity"]
    assert scope_delta["comparability"] == "not-comparable"
    assert scope_delta["producer_authority"] == "caller-claimed"
    assert original["definition_identity"] == other_resolution["definition_identity"]
    assert original["resolution_identity"] != other_resolution["resolution_identity"]
    assert original["resolution_identity"] == other_coverage["resolution_identity"]
    assert original["observation_identity"] != other_coverage["observation_identity"]


def test_v3_derivation_authority_is_traceable_without_history_store(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    for source in assert_array(snapshot["evidence_sources"]):
        assert_object(source)["producer_digest"] = "sha256:" + "a" * 64

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(snapshot)
        derivation = codemap.dependency_resolution_derivation_authority(observation)

    assert derivation["schema"] == "hashmarks.dependency-resolution-derivation.v1"
    assert derivation["definition_identity"] == observation["definition_identity"]
    assert derivation["resolution_identity"] == observation["resolution_identity"]
    assert derivation["observation_identity"] == observation["observation_identity"]
    assert derivation["repository_binding"] == observation["repository_binding"]
    assert derivation["repository_inputs"] == observation["repository_inputs"]
    assert derivation["adapter_semantics"] == "test.neutral-dependency-adapter.v1"
    assert (
        derivation["qualification_semantics"]
        == "hashmarks.dependency-resolution-qualification.v3"
    )
    assert derivation["contributing_source_ids"] == [
        "list:compile",
        "tree:compile",
        "tree:runtime",
    ]
    assert {
        assert_object(row)["source_id"]
        for row in assert_array(derivation["evidence_sources"])
    } == {
        "list:compile",
        "tree:compile",
        "tree:runtime",
    }
    assert (
        len(
            {
                assert_object(row)["producer_digest"]
                for row in assert_array(derivation["evidence_sources"])
            }
        )
        == 1
    )
    assert derivation["semantic_authorities"] == [
        "module-ownership",
        "resolution-graph",
        "resolved-inventory",
        "selection",
    ]


def test_v3_derivation_authority_accepts_caller_retained_old_endpoint(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        original_binding = copy.deepcopy(observation["repository_binding"])

        (tmp_path / "later.py").write_text("VALUE = 1\n", encoding="utf-8")
        codemap.sync(["later.py"])

        derivation = codemap.dependency_resolution_derivation_authority(observation)

    assert derivation["repository_binding"] == original_binding
    assert derivation["observation_identity"] == observation["observation_identity"]


def test_v3_derivation_identity_changes_with_adapter_semantics_only(
    tmp_path: Path,
) -> None:
    before_raw = _snapshot_v3()
    after_raw = copy.deepcopy(before_raw)
    assert_object(after_raw["producer"])["adapter_semantics"] = (
        "test.neutral-dependency-adapter.v2"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(before_raw)
        after = codemap.dependency_resolution_evidence(after_raw)
        before_derivation = codemap.dependency_resolution_derivation_authority(before)
        after_derivation = codemap.dependency_resolution_derivation_authority(after)

    assert before["definition_identity"] == after["definition_identity"]
    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert (
        before_derivation["derivation_identity"]
        != after_derivation["derivation_identity"]
    )


def test_v3_derivation_authority_requires_explicit_adapter_semantics(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    assert_object(snapshot["producer"]).pop("adapter_semantics")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(snapshot)
        with pytest.raises(ValueError, match="adapter semantics must be a string"):
            codemap.dependency_resolution_derivation_authority(observation)


def test_v3_derivation_authority_revalidates_observation_before_projection(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        tampered = copy.deepcopy(observation)
        assert_object(assert_array(tampered["evidence_sources"])[0])["source_id"] = (
            "forged-source"
        )

        with pytest.raises(ValueError):
            codemap.dependency_resolution_derivation_authority(tampered)


def test_v3_opaque_empty_semantic_scope_is_valid(tmp_path: Path) -> None:
    snapshot = _snapshot_v3()
    snapshot["scope"] = {}
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)
    assert packet["scope"] == {}


@pytest.mark.parametrize(
    "authority",
    ["selection", "resolution-graph", "resolved-inventory", "module-ownership"],
)
def test_v3_each_coverage_domain_is_independent_of_source_completeness(
    tmp_path: Path,
    authority: str,
) -> None:
    snapshot = {
        "schema": "hashmarks.dependency-resolution.v3",
        "producer": {"kind": "generic", "schema_version": "1"},
        "scope": {},
        "contexts": ["empty"],
        "roots": [],
        "components": [],
        "selections": [],
        "inventory": [],
        "relationships": [],
        "module_ownership": [],
        "repository_inputs": [],
        "evidence_sources": [
            {
                "source_id": "one-artifact",
                "kind": "opaque",
                "authorities": [authority],
                "context": "empty",
                "completeness": "complete",
                "truncation": "complete",
            }
        ],
        "coverage": [
            {
                "context": "empty",
                "kind": authority,
                "completeness": "incomplete",
                "truncation": "complete",
                "evidence_sources": ["one-artifact"],
            }
        ],
    }
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        partial = codemap.dependency_resolution_evidence(snapshot)
        snapshot["coverage"][0]["completeness"] = "complete"
        complete = codemap.dependency_resolution_evidence(snapshot)
        snapshot["evidence_sources"][0]["completeness"] = "incomplete"
        with pytest.raises(ValueError, match="coverage exceeds evidence source"):
            codemap.dependency_resolution_evidence(snapshot)

    assert (
        assert_object(assert_array(partial["negative_evidence"])[0])["state"]
        == "not-admissible"
    )
    assert (
        assert_object(assert_array(complete["negative_evidence"])[0])["state"]
        == "admissible-within-declared-scope"
    )


def test_v3_negative_evidence_is_scoped_by_context_and_coverage_kind(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["coverage"])[1])["completeness"] = "incomplete"
    assert_object(assert_array(changed["coverage"])[1])["truncation"] = "truncated"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(changed)

    states = {
        (assert_object(row)["context"], assert_object(row)["kind"]): assert_object(row)[
            "state"
        ]
        for row in assert_array(packet["negative_evidence"])
    }
    assert states[("compile", "resolution-graph")] == "admissible-within-declared-scope"
    assert states[("runtime", "resolution-graph")] == "not-admissible"


@pytest.mark.parametrize(
    ("target", "field"),
    [
        ("snapshot", "adapter_hint"),
        ("source", "physical_source_id"),
        ("selection", "producer_selection_hint"),
        ("coverage", "producer_coverage_hint"),
    ],
)
def test_v3_refuses_unknown_authority_contract_fields(
    tmp_path: Path,
    target: str,
    field: str,
) -> None:
    changed = _snapshot_v3()
    if target == "snapshot":
        changed[field] = "unexpected"
    elif target == "source":
        assert_object(assert_array(changed["evidence_sources"])[0])[field] = (
            "unexpected"
        )
    elif target == "selection":
        assert_object(assert_array(changed["selections"])[0])[field] = "unexpected"
    else:
        assert_object(assert_array(changed["coverage"])[0])[field] = "unexpected"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="unknown dependency .* field"):
            codemap.dependency_resolution_evidence(changed)


@pytest.mark.parametrize(
    ("target", "field", "value", "message"),
    [
        ("producer", "kind", 123, "producer kind must be a string"),
        ("component", "component_id", True, "component_id must be a string"),
        ("component", "name", 123, "component name must be a string"),
        ("selection", "version", 1, "version must be a string"),
        ("selection", "source", False, "source must be a string"),
        ("relationship", "marker", 123, "marker must be a string"),
    ],
)
def test_v3_refuses_non_string_typed_fields(
    tmp_path: Path,
    target: str,
    field: str,
    value: object,
    message: str,
) -> None:
    changed = _snapshot_v3()
    if target == "producer":
        assert_object(changed["producer"])[field] = value
    elif target == "component":
        assert_object(assert_array(changed["components"])[0])[field] = value
    elif target == "selection":
        assert_object(assert_array(changed["selections"])[0])[field] = value
    else:
        assert_object(assert_array(changed["relationships"])[0])[field] = value

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match=message):
            codemap.dependency_resolution_evidence(changed)


def test_v3_rejects_dangling_evidence_source_reference(tmp_path: Path) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["relationships"])[0])["evidence_sources"] = [
        "missing"
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="dangling relationship evidence source"):
            codemap.dependency_resolution_evidence(changed)


def test_v3_delta_reports_selection_inventory_and_relationship_change(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(_snapshot_v3())
        changed = _snapshot_v3()
        assert_object(assert_array(changed["selections"])[1])["version"] = "2"
        changed["inventory"] = [
            row
            for row in assert_array(changed["inventory"])
            if assert_object(row)["node_id"] != "inventory-only@1"
        ]
        assert_object(assert_array(changed["relationships"])[0])["effective_scope"] = (
            "runtime"
        )
        after = codemap.dependency_resolution_evidence(changed)
        delta = codemap.dependency_resolution_delta(before, after)

    assert delta["selections_changed"] == ["library@1"]
    assert delta["inventory_removed"] == [["inventory-only@1", "compile"]]
    assert delta["relationships_added"] == [
        ["app@1", "library@1", "dependency", "compile", "runtime", ""]
    ]
    assert delta["relationships_removed"] == [
        ["app@1", "library@1", "dependency", "compile", "compile", ""]
    ]
    assert delta["causation"] == "not-inferred"


def test_v3_relationship_parent_change_is_not_selection_change(
    tmp_path: Path,
) -> None:
    before_snapshot = _snapshot_v3()
    after_snapshot = _snapshot_v3()
    assert_object(assert_array(after_snapshot["relationships"])[0])["source"] = (
        "inventory-only@1"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(before_snapshot)
        after = codemap.dependency_resolution_evidence(after_snapshot)
        delta = codemap.dependency_resolution_delta(before, after)

    assert delta["selections_added"] == []
    assert delta["selections_removed"] == []
    assert delta["selections_changed"] == []
    assert delta["relationships_removed"] == [
        ["app@1", "library@1", "dependency", "compile", "compile", ""]
    ]
    assert delta["relationships_added"] == [
        ["inventory-only@1", "library@1", "dependency", "compile", "compile", ""]
    ]


def test_v3_rejects_module_owner_outside_observed_context(tmp_path: Path) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["selections"])[1])["contexts"] = ["runtime"]
    assert_object(assert_array(changed["selections"])[1])["evidence_sources"] = [
        "tree:runtime"
    ]
    changed["inventory"] = [
        row
        for row in assert_array(changed["inventory"])
        if assert_object(row)["node_id"] != "library@1"
    ]
    changed["relationships"] = [
        row
        for row in assert_array(changed["relationships"])
        if assert_object(row)["target"] != "library@1"
        or assert_object(row)["context"] != "compile"
    ]
    changed["module_ownership"] = [
        {
            "module": "library.module",
            "context": "compile",
            "owners": ["library@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        }
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="module owner context not selected"):
            codemap.dependency_resolution_evidence(changed)


def test_v3_module_ownership_preserves_ambiguous_maven_module(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    snapshot["module_ownership"] = [
        {
            "module": "shared.module",
            "context": "compile",
            "owners": ["library@1", "inventory-only@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        }
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(snapshot)

    ownership = assert_array(observation["module_ownership"])[0]
    assert assert_object(ownership)["state"] == "resolved-ambiguous"
    assert assert_object(ownership)["owners"] == ["inventory-only@1", "library@1"]


def test_v3_repository_correspondence_refuses_foreign_repository_binding(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    with CodeMap(source) as source_map:
        source_map.sync()
        observation = source_map.dependency_resolution_evidence(_snapshot_v3())

    with CodeMap(target) as target_map:
        target_map.sync()
        with pytest.raises(
            ValueError,
            match="dependency observation repository binding mismatch",
        ):
            target_map.dependency_import_correspondence(
                observation,
                source_path="consumer.py",
                import_target="library",
            )


def test_v3_repository_correlation_refuses_stale_generation(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        (tmp_path / "changed.py").write_text("value = 1\n")
        codemap.sync()

        with pytest.raises(
            ValueError,
            match="dependency observation repository binding mismatch",
        ):
            codemap.dependency_evidence_correlation(
                observation,
                {"correlations": []},
            )


@pytest.mark.parametrize(
    "payload",
    [
        {"correlatons": []},
        {
            "correlations": [
                {
                    "module": "library",
                    "anchors": [],
                    "diagnosis": "caller-owned",
                }
            ]
        },
    ],
)
def test_v3_dependency_correlation_refuses_unknown_fields(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        with pytest.raises(ValueError, match="unknown dependency correlation"):
            codemap.dependency_evidence_correlation(observation, payload)


def test_v3_dependency_correlation_preserves_contextual_ownership(
    tmp_path: Path,
) -> None:
    (tmp_path / "consumer.py").write_text("import library\n")
    snapshot = _snapshot_v3()
    runtime_source = next(
        row
        for row in assert_array(snapshot["evidence_sources"])
        if assert_object(row)["source_id"] == "tree:runtime"
    )
    assert_array(assert_object(runtime_source)["authorities"]).append(
        "module-ownership"
    )
    snapshot["module_ownership"] = [
        {
            "module": "library",
            "context": "compile",
            "owners": ["library@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        },
        {
            "module": "library",
            "context": "runtime",
            "owners": ["app@1"],
            "completeness": "complete",
            "evidence_sources": ["tree:runtime"],
        },
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(snapshot)
        packet = codemap.dependency_evidence_correlation(
            observation,
            {
                "correlations": [
                    {
                        "module": "library",
                        "context": "compile",
                        "completeness": "complete",
                        "truncation": "complete",
                        "anchors": [
                            {
                                "anchor_id": "compile-use",
                                "path": "consumer.py",
                                "line": 1,
                            }
                        ],
                    }
                ]
            },
        )

    assert packet["schema"] == "hashmarks.dependency-evidence-correlation.v2"
    assert packet["dependency_links"] == [
        {
            "bundle_id": assert_object(
                assert_array(assert_object(packet["correlation"])["bundles"])[0]
            )["bundle_id"],
            "module": "library",
            "context": "compile",
            "distribution_state": "resolved-unique",
            "distribution_nodes": ["library@1"],
            "ownership_completeness": "complete",
            "observed_contexts": ["compile"],
            "evidence_sources": ["list:compile"],
            "observation_identity": observation["observation_identity"],
            "authority": "qualified-external-observation",
            "producer_authority": "caller-claimed",
            "causation": "not-inferred",
        }
    ]
    assert (
        assert_object(packet["dependency_provenance"])["producer"]
        == observation["producer"]
    )
    assert (
        assert_object(packet["dependency_provenance"])["repository_binding"]
        == observation["repository_binding"]
    )
    assert [
        assert_object(row)["source_id"]
        for row in assert_array(
            assert_object(packet["dependency_provenance"])["evidence_sources"]
        )
    ] == ["list:compile"]
    assert_object(assert_object(packet["dependency_provenance"])["producer"])[
        "kind"
    ] = "changed-by-consumer"
    assert_object(
        assert_array(
            assert_object(packet["dependency_provenance"])["evidence_sources"]
        )[0]
    )["kind"] = "changed-by-consumer"
    assert assert_object(observation["producer"])["kind"] == "neutral-resolver"
    assert (
        assert_object(assert_array(observation["evidence_sources"])[0])["kind"]
        == "test-inventory-source"
    )
    assert packet["producer_authority"] == "caller-claimed"
    assert packet["observation_identity"] == observation["observation_identity"]
    assert (
        assert_object(assert_array(assert_object(packet["correlation"])["bundles"])[0])[
            "producer_authority"
        ]
        == "caller-claimed"
    )
    assert assert_object(
        assert_array(assert_object(packet["correlation"])["bundles"])[0]
    )["scope"] == {
        "kind": "dependency-module-correlation",
        "module": "library",
        "context": "compile",
    }


def test_v3_dependency_correlation_without_context_preserves_cross_context_ambiguity(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    runtime_source = next(
        row
        for row in assert_array(snapshot["evidence_sources"])
        if assert_object(row)["source_id"] == "tree:runtime"
    )
    assert_array(assert_object(runtime_source)["authorities"]).append(
        "module-ownership"
    )
    snapshot["module_ownership"] = [
        {
            "module": "library",
            "context": "compile",
            "owners": ["library@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        },
        {
            "module": "library",
            "context": "runtime",
            "owners": ["app@1"],
            "completeness": "complete",
            "evidence_sources": ["tree:runtime"],
        },
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(snapshot)
        packet = codemap.dependency_evidence_correlation(
            observation,
            {
                "correlations": [
                    {
                        "module": "library",
                        "completeness": "complete",
                        "truncation": "complete",
                        "anchors": [],
                    }
                ]
            },
        )

    link = assert_array(packet["dependency_links"])[0]
    assert assert_object(link)["distribution_state"] == "resolved-ambiguous"
    assert assert_object(link)["distribution_nodes"] == ["app@1", "library@1"]
    assert assert_object(link)["observed_contexts"] == ["compile", "runtime"]


def test_import_correspondence_selects_most_specific_owner_per_context(
    tmp_path: Path,
) -> None:
    (tmp_path / "consumer.py").write_text("import library.sub\n")
    snapshot = _snapshot_v3()
    runtime_source = next(
        row
        for row in assert_array(snapshot["evidence_sources"])
        if assert_object(row)["source_id"] == "tree:runtime"
    )
    assert_array(assert_object(runtime_source)["authorities"]).append(
        "module-ownership"
    )
    snapshot["module_ownership"] = [
        {
            "module": "library.sub",
            "context": "compile",
            "owners": ["library@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        },
        {
            "module": "library",
            "context": "compile",
            "owners": ["inventory-only@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        },
        {
            "module": "library",
            "context": "runtime",
            "owners": ["app@1"],
            "completeness": "complete",
            "evidence_sources": ["tree:runtime"],
        },
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(snapshot)
        compile_result = codemap.dependency_import_correspondence(
            observation,
            source_path="consumer.py",
            import_target="library.sub",
            context="compile",
        )
        aggregate = codemap.dependency_import_correspondence(
            observation,
            source_path="consumer.py",
            import_target="library.sub",
        )

    assert compile_result["distribution_state"] == "resolved-unique"
    assert compile_result["distribution_nodes"] == ["library@1"]
    assert compile_result["matched_modules"] == [
        {
            "context": "compile",
            "module": "library.sub",
            "evidence_sources": ["list:compile"],
        }
    ]
    assert compile_result["import_claim_authority"] == "caller-claimed"
    assert (
        assert_object(compile_result["dependency_provenance"])["observation_identity"]
        == (observation["observation_identity"])
    )
    assert aggregate["distribution_state"] == "resolved-ambiguous"
    assert aggregate["distribution_nodes"] == ["app@1", "library@1"]
    assert aggregate["matched_modules"] == [
        {
            "context": "compile",
            "module": "library.sub",
            "evidence_sources": ["list:compile"],
        },
        {
            "context": "runtime",
            "module": "library",
            "evidence_sources": ["tree:runtime"],
        },
    ]
    assert [
        assert_object(row)["source_id"]
        for row in assert_array(
            assert_object(aggregate["dependency_provenance"])["evidence_sources"]
        )
    ] == ["list:compile", "tree:runtime"]


def test_import_correspondence_does_not_fall_back_from_observed_empty_exact_row(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    parent = {
        "module": "library",
        "context": "compile",
        "owners": ["library@1"],
        "completeness": "complete",
        "evidence_sources": ["list:compile"],
    }
    snapshot["module_ownership"] = [parent]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        fallback = codemap.dependency_resolution_evidence(snapshot)
        fallback_result = codemap.dependency_import_correspondence(
            fallback,
            source_path="consumer.py",
            import_target="library.sub",
            context="compile",
        )
        snapshot["module_ownership"] = [
            parent,
            {
                "module": "library.sub",
                "context": "compile",
                "owners": [],
                "completeness": "incomplete",
                "evidence_sources": ["list:compile"],
            },
        ]
        observed = codemap.dependency_resolution_evidence(snapshot)
        exact_result = codemap.dependency_import_correspondence(
            observed,
            source_path="consumer.py",
            import_target="library.sub",
            context="compile",
        )
        missing_result = codemap.dependency_import_correspondence(
            observed,
            source_path="consumer.py",
            import_target="missing.module",
            context="compile",
        )

    assert fallback_result["distribution_nodes"] == ["library@1"]
    assert (
        assert_object(assert_array(fallback_result["matched_modules"])[0])["module"]
        == "library"
    )
    assert exact_result["distribution_state"] == "unresolved"
    assert exact_result["distribution_nodes"] == []
    assert exact_result["ownership_completeness"] == "incomplete"
    assert (
        assert_object(assert_array(exact_result["matched_modules"])[0])["module"]
        == "library.sub"
    )
    assert missing_result["distribution_state"] == "unknown"
    assert missing_result["matched_modules"] == []
    assert (
        assert_object(missing_result["dependency_provenance"])["evidence_sources"] == []
    )


def test_dependency_correlation_identity_ignores_request_and_anchor_order(
    tmp_path: Path,
) -> None:
    (tmp_path / "consumer.py").write_text("A = 1\nB = 2\n")
    snapshot = _snapshot_v3()
    snapshot["module_ownership"] = [
        {
            "module": "library",
            "context": "compile",
            "owners": ["library@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        },
        {
            "module": "inventory",
            "context": "compile",
            "owners": ["inventory-only@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        },
    ]
    first = {
        "module": "library",
        "context": "compile",
        "anchors": [
            {"anchor_id": "a", "path": "consumer.py", "line": 1},
            {"anchor_id": "b", "path": "consumer.py", "line": 2},
        ],
    }
    second = {"module": "inventory", "context": "compile", "anchors": []}
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(snapshot)
        forward = codemap.dependency_evidence_correlation(
            observation, {"correlations": [first, second]}
        )
        reversed_first = {**first, "anchors": list(reversed(first["anchors"]))}
        reverse = codemap.dependency_evidence_correlation(
            observation, {"correlations": [second, reversed_first]}
        )
        changed = codemap.dependency_evidence_correlation(
            observation,
            {
                "correlations": [
                    {**first, "completeness": "complete", "truncation": "complete"},
                    second,
                ]
            },
        )
        duplicates = codemap.dependency_evidence_correlation(
            observation, {"correlations": [second, first, second]}
        )
        reordered_duplicates = codemap.dependency_evidence_correlation(
            observation, {"correlations": [second, second, reversed_first]}
        )

    assert forward["schema"] == "hashmarks.dependency-evidence-correlation.v2"
    assert (
        assert_object(forward["correlation"])["evidence_definition_identity"]
        == (assert_object(reverse["correlation"])["evidence_definition_identity"])
    )
    assert (
        assert_object(forward["correlation"])["correlation_identity"]
        == (assert_object(reverse["correlation"])["correlation_identity"])
    )
    assert forward["dependency_links"] == reverse["dependency_links"]
    assert (
        assert_object(forward["correlation"])["evidence_definition_identity"]
        != (assert_object(changed["correlation"])["evidence_definition_identity"])
    )
    assert (
        len(
            {
                assert_object(row)["bundle_id"]
                for row in assert_array(duplicates["dependency_links"])
            }
        )
        == 3
    )
    assert (
        assert_object(duplicates["correlation"])["correlation_identity"]
        == (assert_object(reordered_duplicates["correlation"])["correlation_identity"])
    )
    assert {
        assert_object(row)["bundle_id"]
        for row in assert_array(forward["dependency_links"])
    } == {
        assert_object(row)["bundle_id"]
        for row in assert_array(assert_object(forward["correlation"])["bundles"])
    }


def test_v3_repository_binding_tracks_current_codemap_generation(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(_snapshot_v3())
        expected_identity = codemap._repository_packet_identity()
        expected_generation = codemap.store.generation()

    binding = packet["repository_binding"]
    assert assert_object(binding)["repository_identity"] == expected_identity
    assert assert_text(assert_object(binding)["repository_identity"]).startswith(
        ("git-tree:", "workspace:")
    )
    assert assert_object(binding)["codemap_generation"] == expected_generation


def test_v3_graph_query_refuses_node_outside_requested_context(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        with pytest.raises(
            ValueError,
            match="dependency query node_id not selected in context: inventory-only@1:runtime",
        ):
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "dependencies",
                        "node_id": "inventory-only@1",
                        "context": "runtime",
                    }
                ],
            )


def test_v3_graph_query_refuses_target_outside_requested_context(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        with pytest.raises(
            ValueError,
            match=(
                "dependency query target_id not selected in context: "
                "inventory-only@1:runtime"
            ),
        ):
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "reachability",
                        "node_id": "app@1",
                        "target_id": "inventory-only@1",
                        "context": "runtime",
                    }
                ],
            )


def test_v3_dependency_query_refuses_unknown_request_field(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        with pytest.raises(
            ValueError,
            match="unknown dependency query field: contxt",
        ):
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "inventory",
                        "node_id": "library@1",
                        "contxt": "compile",
                    }
                ],
            )


@pytest.mark.parametrize(
    ("query_request", "operation", "field"),
    [
        (
            {"operation": "component", "component_id": "library", "node_id": "app@1"},
            "component",
            "node_id",
        ),
        (
            {"operation": "inventory", "node_id": "library@1", "target_id": "app@1"},
            "inventory",
            "target_id",
        ),
        (
            {
                "operation": "module-owners",
                "module": "library",
                "component_id": "library",
            },
            "module-owners",
            "component_id",
        ),
        (
            {"operation": "dependencies", "node_id": "app@1", "module": "library"},
            "dependencies",
            "module",
        ),
        (
            {
                "operation": "reachability",
                "node_id": "app@1",
                "target_id": "library@1",
                "context": "compile",
                "max_results": 1,
            },
            "reachability",
            "max_results",
        ),
    ],
)
def test_v3_dependency_query_rejects_operation_irrelevant_fields(
    tmp_path: Path,
    query_request: dict[str, object],
    operation: str,
    field: str,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        with pytest.raises(
            ValueError,
            match=f"dependency query field is not valid for {operation}: {field}",
        ):
            codemap.dependency_resolution_queries(observation, [query_request])


@pytest.mark.parametrize(
    ("query_request", "field"),
    [
        ({"operation": True}, "operation"),
        (
            {
                "operation": "dependencies",
                "node_id": 7,
                "context": "compile",
            },
            "node_id",
        ),
        (
            {
                "operation": "reachability",
                "node_id": "app@1",
                "target_id": False,
                "context": "compile",
            },
            "target_id",
        ),
        (
            {
                "operation": "component",
                "component_id": ["library"],
            },
            "component_id",
        ),
        (
            {
                "operation": "dependencies",
                "node_id": "app@1",
                "context": 1,
            },
            "context",
        ),
        (
            {
                "operation": "module-owners",
                "module": {"name": "library"},
            },
            "module",
        ),
    ],
)
def test_v3_dependency_query_rejects_non_string_identifiers(
    tmp_path: Path, query_request: dict[str, object], field: str
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        with pytest.raises(ValueError, match=f"{field} must be a string"):
            codemap.dependency_resolution_queries(observation, [query_request])


@pytest.mark.parametrize("field", ["max_depth", "max_results", "max_visits"])
@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_v3_dependency_query_rejects_coerced_bounds(
    tmp_path: Path, field: str, value: object
) -> None:
    request: dict[str, object] = {
        "operation": "dependencies",
        "node_id": "app@1",
        "context": "compile",
    }
    request[field] = value

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        with pytest.raises(ValueError, match=f"{field} must be a positive integer"):
            codemap.dependency_resolution_queries(observation, [request])


def test_v3_multicontext_graph_query_requires_explicit_context(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    changed["relationships"] = [
        row
        for row in assert_array(changed["relationships"])
        if assert_object(row)["context"] == "compile"
    ]
    inventory_only = next(
        row
        for row in assert_array(changed["selections"])
        if assert_object(row)["node_id"] == "inventory-only@1"
    )
    assert_array(assert_object(inventory_only)["contexts"]).append("runtime")
    assert_array(assert_object(inventory_only)["evidence_sources"]).append(
        "tree:runtime"
    )
    changed["relationships"].append(
        {
            "source": "library@1",
            "target": "inventory-only@1",
            "kind": "dependency",
            "context": "runtime",
            "effective_scope": "runtime",
            "evidence_sources": ["tree:runtime"],
        }
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        with pytest.raises(
            ValueError,
            match="graph query requires context for multi-context observation",
        ):
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "paths",
                        "node_id": "app@1",
                        "target_id": "inventory-only@1",
                    }
                ],
            )


@pytest.mark.parametrize(
    "operation",
    ["dependencies", "dependents", "reachability", "paths"],
)
def test_v3_graph_query_reports_conditional_relationship_omission(
    tmp_path: Path,
    operation: str,
) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["relationships"])[0])["marker"] = (
        "sys_platform == 'linux'"
    )
    request = {
        "operation": operation,
        "node_id": "app@1" if operation != "dependents" else "library@1",
        "context": "compile",
    }
    if operation in {"reachability", "paths"}:
        request["target_id"] = "library@1"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        result = assert_array(
            codemap.dependency_resolution_queries(observation, [request])["results"]
        )[0]

    assert assert_object(result)["completeness"] == "incomplete"
    assert assert_object(result)["omissions"] == [
        {"reason": "conditional-edge", "node_id": request["node_id"]}
    ]
    if operation == "reachability":
        assert assert_object(assert_object(result)["result"])["reachable"] is False
        assert (
            assert_object(assert_object(result)["result"])["negative_evidence"]
            == "not-admissible"
        )
    elif operation == "paths":
        assert assert_object(result)["result"] == []
        assert assert_object(result)["negative_evidence"] == "not-admissible"
    else:
        assert assert_object(result)["result"] == []
        assert assert_object(result)["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize("marked_node", ["app@1", "library@1"])
@pytest.mark.parametrize(
    "operation", ["dependencies", "dependents", "reachability", "paths"]
)
def test_v3_graph_query_does_not_traverse_marker_qualified_selection(
    tmp_path: Path, operation: str, marked_node: str
) -> None:
    changed = _snapshot_v3()
    selection = next(
        row
        for row in assert_array(changed["selections"])
        if assert_object(row)["node_id"] == marked_node
    )
    assert_object(selection)["marker"] = "sys_platform == 'linux'"
    start = "library@1" if operation == "dependents" else "app@1"
    request = {"operation": operation, "node_id": start, "context": "compile"}
    if operation in {"reachability", "paths"}:
        request["target_id"] = "library@1"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        result = assert_array(
            codemap.dependency_resolution_queries(observation, [request])["results"]
        )[0]

    reason = "conditional-selection" if start == marked_node else "conditional-edge"
    assert assert_object(result)["omissions"] == [{"reason": reason, "node_id": start}]
    assert assert_object(result)["completeness"] == "incomplete"
    if operation == "reachability":
        assert assert_object(result)["result"] == {
            "reachable": False,
            "negative_evidence": "not-admissible",
        }
    else:
        assert assert_object(result)["result"] == []
        assert assert_object(result)["negative_evidence"] == "not-admissible"


def test_v3_isolated_conditional_selection_cannot_prove_graph_absence(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["selections"])[2])["marker"] = (
        "sys_platform == 'linux'"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        results = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "dependencies",
                    "node_id": "inventory-only@1",
                    "context": "compile",
                },
                {
                    "operation": "dependencies",
                    "node_id": "app@1",
                    "context": "compile",
                },
            ],
        )["results"]

    assert assert_object(assert_array(results)[0])["result"] == []
    assert (
        assert_object(assert_array(results)[0])["negative_evidence"] == "not-admissible"
    )
    assert assert_object(assert_array(results)[0])["omissions"] == [
        {"reason": "conditional-selection", "node_id": "inventory-only@1"}
    ]
    assert [
        assert_object(row)["node_id"]
        for row in assert_array(assert_object(assert_array(results)[1])["result"])
    ] == ["library@1"]
    assert assert_object(assert_array(results)[1])["completeness"] == "complete"


def test_v3_depth_bound_precedes_conditional_edge_omission(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["relationships"]).append(
        {
            "source": "library@1",
            "target": "inventory-only@1",
            "kind": "dependency",
            "context": "compile",
            "marker": "sys_platform == 'linux'",
            "evidence_sources": ["tree:compile"],
        }
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        result = assert_array(
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "dependencies",
                        "node_id": "app@1",
                        "context": "compile",
                        "max_depth": 1,
                    }
                ],
            )["results"]
        )[0]

    assert [
        assert_object(row)["node_id"]
        for row in assert_array(assert_object(result)["result"])
    ] == ["library@1"]
    assert assert_object(result)["omissions"] == [
        {"reason": "depth-limit", "node_id": "library@1"}
    ]
    assert assert_object(result)["completeness"] == "incomplete"


def test_v3_zero_length_path_does_not_consume_conditional_edges(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["relationships"])[0])["marker"] = (
        "sys_platform == 'linux'"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        result = assert_array(
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "paths",
                        "node_id": "app@1",
                        "target_id": "app@1",
                        "context": "compile",
                    }
                ],
            )["results"]
        )[0]

    assert assert_object(result)["result"] == [["app@1"]]
    assert assert_object(result)["completeness"] == "complete"
    assert assert_object(result)["omissions"] == []


@pytest.mark.parametrize("operation", ["paths", "reachability"])
def test_v3_zero_length_identity_query_preserves_conditional_selection(
    tmp_path: Path, operation: str
) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["selections"])[0])["marker"] = (
        "sys_platform == 'linux'"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        result = assert_array(
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": operation,
                        "node_id": "app@1",
                        "target_id": "app@1",
                        "context": "compile",
                    }
                ],
            )["results"]
        )[0]

    assert assert_object(result)["result"] == (
        [["app@1"]]
        if operation == "paths"
        else {"reachable": True, "negative_evidence": "not-applicable"}
    )
    assert assert_object(result)["completeness"] == "complete"
    assert assert_object(result)["omissions"] == []


def test_v3_conditional_duplicate_does_not_weaken_unconditional_topology(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["relationships"]).append(
        {
            "source": "app@1",
            "target": "library@1",
            "kind": "dependency",
            "context": "compile",
            "marker": "sys_platform == 'linux'",
            "evidence_sources": ["tree:compile"],
        }
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        result = assert_array(
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "dependencies",
                        "node_id": "app@1",
                        "context": "compile",
                    }
                ],
            )["results"]
        )[0]

    assert [
        assert_object(row)["node_id"]
        for row in assert_array(assert_object(result)["result"])
    ] == ["library@1"]
    assert assert_object(result)["completeness"] == "complete"
    assert assert_object(result)["omissions"] == []


def test_v3_duplicate_unconditional_edges_do_not_duplicate_node_paths(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["relationships"]).append(
        {
            "source": "app@1",
            "target": "library@1",
            "kind": "dependency",
            "context": "compile",
            "effective_scope": "alternate",
            "evidence_sources": ["tree:compile"],
        }
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        result = assert_array(
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "paths",
                        "node_id": "app@1",
                        "target_id": "library@1",
                        "context": "compile",
                        "max_results": 1,
                    }
                ],
            )["results"]
        )[0]

    assert assert_object(result)["result"] == [["app@1", "library@1"]]
    assert assert_object(result)["completeness"] == "complete"
    assert assert_object(result)["omissions"] == []


def test_v3_bounded_queries_report_dependencies_paths_and_contexts(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        packet = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "dependencies",
                    "node_id": "app@1",
                    "context": "compile",
                },
                {
                    "operation": "paths",
                    "node_id": "app@1",
                    "target_id": "library@1",
                    "context": "runtime",
                },
                {"operation": "contexts", "node_id": "library@1"},
            ],
        )

    dependencies, paths, contexts = assert_array(packet["results"])
    assert (
        assert_object(assert_array(assert_object(dependencies)["result"])[0])["node_id"]
        == "library@1"
    )
    assert assert_object(paths)["result"] == [["app@1", "library@1"]]
    assert assert_object(contexts)["result"] == ["compile", "runtime"]
    assert all(
        assert_object(row)["completeness"] == "complete"
        for row in assert_array(packet["results"])
    )


def test_v3_contexts_query_exposes_incomplete_context_evidence(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    selection_runtime = next(
        row
        for row in assert_array(changed["coverage"])
        if assert_object(row)["kind"] == "selection"
        and assert_object(row)["context"] == "runtime"
    )
    assert_object(selection_runtime)["completeness"] = "incomplete"
    assert_object(selection_runtime)["truncation"] = "truncated"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "contexts", "node_id": "library@1"}],
        )

    result = assert_array(packet["results"])[0]
    assert assert_object(result)["result"] == ["compile", "runtime"]
    assert assert_object(result)["completeness"] == "incomplete"


def test_v3_reachability_absence_requires_complete_context_coverage(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["coverage"])[1])["completeness"] = "incomplete"
    assert_object(assert_array(changed["coverage"])[1])["truncation"] = "truncated"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "reachability",
                    "node_id": "library@1",
                    "target_id": "app@1",
                    "context": "compile",
                },
                {
                    "operation": "reachability",
                    "node_id": "library@1",
                    "target_id": "app@1",
                    "context": "runtime",
                },
            ],
        )

    assert (
        assert_object(assert_object(assert_array(packet["results"])[0])["result"])[
            "negative_evidence"
        ]
        == "admissible-within-declared-scope"
    )
    assert (
        assert_object(assert_object(assert_array(packet["results"])[1])["result"])[
            "negative_evidence"
        ]
        == "not-admissible"
    )


def test_v3_query_exposes_depth_omission_instead_of_silent_partial_result(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["components"]).append(
        {"component_id": "leaf", "name": "leaf", "ecosystem": "test"}
    )
    assert_array(changed["selections"]).append(
        {
            "node_id": "leaf@1",
            "component_id": "leaf",
            "version": "1",
            "source": "registry",
            "contexts": ["compile"],
            "evidence_sources": ["tree:compile"],
        }
    )
    assert_array(changed["relationships"]).append(
        {
            "source": "library@1",
            "target": "leaf@1",
            "kind": "dependency",
            "context": "compile",
            "effective_scope": "compile",
            "evidence_sources": ["tree:compile"],
        }
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "dependencies",
                    "node_id": "app@1",
                    "context": "compile",
                    "max_depth": 1,
                }
            ],
        )

    result = assert_array(packet["results"])[0]
    assert [
        assert_object(row)["node_id"]
        for row in assert_array(assert_object(result)["result"])
    ] == ["library@1"]
    assert assert_object(result)["completeness"] == "incomplete"
    assert assert_object(result)["omissions"] == [
        {"reason": "depth-limit", "node_id": "library@1"}
    ]


def test_v3_repository_input_revision_requires_string_sha256(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    snapshot["repository_inputs"] = [
        {
            "path": "dependency.lock",
            "member_revision": int("1" * 64),
        }
    ]
    (tmp_path / "dependency.lock").write_text("content\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="member_revision must be lowercase sha256 hex",
        ):
            codemap.dependency_resolution_evidence(snapshot)


def test_v3_repository_input_change_is_observation_only(tmp_path: Path) -> None:
    dependency_input = tmp_path / "dependency.lock"
    dependency_input.write_text("before\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        snapshot = _snapshot_v3()
        snapshot["repository_inputs"] = [{"path": "dependency.lock"}]
        before = codemap.dependency_resolution_evidence(snapshot)

        dependency_input.write_text("after\n")
        codemap.sync()
        after = codemap.dependency_resolution_evidence(snapshot)
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert delta["selections_changed"] == []
    assert delta["relationships_added"] == []
    assert delta["relationships_removed"] == []


def test_v3_module_ownership_change_is_observation_only(tmp_path: Path) -> None:
    before_snapshot = _snapshot_v3()
    before_snapshot["module_ownership"] = [
        {
            "module": "library.module",
            "context": "compile",
            "owners": ["library@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        }
    ]
    after_snapshot = _snapshot_v3()
    after_snapshot["module_ownership"] = [
        {
            "module": "library.module",
            "context": "compile",
            "owners": ["inventory-only@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(before_snapshot)
        after = codemap.dependency_resolution_evidence(after_snapshot)
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert delta["module_ownership_changed"] == ["library.module|compile"]
    assert delta["selections_changed"] == []
    assert delta["relationships_added"] == []
    assert delta["relationships_removed"] == []


def test_v3_provenance_change_does_not_masquerade_as_resolution_change(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(_snapshot_v3())
        changed = _snapshot_v3()
        assert_object(assert_array(changed["evidence_sources"])[0])[
            "producer_digest"
        ] = "sha256:producer-a"
        after = codemap.dependency_resolution_evidence(changed)
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert delta["selections_changed"] == []
    assert delta["relationships_added"] == []
    assert delta["relationships_removed"] == []


def test_v3_contextual_module_ownership_preserves_independent_observations(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    runtime_source = next(
        row
        for row in assert_array(changed["evidence_sources"])
        if assert_object(row)["source_id"] == "tree:runtime"
    )
    assert_array(assert_object(runtime_source)["authorities"]).append(
        "module-ownership"
    )
    changed["module_ownership"] = [
        {
            "module": "library.module",
            "context": "compile",
            "owners": ["library@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        },
        {
            "module": "library.module",
            "context": "runtime",
            "owners": [],
            "completeness": "unknown",
            "evidence_sources": ["tree:runtime"],
        },
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(changed)

    assert [
        (assert_object(row)["module"], assert_object(row)["context"])
        for row in assert_array(packet["module_ownership"])
    ] == [
        ("library.module", "compile"),
        ("library.module", "runtime"),
    ]


def test_v3_explicit_empty_complete_module_ownership_is_negative_evidence(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    assert_array(snapshot["coverage"]).append(
        {
            "context": "compile",
            "kind": "module-ownership",
            "completeness": "complete",
            "truncation": "complete",
            "evidence_sources": ["list:compile"],
        }
    )
    snapshot["module_ownership"] = [
        {
            "module": "missing.module",
            "context": "compile",
            "owners": [],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(snapshot)
        result = assert_array(
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "module-owners",
                        "module": "missing.module",
                        "context": "compile",
                    }
                ],
            )["results"]
        )[0]

    assert (
        assert_object(assert_array(assert_object(result)["result"])[0])["state"]
        == "unresolved"
    )
    assert (
        assert_object(assert_array(assert_object(result)["result"])[0])["owners"] == []
    )
    assert (
        assert_object(result)["negative_evidence"] == "admissible-within-declared-scope"
    )


def test_v3_explicit_empty_unknown_module_ownership_is_not_negative_evidence(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    assert_array(snapshot["coverage"]).append(
        {
            "context": "compile",
            "kind": "module-ownership",
            "completeness": "complete",
            "truncation": "complete",
            "evidence_sources": ["list:compile"],
        }
    )
    snapshot["module_ownership"] = [
        {
            "module": "missing.module",
            "context": "compile",
            "owners": [],
            "completeness": "unknown",
            "evidence_sources": ["list:compile"],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(snapshot)
        result = assert_array(
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "module-owners",
                        "module": "missing.module",
                        "context": "compile",
                    }
                ],
            )["results"]
        )[0]

    assert (
        assert_object(assert_array(assert_object(result)["result"])[0])["owners"] == []
    )
    assert assert_object(result)["negative_evidence"] == "not-admissible"


def test_v3_source_kind_is_opaque_when_semantic_authorities_are_explicit(
    tmp_path: Path,
) -> None:
    snapshot = {
        "schema": "hashmarks.dependency-resolution.v3",
        "producer": {"kind": "fixture-resolver", "schema_version": "1"},
        "scope": {"python": "3.14", "platform": "linux"},
        "contexts": ["default", "dev"],
        "roots": [
            {
                "node_id": "demo@workspace",
                "context": "default",
                "evidence_sources": ["resolver:lock"],
            },
            {
                "node_id": "demo@workspace",
                "context": "dev",
                "evidence_sources": ["resolver:lock"],
            },
        ],
        "evidence_sources": [
            {
                "source_id": "resolver:lock",
                "kind": "opaque-lock-format",
                "authorities": ["resolution-graph", "resolved-inventory", "selection"],
                "context": "",
                "completeness": "complete",
                "truncation": "complete",
            }
        ],
        "components": [
            {"component_id": "demo", "name": "demo", "ecosystem": "pypi"},
            {"component_id": "pytest", "name": "pytest", "ecosystem": "pypi"},
        ],
        "selections": [
            {
                "node_id": "demo@workspace",
                "component_id": "demo",
                "version": "0.1.0",
                "source": "workspace",
                "contexts": ["default", "dev"],
                "evidence_sources": ["resolver:lock"],
            },
            {
                "node_id": "pytest@9",
                "component_id": "pytest",
                "version": "9.0.2",
                "source": "registry",
                "contexts": ["dev"],
                "evidence_sources": ["resolver:lock"],
            },
        ],
        "inventory": [
            {
                "node_id": "pytest@9",
                "context": "dev",
                "evidence_sources": ["resolver:lock"],
            }
        ],
        "relationships": [
            {
                "source": "demo@workspace",
                "target": "pytest@9",
                "kind": "dependency",
                "context": "dev",
                "effective_scope": "dev",
                "marker": "python_version >= '3.11'",
                "evidence_sources": ["resolver:lock"],
            }
        ],
        "coverage": [
            {
                "context": "dev",
                "kind": "resolution-graph",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["resolver:lock"],
            },
            {
                "context": "default",
                "kind": "selection",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["resolver:lock"],
            },
            {
                "context": "dev",
                "kind": "selection",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["resolver:lock"],
            },
        ],
        "repository_inputs": [],
        "module_ownership": [],
    }
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)

    assert assert_object(packet["producer"])["kind"] == "fixture-resolver"
    assert packet["contexts"] == ["default", "dev"]
    assert assert_object(assert_array(packet["relationships"])[0])["context"] == "dev"
    assert "groupId" not in repr(packet)
    assert "artifactId" not in repr(packet)


@pytest.mark.parametrize("producer_kind", ["maven-like", "uv-like"])
def test_v3_equivalent_producer_packets_have_query_and_delta_parity(
    tmp_path: Path,
    producer_kind: str,
) -> None:
    original = _snapshot_v3()
    translated = copy.deepcopy(original)
    translated["producer"] = {"kind": producer_kind, "schema_version": "42"}
    source_ids = {
        assert_object(source)["source_id"]: f"other:{index}"
        for index, source in enumerate(assert_array(translated["evidence_sources"]))
    }
    for source in assert_array(translated["evidence_sources"]):
        assert_object(source)["source_id"] = source_ids[
            assert_object(source)["source_id"]
        ]
        assert_object(source)["kind"] = f"{producer_kind}-physical-format"
    for family in (
        "roots",
        "selections",
        "inventory",
        "relationships",
        "coverage",
        "module_ownership",
    ):
        for row in assert_array(translated[family]):
            assert_object(row)["evidence_sources"] = [
                source_ids[ref]
                for ref in assert_array(assert_object(row)["evidence_sources"])
            ]

    requests = [
        {"operation": "dependencies", "node_id": "app@1", "context": "compile"},
        {"operation": "inventory", "context": "compile"},
        {"operation": "module-owners", "module": "missing", "context": "compile"},
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(original)
        after = codemap.dependency_resolution_evidence(translated)
        before_queries = codemap.dependency_resolution_queries(before, requests)
        after_queries = codemap.dependency_resolution_queries(after, requests)
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["definition_identity"] == after["definition_identity"]
    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    for left, right in zip(
        assert_array(before_queries["results"]),
        assert_array(after_queries["results"]),
        strict=True,
    ):
        assert _without_source_refs(
            assert_object(left)["result"]
        ) == _without_source_refs(assert_object(right)["result"])
        assert (
            assert_object(left)["completeness"] == assert_object(right)["completeness"]
        )
        assert (
            assert_object(left)["negative_evidence"]
            == assert_object(right)["negative_evidence"]
        )
        assert (
            assert_object(left)["producer_authority"]
            == assert_object(right)["producer_authority"]
            == "caller-claimed"
        )
    assert delta["comparability"] == "comparable"
    for field in (
        "components_added",
        "components_removed",
        "components_changed",
        "selections_added",
        "selections_removed",
        "selections_changed",
        "inventory_added",
        "inventory_removed",
        "relationships_added",
        "relationships_removed",
        "module_ownership_added",
        "module_ownership_removed",
        "module_ownership_changed",
    ):
        assert delta[field] == []
    assert delta["producer_authority"] == "caller-claimed"


def test_v3_module_owner_absence_requires_complete_ownership_coverage(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["coverage"]).append(
        {
            "context": "compile",
            "kind": "module-ownership",
            "completeness": "complete",
            "truncation": "complete",
            "evidence_sources": ["list:compile"],
        }
    )
    assert_array(changed["evidence_sources"]).append(
        {
            "source_id": "modules:runtime",
            "kind": "test-module-source",
            "authorities": ["module-ownership"],
            "context": "runtime",
            "completeness": "incomplete",
            "truncation": "complete",
        }
    )
    assert_array(changed["coverage"]).append(
        {
            "context": "runtime",
            "kind": "module-ownership",
            "completeness": "incomplete",
            "truncation": "complete",
            "evidence_sources": ["modules:runtime"],
        }
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "module-owners",
                    "module": "missing.module",
                    "context": "compile",
                },
                {
                    "operation": "module-owners",
                    "module": "missing.module",
                    "context": "runtime",
                },
            ],
        )

    compile_result, runtime_result = assert_array(packet["results"])
    assert assert_object(compile_result)["result"] == []
    assert (
        assert_object(compile_result)["negative_evidence"]
        == "admissible-within-declared-scope"
    )
    assert assert_object(compile_result)["completeness"] == "complete"
    assert assert_object(runtime_result)["result"] == []
    assert assert_object(runtime_result)["completeness"] == "incomplete"
    assert assert_object(runtime_result)["negative_evidence"] == "not-admissible"


def test_v3_dependency_query_exact_result_bound_is_complete(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        packet = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "dependencies",
                    "node_id": "app@1",
                    "context": "compile",
                    "max_results": 1,
                }
            ],
        )

    result = assert_array(packet["results"])[0]
    assert [
        assert_object(row)["node_id"]
        for row in assert_array(assert_object(result)["result"])
    ] == ["library@1"]
    assert assert_object(result)["completeness"] == "complete"
    assert assert_object(result)["omissions"] == []


def test_v3_dependency_query_reports_result_bound_when_result_is_omitted(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["components"]).append(
        {"component_id": "second", "name": "second", "ecosystem": "test"}
    )
    assert_array(changed["selections"]).append(
        {
            "node_id": "second@1",
            "component_id": "second",
            "version": "1",
            "source": "registry",
            "contexts": ["compile"],
            "evidence_sources": ["tree:compile"],
        }
    )
    assert_array(changed["relationships"]).append(
        {
            "source": "app@1",
            "target": "second@1",
            "kind": "dependency",
            "context": "compile",
            "effective_scope": "compile",
            "evidence_sources": ["tree:compile"],
        }
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "dependencies",
                    "node_id": "app@1",
                    "context": "compile",
                    "max_results": 1,
                }
            ],
        )

    result = assert_array(packet["results"])[0]
    assert len(assert_array(assert_object(result)["result"])) == 1
    assert assert_object(result)["completeness"] == "incomplete"
    assert assert_object(result)["omissions"] == [{"reason": "result-limit"}]


def test_v3_context_query_rejects_context_argument_instead_of_ignoring_it(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        with pytest.raises(
            ValueError,
            match="dependency query field is not valid for contexts: context",
        ):
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "contexts",
                        "node_id": "library@1",
                        "context": "compile",
                    }
                ],
            )


def test_v3_context_query_includes_selection_context_without_inventory_or_edge(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["contexts"]).append("optional")
    assert_array(changed["evidence_sources"]).append(
        {
            "source_id": "tree:optional",
            "kind": "test-resolution-source",
            "authorities": ["resolution-graph", "selection"],
            "context": "optional",
            "completeness": "incomplete",
            "truncation": "complete",
        }
    )
    assert_array(
        assert_object(assert_array(changed["selections"])[1])["contexts"]
    ).append("optional")
    assert_array(
        assert_object(assert_array(changed["selections"])[1])["evidence_sources"]
    ).append("tree:optional")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "contexts", "node_id": "library@1"}],
        )

    assert assert_object(assert_array(packet["results"])[0])["result"] == [
        "compile",
        "optional",
        "runtime",
    ]


def test_v3_inventory_absence_requires_complete_inventory_coverage(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["evidence_sources"]).append(
        {
            "source_id": "list:runtime",
            "kind": "test-inventory-source",
            "authorities": ["module-ownership", "resolved-inventory", "selection"],
            "context": "runtime",
            "completeness": "incomplete",
            "truncation": "complete",
        }
    )
    assert_array(changed["coverage"]).append(
        {
            "context": "runtime",
            "kind": "resolved-inventory",
            "completeness": "incomplete",
            "truncation": "complete",
            "evidence_sources": ["list:runtime"],
        }
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "inventory",
                    "node_id": "missing@1",
                    "context": "compile",
                },
                {
                    "operation": "inventory",
                    "node_id": "missing@1",
                    "context": "runtime",
                },
            ],
        )

    compile_result, runtime_result = assert_array(packet["results"])
    assert assert_object(compile_result)["result"] == []
    assert assert_object(compile_result)["completeness"] == "complete"
    assert (
        assert_object(compile_result)["negative_evidence"]
        == "admissible-within-declared-scope"
    )
    assert assert_object(runtime_result)["result"] == []
    assert assert_object(runtime_result)["completeness"] == "incomplete"
    assert assert_object(runtime_result)["negative_evidence"] == "not-admissible"


def test_v3_unscoped_module_absence_requires_coverage_for_every_context(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["evidence_sources"]).append(
        {
            "source_id": "modules:compile",
            "kind": "test-module-source",
            "authorities": ["module-ownership"],
            "context": "compile",
            "completeness": "complete",
            "truncation": "complete",
        }
    )
    assert_array(changed["coverage"]).append(
        {
            "context": "compile",
            "kind": "module-ownership",
            "completeness": "complete",
            "truncation": "complete",
            "evidence_sources": ["modules:compile"],
        }
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "module-owners", "module": "missing.module"}],
        )

    result = assert_array(packet["results"])[0]
    assert assert_object(result)["result"] == []
    assert assert_object(result)["completeness"] == "incomplete"
    assert assert_object(result)["negative_evidence"] == "not-admissible"


def test_v3_unscoped_module_absence_is_admissible_when_all_contexts_complete(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    for context in ("compile", "runtime"):
        source_id = f"modules:{context}"
        assert_array(changed["evidence_sources"]).append(
            {
                "source_id": source_id,
                "kind": "test-module-source",
                "authorities": ["module-ownership"],
                "context": context,
                "completeness": "complete",
                "truncation": "complete",
            }
        )
        assert_array(changed["coverage"]).append(
            {
                "context": context,
                "kind": "module-ownership",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": [source_id],
            }
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "module-owners", "module": "missing.module"}],
        )

    result = assert_array(packet["results"])[0]
    assert assert_object(result)["result"] == []
    assert assert_object(result)["completeness"] == "complete"
    assert (
        assert_object(result)["negative_evidence"] == "admissible-within-declared-scope"
    )


def test_v3_graph_query_completeness_requires_complete_resolution_coverage(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    runtime_coverage = next(
        row
        for row in assert_array(changed["coverage"])
        if assert_object(row)["context"] == "runtime"
        and assert_object(row)["kind"] == "resolution-graph"
    )
    assert_object(runtime_coverage)["completeness"] = "incomplete"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "dependencies",
                    "node_id": "app@1",
                    "context": "runtime",
                },
                {
                    "operation": "paths",
                    "node_id": "app@1",
                    "target_id": "library@1",
                    "context": "runtime",
                },
            ],
        )

    dependencies, paths = assert_array(packet["results"])
    assert [
        assert_object(row)["node_id"]
        for row in assert_array(assert_object(dependencies)["result"])
    ] == ["library@1"]
    assert assert_object(dependencies)["omissions"] == []
    assert assert_object(dependencies)["completeness"] == "incomplete"
    assert assert_object(paths)["result"] == [["app@1", "library@1"]]
    assert assert_object(paths)["omissions"] == []
    assert assert_object(paths)["completeness"] == "incomplete"


def test_v3_empty_graph_queries_expose_negative_evidence_authority(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    runtime_coverage = next(
        row
        for row in assert_array(changed["coverage"])
        if assert_object(row)["context"] == "runtime"
        and assert_object(row)["kind"] == "resolution-graph"
    )
    assert_object(runtime_coverage)["completeness"] = "incomplete"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "dependencies",
                    "node_id": "library@1",
                    "context": "compile",
                },
                {
                    "operation": "dependencies",
                    "node_id": "library@1",
                    "context": "runtime",
                },
                {
                    "operation": "paths",
                    "node_id": "library@1",
                    "target_id": "app@1",
                    "context": "compile",
                },
                {
                    "operation": "paths",
                    "node_id": "library@1",
                    "target_id": "app@1",
                    "context": "runtime",
                },
            ],
        )

    compile_dependencies, runtime_dependencies, compile_paths, runtime_paths = (
        assert_array(packet["results"])
    )
    assert assert_object(compile_dependencies)["result"] == []
    assert (
        assert_object(compile_dependencies)["negative_evidence"]
        == "admissible-within-declared-scope"
    )
    assert assert_object(runtime_dependencies)["result"] == []
    assert assert_object(runtime_dependencies)["negative_evidence"] == "not-admissible"
    assert assert_object(compile_paths)["result"] == []
    assert (
        assert_object(compile_paths)["negative_evidence"]
        == "admissible-within-declared-scope"
    )
    assert assert_object(runtime_paths)["result"] == []
    assert assert_object(runtime_paths)["negative_evidence"] == "not-admissible"


def test_v3_path_query_exact_result_bound_does_not_claim_omission(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["components"]).extend(
        [
            {"component_id": "dead", "ecosystem": "generic", "name": "dead"},
            {
                "component_id": "target",
                "ecosystem": "generic",
                "name": "target",
            },
        ]
    )
    assert_array(changed["selections"]).extend(
        [
            {
                "node_id": "dead@1",
                "component_id": "dead",
                "version": "1",
                "contexts": ["compile"],
                "evidence_sources": ["tree:compile"],
            },
            {
                "node_id": "target@1",
                "component_id": "target",
                "version": "1",
                "contexts": ["compile"],
                "evidence_sources": ["tree:compile"],
            },
        ]
    )
    assert_array(changed["relationships"]).extend(
        [
            {
                "source": "app@1",
                "target": "dead@1",
                "kind": "dependency",
                "context": "compile",
                "evidence_sources": ["tree:compile"],
            },
            {
                "source": "library@1",
                "target": "target@1",
                "kind": "dependency",
                "context": "compile",
                "evidence_sources": ["tree:compile"],
            },
        ]
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        result = assert_array(
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "paths",
                        "node_id": "app@1",
                        "target_id": "target@1",
                        "context": "compile",
                        "max_results": 1,
                    }
                ],
            )["results"]
        )[0]

    assert assert_object(result)["result"] == [["app@1", "library@1", "target@1"]]
    assert assert_object(result)["omissions"] == []
    assert assert_object(result)["completeness"] == "complete"


def test_v3_path_query_reports_result_bound_only_when_a_path_is_omitted(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["relationships"]).extend(
        [
            {
                "source": "app@1",
                "target": "inventory-only@1",
                "kind": "dependency",
                "context": "compile",
                "evidence_sources": ["tree:compile"],
            },
            {
                "source": "inventory-only@1",
                "target": "library@1",
                "kind": "dependency",
                "context": "compile",
                "evidence_sources": ["tree:compile"],
            },
        ]
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        result = assert_array(
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "paths",
                        "node_id": "app@1",
                        "target_id": "library@1",
                        "context": "compile",
                        "max_results": 1,
                    }
                ],
            )["results"]
        )[0]

    assert len(assert_array(assert_object(result)["result"])) == 1
    assert assert_object(result)["omissions"] == [{"reason": "result-limit"}]
    assert assert_object(result)["completeness"] == "incomplete"


def _visit_limit_snapshot() -> dict[str, object]:
    snapshot = _snapshot_v3()
    assert_array(snapshot["components"]).extend(
        [
            {"component_id": "left", "name": "left", "ecosystem": "test"},
            {"component_id": "right", "name": "right", "ecosystem": "test"},
        ]
    )
    assert_array(snapshot["selections"]).extend(
        [
            {
                "node_id": "left@1",
                "component_id": "left",
                "version": "1",
                "source": "registry",
                "contexts": ["compile"],
                "evidence_sources": ["tree:compile"],
            },
            {
                "node_id": "right@1",
                "component_id": "right",
                "version": "1",
                "source": "registry",
                "contexts": ["compile"],
                "evidence_sources": ["tree:compile"],
            },
        ]
    )
    snapshot["relationships"] = [
        {
            "source": "app@1",
            "target": "left@1",
            "kind": "dependency",
            "context": "compile",
            "effective_scope": "compile",
            "evidence_sources": ["tree:compile"],
        },
        {
            "source": "app@1",
            "target": "right@1",
            "kind": "dependency",
            "context": "compile",
            "effective_scope": "compile",
            "evidence_sources": ["tree:compile"],
        },
    ]
    return snapshot


@pytest.mark.parametrize("operation", ["dependencies", "reachability", "paths"])
def test_v3_query_visit_accounting_never_exceeds_declared_bound(
    tmp_path: Path,
    operation: str,
) -> None:
    request = {
        "operation": operation,
        "node_id": "app@1",
        "context": "compile",
        "max_visits": 1,
    }
    if operation in {"reachability", "paths"}:
        request["target_id"] = "inventory-only@1"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_visit_limit_snapshot())
        result = assert_array(
            codemap.dependency_resolution_queries(observation, [request])["results"]
        )[0]

    bounds = assert_object(assert_object(result)["bounds"])
    assert assert_number(bounds["visited"]) <= assert_number(bounds["max_visits"])
    assert assert_object(result)["completeness"] == "incomplete"
    assert assert_object(result)["omissions"] == [{"reason": "visit-limit"}]


def test_v3_complete_module_ownership_cannot_exceed_incomplete_source(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    assert_array(snapshot["evidence_sources"]).append(
        {
            "source_id": "ownership:compile",
            "kind": "test-module-source",
            "authorities": ["module-ownership"],
            "context": "compile",
            "completeness": "incomplete",
            "truncation": "complete",
        }
    )
    snapshot["module_ownership"] = [
        {
            "module": "library.module",
            "context": "compile",
            "owners": ["library@1"],
            "completeness": "complete",
            "evidence_sources": ["ownership:compile"],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError, match="module ownership exceeds evidence source"
        ):
            codemap.dependency_resolution_evidence(snapshot)


def test_v3_complete_module_ownership_cannot_be_backed_only_by_unknown_source(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    assert_array(snapshot["evidence_sources"]).append(
        {
            "source_id": "ownership:compile",
            "kind": "test-module-source",
            "authorities": ["module-ownership"],
            "context": "compile",
            "completeness": "unknown",
            "truncation": "unknown",
        }
    )
    snapshot["module_ownership"] = [
        {
            "module": "library.module",
            "context": "compile",
            "owners": ["library@1"],
            "completeness": "complete",
            "evidence_sources": ["ownership:compile"],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError, match="module ownership exceeds evidence source"
        ):
            codemap.dependency_resolution_evidence(snapshot)


def test_v3_complete_coverage_can_combine_complete_sources(tmp_path: Path) -> None:
    snapshot = _snapshot_v3()
    assert_array(snapshot["evidence_sources"]).append(
        {
            "source_id": "tree:compile:second",
            "kind": "test-resolution-source",
            "authorities": ["resolution-graph", "selection"],
            "context": "compile",
            "completeness": "complete",
            "truncation": "complete",
        }
    )
    assert_array(
        assert_object(assert_array(snapshot["coverage"])[0])["evidence_sources"]
    ).append("tree:compile:second")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)

    coverage = next(
        row
        for row in assert_array(packet["coverage"])
        if assert_object(row)["context"] == "compile"
        and assert_object(row)["kind"] == "resolution-graph"
    )
    assert assert_object(coverage)["completeness"] == "complete"
    assert assert_object(coverage)["truncation"] == "complete"


def test_v3_unknown_coverage_can_reference_complete_source_without_strengthening(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    assert_object(assert_array(snapshot["coverage"])[0])["completeness"] = "unknown"
    assert_object(assert_array(snapshot["coverage"])[0])["truncation"] = "unknown"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)

    coverage = next(
        row
        for row in assert_array(packet["coverage"])
        if assert_object(row)["context"] == "compile"
        and assert_object(row)["kind"] == "resolution-graph"
    )
    assert assert_object(coverage)["completeness"] == "unknown"
    assert assert_object(coverage)["truncation"] == "unknown"


def test_v3_reachability_rejects_unknown_target_node(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        with pytest.raises(ValueError, match="unknown dependency query target_id"):
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "reachability",
                        "node_id": "app@1",
                        "target_id": "missing@1",
                    }
                ],
            )


def test_v3_paths_rejects_unknown_target_node(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        with pytest.raises(ValueError, match="unknown dependency query target_id"):
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "paths",
                        "node_id": "app@1",
                        "target_id": "missing@1",
                    }
                ],
            )


def test_v3_contexts_rejects_unknown_node(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        with pytest.raises(ValueError, match="unknown dependency query node_id"):
            codemap.dependency_resolution_queries(
                observation,
                [{"operation": "contexts", "node_id": "missing@1"}],
            )


def test_v3_queries_reject_unknown_context_filter(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        for request in (
            {
                "operation": "dependencies",
                "node_id": "app@1",
                "context": "missing",
            },
            {"operation": "inventory", "context": "missing"},
            {"operation": "module-owners", "module": "library", "context": "missing"},
        ):
            with pytest.raises(ValueError, match="unknown dependency query context"):
                codemap.dependency_resolution_queries(observation, [request])


def test_v3_component_unknown_identity_is_authoritative_absence(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        packet = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "component", "component_id": "missing"}],
        )

    result = assert_array(packet["results"])[0]
    assert assert_object(result)["result"] == []
    assert (
        assert_object(result)["negative_evidence"] == "admissible-within-declared-scope"
    )


def test_v3_component_absence_requires_complete_selection_coverage(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    snapshot["coverage"] = [
        row
        for row in assert_array(snapshot["coverage"])
        if assert_object(row)["kind"] != "selection"
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(snapshot)
        result = assert_array(
            codemap.dependency_resolution_queries(
                observation, [{"operation": "component", "component_id": "missing"}]
            )["results"]
        )[0]

    assert assert_object(result)["result"] == []
    assert assert_object(result)["completeness"] == "incomplete"
    assert assert_object(result)["negative_evidence"] == "not-admissible"


def test_v3_component_present_identity_does_not_claim_negative_evidence(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        packet = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "component", "component_id": "library"}],
        )

    result = assert_array(packet["results"])[0]
    assert assert_object(result)["result"]
    assert assert_object(result)["negative_evidence"] == "not-applicable"


def test_v3_component_absence_remains_authoritative_with_incomplete_resolution_coverage(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["coverage"])[1])["completeness"] = "incomplete"
    assert_object(assert_array(changed["coverage"])[1])["truncation"] = "truncated"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "component", "component_id": "missing"}],
        )

    result = assert_array(packet["results"])[0]
    assert assert_object(result)["result"] == []
    assert assert_object(result)["completeness"] == "complete"
    assert (
        assert_object(result)["negative_evidence"] == "admissible-within-declared-scope"
    )


def test_v3_component_result_limit_does_not_weaken_exact_identity_lookup(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        packet = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "component",
                    "component_id": "library",
                    "max_results": 1,
                }
            ],
        )

    result = assert_array(packet["results"])[0]
    assert len(assert_array(assert_object(result)["result"])) == 1
    assert assert_object(result)["completeness"] == "complete"
    assert assert_object(result)["omissions"] == []


def test_v3_component_without_selection_is_rejected(tmp_path: Path) -> None:
    snapshot = _snapshot_v3()
    assert_array(snapshot["components"]).append(
        {"component_id": "orphan", "name": "orphan", "ecosystem": "test"}
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="component has no dependency selection"):
            codemap.dependency_resolution_evidence(snapshot)


def test_v3_multiple_selections_for_one_component_remain_valid(tmp_path: Path) -> None:
    snapshot = _snapshot_v3()
    assert_array(snapshot["selections"]).append(
        {
            "node_id": "library@2",
            "component_id": "library",
            "version": "2",
            "source": "registry",
            "contexts": ["compile"],
            "evidence_sources": ["tree:compile"],
        }
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)

    library_nodes = {
        assert_object(row)["node_id"]
        for row in assert_array(packet["selections"])
        if assert_object(row)["component_id"] == "library"
    }
    assert library_nodes == {"library@1", "library@2"}


def test_v3_selection_without_any_context_is_rejected(tmp_path: Path) -> None:
    snapshot = _snapshot_v3()
    selection = next(
        row
        for row in assert_array(snapshot["selections"])
        if assert_object(row)["node_id"] == "library@1"
    )
    assert_object(selection)["contexts"] = []
    snapshot["inventory"] = [
        row
        for row in assert_array(snapshot["inventory"])
        if assert_object(row)["node_id"] != "library@1"
    ]
    snapshot["relationships"] = [
        row
        for row in assert_array(snapshot["relationships"])
        if assert_object(row)["source"] != "library@1"
        and assert_object(row)["target"] != "library@1"
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="selection context must not be empty"):
            codemap.dependency_resolution_evidence(snapshot)


def test_v3_root_requires_evidence_source_provenance(tmp_path: Path) -> None:
    snapshot = _snapshot_v3()
    assert_object(assert_array(snapshot["roots"])[0])["evidence_sources"] = []
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="root must reference evidence source"):
            codemap.dependency_resolution_evidence(snapshot)


def test_v3_root_rejects_incompatible_evidence_source_context(tmp_path: Path) -> None:
    snapshot = _snapshot_v3()
    assert_object(assert_array(snapshot["roots"])[0])["evidence_sources"] = [
        "tree:runtime"
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError, match="incompatible root evidence source context"
        ):
            codemap.dependency_resolution_evidence(snapshot)


def test_v3_root_provenance_changes_observation_not_resolution_identity(
    tmp_path: Path,
) -> None:
    baseline = _snapshot_v3()
    changed = _snapshot_v3()
    assert_array(changed["evidence_sources"]).append(
        {
            "source_id": "tree:compile:copy",
            "kind": "test-resolution-source",
            "authorities": ["resolution-graph", "selection"],
            "context": "compile",
            "completeness": "complete",
            "truncation": "complete",
        }
    )
    assert_object(assert_array(changed["roots"])[0])["evidence_sources"] = [
        "tree:compile:copy"
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(baseline)
        after = codemap.dependency_resolution_evidence(changed)

    assert before["definition_identity"] == after["definition_identity"]
    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]


def test_v3_selection_requires_provenance_for_each_observed_context(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    library = next(
        row
        for row in assert_array(snapshot["selections"])
        if assert_object(row)["node_id"] == "library@1"
    )
    assert_object(library)["contexts"] = ["compile", "runtime"]
    assert_object(library)["evidence_sources"] = ["tree:compile"]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="selection context lacks selection evidence authority: library@1:runtime",
        ):
            codemap.dependency_resolution_evidence(snapshot)


def test_v3_complete_resolution_graph_can_have_selected_nodes_without_root(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    changed["roots"] = [
        row
        for row in assert_array(changed["roots"])
        if assert_object(row)["context"] != "runtime"
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        result = assert_array(
            codemap.dependency_resolution_queries(
                observation,
                [
                    {
                        "operation": "dependencies",
                        "node_id": "library@1",
                        "context": "runtime",
                    }
                ],
            )["results"]
        )[0]

    assert assert_object(result)["result"] == []
    assert (
        assert_object(result)["negative_evidence"] == "admissible-within-declared-scope"
    )


def test_v3_unscoped_inventory_absence_requires_coverage_for_every_context(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v3())
        packet = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "inventory", "node_id": "missing@1"}],
        )

    result = assert_array(packet["results"])[0]
    assert assert_object(result)["result"] == []
    assert assert_object(result)["completeness"] == "incomplete"
    assert assert_object(result)["negative_evidence"] == "not-admissible"


def test_v3_empty_complete_graph_and_inventory_preserve_negative_evidence(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    changed["roots"] = []
    changed["components"] = []
    changed["selections"] = []
    changed["inventory"] = []
    changed["relationships"] = []
    changed["module_ownership"] = []
    assert_array(changed["coverage"]).append(
        {
            "context": "compile",
            "kind": "module-ownership",
            "completeness": "complete",
            "truncation": "complete",
            "evidence_sources": ["list:compile"],
        }
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        results = codemap.dependency_resolution_queries(
            observation,
            [
                {"operation": "inventory", "node_id": "absent", "context": "compile"},
                {
                    "operation": "module-owners",
                    "module": "absent",
                    "context": "compile",
                },
            ],
        )["results"]

    assert observation["roots"] == []
    assert (
        assert_object(assert_array(observation["negative_evidence"])[0])[
            "producer_authority"
        ]
        == "caller-claimed"
    )
    assert all(
        assert_object(row)["negative_evidence"] == "admissible-within-declared-scope"
        for row in assert_array(results)
    )


def test_v3_inventory_requires_resolved_inventory_evidence_authority(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["evidence_sources"]).append(
        {
            "source_id": "fact:inventory:compile",
            "kind": "opaque-fact-source",
            "authorities": ["selection"],
            "context": "compile",
            "completeness": "complete",
            "truncation": "complete",
        }
    )
    assert_object(assert_array(changed["inventory"])[0])["evidence_sources"] = [
        "fact:inventory:compile"
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="inventory requires resolved-inventory evidence authority",
        ):
            codemap.dependency_resolution_evidence(changed)


def test_v3_module_ownership_requires_module_ownership_evidence_authority(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["evidence_sources"])[2])["authorities"] = [
        "resolved-inventory",
        "selection",
    ]
    changed["module_ownership"] = [
        {
            "module": "library.module",
            "context": "compile",
            "owners": ["library@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile"],
        }
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="module ownership requires module-ownership evidence authority",
        ):
            codemap.dependency_resolution_evidence(changed)


def test_v3_selection_requires_selection_evidence_authority(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["evidence_sources"])[2])["authorities"] = [
        "module-ownership",
        "resolved-inventory",
    ]
    selection_coverage = next(
        row
        for row in assert_array(changed["coverage"])
        if assert_object(row)["context"] == "compile"
        and assert_object(row)["kind"] == "selection"
    )
    assert_object(selection_coverage)["evidence_sources"] = ["tree:compile"]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="selection requires selection evidence authority",
        ):
            codemap.dependency_resolution_evidence(changed)


def test_v3_rejects_producer_specific_coverage_kind(tmp_path: Path) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["coverage"])[0])["kind"] = (
        "maven-dependency-tree"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="unsupported dependency coverage kind: maven-dependency-tree",
        ):
            codemap.dependency_resolution_evidence(changed)


def test_v3_complete_graph_coverage_refuses_inventory_only_source_authority(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["evidence_sources"])[0])["authorities"] = [
        "selection"
    ]
    assert_object(assert_array(changed["coverage"])[0])["evidence_sources"] = [
        "tree:compile"
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="resolution-graph coverage requires resolution-graph evidence authority",
        ):
            codemap.dependency_resolution_evidence(changed)


def test_v3_relationship_refuses_inventory_only_source_authority(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_array(changed["evidence_sources"]).append(
        {
            "source_id": "fact:relationship:compile",
            "kind": "opaque-fact-source",
            "authorities": ["selection"],
            "context": "compile",
            "completeness": "complete",
            "truncation": "complete",
        }
    )
    assert_object(assert_array(changed["relationships"])[0])["evidence_sources"] = [
        "fact:relationship:compile"
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="relationship requires resolution-graph evidence authority",
        ):
            codemap.dependency_resolution_evidence(changed)


def test_v3_root_refuses_inventory_only_source_authority(tmp_path: Path) -> None:
    changed = _snapshot_v3()
    assert_array(changed["evidence_sources"]).append(
        {
            "source_id": "fact:root:compile",
            "kind": "opaque-fact-source",
            "authorities": ["selection"],
            "context": "compile",
            "completeness": "complete",
            "truncation": "complete",
        }
    )
    assert_object(assert_array(changed["roots"])[0])["evidence_sources"] = [
        "fact:root:compile"
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="root requires resolution-graph evidence authority",
        ):
            codemap.dependency_resolution_evidence(changed)


def test_v3_complete_inventory_coverage_refuses_graph_only_source_authority(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v3()
    assert_object(assert_array(changed["evidence_sources"])[2])["authorities"] = [
        "selection"
    ]
    assert_object(assert_array(changed["coverage"])[2])["evidence_sources"] = [
        "list:compile"
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="resolved-inventory coverage requires resolved-inventory evidence authority",
        ):
            codemap.dependency_resolution_evidence(changed)


@pytest.mark.parametrize(
    ("family", "index", "unsupported", "message"),
    [
        ("roots", 0, "list:compile", "root requires resolution-graph"),
        ("relationships", 0, "list:compile", "relationship requires resolution-graph"),
        ("inventory", 0, "tree:compile", "inventory requires resolved-inventory"),
        (
            "coverage",
            0,
            "list:compile",
            "resolution-graph coverage requires resolution-graph",
        ),
        (
            "coverage",
            2,
            "tree:compile",
            "resolved-inventory coverage requires resolved-inventory",
        ),
        ("coverage", 3, "tree:runtime", "incompatible evidence source context"),
    ],
)
def test_v3_every_cited_source_must_support_its_fact_or_coverage(
    tmp_path: Path,
    family: str,
    index: int,
    unsupported: str,
    message: str,
) -> None:
    snapshot = _snapshot_v3()
    assert_array(
        assert_object(assert_array(snapshot[family])[index])["evidence_sources"]
    ).append(unsupported)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match=message):
            codemap.dependency_resolution_evidence(snapshot)


def test_v3_mixed_module_ownership_sources_do_not_borrow_authority(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v3()
    snapshot["module_ownership"] = [
        {
            "module": "library.module",
            "context": "compile",
            "owners": ["library@1"],
            "completeness": "complete",
            "evidence_sources": ["list:compile", "tree:compile"],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError, match="module ownership requires module-ownership"
        ):
            codemap.dependency_resolution_evidence(snapshot)


def test_v3_mixed_selection_sources_do_not_borrow_authority(tmp_path: Path) -> None:
    snapshot = _snapshot_v3()
    assert_array(snapshot["evidence_sources"]).append(
        {
            "source_id": "ownership-only:compile",
            "kind": "opaque",
            "authorities": ["module-ownership"],
            "context": "compile",
            "completeness": "complete",
            "truncation": "complete",
        }
    )
    assert_array(
        assert_object(assert_array(snapshot["selections"])[0])["evidence_sources"]
    ).append("ownership-only:compile")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError, match="selection requires selection evidence authority"
        ):
            codemap.dependency_resolution_evidence(snapshot)


def test_v3_delta_reports_cross_repository_identity_change(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()

    with CodeMap(left) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(_snapshot_v3())
    with CodeMap(right) as codemap:
        codemap.sync()
        after = codemap.dependency_resolution_evidence(_snapshot_v3())

    delta = CodeMap.dependency_resolution_delta(before, after)

    assert delta["comparability"] == "comparable"
    assert assert_object(delta["change_axes"])["repository_identity"] == "changed"
    assert assert_object(delta["change_axes"])["semantic_resolution"] == "unchanged"
