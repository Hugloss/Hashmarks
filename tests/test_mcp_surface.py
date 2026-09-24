from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from hashmarks import mcp_server, mcp_surface, repository_retry
from hashmarks.file_store import UnstableFileError
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "src" / "feature.py").write_text(
        "def flare041(value: int) -> int:\n    return value + 1\n", encoding="utf-8"
    )
    (repo / "tests" / "test_feature.py").write_text(
        "from src.feature import flare041\n\ndef test_flare041():\n    assert flare041(1) == 2\n",
        encoding="utf-8",
    )
    return repo


def test_mcp_surface_exposes_only_bounded_repository_intelligence(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        context = surface.repository_context()
        assert context["schema"] == "hashmarks.repository-capsule.v1"

        found = surface.find("flare041", limit=5)
        assert found["schema"] == "hashmarks.mcp-find.v1"
        assert any(row["path"] == "src/feature.py" for row in found["results"])

        evidence = surface.task_evidence("change flare041 behavior", token_budget=256)
        assert evidence["schema"] == "hashmarks.task-evidence.v2"
        assert evidence["retrieval"]["ownership_authority"] is False
        assert evidence["ownership"]["authority"] == "repository-ownership-only"
        assert evidence["freshness"]["state"] in {"unknown", "current", "stale"}
        assert "status" not in evidence
        assert "provenance" in evidence
    finally:
        surface.close()


def test_mcp_surface_rejects_unbounded_or_empty_inputs(tmp_path: Path) -> None:
    surface = HashmarksMcpSurface(
        str(_repo(tmp_path)), state_dir=str(tmp_path / "state")
    )
    try:
        with pytest.raises(McpSurfaceError, match="query must not be empty"):
            surface.find(" ")
        with pytest.raises(McpSurfaceError, match="between 1 and 50"):
            surface.find("flare041", limit=51)
        with pytest.raises(McpSurfaceError, match="changed_paths exceeds"):
            surface.change_impact("task", [f"p{i}.py" for i in range(257)])
        huge = {"schema": "hashmarks.task-evidence.v2", "payload": "x" * 300_000}
        with pytest.raises(McpSurfaceError, match="encoded bytes"):
            surface.post_change("task", ["src/feature.py"], huge)
        with pytest.raises((ValueError, McpSurfaceError)):
            surface.change_impact("task", ["../escape.py"])
    finally:
        surface.close()


def test_mcp_surface_correlates_external_evidence_without_interpreting_it(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        packet = surface.correlate_evidence(
            [
                {
                    "bundle_id": "runtime:1",
                    "producer": {"kind": "traceback"},
                    "completeness": "complete",
                    "scope": {"kind": "traceback-request"},
                    "truncation": "complete",
                    "anchors": [
                        {
                            "anchor_id": "frame:0",
                            "path": "/app/src/feature.py",
                            "line": 2,
                            "symbol": "flare041",
                            "metadata": {"commit": "opaque-runtime-value"},
                        }
                    ],
                }
            ],
            path_mappings=[{"external_prefix": "/app", "repository_prefix": ""}],
            include_relationships=False,
        )
        anchor = packet["bundles"][0]["anchors"][0]
        assert packet["schema"] == "hashmarks.evidence-correlation.v1"
        assert packet["causation"] == "not-inferred"
        assert packet["interpretation_authority"] == "consumer-owned"
        assert anchor["resolution"]["repository_path"] == "src/feature.py"
        assert anchor["source_equivalence"]["state"] == "unknown"

        with pytest.raises(McpSurfaceError, match="bundles must be a list"):
            surface.correlate_evidence({})  # type: ignore[arg-type]
        with pytest.raises(McpSurfaceError, match="relationship_limit_per_path"):
            surface.correlate_evidence([], relationship_limit_per_path=1001)
    finally:
        surface.close()


def test_mcp_correlation_accepts_core_legal_request_above_old_transport_cap(
    tmp_path: Path,
) -> None:
    surface = HashmarksMcpSurface(
        str(tmp_path),
        state_dir=str(tmp_path / "state"),
    )
    module = "m" * 1000
    symbol = "s" * 1000
    anchors = [
        {
            "anchor_id": (f"a{index:03d}-" + "x" * 490)[:500],
            "module": module,
            "symbol": symbol,
        }
        for index in range(256)
    ]
    bundles = [
        {
            "bundle_id": "large-legal-input",
            "producer": {"kind": "dogfood"},
            "completeness": "unknown",
            "anchors": anchors,
        }
    ]
    try:
        packet = surface.correlate_evidence(
            bundles,
            include_relationships=False,
        )
    finally:
        surface.close()

    assert packet["schema"] == "hashmarks.evidence-correlation.v1"
    assert packet["bounds"]["request_max_bytes"] == 1_048_576
    assert all(
        anchor["resolution"]["state"] == "unresolved"
        for anchor in packet["bundles"][0]["anchors"]
    )


def test_mcp_correlation_round_trips_max_repeated_anchor_set(
    tmp_path: Path,
) -> None:
    (tmp_path / "worker.py").write_text(
        "def process_output_data(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    anchors = [
        {
            "anchor_id": f"frame:{index}",
            "path": "worker.py",
            "line": 2,
            "symbol": "process_output_data",
        }
        for index in range(256)
    ]
    bundles = [
        {
            "bundle_id": "traceback-sample",
            "producer": {"kind": "traceback"},
            "completeness": "complete",
            "scope": {"kind": "traceback-sample"},
            "truncation": "complete",
            "anchors": anchors,
        }
    ]
    surface = HashmarksMcpSurface(
        str(tmp_path),
        state_dir=str(tmp_path / "state"),
    )
    try:
        before = surface.correlate_evidence(bundles)
        after = surface.correlate_evidence(
            bundles,
            previous_correlation=before,
        )
    finally:
        surface.close()

    assert len(before["repository_evidence"]["bindings"]) == 1
    assert (
        after["delta_from_previous"]["schema"]
        == "hashmarks.evidence-correlation-delta.v1"
    )


def test_mcp_find_truncated_only_when_an_extra_hit_exists(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "src" / "feature_two.py").write_text(
        "def flare041_second(value: int) -> int:\n    return value + 2\n",
        encoding="utf-8",
    )
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        one = surface.find("flare041", limit=1)
        assert len(one["results"]) == 1
        assert one["truncated"] is True

        exact = surface.find("feature_two.py", limit=10)
        assert exact["truncated"] is False
    finally:
        surface.close()


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError(
            "CodeMap generation is incomplete (BUILDING); run sync() before querying"
        ),
        RuntimeError("CodeMap generation changed before nested decision session"),
        RuntimeError("CodeMap generation changed during decision session"),
        UnstableFileError("file changed while hashing: src/feature.py"),
    ],
)
def test_mcp_transient_repository_races_are_retried_from_scratch(
    monkeypatch: pytest.MonkeyPatch, exc: BaseException
) -> None:
    calls = 0
    monkeypatch.setattr(repository_retry.time, "sleep", lambda _delay: None)

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise exc
        return "fresh"

    assert repository_retry.retry_transient_repository_race(operation) == "fresh"
    assert calls == 3


