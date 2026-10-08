from __future__ import annotations

import inspect
import json
import sys
import types
from pathlib import Path

import pytest

from hashmarks import mcp_server, mcp_surface, repository_retry
from hashmarks.codemap import CodeMap
from hashmarks.codemap.change_impact import (
    CHANGE_IMPACT_DEFAULT_REQUEST,
    ChangeImpactOptions,
)
from hashmarks.codemap.evidence_packet import TASK_EVIDENCE_DEFAULT_OPTIONS
from hashmarks.file_store import UnstableFileError
from hashmarks.mcp_contract import tool_contract
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
        assert found["schema"] == "hashmarks.find.v2"
        assert any(row["path"] == "src/feature.py" for row in found["results"])

        evidence = surface.task_evidence("change flare041 behavior", token_budget=256)
        assert evidence["schema"] == "hashmarks.task-evidence.v5"
        assert evidence["retrieval"]["ownership_authority"] is False
        assert evidence["ownership"]["authority"] == "repository-ownership-only"
        assert evidence["freshness"]["state"] in {"unknown", "current", "stale"}
        assert "status" not in evidence
        assert "provenance" in evidence
    finally:
        surface.close()


def test_mcp_change_impact_consumes_canonical_semantic_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = CHANGE_IMPACT_DEFAULT_REQUEST
    captured: dict[str, object] = {}
    surface = HashmarksMcpSurface(str(tmp_path), state_dir=str(tmp_path / "state"))

    def project(
        task: str,
        changed_paths: list[str],
        *,
        limit: int,
        per_role: int,
        options: ChangeImpactOptions,
    ) -> dict[str, object]:
        captured.update(
            task=task,
            changed_paths=changed_paths,
            limit=limit,
            per_role=per_role,
            options=options,
        )
        return {"schema": "hashmarks.task-change-impact.v1"}

    monkeypatch.setattr(surface._map, "task_change_impact", project)
    try:
        surface.change_impact("inspect widget", ["src/widget.py"])
    finally:
        surface.close()

    assert captured["limit"] == defaults.limit
    assert captured["per_role"] == defaults.per_role
    options = captured["options"]
    assert isinstance(options, ChangeImpactOptions)
    assert options.impact_limit_per_surface == defaults.options.impact_limit_per_surface
    assert options.max_depth == defaults.options.max_depth
    assert options.project_impact_limit == defaults.options.project_impact_limit
    assert options.project_impact_encoding == "compact"


def test_mcp_surface_rejects_unbounded_or_empty_inputs(tmp_path: Path) -> None:
    surface = HashmarksMcpSurface(
        str(_repo(tmp_path)), state_dir=str(tmp_path / "state")
    )
    try:
        with pytest.raises(McpSurfaceError, match="query must not be empty") as invalid:
            surface.find(" ")
        assert invalid.value.reason == "invalid-request"
        assert invalid.value.as_dict() == {
            "schema": "hashmarks.mcp-error.v1",
            "reason": "invalid-request",
            "message": "query must not be empty",
            "recovery_authority": "consumer-owned",
        }
        with pytest.raises(McpSurfaceError, match="between 1 and 50"):
            surface.find("flare041", limit=51)
        with pytest.raises(McpSurfaceError, match="changed_paths exceeds"):
            surface.change_impact("task", [f"p{i}.py" for i in range(257)])
        huge = {"schema": "hashmarks.task-evidence.v5", "payload": "x" * 300_000}
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
        assert packet["schema"] == "hashmarks.evidence-correlation.v2"
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

    assert packet["schema"] == "hashmarks.evidence-correlation.v2"
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
        == "hashmarks.evidence-correlation-delta.v2"
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
        assert "find-result-limit" in one["omissions"]
        assert one["uniqueness_evidence"] == "not-admissible"

        exact = surface.find("feature_two.py", limit=10)
        assert exact["truncated"] is False
        assert exact["query_intent"] == "path"
        assert exact["observed_exact_match_count"] == 1
    finally:
        surface.close()


