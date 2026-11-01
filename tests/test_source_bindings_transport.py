"""Public source-binding transports preserve qualification and source identity."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Never, NotRequired, TypedDict

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.codemap import CodeMapService, CodeMapServiceClient
from hashmarks.codemap.service import PROTOCOL
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError


class _SourceSelectors(TypedDict, total=False):
    paths: list[str]
    literal: str
    literals: list[str]
    byte_range: dict[str, object]
    context_lines: int | dict[str, object]
    limit: int
    max_bytes: int


class _BindingRequest(TypedDict):
    paths: list[str]
    result_mode: str
    literal: NotRequired[str]
    literals: NotRequired[list[str]]
    byte_range: NotRequired[dict[str, object]]
    context_lines: NotRequired[int | dict[str, object]]
    limit: NotRequired[int]
    max_bytes: NotRequired[int]


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "consumer.py").write_text(
        "from subprocess import Popen as launcher\n"
        "alias = launcher\n"
        "def invoke(factory=alias):\n"
        "    return factory(['true'])\n",
        encoding="utf-8",
    )
    (root / "consumer.ts").write_text(
        'const key = "fe" + "tch";\n'
        "const transport = globalThis[key];\n"
        'function local(fetch) { return fetch("/api"); }\n'
        'transport("/api");\n',
        encoding="utf-8",
    )
    return root


def _native_grammar(path: str) -> None:
    if path.endswith(".ts"):
        pytest.importorskip("tree_sitter_language_pack")


def _cli(
    root: Path, state: Path, path: str, options: list[str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "hashmarks.cli",
            "--workspace",
            str(root),
            "--state-dir",
            str(state),
            "source-observation",
            path,
            "--result-mode",
            "bindings",
            *options,
        ],
        env={**os.environ, "HASHMARKS_NO_UPDATE_CHECK": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


@pytest.mark.parametrize("path", ["consumer.py", "consumer.ts"])
@pytest.mark.parametrize("presentation", ["none", "compact"])
def test_cli_binding_projection_preserves_exact_native_packet(
    repository: Path, tmp_path: Path, path: str, presentation: str
) -> None:
    _native_grammar(path)
    state = tmp_path / "state"
    with CodeMap(repository, state_dir=state) as codemap:
        codemap.index.sync([path])
        expected = codemap.source.bindings(path, limit=2, max_bytes=4096)
    result = _cli(
        repository,
        state,
        path,
        ["--limit", "2", "--max-bytes", "4096", "--presentation", presentation],
    )
    assert result.returncode == 0, result.stderr
    value = assert_object(json.loads(result.stdout))
    if presentation == "compact":
        assert value["schema"] == "hashmarks.evidence-presentation-envelope.v1"
        assert assert_object(value["presentation"])["supported"] is True
        value = assert_object(value["result"])
    assert value == expected
    assert value["schema"] == "hashmarks.source-bindings.v1"
    assert len(assert_records(value["facts"])) == 2
    assert value["truncation"] == "truncated"
    assert value["negative_evidence"] == "not-admissible"
    assert value["runtime_target_resolution"] == "not-performed"


@pytest.mark.parametrize("path", ["consumer.py", "consumer.ts"])
def test_mcp_bindings_preserve_full_qualification_and_source_change(
    repository: Path, tmp_path: Path, path: str
) -> None:
    _native_grammar(path)
    surface = HashmarksMcpSurface(str(repository), state_dir=str(tmp_path / "state"))
    try:
        before = surface.source_observation(
            [path], result_mode="bindings", limit=50, max_bytes=4096
        )
        assert before == surface._map.source.bindings(path, limit=50, max_bytes=4096)
        facts = assert_records(before["facts"])
        assert facts
        assert all(row["runtime_target"] == "not-established" for row in facts)
        assert any(row["qualification"] == "unknown" for row in facts)
        member = assert_object(before["member"])
        original = (repository / path).read_text(encoding="utf-8")
        comment = (
            "# changed revision\n" if path.endswith(".py") else "// changed revision\n"
        )
        (repository / path).write_text(original + comment, encoding="utf-8")
        after = surface.source_observation(
            [path], result_mode="bindings", limit=50, max_bytes=4096
        )
        assert (
            assert_object(after["member"])["member_revision"]
            != member["member_revision"]
        )
        assert after["observation_identity"] != before["observation_identity"]
        assert after["negative_evidence"] == "not-admissible"
        assert after == surface._map.source.bindings(path, limit=50, max_bytes=4096)
    finally:
        surface.close()


@pytest.mark.parametrize("path", ["consumer.py", "consumer.ts"])
def test_service_binding_route_and_client_preserve_json_packet(
    repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    _native_grammar(path)
    with CodeMap(repository, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync([path])
        service = CodeMapService(repository)
        service._codemap = codemap
        client = CodeMapServiceClient(repository)

        def transport(op: str, **payload: object) -> dict[str, object]:
            request = json.loads(
                json.dumps({"protocol": PROTOCOL, "op": op, **payload})
            )
            return assert_object(json.loads(json.dumps(service.dispatch(request))))

        monkeypatch.setattr(client, "request", transport)
        expected = codemap.source.bindings(path, limit=50, max_bytes=4096)
        assert client.source_bindings(path, limit=50, max_bytes=4096) == expected
        assert expected["module_resolution"] == "not-performed"
        assert expected["execution_effect"] == "none"


@pytest.mark.parametrize(
    "invalid",
    [
        {"paths": ["consumer.py", "consumer.ts"]},
        {"literal": "launcher"},
        {"literals": ["launcher"]},
        {"byte_range": {"start_byte": 0, "end_byte": 3}},
        {"context_lines": 1},
        {"context_lines": {"lines": [1], "radius": 1}},
        {"limit": True},
        {"limit": 51},
        {"max_bytes": True},
        {"max_bytes": 0},
    ],
)
def test_mcp_binding_selectors_fail_before_index_or_source_access(
    repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid: _SourceSelectors,
) -> None:
    surface = HashmarksMcpSurface(str(repository), state_dir=str(tmp_path / "state"))

    def unexpected_sync(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError("invalid binding request reached repository sync")

    monkeypatch.setattr(surface._map.index, "sync", unexpected_sync)
    options: _BindingRequest = {
        "paths": ["consumer.py"],
        "result_mode": "bindings",
        **invalid,
    }
    try:
        with pytest.raises(McpSurfaceError):
            surface.source_observation(**options)
    finally:
        surface.close()


@pytest.mark.parametrize(
    "invalid",
    [
        {"path": ["consumer.py"]},
        {"path": ""},
        {"paths": ["consumer.py"]},
        {"result_mode": "ecmascript"},
        {"literal": "launcher"},
    ],
)
def test_service_binding_request_rejects_widened_or_ambiguous_selection(
    repository: Path, invalid: dict[str, object]
) -> None:
    service = CodeMapService(repository)
    with pytest.raises(ValueError):
        service.dispatch(
            {
                "protocol": PROTOCOL,
                "op": "source_bindings",
                "path": "consumer.py",
                **invalid,
            }
        )


def test_service_binding_response_cannot_masquerade_as_syntax_only(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = CodeMapService(repository)
    wrong = {
        "ok": True,
        "source_bindings": {"schema": "hashmarks.ecmascript-source-observation.v1"},
    }
    monkeypatch.setattr(service, "_source_bindings_response", lambda _request: wrong)
    with pytest.raises(RuntimeError, match="schema drift"):
        service.dispatch(
            {"protocol": PROTOCOL, "op": "source_bindings", "path": "consumer.py"}
        )
    client = CodeMapServiceClient(repository)
    monkeypatch.setattr(client, "request", lambda _op, **_payload: wrong)
    with pytest.raises(RuntimeError, match="schema drift"):
        client.source_bindings("consumer.py")


@pytest.mark.parametrize("options", [["--line", "1"], ["--start-byte", "0"]])
def test_cli_binding_mode_rejects_foreign_selectors_before_opening_index(
    repository: Path, tmp_path: Path, options: list[str]
) -> None:
    state = tmp_path / "unopened-state"
    result = _cli(repository, state, "consumer.py", options)
    assert result.returncode != 0
    assert (
        "requires member mode" in result.stderr or "require range mode" in result.stderr
    )
    assert not state.exists()