def test_mcp_retry_does_not_hide_unrelated_runtime_failures() -> None:
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("real implementation failure")

    with pytest.raises(RuntimeError, match="real implementation failure"):
        repository_retry.retry_transient_repository_race(operation)
    assert calls == 1


def test_mcp_retry_remains_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    monkeypatch.setattr(repository_retry.time, "sleep", lambda _delay: None)

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("CodeMap generation changed during decision session")

    with pytest.raises(RuntimeError, match="generation changed"):
        repository_retry.retry_transient_repository_race(operation)
    assert calls == len(repository_retry._TRANSIENT_RETRY_DELAYS)


def test_mcp_surface_read_centralizes_gate_and_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    surface = HashmarksMcpSurface(
        str(_repo(tmp_path)), state_dir=str(tmp_path / "state")
    )
    calls: list[object] = []

    def fake_retry(operation):
        calls.append(operation)
        return "fresh"

    monkeypatch.setattr(mcp_surface, "retry_transient_repository_race", fake_retry)
    try:
        assert surface._read(lambda: "fresh") == "fresh"
        assert len(calls) == 1
    finally:
        surface.close()


def test_mcp_server_boundary_translates_only_surface_errors() -> None:
    class FakeToolError(Exception):
        pass

    def invalid() -> None:
        raise McpSurfaceError("invalid query")

    def broken() -> None:
        raise RuntimeError("implementation bug")

    with pytest.raises(FakeToolError, match="invalid query"):
        mcp_server._call_surface(FakeToolError, invalid)
    with pytest.raises(RuntimeError, match="implementation bug"):
        mcp_server._call_surface(FakeToolError, broken)