def test_mcp_find_qualifies_absence_and_uniqueness_against_freshness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        surface.repository_context()

        def current_generation() -> tuple[int, int, bool]:
            generation = surface._map.store.generation()
            return generation, generation, False

        monkeypatch.setattr(surface._map, "_generation_status", current_generation)

        missing = surface.find("definitely_missing_symbol", limit=10)
        assert missing["query_intent"] == "identifier"
        assert missing["observed_exact_match_count"] == 0
        assert missing["freshness"] == "current"
        assert missing["completeness"] == "complete"
        assert missing["negative_evidence"] == "admissible-within-declared-scope"
        assert missing["admissibility_reasons"] == []

        unique_path = surface.find("src/feature.py", limit=10)
        assert unique_path["query_intent"] == "path"
        assert unique_path["observed_exact_match_count"] == 1
        assert unique_path["uniqueness_evidence"] == "admissible-within-declared-scope"

        conceptual = surface.find("where is definitely_missing behavior", limit=10)
        assert conceptual["negative_evidence"] == "not-admissible"
        assert "query-intent-not-exact" in conceptual["admissibility_reasons"]
    finally:
        surface.close()


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError(
            "CodeMap generation is incomplete (BUILDING); run sync() before querying"
        ),
        RuntimeError(
            "CodeMap generation changed before expected decision session (30 -> 31)"
        ),
        RuntimeError("CodeMap generation changed before nested decision session"),
        RuntimeError(
            "CodeMap generation changed before expected decision session (30 -> 31)"
        ),
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


def test_mcp_retry_propagates_unrelated_failure_after_transient_race() -> None:
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("CodeMap generation changed during decision session")
        raise RuntimeError(
            "unrelated failure: CodeMap generation changed during decision session"
        )

    with pytest.raises(RuntimeError, match="^unrelated failure:"):
        repository_retry.retry_transient_repository_race(operation)
    assert calls == 2


def test_mcp_retry_absorbs_release_scale_transient_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = 0.0

    def monotonic() -> float:
        return clock

    def sleep(delay: float) -> None:
        nonlocal clock
        clock += delay

    monkeypatch.setattr(repository_retry.time, "monotonic", monotonic)
    monkeypatch.setattr(repository_retry.time, "sleep", sleep)

    def operation() -> str:
        if clock < 1.0:
            raise RuntimeError(
                "CodeMap generation is incomplete (BUILDING); run sync() before querying"
            )
        return "fresh"

    assert repository_retry.retry_transient_repository_race(operation) == "fresh"
    assert 1.0 <= clock < repository_retry._TRANSIENT_RETRY_BUDGET_SECONDS


def test_mcp_surface_recovers_from_prolonged_building_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    surface = HashmarksMcpSurface(
        str(_repo(tmp_path)), state_dir=str(tmp_path / "state")
    )
    assert surface.find("flare041")["results"]
    clock = 0.0
    delays: list[float] = []

    def sleep(delay: float) -> None:
        nonlocal clock
        delays.append(delay)
        clock += delay
        if clock >= 1.1:
            surface._map.store.set_meta("sync.build_state", "COMPLETE")

    monkeypatch.setattr(repository_retry.time, "monotonic", lambda: clock)
    monkeypatch.setattr(repository_retry.time, "sleep", sleep)
    try:
        surface._map.store.set_meta("sync.build_state", "BUILDING")
        result = surface.find("flare041")
        assert result["results"]
        assert "BUILDING" not in json.dumps(result)
        assert 1.1 <= clock < repository_retry._TRANSIENT_RETRY_BUDGET_SECONDS
        assert delays and max(delays) <= 0.25
    finally:
        surface._map.store.set_meta("sync.build_state", "COMPLETE")
        surface.close()


def test_mcp_retry_remains_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    clock = 0.0

    def monotonic() -> float:
        return clock

    def sleep(delay: float) -> None:
        nonlocal clock
        clock += delay

    monkeypatch.setattr(repository_retry.time, "monotonic", monotonic)
    monkeypatch.setattr(repository_retry.time, "sleep", sleep)

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("CodeMap generation changed during decision session")

    with pytest.raises(RuntimeError, match="generation changed"):
        repository_retry.retry_transient_repository_race(operation)
    assert clock == pytest.approx(repository_retry._TRANSIENT_RETRY_BUDGET_SECONDS)
    assert calls > 3


