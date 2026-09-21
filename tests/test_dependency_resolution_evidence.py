from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.codemap.engine import CodeMap


def _snapshot(*, scope: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "schema": "hashmarks.dependency-resolution.v1",
        "producer": {"kind": "uv-workspace-metadata", "schema_version": "preview-1"},
        "scope": scope or {"python": "3.14", "platform": "linux", "groups": ["default"]},
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


def test_resolution_delta_reports_node_change_without_recommendation(tmp_path: Path) -> None:
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
        {"source": "crypto-registry", "target": "root", "kind": "dependency", "marker": ""}
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
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n")
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