def test_mcp_server_registers_exact_small_read_only_tool_catalog(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registered: list[dict[str, object]] = []

    class FakeToolAnnotations:
        def __init__(self, **kwargs):
            self.values = kwargs

    class FakeMCPServer:
        def __init__(self, name: str):
            self.name = name

        def tool(self, **metadata):
            def decorate(fn):
                registered.append({"fn": fn, **metadata})
                return fn

            return decorate

        def run(self, *, transport: str = "stdio") -> None:
            assert transport == "stdio"

    class FakeToolError(Exception):
        pass

    mcp_module = types.ModuleType("mcp")
    server_module = types.ModuleType("mcp.server")
    mcpserver_module = types.ModuleType("mcp.server.mcpserver")
    exceptions_module = types.ModuleType("mcp.server.mcpserver.exceptions")
    types_module = types.ModuleType("mcp.types")
    server_module.MCPServer = FakeMCPServer
    exceptions_module.ToolError = FakeToolError
    types_module.ToolAnnotations = FakeToolAnnotations
    monkeypatch.setitem(sys.modules, "mcp", mcp_module)
    monkeypatch.setitem(sys.modules, "mcp.server", server_module)
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", mcpserver_module)
    monkeypatch.setitem(
        sys.modules, "mcp.server.mcpserver.exceptions", exceptions_module
    )
    monkeypatch.setitem(sys.modules, "mcp.types", types_module)

    from hashmarks.mcp_server import build_server

    server = build_server(_repo(tmp_path), state_dir=tmp_path / "state")
    try:
        names = [str(row["name"]) for row in registered]
        assert names == [
            "repository_context",
            "find",
            "task_evidence",
            "change_impact",
            "correlate_evidence",
            "dependency_codemap",
            "post_change",
        ]
        for row in registered:
            annotations = row["annotations"]
            assert annotations.values == {
                "read_only_hint": True,
                "destructive_hint": False,
                "idempotent_hint": True,
                "open_world_hint": False,
            }
            assert len(str(row["description"])) < 220

        find_tool = next(row["fn"] for row in registered if row["name"] == "find")
        with pytest.raises(FakeToolError, match="query must not be empty"):
            find_tool(" ", limit=5)
        with pytest.raises(McpSurfaceError, match="query must not be empty"):
            server._hashmarks_surface.find(" ", limit=5)
    finally:
        server._hashmarks_surface.close()


def test_mcp_server_construction_does_not_scan_or_build_repository(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "large-repo"
    repo.mkdir()
    for index in range(500):
        path = repo / f"src/p{index:04d}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"def f{index}():\n    return {index}\n", encoding="utf-8")

    registered: list[str] = []

    class FakeToolAnnotations:
        def __init__(self, **kwargs):
            self.values = kwargs

    class FakeMCPServer:
        def __init__(self, name: str):
            self.name = name

        def tool(self, **metadata):
            def decorate(fn):
                registered.append(str(metadata["name"]))
                return fn

            return decorate

    class FakeToolError(Exception):
        pass

    mcp_module = types.ModuleType("mcp")
    server_module = types.ModuleType("mcp.server")
    mcpserver_module = types.ModuleType("mcp.server.mcpserver")
    exceptions_module = types.ModuleType("mcp.server.mcpserver.exceptions")
    types_module = types.ModuleType("mcp.types")
    server_module.MCPServer = FakeMCPServer
    exceptions_module.ToolError = FakeToolError
    types_module.ToolAnnotations = FakeToolAnnotations
    monkeypatch.setitem(sys.modules, "mcp", mcp_module)
    monkeypatch.setitem(sys.modules, "mcp.server", server_module)
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", mcpserver_module)
    monkeypatch.setitem(
        sys.modules, "mcp.server.mcpserver.exceptions", exceptions_module
    )
    monkeypatch.setitem(sys.modules, "mcp.types", types_module)

    from hashmarks.mcp_server import build_server

    state = tmp_path / "state"
    server = build_server(repo, state_dir=state)
    try:
        assert registered == [
            "repository_context",
            "find",
            "task_evidence",
            "change_impact",
            "correlate_evidence",
            "dependency_codemap",
            "post_change",
        ]
        # Construction may initialize empty SQLite files, but it must not build a generation.
        status = server._hashmarks_surface._map.status()
        assert status["generation"] == 0
        assert status["build"]["state"] == "NEVER_SYNCED"
        assert status["build"]["complete"] is False
        assert status["files"] == 0
    finally:
        server._hashmarks_surface.close()


def test_mcp_task_evidence_preserves_canonical_authority_proof_identity(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        task = "change flare041 behavior"
        direct = surface._read(
            lambda: surface._map.task_action_map(task, limit=20, per_role=3)
        )
        evidence = surface.task_evidence(task, token_budget=256)
    finally:
        surface.close()

    assert (
        evidence["ownership"]["authority_proof_identity"]
        == (direct["ownership_authority"]["authority_proof_identity"])
    )
    assert evidence["ownership"]["status"] == direct["ownership_authority"]["status"]


def test_mcp_surface_qualifies_and_queries_dependency_codemap(tmp_path: Path) -> None:
    surface = HashmarksMcpSurface(
        str(_repo(tmp_path)), state_dir=str(tmp_path / "state")
    )
    snapshot = {
        "schema": "hashmarks.dependency-resolution.v3",
        "producer": {"kind": "test-resolver", "schema_version": "1"},
        "scope": {"environment": "test"},
        "contexts": ["runtime"],
        "roots": [
            {
                "node_id": "app@1",
                "context": "runtime",
                "evidence_sources": ["tree:runtime"],
            }
        ],
        "evidence_sources": [
            {
                "source_id": "tree:runtime",
                "kind": "test-resolution-source",
                "authorities": ["resolution-graph", "selection"],
                "context": "runtime",
                "completeness": "complete",
                "truncation": "complete",
            }
        ],
        "components": [
            {"component_id": "app", "name": "app", "ecosystem": "test"},
            {"component_id": "lib", "name": "lib", "ecosystem": "test"},
        ],
        "selections": [
            {
                "node_id": "app@1",
                "component_id": "app",
                "version": "1",
                "source": "workspace",
                "contexts": ["runtime"],
                "evidence_sources": ["tree:runtime"],
            },
            {
                "node_id": "lib@1",
                "component_id": "lib",
                "version": "1",
                "source": "registry",
                "contexts": ["runtime"],
                "evidence_sources": ["tree:runtime"],
            },
        ],
        "inventory": [],
        "relationships": [
            {
                "source": "app@1",
                "target": "lib@1",
                "kind": "dependency",
                "context": "runtime",
                "effective_scope": "runtime",
                "evidence_sources": ["tree:runtime"],
            }
        ],
        "coverage": [
            {
                "context": "runtime",
                "kind": "resolution-graph",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["tree:runtime"],
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
    try:
        packet = surface.dependency_codemap(
            snapshot,
            [
                {
                    "operation": "dependencies",
                    "node_id": "app@1",
                    "context": "runtime",
                }
            ],
        )
    finally:
        surface.close()

    assert packet["schema"] == "hashmarks.mcp-dependency-codemap.v1"
    assert packet["observation"]["schema"] == "hashmarks.dependency-resolution.v3"
    assert packet["producer_authority"] == "caller-claimed"
    assert packet["observation"]["producer_authority"] == "caller-claimed"
    assert packet["queries"]["results"][0]["result"][0]["node_id"] == "lib@1"
    assert packet["queries"]["producer_authority"] == "caller-claimed"
    assert packet["queries"]["results"][0]["producer_authority"] == "caller-claimed"
    assert packet["causation"] == "not-inferred"
