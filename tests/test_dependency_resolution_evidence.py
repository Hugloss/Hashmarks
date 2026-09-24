from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.codemap.engine import CodeMap


def _snapshot_v2() -> dict[str, object]:
    return {
        "schema": "hashmarks.dependency-resolution.v2",
        "producer": {"kind": "neutral-resolver", "schema_version": "1"},
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
                "kind": "resolution-graph",
                "context": "compile",
                "completeness": "complete",
                "truncation": "complete",
            },
            {
                "source_id": "tree:runtime",
                "kind": "resolution-graph",
                "context": "runtime",
                "completeness": "complete",
                "truncation": "complete",
            },
            {
                "source_id": "list:compile",
                "kind": "resolved-inventory",
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
        ],
        "repository_inputs": [],
        "module_ownership": [],
    }


def test_v2_distinguishes_inventory_membership_from_graph_reachability(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(_snapshot_v2())

    inventory_nodes = {row["node_id"] for row in packet["inventory"]}
    graph_nodes = {
        endpoint
        for row in packet["relationships"]
        for endpoint in (row["source"], row["target"])
    }
    assert "inventory-only@1" in inventory_nodes
    assert "inventory-only@1" not in graph_nodes


def test_v2_separates_component_selection_and_observation_identity(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.dependency_resolution_evidence(_snapshot_v2())
        changed = _snapshot_v2()
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


def test_v2_negative_evidence_is_scoped_by_context_and_source_kind(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    changed["coverage"][1]["completeness"] = "incomplete"
    changed["coverage"][1]["truncation"] = "truncated"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(changed)

    states = {
        (row["context"], row["kind"]): row["state"]
        for row in packet["negative_evidence"]
    }
    assert states[("compile", "resolution-graph")] == "admissible-within-declared-scope"
    assert states[("runtime", "resolution-graph")] == "not-admissible"


def test_v2_rejects_dangling_evidence_source_reference(tmp_path: Path) -> None:
    changed = _snapshot_v2()
    changed["relationships"][0]["evidence_sources"] = ["missing"]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="dangling relationship evidence source"):
            codemap.dependency_resolution_evidence(changed)


def test_v2_delta_reports_selection_inventory_and_relationship_change(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(_snapshot_v2())
        changed = _snapshot_v2()
        changed["selections"][1]["version"] = "2"
        changed["inventory"] = [
            row for row in changed["inventory"] if row["node_id"] != "inventory-only@1"
        ]
        changed["relationships"][0]["effective_scope"] = "runtime"
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


def test_v2_relationship_parent_change_is_not_selection_change(
    tmp_path: Path,
) -> None:
    before_snapshot = _snapshot_v2()
    after_snapshot = _snapshot_v2()
    after_snapshot["relationships"][0]["source"] = "inventory-only@1"

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


def test_v2_rejects_module_owner_outside_observed_context(tmp_path: Path) -> None:
    changed = _snapshot_v2()
    changed["selections"][1]["contexts"] = ["runtime"]
    changed["selections"][1]["evidence_sources"] = ["tree:runtime"]
    changed["inventory"] = [
        row for row in changed["inventory"] if row["node_id"] != "library@1"
    ]
    changed["relationships"] = [
        row
        for row in changed["relationships"]
        if row["target"] != "library@1" or row["context"] != "compile"
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


def test_v2_module_ownership_preserves_ambiguous_maven_module(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v2()
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

    ownership = observation["module_ownership"][0]
    assert ownership["state"] == "resolved-ambiguous"
    assert ownership["owners"] == ["inventory-only@1", "library@1"]


def test_v2_dependency_correlation_preserves_contextual_ownership(
    tmp_path: Path,
) -> None:
    (tmp_path / "consumer.py").write_text("import library\n")
    snapshot = _snapshot_v2()
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

    assert packet["dependency_links"] == [
        {
            "module": "library",
            "context": "compile",
            "distribution_state": "resolved-unique",
            "distribution_nodes": ["library@1"],
            "ownership_completeness": "complete",
            "observed_contexts": ["compile"],
            "causation": "not-inferred",
        }
    ]
    assert packet["correlation"]["bundles"][0]["scope"] == {
        "kind": "dependency-module-correlation",
        "module": "library",
        "context": "compile",
    }


def test_v2_dependency_correlation_without_context_preserves_cross_context_ambiguity(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v2()
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

    link = packet["dependency_links"][0]
    assert link["distribution_state"] == "resolved-ambiguous"
    assert link["distribution_nodes"] == ["app@1", "library@1"]
    assert link["observed_contexts"] == ["compile", "runtime"]


def test_v2_repository_binding_tracks_current_codemap_generation(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(_snapshot_v2())
        expected_identity = codemap._repository_packet_identity()
        expected_generation = codemap.store.generation()

    binding = packet["repository_binding"]
    assert binding["repository_identity"] == expected_identity
    assert binding["repository_identity"].startswith(("git-tree:", "workspace:"))
    assert binding["codemap_generation"] == expected_generation


def test_v2_bounded_queries_report_dependencies_paths_and_contexts(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v2())
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

    dependencies, paths, contexts = packet["results"]
    assert dependencies["result"][0]["node_id"] == "library@1"
    assert paths["result"] == [["app@1", "library@1"]]
    assert contexts["result"] == ["compile", "runtime"]
    assert all(row["completeness"] == "complete" for row in packet["results"])


def test_v2_reachability_absence_requires_complete_context_coverage(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    changed["coverage"][1]["completeness"] = "incomplete"
    changed["coverage"][1]["truncation"] = "truncated"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "reachability",
                    "node_id": "inventory-only@1",
                    "target_id": "library@1",
                    "context": "compile",
                },
                {
                    "operation": "reachability",
                    "node_id": "inventory-only@1",
                    "target_id": "library@1",
                    "context": "runtime",
                },
            ],
        )

    assert (
        packet["results"][0]["result"]["negative_evidence"]
        == "admissible-within-declared-scope"
    )
    assert packet["results"][1]["result"]["negative_evidence"] == "not-admissible"


def test_v2_query_exposes_depth_omission_instead_of_silent_partial_result(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    changed["components"].append(
        {"component_id": "leaf", "name": "leaf", "ecosystem": "test"}
    )
    changed["selections"].append(
        {
            "node_id": "leaf@1",
            "component_id": "leaf",
            "version": "1",
            "source": "registry",
            "contexts": ["compile"],
            "evidence_sources": ["tree:compile"],
        }
    )
    changed["relationships"].append(
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

    result = packet["results"][0]
    assert [row["node_id"] for row in result["result"]] == ["library@1"]
    assert result["completeness"] == "incomplete"
    assert result["omissions"] == [{"reason": "depth-limit", "node_id": "library@1"}]


def test_v2_provenance_change_does_not_masquerade_as_resolution_change(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(_snapshot_v2())
        changed = _snapshot_v2()
        changed["evidence_sources"][0]["producer_digest"] = "sha256:producer-a"
        after = codemap.dependency_resolution_evidence(changed)
        delta = codemap.dependency_resolution_delta(before, after)

    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]
    assert delta["selections_changed"] == []
    assert delta["relationships_added"] == []
    assert delta["relationships_removed"] == []


def test_v2_contextual_module_ownership_preserves_independent_observations(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
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

    assert [(row["module"], row["context"]) for row in packet["module_ownership"]] == [
        ("library.module", "compile"),
        ("library.module", "runtime"),
    ]


def test_v2_producer_neutral_model_accepts_uv_contexts_without_maven_semantics(
    tmp_path: Path,
) -> None:
    snapshot = {
        "schema": "hashmarks.dependency-resolution.v2",
        "producer": {"kind": "uv-lock-projection", "schema_version": "1"},
        "scope": {"python": "3.14", "platform": "linux"},
        "contexts": ["default", "dev"],
        "roots": [
            {
                "node_id": "demo@workspace",
                "context": "default",
                "evidence_sources": ["uv:lock"],
            },
            {
                "node_id": "demo@workspace",
                "context": "dev",
                "evidence_sources": ["uv:lock"],
            },
        ],
        "evidence_sources": [
            {
                "source_id": "uv:lock",
                "kind": "resolution-graph",
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
                "evidence_sources": ["uv:lock"],
            },
            {
                "node_id": "pytest@9",
                "component_id": "pytest",
                "version": "9.0.2",
                "source": "registry",
                "contexts": ["dev"],
                "evidence_sources": ["uv:lock"],
            },
        ],
        "inventory": [
            {
                "node_id": "pytest@9",
                "context": "dev",
                "evidence_sources": ["uv:lock"],
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
                "evidence_sources": ["uv:lock"],
            }
        ],
        "coverage": [
            {
                "context": "dev",
                "kind": "resolution-graph",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["uv:lock"],
            }
        ],
        "repository_inputs": [],
        "module_ownership": [],
    }
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)

    assert packet["producer"]["kind"] == "uv-lock-projection"
    assert packet["contexts"] == ["default", "dev"]
    assert packet["relationships"][0]["context"] == "dev"
    assert "groupId" not in repr(packet)
    assert "artifactId" not in repr(packet)


def test_v2_module_owner_absence_requires_complete_ownership_coverage(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    changed["coverage"].append(
        {
            "context": "compile",
            "kind": "module-ownership",
            "completeness": "complete",
            "truncation": "complete",
            "evidence_sources": ["list:compile"],
        }
    )
    changed["coverage"].append(
        {
            "context": "runtime",
            "kind": "module-ownership",
            "completeness": "incomplete",
            "truncation": "complete",
            "evidence_sources": ["tree:runtime"],
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

    compile_result, runtime_result = packet["results"]
    assert compile_result["result"] == []
    assert compile_result["negative_evidence"] == "admissible-within-declared-scope"
    assert compile_result["completeness"] == "complete"
    assert runtime_result["result"] == []
    assert runtime_result["completeness"] == "incomplete"
    assert runtime_result["negative_evidence"] == "not-admissible"


def test_v2_dependency_query_exact_result_bound_is_complete(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v2())
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

    result = packet["results"][0]
    assert [row["node_id"] for row in result["result"]] == ["library@1"]
    assert result["completeness"] == "complete"
    assert result["omissions"] == []


def test_v2_dependency_query_reports_result_bound_when_result_is_omitted(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    changed["components"].append(
        {"component_id": "second", "name": "second", "ecosystem": "test"}
    )
    changed["selections"].append(
        {
            "node_id": "second@1",
            "component_id": "second",
            "version": "1",
            "source": "registry",
            "contexts": ["compile"],
            "evidence_sources": ["tree:compile"],
        }
    )
    changed["relationships"].append(
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

    result = packet["results"][0]
    assert len(result["result"]) == 1
    assert result["completeness"] == "incomplete"
    assert result["omissions"] == [{"reason": "result-limit"}]


def test_v2_context_query_reports_observed_contexts_despite_context_argument(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v2())
        packet = codemap.dependency_resolution_queries(
            observation,
            [
                {
                    "operation": "contexts",
                    "node_id": "library@1",
                    "context": "compile",
                }
            ],
        )

    result = packet["results"][0]
    assert result["result"] == ["compile", "runtime"]


def test_v2_context_query_includes_selection_context_without_inventory_or_edge(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    changed["contexts"].append("optional")
    changed["evidence_sources"].append(
        {
            "source_id": "tree:optional",
            "kind": "resolution-graph",
            "context": "optional",
            "completeness": "incomplete",
            "truncation": "complete",
        }
    )
    changed["selections"][1]["contexts"].append("optional")
    changed["selections"][1]["evidence_sources"].append("tree:optional")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "contexts", "node_id": "library@1"}],
        )

    assert packet["results"][0]["result"] == ["compile", "optional", "runtime"]


def test_v2_inventory_absence_requires_complete_inventory_coverage(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    changed["evidence_sources"].append(
        {
            "source_id": "list:runtime",
            "kind": "resolved-inventory",
            "context": "runtime",
            "completeness": "incomplete",
            "truncation": "complete",
        }
    )
    changed["coverage"].append(
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

    compile_result, runtime_result = packet["results"]
    assert compile_result["result"] == []
    assert compile_result["completeness"] == "complete"
    assert compile_result["negative_evidence"] == "admissible-within-declared-scope"
    assert runtime_result["result"] == []
    assert runtime_result["completeness"] == "incomplete"
    assert runtime_result["negative_evidence"] == "not-admissible"


def test_v2_unscoped_module_absence_requires_coverage_for_every_context(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    changed["evidence_sources"].append(
        {
            "source_id": "modules:compile",
            "kind": "module-ownership",
            "context": "compile",
            "completeness": "complete",
            "truncation": "complete",
        }
    )
    changed["coverage"].append(
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

    result = packet["results"][0]
    assert result["result"] == []
    assert result["completeness"] == "incomplete"
    assert result["negative_evidence"] == "not-admissible"


def test_v2_unscoped_module_absence_is_admissible_when_all_contexts_complete(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    for context in ("compile", "runtime"):
        source_id = f"modules:{context}"
        changed["evidence_sources"].append(
            {
                "source_id": source_id,
                "kind": "module-ownership",
                "context": context,
                "completeness": "complete",
                "truncation": "complete",
            }
        )
        changed["coverage"].append(
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

    result = packet["results"][0]
    assert result["result"] == []
    assert result["completeness"] == "complete"
    assert result["negative_evidence"] == "admissible-within-declared-scope"


def test_v2_graph_query_completeness_requires_complete_resolution_coverage(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    runtime_coverage = next(
        row
        for row in changed["coverage"]
        if row["context"] == "runtime" and row["kind"] == "resolution-graph"
    )
    runtime_coverage["completeness"] = "incomplete"
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

    dependencies, paths = packet["results"]
    assert [row["node_id"] for row in dependencies["result"]] == ["library@1"]
    assert dependencies["omissions"] == []
    assert dependencies["completeness"] == "incomplete"
    assert paths["result"] == [["app@1", "library@1"]]
    assert paths["omissions"] == []
    assert paths["completeness"] == "incomplete"


def test_v2_empty_graph_queries_expose_negative_evidence_authority(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    runtime_coverage = next(
        row
        for row in changed["coverage"]
        if row["context"] == "runtime" and row["kind"] == "resolution-graph"
    )
    runtime_coverage["completeness"] = "incomplete"
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

    compile_dependencies, runtime_dependencies, compile_paths, runtime_paths = packet[
        "results"
    ]
    assert compile_dependencies["result"] == []
    assert (
        compile_dependencies["negative_evidence"] == "admissible-within-declared-scope"
    )
    assert runtime_dependencies["result"] == []
    assert runtime_dependencies["negative_evidence"] == "not-admissible"
    assert compile_paths["result"] == []
    assert compile_paths["negative_evidence"] == "admissible-within-declared-scope"
    assert runtime_paths["result"] == []
    assert runtime_paths["negative_evidence"] == "not-admissible"


def test_v2_path_query_exact_result_bound_does_not_claim_omission(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    changed["components"].extend(
        [
            {"component_id": "dead", "ecosystem": "generic", "name": "dead"},
            {
                "component_id": "target",
                "ecosystem": "generic",
                "name": "target",
            },
        ]
    )
    changed["selections"].extend(
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
    changed["relationships"].extend(
        [
            {
                "source": "app@1",
                "target": "dead@1",
                "kind": "depends-on",
                "context": "compile",
                "evidence_sources": ["tree:compile"],
            },
            {
                "source": "library@1",
                "target": "target@1",
                "kind": "depends-on",
                "context": "compile",
                "evidence_sources": ["tree:compile"],
            },
        ]
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        result = codemap.dependency_resolution_queries(
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
        )["results"][0]

    assert result["result"] == [["app@1", "library@1", "target@1"]]
    assert result["omissions"] == []
    assert result["completeness"] == "complete"


def test_v2_path_query_reports_result_bound_only_when_a_path_is_omitted(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    changed["relationships"].append(
        {
            "source": "app@1",
            "target": "library@1",
            "kind": "depends-on",
            "context": "compile",
            "evidence_sources": ["tree:compile"],
        }
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        result = codemap.dependency_resolution_queries(
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
        )["results"][0]

    assert len(result["result"]) == 1
    assert result["omissions"] == [{"reason": "result-limit"}]
    assert result["completeness"] == "incomplete"


def _visit_limit_snapshot() -> dict[str, object]:
    snapshot = _snapshot_v2()
    snapshot["components"].extend(
        [
            {"component_id": "left", "name": "left", "ecosystem": "test"},
            {"component_id": "right", "name": "right", "ecosystem": "test"},
        ]
    )
    snapshot["selections"].extend(
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
def test_v2_query_visit_accounting_never_exceeds_declared_bound(
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
        result = codemap.dependency_resolution_queries(observation, [request])[
            "results"
        ][0]

    assert result["bounds"]["visited"] <= result["bounds"]["max_visits"]
    assert result["completeness"] == "incomplete"
    assert result["omissions"] == [{"reason": "visit-limit"}]


def test_v2_complete_module_ownership_cannot_exceed_incomplete_source(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v2()
    snapshot["evidence_sources"].append(
        {
            "source_id": "ownership:compile",
            "kind": "module-ownership",
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


def test_v2_complete_module_ownership_cannot_be_backed_only_by_unknown_source(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v2()
    snapshot["evidence_sources"].append(
        {
            "source_id": "ownership:compile",
            "kind": "module-ownership",
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


def test_v2_complete_coverage_can_combine_complete_sources(tmp_path: Path) -> None:
    snapshot = _snapshot_v2()
    snapshot["evidence_sources"].append(
        {
            "source_id": "tree:compile:second",
            "kind": "resolution-graph",
            "context": "compile",
            "completeness": "complete",
            "truncation": "complete",
        }
    )
    snapshot["coverage"][0]["evidence_sources"].append("tree:compile:second")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)

    coverage = next(
        row
        for row in packet["coverage"]
        if row["context"] == "compile" and row["kind"] == "resolution-graph"
    )
    assert coverage["completeness"] == "complete"
    assert coverage["truncation"] == "complete"


def test_v2_unknown_coverage_can_reference_complete_source_without_strengthening(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v2()
    snapshot["coverage"][0]["completeness"] = "unknown"
    snapshot["coverage"][0]["truncation"] = "unknown"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)

    coverage = next(
        row
        for row in packet["coverage"]
        if row["context"] == "compile" and row["kind"] == "resolution-graph"
    )
    assert coverage["completeness"] == "unknown"
    assert coverage["truncation"] == "unknown"


def test_v2_reachability_rejects_unknown_target_node(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v2())
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


def test_v2_paths_rejects_unknown_target_node(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v2())
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


def test_v2_contexts_rejects_unknown_node(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v2())
        with pytest.raises(ValueError, match="unknown dependency query node_id"):
            codemap.dependency_resolution_queries(
                observation,
                [{"operation": "contexts", "node_id": "missing@1"}],
            )


def test_v2_queries_reject_unknown_context_filter(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v2())
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


def test_v2_component_unknown_identity_is_authoritative_absence(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v2())
        packet = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "component", "component_id": "missing"}],
        )

    result = packet["results"][0]
    assert result["result"] == []
    assert result["negative_evidence"] == "admissible-within-declared-scope"


def test_v2_component_present_identity_does_not_claim_negative_evidence(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v2())
        packet = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "component", "component_id": "library"}],
        )

    result = packet["results"][0]
    assert result["result"]
    assert result["negative_evidence"] == "not-applicable"


def test_v2_component_absence_remains_authoritative_with_incomplete_resolution_coverage(
    tmp_path: Path,
) -> None:
    changed = _snapshot_v2()
    changed["coverage"][1]["completeness"] = "incomplete"
    changed["coverage"][1]["truncation"] = "truncated"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(changed)
        packet = codemap.dependency_resolution_queries(
            observation,
            [{"operation": "component", "component_id": "missing"}],
        )

    result = packet["results"][0]
    assert result["result"] == []
    assert result["completeness"] == "complete"
    assert result["negative_evidence"] == "admissible-within-declared-scope"


def test_v2_component_result_limit_does_not_weaken_exact_identity_lookup(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot_v2())
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

    result = packet["results"][0]
    assert len(result["result"]) == 1
    assert result["completeness"] == "complete"
    assert result["omissions"] == []


def test_v2_component_without_selection_is_rejected(tmp_path: Path) -> None:
    snapshot = _snapshot_v2()
    snapshot["components"].append(
        {"component_id": "orphan", "name": "orphan", "ecosystem": "test"}
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="component has no dependency selection"):
            codemap.dependency_resolution_evidence(snapshot)


def test_v2_multiple_selections_for_one_component_remain_valid(tmp_path: Path) -> None:
    snapshot = _snapshot_v2()
    snapshot["selections"].append(
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
        row["node_id"]
        for row in packet["selections"]
        if row["component_id"] == "library"
    }
    assert library_nodes == {"library@1", "library@2"}


def test_v2_selection_without_any_context_is_rejected(tmp_path: Path) -> None:
    snapshot = _snapshot_v2()
    selection = next(
        row for row in snapshot["selections"] if row["node_id"] == "library@1"
    )
    selection["contexts"] = []
    snapshot["inventory"] = [
        row for row in snapshot["inventory"] if row["node_id"] != "library@1"
    ]
    snapshot["relationships"] = [
        row
        for row in snapshot["relationships"]
        if row["source"] != "library@1" and row["target"] != "library@1"
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="selection context must not be empty"):
            codemap.dependency_resolution_evidence(snapshot)


def test_v2_root_requires_evidence_source_provenance(tmp_path: Path) -> None:
    snapshot = _snapshot_v2()
    snapshot["roots"][0]["evidence_sources"] = []
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="root must reference evidence source"):
            codemap.dependency_resolution_evidence(snapshot)


def test_v2_root_rejects_incompatible_evidence_source_context(tmp_path: Path) -> None:
    snapshot = _snapshot_v2()
    snapshot["roots"][0]["evidence_sources"] = ["tree:runtime"]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError, match="incompatible root evidence source context"
        ):
            codemap.dependency_resolution_evidence(snapshot)


def test_v2_root_provenance_changes_observation_not_resolution_identity(
    tmp_path: Path,
) -> None:
    baseline = _snapshot_v2()
    changed = _snapshot_v2()
    changed["evidence_sources"].append(
        {
            "source_id": "tree:compile:copy",
            "kind": "resolution-graph",
            "context": "compile",
            "completeness": "complete",
            "truncation": "complete",
        }
    )
    changed["roots"][0]["evidence_sources"] = ["tree:compile:copy"]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(baseline)
        after = codemap.dependency_resolution_evidence(changed)

    assert before["definition_identity"] == after["definition_identity"]
    assert before["resolution_identity"] == after["resolution_identity"]
    assert before["observation_identity"] != after["observation_identity"]


def test_v2_selection_requires_provenance_for_each_observed_context(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_v2()
    library = next(
        row for row in snapshot["selections"] if row["node_id"] == "library@1"
    )
    library["contexts"] = ["compile", "runtime"]
    library["evidence_sources"] = ["tree:compile"]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="selection context lacks evidence source: library@1:runtime",
        ):
            codemap.dependency_resolution_evidence(snapshot)
