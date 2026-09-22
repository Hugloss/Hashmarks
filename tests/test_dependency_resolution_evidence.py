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
