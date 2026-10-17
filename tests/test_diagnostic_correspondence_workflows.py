"""Standalone local correspondence, source deltas and existing delivery paths."""

from __future__ import annotations

import asyncio
import json
import tomllib
from copy import deepcopy
from typing import TYPE_CHECKING, Any

import pytest
from contract_assertions import assert_object, assert_records

from benchmarks.diagnostic_correspondence import (
    claim_bundle,
    materialize_fixture,
    run_vectors,
)
from hashmarks import CodeMap
from hashmarks.adapters import uv_lock_dependency_observation
from hashmarks.codemap.repository_delta import RepositoryGenerationBinding
from hashmarks.codemap.repository_intelligence_query import (
    RepositoryIntelligenceQueryOptions,
)
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError
from scripts.repository_evaluation.backend_transport import capture_cli

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[CodeMap]:
    materialize_fixture(tmp_path / "repo")
    with CodeMap(
        tmp_path / "repo",
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        yield codemap


def _diagnostic(source: dict[str, Any], line: int) -> dict[str, Any]:
    return CodeMap.external_diagnostic_observation(
        producer="example-test",
        binding=RepositoryGenerationBinding("repo:local-fixture", source["generation"]),
        environment_identity="fixture-session",
        diagnostics=[
            {
                "tool": "example-test",
                "path": "app/service.py",
                "symbol": "handle_request",
                "line": line,
                "message": "fictional failure",
            }
        ],
        outcome="fail",
        scope_paths=["app/service.py"],
        collection_state="fresh-complete",
        source_revisions={"app/service.py": source["member"]["member_revision"]},
    )


def test_frozen_local_vectors_retain_unknown_and_ambiguous_evidence(
    repository: CodeMap,
) -> None:
    manifest = materialize_fixture(repository.workspace)
    results = run_vectors(repository, manifest)
    assert {row["name"] for row in results} == {
        row["name"] for row in manifest["cases"]
    }
    for row in results:
        assert row["passed"], row


def test_line_move_comparison_has_identical_core_and_mcp_evidence(
    repository: CodeMap,
) -> None:
    before_source: Any = repository.source.observe("app/service.py", lines=[4])
    before = _diagnostic(before_source, 4)
    path = repository.workspace / "app/service.py"
    path.write_bytes(b"\n" + path.read_bytes())
    repository.index.sync()
    after_source: Any = repository.source.observe("app/service.py", lines=[5])
    after = _diagnostic(after_source, 5)
    expected: Any = repository.diagnostic_observation_delta(
        before, after, before_source=before_source, after_source=after_source
    )
    surface = HashmarksMcpSurface(
        str(repository.workspace), state_dir=str(repository.state_dir)
    )
    try:
        actual = surface.evidence_comparison(
            before,
            after,
            result_mode="diagnostics",
            before_source=before_source,
            after_source=after_source,
        )
        assert actual == expected
        with pytest.raises(McpSurfaceError, match="both endpoint"):
            surface.evidence_comparison(
                before, after, result_mode="diagnostics", before_source=before_source
            )
        with pytest.raises(McpSurfaceError, match="diagnostics mode"):
            surface.evidence_comparison(
                before,
                after,
                result_mode="bindings",
                before_source=before_source,
                after_source=after_source,
            )
    finally:
        surface.close()
    proof = expected["diagnostics"]["source_correspondence"]
    assert len(proof["supported"]) == 1
    assert proof["supported"][0]["before_line"] == 4
    assert proof["supported"][0]["after_line"] == 5
    assert proof["diagnostic_identity_authority"] is False
    assert (
        len(expected["diagnostics"]["added"])
        == len(expected["diagnostics"]["removed"])
        == 1
    )


@pytest.mark.parametrize("change", ["rename", "delete", "replace-symbol"])
def test_old_locations_do_not_become_exact_current_source_after_changes(
    repository: CodeMap, change: str
) -> None:
    before: Any = repository.source.observe("app/service.py", lines=[4])
    path = repository.workspace / "app/service.py"
    if change == "rename":
        path.rename(path.with_name("renamed.py"))
    elif change == "delete":
        path.unlink()
    else:
        path.write_text("def replacement():\n    return 42\n", encoding="utf-8")
    repository.index.sync()
    packet: Any = repository.correlation.observe(
        claim_bundle(
            {
                "anchor_id": "prior",
                "path": "app/service.py",
                "line": 4,
                "member_revision": before["member"]["member_revision"],
            }
        ),
        include_relationships=False,
    )
    anchor = packet["bundles"][0]["anchors"][0]
    assert anchor["source_equivalence"]["state"] != "proven"
    current: Any = repository.source.observe("app/service.py")
    result: Any = repository.diagnostic_source_revision_evidence(
        _diagnostic(before, 4), [current]
    )
    assert result["rows"][0]["state"] in {"unknown", "different"}
    assert not result["matching_count"]


def test_line_endings_and_encoding_remain_exact_member_evidence(
    repository: CodeMap,
) -> None:
    path = repository.workspace / "app/encoded.py"
    before: Any = repository.source.observe("app/encoded.py", lines=[2])
    assert (
        before["member"]["member_revision"] == hash_file(path, domain=FILE_DOMAIN).hash
    )
    assert b"\r\n" in path.read_bytes()
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    repository.index.sync()
    after: Any = repository.source.observe("app/encoded.py", lines=[2])
    assert before["member"]["member_revision"] != after["member"]["member_revision"]
    assert (
        before["line_anchors"][0]["line_sha256"]
        != after["line_anchors"][0]["line_sha256"]
    )


def test_alias_reexport_call_chain_and_verifier_correspondence(
    repository: CodeMap,
) -> None:
    locality: Any = repository.structure.locality("app/service.py::handle_request")
    assert {row["symbol_id"] for row in locality["nodes"]} == {
        "app/service.py::handle_request",
        "app/config.py::load_config",
    }
    assert "tests/test_service.py" in locality["verification_paths"]
    evidence: Any = repository.tasks.evidence(
        "Change app/service.py handle_request and verify its test"
    )
    assert evidence["ownership"]["owner"]["path"] == "app/service.py"
    assert evidence["verification"]["selected"]["path"] == "tests/test_service.py"
    assert locality["claims"]["execution_authority"] is False
    indirect: Any = repository.structure.locality("app/api.py::dispatch")
    assert {row["symbol_id"] for row in indirect["nodes"]} == {
        "app/api.py::dispatch",
        "app/service.py::handle_request",
        "app/config.py::load_config",
    }


def test_observer_visibility_changes_are_not_repository_edits(
    repository: CodeMap,
) -> None:
    source: Any = repository.source.observe("app/service.py")
    before = _diagnostic(source, 4)
    after = deepcopy(before)
    after["diagnostics"] = []
    after["diagnostic_count"] = 0
    after["collection"] = {"state": "unavailable", "authority": "producer-claimed"}
    after["outcome"] = "blocked-permission"
    delta: Any = repository.diagnostic_observation_delta(before, after)
    assert delta["generation"]["before"] == delta["generation"]["after"]
    assert delta["source_revisions"]["changed"] is False
    assert delta["diagnostics"]["qualification"]["qualified_removed_identities"] == []
    assert len(delta["diagnostics"]["removed"]) == 1


def test_local_lock_observations_preserve_versions_and_repository_binding(
    repository: CodeMap,
) -> None:
    lock = repository.workspace / "uv.lock"
    before: Any = repository.dependency_resolution_evidence(
        uv_lock_dependency_observation(
            lock=lock.read_bytes(),
            repository_inputs=[
                {
                    "path": "uv.lock",
                    "member_revision": hash_file(lock, domain=FILE_DOMAIN).hash,
                }
            ],
        )
    )
    lock.write_bytes(
        lock.read_bytes().replace(b"version = '1.0.0'", b"version = '2.0.0'")
    )
    repository.index.sync()
    after: Any = repository.dependency_resolution_evidence(
        uv_lock_dependency_observation(
            lock=lock.read_bytes(),
            repository_inputs=[
                {
                    "path": "uv.lock",
                    "member_revision": hash_file(lock, domain=FILE_DOMAIN).hash,
                }
            ],
        )
    )
    delta: Any = repository.dependency_resolution_delta(before, after)
    assert {
        row["version"]
        for row in before["selections"]
        if row["component_id"] == "local-dep"
    } == {"1.0.0"}
    assert {
        row["version"]
        for row in after["selections"]
        if row["component_id"] == "local-dep"
    } == {"2.0.0"}
    assert all(
        row["source_equivalence"] == "proven" for row in after["repository_inputs"]
    )
    assert delta["causation"] == "not-inferred"
    assert delta["selections_added"] and delta["selections_removed"]
    assert after["module_ownership"] == []


def test_source_packet_revision_and_bounds_converge_through_cli_and_mcp(
    repository: CodeMap,
) -> None:
    core: Any = repository.source.observe(
        "app/service.py", lines=[4], anchor_context_lines=1
    )
    surface = HashmarksMcpSurface(
        str(repository.workspace), state_dir=str(repository.state_dir)
    )
    try:
        mcp: Any = surface.source_observation(
            ["app/service.py"], context_lines={"lines": [4], "radius": 1}
        )
    finally:
        surface.close()
    case = {
        "operation": "source_observation",
        "inputs": {
            "paths": ["app/service.py"],
            "result_mode": "member",
            "context_lines": {"lines": [4], "radius": 1},
        },
    }
    captures = capture_cli(repository.workspace, repository.state_dir, case)
    for capture in captures:
        response = capture["response"]
        packet = response.get("result", response)
        for field in ("member", "limits", "line_anchors", "line_coverage", "authority"):
            assert packet[field] == mcp[field] == core[field]
        if "presentation" in response:
            assert (
                response["presentation"]["source_evidence_identity"]
                == packet["observation_identity"]
            )


def test_replay_rejects_substitution_and_does_not_persist_claims(
    repository: CodeMap,
) -> None:
    bundle = claim_bundle({"anchor_id": "current", "path": "app/service.py"})
    before: Any = repository.correlation.observe(bundle, include_relationships=False)
    assert repository.correlation.observe(bundle, include_relationships=False) == before
    tampered = deepcopy(before)
    tampered["bundles"][0]["anchors"][0]["claims"]["path"] = "app/unrelated.py"
    with pytest.raises(ValueError, match="identity"):
        repository.correlation.observe(
            bundle, previous_correlation=tampered, include_relationships=False
        )
    repository.correlation.observe(
        bundle, previous_correlation=before, include_relationships=False
    )
    assert (
        repository.correlation.observe([], include_relationships=False)["bundles"] == []
    )
    projected = present_repository_evidence(before, format="compact")
    assert projected["source_evidence_identity"] == before["correlation_identity"]


def test_current_claim_cannot_repair_a_stale_index(repository: CodeMap) -> None:
    before: Any = repository.source.observe("app/service.py", lines=[4])
    path = repository.workspace / "app/service.py"
    path.write_bytes(b"\n" + path.read_bytes())
    producer_claim = deepcopy(before)
    producer_claim["member"]["member_revision"] = hash_file(
        path, domain=FILE_DOMAIN
    ).hash
    current = repository.source.observe("app/service.py", lines=[4])
    result: Any = repository.diagnostic_source_revision_evidence(
        _diagnostic(producer_claim, 4), [current]
    )
    assert result["rows"][0]["state"] == "unknown"
    assert result["matching_count"] == 0


def test_declared_and_locked_versions_have_evidence_without_a_winner(
    repository: CodeMap,
) -> None:
    intent = repository.workspace / "pyproject.toml"
    lock = repository.workspace / "uv.lock"
    declared = tomllib.loads(intent.read_text())["project"]["dependencies"][0].split(
        "=="
    )[1]
    lock.write_bytes(
        lock.read_bytes().replace(b"version = '1.0.0'", b"version = '2.0.0'")
    )
    repository.index.sync()
    locked = next(
        row["version"]
        for row in tomllib.loads(lock.read_text())["package"]
        if row["name"] == "local-dep"
    )
    declarations = []
    for name, path, value in (("intent", intent, declared), ("lock", lock, locked)):
        line = next(
            n
            for n, text in enumerate(path.read_text().splitlines(), 1)
            if value in text
        )
        declarations.append(
            {
                "declaration_id": name,
                "value_state": "resolved",
                "value": value,
                "producer": {"kind": "fixture-provider"},
                "evidence": [
                    {
                        "path": path.relative_to(repository.workspace).as_posix(),
                        "start_line": line,
                        "end_line": line,
                    }
                ],
            }
        )
    packet: Any = repository.repository_declarations(
        [
            {
                "group_id": "dependency-version",
                "semantic_namespace": "fixture",
                "concept": {"kind": "package-version", "identity": "local-dep"},
                "scope": {},
                "correspondence": {
                    "state": "declared",
                    "basis": {
                        "provider": "fixture-provider",
                        "rule": "explicit-package-and-version",
                    },
                },
                "declarations": declarations,
                "coverage": {
                    "state": "incomplete",
                    "truncation": "unknown",
                    "expected_declaration_ids": ["intent", "lock", "unobserved"],
                    "scope": {"repository": "fixture"},
                    "provenance": {"provider": "fixture-provider"},
                },
            }
        ]
    )
    assert packet["groups"][0]["comparison"]["state"] == "differing"
    assert packet["groups"][0]["absence"]["state"] == "unknown"
    assert packet["winner"] == "not-selected"
    assert packet["correspondence_authority"] == "provider-claimed"


@pytest.mark.host_mcp_sdk
def test_registered_mcp_tool_transports_paired_source_observations(
    repository: CodeMap,
) -> None:
    pytest.importorskip("mcp", reason="optional official MCP SDK unavailable")
    from hashmarks.mcp_server import build_server

    source: Any = repository.source.observe("app/service.py", lines=[4])
    diagnostic = _diagnostic(source, 4)
    expected = repository.diagnostic_observation_delta(
        diagnostic, diagnostic, before_source=source, after_source=source
    )
    server: Any = build_server(
        workspace=str(repository.workspace), state_dir=str(repository.state_dir)
    )

    async def exercise() -> None:
        tools = await server.list_tools()
        tool = next(row for row in tools if row.name == "evidence_comparison")
        assert {"before_source", "after_source"} <= tool.input_schema[
            "properties"
        ].keys()
        assert tool.annotations.read_only_hint is True
        result = await server.call_tool(
            "evidence_comparison",
            {
                "before": diagnostic,
                "after": diagnostic,
                "result_mode": "diagnostics",
                "before_source": source,
                "after_source": source,
            },
        )
        assert result.is_error is not True
        assert result.structured_content == expected

    try:
        asyncio.run(exercise())
    finally:
        server._hashmarks_surface.close()


def test_changed_test_source_replaces_exact_caller_correspondence(
    repository: CodeMap,
) -> None:
    target = "app/service.py::handle_request"
    before: Any = repository.structure.locality(target)
    assert "tests/test_service.py" in {
        row["path"] for row in before["nodes"][0]["exact_callers"]
    }
    (repository.workspace / "tests/test_service.py").write_text(
        "from app.unrelated import handle_request\n"
        "def test_service():\n    assert handle_request()\n",
        encoding="utf-8",
    )
    (repository.workspace / "tests/test_replacement.py").write_text(
        "from app.service import handle_request\n"
        "def test_replacement():\n    assert handle_request()\n",
        encoding="utf-8",
    )
    repository.index.sync()
    after: Any = repository.structure.locality(target)
    owner = next(row for row in after["nodes"] if row["symbol_id"] == target)
    callers = {row["path"] for row in owner["exact_callers"]}
    assert "tests/test_replacement.py" in callers
    assert "tests/test_service.py" not in callers
    assert "tests/test_replacement.py" in after["verification_paths"]


@pytest.mark.parametrize(
    "operation",
    [
        "task_evidence",
        "structural_locality",
        "dependency_codemap",
        "repository_evidence",
        "correlate_evidence",
    ],
)
def test_existing_delivery_routes_preserve_complete_local_packets(
    repository: CodeMap, operation: str
) -> None:
    task = "Change app/service.py handle_request and verify its test"
    lock = repository.workspace / "uv.lock"
    snapshot = uv_lock_dependency_observation(
        lock=lock.read_bytes(),
        repository_inputs=[
            {
                "path": "uv.lock",
                "member_revision": hash_file(lock, domain=FILE_DOMAIN).hash,
            }
        ],
    )
    bindings = [
        {
            "binding_id": "opaque-consumer",
            "evidence": [{"path": "app/service.py", "start_line": 3, "end_line": 4}],
        }
    ]
    inputs: dict[str, Any] = {
        "task_evidence": {"task": task},
        "structural_locality": {"target": "app/service.py::handle_request"},
        "dependency_codemap": {"snapshot": snapshot},
        "repository_evidence": {"request": {"bindings": bindings}},
        "correlate_evidence": {
            "bundles": claim_bundle({"anchor_id": "same", "path": "app/service.py"})
        },
    }[operation]
    if operation == "repository_evidence":
        expected = repository.bindings.observe(bindings)
    else:
        expected = getattr(repository, operation)(**inputs)
    surface = HashmarksMcpSurface(
        str(repository.workspace), state_dir=str(repository.state_dir)
    )
    try:
        assert getattr(surface, operation)(**inputs) == expected
    finally:
        surface.close()
    if operation in {"repository_evidence", "correlate_evidence"}:
        return  # These operations have no dedicated CLI command.
    captures = capture_cli(
        repository.workspace,
        repository.state_dir,
        {"operation": operation, "inputs": inputs},
    )
    for capture in captures:
        response = capture["response"]
        packet = response["result"] if "presentation" in response else response
        assert packet == expected


def test_query_delivery_uses_matching_presentation_and_exact_core_identity(
    repository: CodeMap,
) -> None:
    task = "Change app/service.py handle_request and verify its test"
    paths = ["app/service.py"]
    captures = capture_cli(
        repository.workspace,
        repository.state_dir,
        {
            "operation": "repository_intelligence_query",
            "inputs": {
                "surface_name": "freshness",
                "task": task,
                "changed_paths": paths,
            },
        },
    )
    surface = HashmarksMcpSurface(
        str(repository.workspace), state_dir=str(repository.state_dir)
    )
    try:
        for capture in captures:
            presentation = capture["format"]
            expected = repository.repository_intelligence_query(
                "freshness",
                task,
                paths,
                options=RepositoryIntelligenceQueryOptions(presentation=presentation),
            )
            assert capture["response"] == expected
            assert (
                surface.repository_intelligence_query(
                    "freshness", task, paths, presentation=presentation
                )
                == expected
            )
    finally:
        surface.close()
