from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.codemap.engine import CodeMap


def _snapshot(*, scope: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "schema": "hashmarks.dependency-resolution.v1",
        "producer": {"kind": "uv-workspace-metadata", "schema_version": "preview-1"},
        "scope": scope
        or {"python": "3.14", "platform": "linux", "groups": ["default"]},
        "roots": ["root"],
        "nodes": [
            {
                "node_id": "root",
                "name": "demo",
                "version": "0.1.0",
                "source": "workspace",
                "marker": "",
            },
            {
                "node_id": "crypto-registry",
                "name": "cryptography",
                "version": "46.0.4",
                "source": "registry",
                "marker": "python_version >= '3.11'",
            },
        ],
        "edges": [
            {
                "source": "root",
                "target": "crypto-registry",
                "kind": "dependency",
                "marker": "",
            }
        ],
        "repository_inputs": [],
        "completeness": "complete",
        "truncation": "complete",
    }


def test_resolution_identity_is_order_independent(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.dependency_resolution_evidence(_snapshot())
        reordered = _snapshot()
        reordered["nodes"] = list(reversed(reordered["nodes"]))
        reordered["edges"] = list(reversed(reordered["edges"]))
        second = codemap.dependency_resolution_evidence(reordered)

    assert first["resolution_identity"] == second["resolution_identity"]
    assert first["definition_identity"] == second["definition_identity"]


def test_scope_change_is_not_package_delta(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(_snapshot())
        changed_scope = _snapshot(scope={"python": "3.13", "platform": "linux"})
        after = codemap.dependency_resolution_evidence(changed_scope)
        delta = codemap.dependency_resolution_delta(before, after)

    assert delta["comparability"] == "not-comparable"
    assert delta["reason"] == "definition-changed"


def test_resolution_delta_reports_node_change_without_recommendation(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(_snapshot())
        changed = _snapshot()
        changed["nodes"][1]["version"] = "46.0.7"
        after = codemap.dependency_resolution_evidence(changed)
        delta = codemap.dependency_resolution_delta(before, after)

    assert delta["comparability"] == "comparable"
    assert delta["nodes_changed"] == ["crypto-registry"]
    assert "recommendation" not in delta
    assert "cause" not in delta


def test_distribution_name_is_not_graph_identity(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot["nodes"].append(
        {
            "node_id": "crypto-git",
            "name": "cryptography",
            "version": "46.0.4",
            "source": "git",
            "marker": "sys_platform == 'linux'",
        }
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)

    assert [row["node_id"] for row in packet["nodes"]] == [
        "crypto-git",
        "crypto-registry",
        "root",
    ]


def test_cycles_are_legal_but_dangling_edges_fail_closed(tmp_path: Path) -> None:
    cycle = _snapshot()
    cycle["edges"].append(
        {
            "source": "crypto-registry",
            "target": "root",
            "kind": "dependency",
            "marker": "",
        }
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(cycle)
        assert len(packet["edges"]) == 2

        dangling = _snapshot()
        dangling["edges"].append(
            {"source": "root", "target": "missing", "kind": "dependency", "marker": ""}
        )
        with pytest.raises(ValueError, match="dangling dependency resolution edge"):
            codemap.dependency_resolution_evidence(dangling)


def test_duplicate_node_and_edge_ids_fail_closed(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        duplicate_node = _snapshot()
        duplicate_node["nodes"].append(dict(duplicate_node["nodes"][1]))
        with pytest.raises(ValueError, match="duplicate dependency resolution node_id"):
            codemap.dependency_resolution_evidence(duplicate_node)

        duplicate_edge = _snapshot()
        duplicate_edge["edges"].append(dict(duplicate_edge["edges"][0]))
        with pytest.raises(ValueError, match="duplicate dependency resolution edge"):
            codemap.dependency_resolution_evidence(duplicate_edge)


def test_repository_input_binding_requires_independent_member_revision(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='demo'\nversion='0.1.0'\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        unproven = _snapshot()
        unproven["repository_inputs"] = [{"path": "pyproject.toml"}]
        first = codemap.dependency_resolution_evidence(unproven)
        observed = first["repository_inputs"][0]["observed_member_revision"]
        assert first["repository_inputs"][0]["source_equivalence"] == "unknown"

        proven = _snapshot()
        proven["repository_inputs"] = [
            {"path": "pyproject.toml", "member_revision": observed}
        ]
        second = codemap.dependency_resolution_evidence(proven)
        assert second["repository_inputs"][0]["source_equivalence"] == "proven"

        mismatch = _snapshot()
        mismatch["repository_inputs"] = [
            {"path": "pyproject.toml", "member_revision": "0" * 64}
        ]
        third = codemap.dependency_resolution_evidence(mismatch)
        assert third["repository_inputs"][0]["source_equivalence"] == "mismatch"


def test_incomplete_resolution_cannot_prove_dependency_absence(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot["completeness"] = "incomplete"
    snapshot["truncation"] = "truncated"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)

    assert packet["negative_evidence"] == "not-admissible"


def test_complete_resolution_requires_explicit_non_truncation(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot["truncation"] = "unknown"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="completeness=complete requires truncation=complete",
        ):
            codemap.dependency_resolution_evidence(snapshot)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema", "wrong", "dependency resolution schema"),
        ("producer", None, "producer must be an object"),
        ("scope", None, "scope must be an object"),
        ("scope", {}, "scope must not be empty"),
        ("roots", "root", "roots must be a sequence"),
        ("roots", ["root", "root"], "duplicate dependency resolution root"),
        ("roots", ["missing"], "dangling dependency resolution root"),
        ("completeness", "partial", "completeness must be"),
        ("truncation", "partial", "truncation must be"),
    ],
)
def test_resolution_definition_and_bounds_fail_closed(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    snapshot = _snapshot()
    snapshot[field] = value
    with CodeMap(tmp_path) as codemap:
        with pytest.raises(ValueError, match=message):
            codemap.dependency_resolution_evidence(snapshot)


def test_owner_never_executes_dependency_tooling(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    with CodeMap(tmp_path) as codemap:
        codemap.sync()

        def forbidden(*args, **kwargs):
            raise AssertionError("dependency evidence owner must not execute tooling")

        monkeypatch.setattr(subprocess, "run", forbidden)
        packet = codemap.dependency_resolution_evidence(_snapshot())

    assert packet["producer_authority"] == "caller-claimed"
    assert packet["authority"] == "qualified-external-observation"


def test_module_distribution_ownership_requires_explicit_observation(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    snapshot["module_ownership"] = [
        {
            "module": "cryptography",
            "owners": ["crypto-registry"],
            "completeness": "complete",
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)

    ownership = packet["module_ownership"][0]
    assert ownership["module"] == "cryptography"
    assert ownership["owners"] == ["crypto-registry"]
    assert ownership["state"] == "resolved-unique"


def test_distribution_name_never_implies_module_ownership(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(_snapshot())
        result = codemap.dependency_import_correspondence(
            packet, source_path="consumer.py", import_target="cryptography"
        )

    assert result["distribution_state"] == "unknown"
    assert result["distribution_nodes"] == []


def test_import_correspondence_reuses_repository_import_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "consumer.py").write_text("import yaml\n")
    snapshot = _snapshot()
    snapshot["nodes"].append(
        {
            "node_id": "pyyaml-dist",
            "name": "PyYAML",
            "version": "6.0.2",
            "source": "registry",
            "marker": "",
        }
    )
    snapshot["module_ownership"] = [
        {"module": "yaml", "owners": ["pyyaml-dist"], "completeness": "complete"}
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)
        result = codemap.dependency_import_correspondence(
            packet, source_path="consumer.py", import_target="yaml"
        )

    assert result["module"] == "yaml"
    assert result["distribution_nodes"] == ["pyyaml-dist"]
    assert result["causation"] == "not-inferred"


def test_namespace_module_ownership_preserves_ambiguity(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot["nodes"].append(
        {
            "node_id": "namespace-two",
            "name": "namespace-provider",
            "version": "1",
            "source": "registry",
            "marker": "",
        }
    )
    snapshot["module_ownership"] = [
        {
            "module": "shared.namespace",
            "owners": ["crypto-registry", "namespace-two"],
            "completeness": "complete",
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(snapshot)

    assert packet["module_ownership"][0]["state"] == "resolved-ambiguous"


def test_module_ownership_dangling_node_fails_closed(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot["module_ownership"] = [
        {"module": "yaml", "owners": ["missing"], "completeness": "complete"}
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="dangling module ownership node"):
            codemap.dependency_resolution_evidence(snapshot)


def test_dependency_delta_reports_edges_and_module_ownership(tmp_path: Path) -> None:
    before_raw = _snapshot()
    before_raw["module_ownership"] = [
        {
            "module": "cryptography",
            "owners": ["crypto-registry"],
            "completeness": "complete",
        }
    ]
    after_raw = _snapshot()
    after_raw["nodes"].append(
        {
            "node_id": "helper",
            "name": "helper",
            "version": "1",
            "source": "registry",
            "marker": "",
        }
    )
    after_raw["edges"].append(
        {
            "source": "crypto-registry",
            "target": "helper",
            "kind": "dependency",
            "marker": "",
        }
    )
    after_raw["module_ownership"] = [
        {
            "module": "cryptography",
            "owners": ["crypto-registry", "helper"],
            "completeness": "complete",
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(before_raw)
        after = codemap.dependency_resolution_evidence(after_raw)
        delta = codemap.dependency_resolution_delta(before, after)

    assert delta["nodes_added"] == ["helper"]
    assert delta["edges_added"] == [["crypto-registry", "helper", "dependency", ""]]
    assert delta["module_ownership_changed"] == ["cryptography"]
    assert delta["causation"] == "not-inferred"


def test_dependency_correlation_reuses_generic_repository_locator_owner(
    tmp_path: Path,
) -> None:
    (tmp_path / "consumer.py").write_text("import cryptography\n")
    snapshot = _snapshot()
    snapshot["module_ownership"] = [
        {
            "module": "cryptography",
            "owners": ["crypto-registry"],
            "completeness": "complete",
        }
    ]
    request = {
        "correlations": [
            {
                "module": "cryptography",
                "completeness": "complete",
                "truncation": "complete",
                "anchors": [
                    {
                        "anchor_id": "failure",
                        "path": "consumer.py",
                        "line": 1,
                        "metadata": {"kind": "pytest-failure"},
                    }
                ],
            }
        ]
    }
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(snapshot)
        packet = codemap.dependency_evidence_correlation(observation, request)

    assert packet["dependency_links"] == [
        {
            "module": "cryptography",
            "distribution_state": "resolved-unique",
            "distribution_nodes": ["crypto-registry"],
            "ownership_completeness": "complete",
            "causation": "not-inferred",
        }
    ]
    bundle = packet["correlation"]["bundles"][0]
    assert bundle["anchors"][0]["resolution"]["state"] == "resolved-unique"
    assert bundle["anchors"][0]["resolution"]["repository_path"] == "consumer.py"
    assert packet["causation"] == "not-inferred"
    assert packet["interpretation_authority"] == "consumer-owned"


def test_cryptography_upgrade_dogfood_preserves_correlation_without_causation(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='demo'\nversion='0.1.0'\ndependencies=['cryptography>=46.0.4']\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_tls.py").write_text(
        "def test_tls():\n    assert True\n"
    )
    before_raw = _snapshot()
    before_raw["module_ownership"] = [
        {
            "module": "cryptography",
            "owners": ["crypto-registry"],
            "completeness": "complete",
        }
    ]
    after_raw = _snapshot()
    after_raw["nodes"][1]["version"] = "46.0.7"
    after_raw["module_ownership"] = [
        {
            "module": "cryptography",
            "owners": ["crypto-registry"],
            "completeness": "complete",
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.dependency_resolution_evidence(before_raw)
        after = codemap.dependency_resolution_evidence(after_raw)
        delta = codemap.dependency_resolution_delta(before, after)
        correlated = codemap.dependency_evidence_correlation(
            after,
            {
                "correlations": [
                    {
                        "module": "cryptography",
                        "completeness": "complete",
                        "truncation": "complete",
                        "anchors": [
                            {
                                "anchor_id": "pytest-tls",
                                "path": "tests/test_tls.py",
                                "line": 1,
                                "metadata": {
                                    "producer": "pytest",
                                    "message": "TLS setup failed after environment change",
                                },
                            }
                        ],
                    }
                ]
            },
        )

    assert delta["nodes_changed"] == ["crypto-registry"]
    assert delta["causation"] == "not-inferred"
    assert correlated["dependency_links"][0]["distribution_nodes"] == [
        "crypto-registry"
    ]
    assert correlated["causation"] == "not-inferred"
    assert "recommendation" not in correlated


@pytest.mark.parametrize("count", [1, 10, 100, 256])
def test_dependency_correlation_bounded_anchor_scale(
    tmp_path: Path, count: int
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n")
    snapshot = _snapshot()
    snapshot["module_ownership"] = [
        {
            "module": "cryptography",
            "owners": ["crypto-registry"],
            "completeness": "complete",
        }
    ]
    anchors = [
        {"anchor_id": f"a-{index}", "path": "owner.py", "line": 1}
        for index in range(count)
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(snapshot)
        packet = codemap.dependency_evidence_correlation(
            observation,
            {
                "correlations": [
                    {
                        "module": "cryptography",
                        "completeness": "complete",
                        "truncation": "complete",
                        "anchors": anchors,
                    }
                ]
            },
        )

    assert len(packet["correlation"]["bundles"][0]["anchors"]) == count


def test_dependency_correlation_incomplete_external_failure_cannot_prove_absence(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observation = codemap.dependency_resolution_evidence(_snapshot())
        packet = codemap.dependency_evidence_correlation(
            observation,
            {
                "correlations": [
                    {
                        "module": "cryptography",
                        "completeness": "incomplete",
                        "truncation": "truncated",
                        "anchors": [{"anchor_id": "one", "path": "owner.py"}],
                    }
                ]
            },
        )

    assert packet["correlation"]["completeness"]["state"] == "incomplete"
    assert (
        packet["correlation"]["completeness"]["negative_evidence"] == "not-admissible"
    )


def _snapshot_v2() -> dict[str, object]:
    return {
        "schema": "hashmarks.dependency-resolution.v2",
        "producer": {"kind": "neutral-resolver", "schema_version": "1"},
        "scope": {"environment": "test"},
        "contexts": ["compile", "runtime"],
        "roots": [
            {"node_id": "app@1", "context": "compile"},
            {"node_id": "app@1", "context": "runtime"},
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
            {"component_id": "inventory-only", "name": "inventory-only", "ecosystem": "test"},
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
                "owners": ["library@1"],
                "completeness": "complete",
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


def test_v2_repository_binding_tracks_current_codemap_generation(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.dependency_resolution_evidence(_snapshot_v2())

    binding = packet["repository_binding"]
    assert binding["repository_identity"].startswith("sha256:")
    assert isinstance(binding["codemap_generation"], int)


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
