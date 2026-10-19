"""Public transports preserve byte evidence and externally supplied membership."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Never

import pytest
from contract_assertions import assert_object, assert_records, assert_text

from hashmarks import CodeMap, validate_native_consumer_bundle
from hashmarks.mcp_sdk_server import close_sdk_server
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "contract.proto").write_bytes(b"\xef\xbb\xbfcontract\r\n\x00\xff")
    (root / "consumer.ts").write_text(
        "import {gateway as client} from './gateway';\n"
        "const transport = client;\n"
        "const {send: transmit} = transport;\n"
        "transport.send(payload);\ntransmit(payload);\n"
    )
    (root / "test_example.py").write_text(
        "raise RuntimeError('collection must remain external')\n"
        "class TestGroup:\n    def test_case(self): pass\n"
    )
    return root


def _report(codemap: CodeMap) -> dict[str, object]:
    member, _ = codemap.source.member("test_example.py")
    return {
        "schema": "hashmarks.verification-membership-report.v1",
        "selection_kind": "native-collected",
        "producer": {"name": "neutral-collector", "version": "1"},
        "provenance": {"report_id": "supplied:transport"},
        "scope": {"paths": ["test_example.py"]},
        "status": "succeeded",
        "completeness": "complete",
        "truncation": "complete",
        "members": [
            {"path": "test_example.py", "test_symbol": "TestGroup::test_case[a::b]"}
        ],
        "inputs": [
            {"path": "test_example.py", "member_revision": member["member_revision"]}
        ],
    }


def _cli(root: Path, state: Path, arguments: list[str]) -> dict[str, object]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hashmarks.cli",
            "--workspace",
            str(root),
            "--state-dir",
            str(state),
            *arguments,
        ],
        env={**os.environ, "HASHMARKS_NO_UPDATE_CHECK": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return assert_object(json.loads(result.stdout))


def _native(value: dict[str, object], presentation: str) -> dict[str, object]:
    if presentation == "none":
        return value
    assert value["schema"] == "hashmarks.evidence-presentation-envelope.v1"
    assert value["authority"] == "descriptive-only"
    return assert_object(value["result"])


@pytest.mark.parametrize("presentation", ["none", "compact"])
def test_cli_exact_bytes_keep_native_identity_with_optional_presentation(
    repository: Path, tmp_path: Path, presentation: str
) -> None:
    state = tmp_path / "state"
    with CodeMap(repository, state_dir=state) as codemap:
        codemap.index.sync(["contract.proto"])
        expected = codemap.source.range_receipt(
            "contract.proto", start_byte=3, end_byte=15
        )
    value = _cli(
        repository,
        state,
        [
            "source-observation",
            "contract.proto",
            "--result-mode",
            "range",
            "--start-byte",
            "3",
            "--end-byte",
            "15",
            "--presentation",
            presentation,
        ],
    )
    packet = _native(value, presentation)
    assert packet == expected
    content = assert_object(packet["content"])
    assert base64.b64decode(assert_text(content["data"])) == b"contract\r\n\x00\xff"


@pytest.mark.parametrize("presentation", ["none", "compact"])
def test_cli_ecmascript_preserves_native_parser_limits_and_facts(
    repository: Path, tmp_path: Path, presentation: str
) -> None:
    pytest.importorskip("tree_sitter_language_pack")
    state = tmp_path / "state"
    with CodeMap(repository, state_dir=state) as codemap:
        codemap.index.sync(["consumer.ts"])
        expected = codemap.source.ecmascript("consumer.ts", limit=2)
    value = _cli(
        repository,
        state,
        [
            "source-observation",
            "consumer.ts",
            "--result-mode",
            "ecmascript",
            "--limit",
            "2",
            "--presentation",
            presentation,
        ],
    )
    packet = _native(value, presentation)
    assert packet == expected
    assert len(assert_records(packet["facts"])) == 2
    assert packet["completeness"] == "incomplete"
    assert packet["truncation"] == "truncated"
    assert packet["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize("presentation", ["none", "compact"])
def test_cli_supplied_membership_is_a_valid_native_consumer_handoff(
    repository: Path, tmp_path: Path, presentation: str
) -> None:
    state = tmp_path / "state"
    with CodeMap(repository, state_dir=state) as codemap:
        codemap.index.sync()
        report = _report(codemap)
        expected = codemap.verification.observe_membership(report)
    supplied = tmp_path / "report.json"
    supplied.write_text(json.dumps(report))
    value = _cli(
        repository,
        state,
        [
            "verification-membership",
            "--input-json",
            str(supplied),
            "--presentation",
            presentation,
        ],
    )
    packet = _native(value, presentation)
    assert packet == expected
    assert validate_native_consumer_bundle(packet)["valid"] is True
    assert packet["membership_authority"] == "caller-claimed"
    assert packet["collection_completeness_authority"] == "caller-claimed"
    assert packet["repository_absence"] == "not-inferred"


def test_mcp_source_modes_preserve_canonical_bytes_and_bounded_syntax(
    repository: Path, tmp_path: Path
) -> None:
    pytest.importorskip("tree_sitter_language_pack")
    surface = HashmarksMcpSurface(str(repository), state_dir=str(tmp_path / "state"))
    try:
        receipt = surface.source_observation(
            ["contract.proto"],
            result_mode="range",
            byte_range={"start_byte": 3, "end_byte": 15},
        )
        assert receipt == surface._map.source.range_receipt(
            "contract.proto", start_byte=3, end_byte=15
        )
        syntax = surface.source_observation(
            ["consumer.ts"], result_mode="ecmascript", limit=2
        )
        assert syntax == surface._map.source.ecmascript("consumer.ts", limit=2)
        assert syntax["completeness"] == "incomplete"
        assert syntax["negative_evidence"] == "not-admissible"
    finally:
        surface.close()


@pytest.mark.parametrize(
    "byte_range",
    [
        {"start_byte": True, "end_byte": 3},
        {"start_byte": 0.0, "end_byte": 3},
        {"start_byte": -1, "end_byte": 3},
        {"start_byte": 4, "end_byte": 3},
        {"start_byte": 0},
        {"start_byte": 0, "end_byte": 3, "ignored": 1},
    ],
)
def test_mcp_byte_validation_precedes_source_access(
    repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    byte_range: dict[str, object],
) -> None:
    surface = HashmarksMcpSurface(str(repository), state_dir=str(tmp_path / "state"))

    def unexpected_sync(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError("invalid byte coordinates reached source access")

    monkeypatch.setattr(surface._map.index, "sync", unexpected_sync)
    try:
        with pytest.raises(McpSurfaceError):
            surface.source_observation(
                ["contract.proto"], result_mode="range", byte_range=byte_range
            )
    finally:
        surface.close()


def test_mcp_membership_reobserves_current_sources_without_promoting_claims(
    repository: Path, tmp_path: Path
) -> None:
    surface = HashmarksMcpSurface(str(repository), state_dir=str(tmp_path / "state"))
    try:
        surface._map.index.sync()
        report = _report(surface._map)
        before = surface.repository_evidence(report, result_mode="membership")
        (repository / "test_example.py").write_text("# changed since supplied report\n")
        after = surface.repository_evidence(report, result_mode="membership")
        assert assert_object(before["source_equivalence"])["state"] == "proven"
        assert assert_object(after["source_equivalence"])["state"] == "mismatch"
        assert before["membership"] == after["membership"]
        assert after["membership_authority"] == "caller-claimed"
        assert after["collection_completeness_authority"] == "caller-claimed"
        assert after["repository_absence"] == "not-inferred"
        assert validate_native_consumer_bundle(after)["valid"] is True
    finally:
        surface.close()


@pytest.mark.host_mcp_sdk
def test_sdk_routes_new_modes_and_rejects_boolean_byte_coordinates(
    repository: Path, tmp_path: Path
) -> None:
    pytest.importorskip("mcp")
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import CallToolResult

    from hashmarks.mcp_server import build_server

    with CodeMap(repository, state_dir=tmp_path / "report-state") as codemap:
        codemap.index.sync()
        report = _report(codemap)
    server = build_server(
        repository,
        state_dir=tmp_path / "sdk-state",
        tool_names=("source_observation", "repository_evidence"),
    )

    async def exercise() -> None:
        for arguments in (
            {
                "paths": ["contract.proto"],
                "result_mode": "range",
                "byte_range": {"start_byte": 3, "end_byte": 15},
            },
            {"paths": ["consumer.ts"], "result_mode": "ecmascript", "limit": 2},
        ):
            result = await server.call_tool("source_observation", arguments)
            assert isinstance(result, CallToolResult)
            assert result.is_error is not True
            packet = assert_object(result.structured_content)
            assert packet["schema"] in {
                "hashmarks.source-range-receipt.v1",
                "hashmarks.ecmascript-source-observation.v1",
            }
            assert packet["authority"] == "repository-evidence-only"
        result = await server.call_tool(
            "repository_evidence", {"request": report, "result_mode": "membership"}
        )
        assert isinstance(result, CallToolResult)
        assert result.is_error is not True
        packet = assert_object(result.structured_content)
        assert validate_native_consumer_bundle(packet)["valid"] is True
        with pytest.raises(ToolError, match="coordinates must be integers"):
            await server.call_tool(
                "source_observation",
                {
                    "paths": ["contract.proto"],
                    "result_mode": "range",
                    "byte_range": {"start_byte": True, "end_byte": 3},
                },
            )

    try:
        asyncio.run(exercise())
    finally:
        close_sdk_server(server)


@pytest.mark.host_mcp_sdk
def test_sdk_source_integer_bounds_reject_coercion_before_source_access(
    repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("mcp")
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import CallToolResult

    from hashmarks.mcp_server import build_server

    server = build_server(
        repository,
        state_dir=tmp_path / "strict-sdk-state",
        tool_names=("source_observation",),
    )
    surface = getattr(server, "_hashmarks_surface", None)
    assert isinstance(surface, HashmarksMcpSurface)

    def unexpected_sync(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError("invalid source bound reached source access")

    async def exercise() -> None:
        with monkeypatch.context() as protection:
            protection.setattr(surface._map.index, "sync", unexpected_sync)
            for mode in ("range", "ecmascript"):
                request: dict[str, object] = {
                    "paths": ["consumer.ts"],
                    "result_mode": mode,
                }
                if mode == "range":
                    request["byte_range"] = {"start_byte": 0, "end_byte": 6}
                for field in ("limit", "max_bytes"):
                    for value in (True, False, 1.0, "1"):
                        with pytest.raises(ToolError, match="valid integer"):
                            await server.call_tool(
                                "source_observation", {**request, field: value}
                            )
            with pytest.raises(ToolError, match="default limit of 50"):
                await server.call_tool(
                    "source_observation",
                    {
                        "paths": ["consumer.ts"],
                        "result_mode": "range",
                        "byte_range": {"start_byte": 0, "end_byte": 6},
                        "limit": 1,
                    },
                )

        request = {
            "paths": ["consumer.ts"],
            "result_mode": "range",
            "byte_range": {"start_byte": 0, "end_byte": 6},
            "max_bytes": 1024,
        }
        omitted = await server.call_tool("source_observation", request)
        explicit = await server.call_tool(
            "source_observation", {**request, "limit": 50}
        )
        assert isinstance(omitted, CallToolResult)
        assert isinstance(explicit, CallToolResult)
        assert omitted.is_error is explicit.is_error is not True
        assert explicit.structured_content == omitted.structured_content
        packet = assert_object(explicit.structured_content)
        assert assert_object(packet["limits"])["max_bytes"] == 1024

    try:
        asyncio.run(exercise())
    finally:
        close_sdk_server(server)


def test_range_mode_rejects_unused_limit_before_source_access(
    repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    surface = HashmarksMcpSurface(str(repository), state_dir=str(tmp_path / "state"))

    def unexpected_sync(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError("inapplicable limit reached source access")

    monkeypatch.setattr(surface._map.index, "sync", unexpected_sync)
    try:
        with pytest.raises(McpSurfaceError, match="default limit of 50"):
            surface.source_observation(
                ["contract.proto"],
                result_mode="range",
                byte_range={"start_byte": 0, "end_byte": 3},
                limit=1,
            )
    finally:
        surface.close()


def test_strict_source_sdk_metadata_keeps_pydantic_optional_for_fake_catalog(
    tmp_path: Path,
) -> None:
    script = """\
import importlib.util
import sys

def optional(name):
    return any(name == root or name.startswith(root + ".")
               for root in ("mcp", "pydantic", "pydantic_core"))

class MissingSdkDependencies:
    def find_spec(self, fullname, path=None, target=None):
        if optional(fullname):
            raise ModuleNotFoundError("optional SDK dependency unavailable", name=fullname)

sys.meta_path.insert(0, MissingSdkDependencies())
original_find_spec = importlib.util.find_spec
def find_spec(name, *args, **kwargs):
    return None if optional(name) else original_find_spec(name, *args, **kwargs)
importlib.util.find_spec = find_spec

import hashmarks.mcp_server
import pytest
raise SystemExit(pytest.main([
    "-q", "-o", "cache_dir=" + sys.argv[1],
    "tests/test_mcp_surface.py::test_mcp_server_registers_exact_small_read_only_tool_catalog",
]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "pytest-cache")],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "HASHMARKS_CONSTRAINED_HOST": "0",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