def test_mcp_surface_classifies_exhausted_transient_race(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    surface = HashmarksMcpSurface(
        str(_repo(tmp_path)), state_dir=str(tmp_path / "state")
    )

    def exhausted(_operation):
        raise RuntimeError("CodeMap generation changed during decision session")

    monkeypatch.setattr(mcp_surface, "retry_transient_repository_race", exhausted)
    try:
        with pytest.raises(McpSurfaceError) as failure:
            surface._read(lambda: "never")
    finally:
        surface.close()

    assert failure.value.reason == "transient-race-exhausted"
    assert "bounded MCP read window" in str(failure.value)


def test_mcp_surface_classifies_foreign_previous_correlation(
    tmp_path: Path,
) -> None:
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    repo_a.mkdir()
    repo_b.mkdir()
    (repo_a / "owner.py").write_text("def owner():\n    return 1\n", encoding="utf-8")
    (repo_b / "owner.py").write_text("def owner():\n    return 2\n", encoding="utf-8")
    bundle = [
        {
            "bundle_id": "runtime:1",
            "producer": {"kind": "traceback"},
            "completeness": "complete",
            "scope": {"kind": "traceback-request"},
            "truncation": "complete",
            "anchors": [{"anchor_id": "frame", "path": "owner.py"}],
        }
    ]
    first = HashmarksMcpSurface(str(repo_a), state_dir=str(tmp_path / "state-a"))
    second = HashmarksMcpSurface(str(repo_b), state_dir=str(tmp_path / "state-b"))
    try:
        previous = first.correlate_evidence(bundle, include_relationships=False)
        with pytest.raises(McpSurfaceError, match="repository-mismatch") as failure:
            second.correlate_evidence(
                bundle,
                previous_correlation=previous,
                include_relationships=False,
            )
    finally:
        first.close()
        second.close()

    assert failure.value.reason == "stale-or-foreign-evidence"


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

    with pytest.raises(FakeToolError, match="invalid query") as translated:
        mcp_server._call_surface(tool_contract("find"), FakeToolError, invalid)
    assert json.loads(str(translated.value)) == {
        "schema": "hashmarks.mcp-error.v1",
        "reason": "invalid-request",
        "message": "invalid query",
        "recovery_authority": "consumer-owned",
    }
    with pytest.raises(RuntimeError, match="implementation bug"):
        mcp_server._call_surface(tool_contract("find"), FakeToolError, broken)

    with pytest.raises(RuntimeError, match="response schema drift"):
        mcp_server._call_surface(
            tool_contract("find"),
            FakeToolError,
            lambda: {"schema": "hashmarks.repository-capsule.v1"},
        )


def _assert_registered_task_evidence_defaults(
    registered: list[dict[str, object]],
) -> None:
    task_evidence_tool = next(
        row["fn"] for row in registered if row["name"] == "task_evidence"
    )
    parameters = inspect.signature(task_evidence_tool).parameters
    defaults = TASK_EVIDENCE_DEFAULT_OPTIONS
    assert parameters["limit"].default == defaults.limit
    assert parameters["per_role"].default == defaults.per_role
    assert parameters["token_budget"].default == defaults.token_budget


def _assert_registered_change_impact_defaults(
    registered: list[dict[str, object]],
) -> None:
    defaults = CHANGE_IMPACT_DEFAULT_REQUEST
    surface_parameters = inspect.signature(HashmarksMcpSurface.change_impact).parameters
    assert surface_parameters["max_depth"].default == defaults.options.max_depth

    change_impact_tool = next(
        row["fn"] for row in registered if row["name"] == "change_impact"
    )
    parameters = inspect.signature(change_impact_tool).parameters
    assert parameters["max_depth"].default == defaults.options.max_depth


def _assert_registered_public_defaults(
    registered: list[dict[str, object]],
) -> None:
    _assert_registered_task_evidence_defaults(registered)
    _assert_registered_change_impact_defaults(registered)


def test_mcp_server_registers_exact_small_read_only_tool_catalog(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registered: list[dict[str, object]] = []

    class FakeToolAnnotations:
        def __init__(self, **kwargs):
            self.values = kwargs

    class FakeMCPServer:
        def __init__(self, name: str, **kwargs):
            self.name = name
            self.description = kwargs.get("description")
            self.instructions = kwargs.get("instructions")

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
        assert (
            server.description
            == (
                "Semantic read-only repository intelligence for behavior localization, "
                "ownership, impact, freshness, and verification evidence"
            )
            and server.instructions == mcp_server._SERVER_INSTRUCTIONS
            and "call task_evidence before exploratory" in server.instructions
            and "repeated native search/read calls" in server.instructions
            and "unique known path" in server.instructions
        )
        assert names == [
            "repository_context",
            "find",
            "task_evidence",
            "change_impact",
            "correlate_evidence",
            "dependency_codemap",
            "repository_declarations",
            "post_change",
            "repository_intelligence_query",
            "source_observation",
            "repository_evidence",
            "repository_findings",
            "structural_locality",
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

        _assert_registered_public_defaults(registered)

        with pytest.raises(FakeToolError, match="query must not be empty"):
            next(row["fn"] for row in registered if row["name"] == "find")(" ", limit=5)
        with pytest.raises(McpSurfaceError, match="query must not be empty"):
            server._hashmarks_surface.find(" ", limit=5)

        dependency_tool = next(
            row["fn"] for row in registered if row["name"] == "dependency_codemap"
        )
        declaration_tool = next(
            row["fn"] for row in registered if row["name"] == "repository_declarations"
        )
        with pytest.raises(FakeToolError, match="result_mode must be one of"):
            dependency_tool({}, result_mode="history")
        with pytest.raises(FakeToolError, match="result_mode must be one of"):
            declaration_tool([], result_mode="compare")

    finally:
        server._hashmarks_surface.close()


def test_mcp_server_rejects_mode_specific_response_schema_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registered: list[dict[str, object]] = []

    class FakeToolAnnotations:
        def __init__(self, **kwargs):
            self.values = kwargs

    class FakeMCPServer:
        def __init__(self, _name: str, **_kwargs):
            pass

        def tool(self, **metadata):
            def decorate(fn):
                registered.append({"fn": fn, **metadata})
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

    server = mcp_server.build_server(_repo(tmp_path), state_dir=tmp_path / "state")
    try:
        server._hashmarks_surface.dependency_codemap = lambda *_args, **_kwargs: {
            "schema": "hashmarks.dependency-resolution-explain.v1"
        }
        tool = next(
            row["fn"] for row in registered if row["name"] == "dependency_codemap"
        )
        with pytest.raises(RuntimeError, match="response schema drift"):
            tool({}, result_mode="compare")
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
        def __init__(self, name: str, **kwargs):
            self.name = name
            self.description = kwargs.get("description")
            self.instructions = kwargs.get("instructions")

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
            "repository_declarations",
            "post_change",
            "repository_intelligence_query",
            "source_observation",
            "repository_evidence",
            "repository_findings",
            "structural_locality",
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
        "producer": {
            "kind": "test-resolver",
            "schema_version": "1",
            "adapter_semantics": "test.dependency-adapter.v1",
        },
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
        invalid_snapshot = {
            **snapshot,
            "relationships": [
                {**snapshot["relationships"][0], "kind": "conflicts-with"}
            ],
        }
        with pytest.raises(
            McpSurfaceError, match="unsupported dependency relationship kind"
        ) as unsupported:
            surface.dependency_codemap(invalid_snapshot)
        assert unsupported.value.reason == "unsupported-semantic"
        with pytest.raises(
            McpSurfaceError, match="max_depth must be a positive integer"
        ):
            surface.dependency_codemap(
                snapshot,
                [
                    {
                        "operation": "dependencies",
                        "node_id": "app@1",
                        "context": "runtime",
                        "max_depth": "1",
                    }
                ],
            )
    finally:
        surface.close()

    assert packet["schema"] == "hashmarks.dependency-codemap.v1"
    assert packet["observation"]["schema"] == "hashmarks.dependency-resolution.v3"
    assert packet["producer_authority"] == "caller-claimed"
    assert packet["observation"]["producer_authority"] == "caller-claimed"
    assert packet["queries"]["results"][0]["result"][0]["node_id"] == "lib@1"
    assert packet["queries"]["producer_authority"] == "caller-claimed"
    assert packet["queries"]["results"][0]["producer_authority"] == "caller-claimed"
    assert packet["causation"] == "not-inferred"


def test_mcp_dependency_codemap_explain_and_compare_reuse_core_authority(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    snapshot = {
        "schema": "hashmarks.dependency-resolution.v3",
        "producer": {
            "kind": "test-resolver",
            "schema_version": "1",
            "adapter_semantics": "test.dependency-adapter.v1",
        },
        "scope": {"environment": "test"},
        "contexts": ["runtime"],
        "roots": [],
        "evidence_sources": [
            {
                "source_id": "tree:runtime",
                "kind": "test-resolution-source",
                "authorities": ["resolution-graph", "selection"],
                "context": "runtime",
                "completeness": "complete",
                "truncation": "complete",
                "producer_digest": "sha256:" + "a" * 64,
            }
        ],
        "components": [{"component_id": "lib", "name": "lib", "ecosystem": "test"}],
        "selections": [
            {
                "node_id": "lib@1",
                "component_id": "lib",
                "version": "1",
                "source": "registry",
                "contexts": ["runtime"],
                "evidence_sources": ["tree:runtime"],
            }
        ],
        "inventory": [],
        "relationships": [],
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
    changed = json.loads(json.dumps(snapshot))
    changed["selections"][0]["node_id"] = "lib@2"
    changed["selections"][0]["version"] = "2"

    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        observed = surface.dependency_codemap(snapshot)
        explained = surface.dependency_codemap(snapshot, result_mode="explain")
        compared = surface.dependency_codemap(
            changed,
            previous_observation=observed["observation"],
            result_mode="compare",
        )

        with pytest.raises(
            McpSurfaceError,
            match="queries require result_mode=observation",
        ):
            surface.dependency_codemap(
                snapshot,
                [{"operation": "components"}],
                result_mode="explain",
            )
        with pytest.raises(
            McpSurfaceError,
            match="previous_observation is required",
        ):
            surface.dependency_codemap(snapshot, result_mode="compare")
        with pytest.raises(
            McpSurfaceError,
            match="previous_observation is only valid",
        ):
            surface.dependency_codemap(
                snapshot,
                previous_observation=observed["observation"],
            )
        with pytest.raises(McpSurfaceError, match="result_mode must be one of"):
            surface.dependency_codemap(snapshot, result_mode="history")
    finally:
        surface.close()

    assert observed["schema"] == "hashmarks.dependency-codemap.v1"
    assert explained["schema"] == "hashmarks.dependency-resolution-explain.v1"
    assert (
        explained["semantic_result"]["observation_identity"]
        == observed["observation"]["observation_identity"]
    )
    assert compared["schema"] == "hashmarks.dependency-resolution-delta.v3"
    assert compared["comparability"] == "comparable"
    assert compared["change_axes"]["semantic_definition"] == "unchanged"
    assert compared["change_axes"]["semantic_resolution"] == "changed"
    transition = compared["component_selection_transitions"]
    assert len(transition) == 1
    assert transition[0]["component_id"] == "lib"
    assert [row["version"] for row in transition[0]["removed"]] == ["1"]
    assert [row["version"] for row in transition[0]["added"]] == ["2"]
    assert transition[0]["changed"] == []


def test_mcp_surface_projects_repository_declarations_without_choosing_winner(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "runtime-a.yaml").write_text("runtime: 3.12\n", encoding="utf-8")
    (repo / "runtime-b.yaml").write_text("runtime: 3.13\n", encoding="utf-8")
    groups = [
        {
            "group_id": "python-runtime",
            "semantic_namespace": "mcp-fixture",
            "concept": {"kind": "runtime", "identity": "python"},
            "scope": {"environment": "application"},
            "correspondence": {
                "state": "declared",
                "basis": {"provider": "fixture"},
            },
            "declarations": [
                {
                    "declaration_id": "a",
                    "semantic_role": {"kind": "project-intent"},
                    "value_state": "resolved",
                    "value": "3.12",
                    "producer": {"kind": "fixture-yaml"},
                    "evidence": [
                        {
                            "path": "runtime-a.yaml",
                            "start_line": 1,
                            "end_line": 1,
                        }
                    ],
                },
                {
                    "declaration_id": "b",
                    "semantic_role": {"kind": "container-runtime"},
                    "value_state": "resolved",
                    "value": "3.13",
                    "producer": {"kind": "fixture-yaml"},
                    "evidence": [
                        {
                            "path": "runtime-b.yaml",
                            "start_line": 1,
                            "end_line": 1,
                        }
                    ],
                },
            ],
            "coverage": {
                "state": "complete",
                "truncation": "complete",
                "expected_declaration_ids": ["a", "b"],
                "scope": {},
                "provenance": {"provider": "fixture"},
            },
        }
    ]
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        packet = surface.repository_declarations(groups)
        with pytest.raises(McpSurfaceError, match="groups must be a list"):
            surface.repository_declarations({})  # type: ignore[arg-type]
    finally:
        surface.close()

    assert packet["schema"] == "hashmarks.repository-declarations.v1"
    assert packet["groups"][0]["comparison"]["state"] == "differing"
    assert all(
        row["semantic_declaration_identity"].startswith("sha256:")
        for row in packet["groups"][0]["declarations"]
    )
    assert packet["winner"] == "not-selected"
    assert packet["interpretation_authority"] == "consumer-owned"


def test_mcp_repository_declarations_explain_reuses_typed_projection(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "owner.yaml").write_text("owner: team-a\n", encoding="utf-8")
    groups = [
        {
            "group_id": "owner",
            "semantic_namespace": "mcp-fixture",
            "concept": {"kind": "ownership", "identity": "component"},
            "scope": {},
            "correspondence": {
                "state": "declared",
                "basis": {"provider": "fixture"},
            },
            "declarations": [
                {
                    "declaration_id": "owner",
                    "value_state": "resolved",
                    "value": "team-a",
                    "producer": {"kind": "fixture-yaml"},
                    "evidence": [
                        {
                            "path": "owner.yaml",
                            "start_line": 1,
                            "end_line": 1,
                        }
                    ],
                }
            ],
            "coverage": {
                "state": "complete",
                "truncation": "complete",
                "expected_declaration_ids": ["owner"],
                "scope": {},
                "provenance": {"provider": "fixture"},
            },
        }
    ]

    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        observation = surface.repository_declarations(groups)
        explanation = surface.repository_declarations(
            groups,
            result_mode="explain",
        )
        with pytest.raises(
            McpSurfaceError,
            match="previous_observation requires result_mode=observation",
        ):
            surface.repository_declarations(
                groups,
                previous_observation=observation,
                result_mode="explain",
            )
        with pytest.raises(McpSurfaceError, match="result_mode must be one of"):
            surface.repository_declarations(groups, result_mode="compare")
    finally:
        surface.close()

    assert observation["schema"] == "hashmarks.repository-declarations.v1"
    assert explanation["schema"] == "hashmarks.repository-declaration-explain.v1"
    assert (
        explanation["semantic_result"]["observation_identity"]
        == observation["observation_identity"]
    )
    assert explanation["semantic_value_authority"] == "provider-claimed"
    assert explanation["interpretation_authority"] == "consumer-owned"


def test_mcp_correlation_preserves_core_authority_and_completeness(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    bundles = [
        {
            "bundle_id": "runtime:incomplete",
            "producer": {"kind": "traceback"},
            "completeness": "incomplete",
            "scope": {"kind": "traceback-request"},
            "truncation": "truncated",
            "anchors": [{"anchor_id": "missing", "path": "missing.py"}],
        }
    ]
    with CodeMap(repo) as codemap:
        codemap.sync()
        core = codemap.correlate_evidence(bundles, include_relationships=False)
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "mcp-state"))
    try:
        projected = surface.correlate_evidence(bundles, include_relationships=False)
    finally:
        surface.close()

    for key in (
        "evidence_definition_identity",
        "completeness",
        "authority",
        "external_claims_authority",
        "interpretation_authority",
        "causation",
        "execution_effect",
    ):
        assert projected[key] == core[key]
    assert projected["completeness"]["negative_evidence"] == "not-admissible"


def test_mcp_correlation_rejects_recomputed_outer_identity_over_tampered_nested_evidence(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    surface = HashmarksMcpSurface(str(repo), state_dir=str(tmp_path / "state"))
    try:
        before = surface.correlate_evidence(
            [
                {
                    "bundle_id": "runtime:1",
                    "producer": {"kind": "traceback"},
                    "completeness": "complete",
                    "scope": {"kind": "traceback-request"},
                    "truncation": "complete",
                    "anchors": [{"anchor_id": "frame", "path": "src/feature.py"}],
                }
            ],
            include_relationships=False,
        )
        tampered = json.loads(json.dumps(before))
        tampered["repository_evidence"]["bindings"][0]["binding_id"] = (
            "repository-evidence:forged"
        )
        tampered["correlation_identity"] = "sha256:" + surface._map._packet_digest(
            "hashmarks.evidence-correlation.v2",
            {
                key: value
                for key, value in tampered.items()
                if key not in {"correlation_identity", "delta_from_previous"}
            },
        )
        with pytest.raises(
            McpSurfaceError, match="bindings identity mismatch"
        ) as continuity:
            surface.correlate_evidence(
                [
                    {
                        "bundle_id": "runtime:1",
                        "producer": {"kind": "traceback"},
                        "completeness": "complete",
                        "scope": {"kind": "traceback-request"},
                        "truncation": "complete",
                        "anchors": [{"anchor_id": "frame", "path": "src/feature.py"}],
                    }
                ],
                previous_correlation=tampered,
                include_relationships=False,
            )
        assert continuity.value.reason == "continuity-mismatch"
    finally:
        surface.close()
