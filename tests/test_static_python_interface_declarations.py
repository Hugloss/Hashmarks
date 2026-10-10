"""Adversarial static interface discovery without runtime-route claims."""

from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.static_python_interface_declarations import (
    StaticPythonInterfaceDeclarations,
)


def _observe(repo: Path, *, paths: tuple[str, ...] = ("service.py",)) -> dict:
    with CodeMap(repo) as cm:
        cm.sync()
        return cm.discover_repository_declarations(
            [StaticPythonInterfaceDeclarations(paths=paths)]
        )


def test_observes_route_and_mcp_tool_syntax_without_runtime_authority(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        '@app.get("/users")\n'
        "def users():\n"
        "    return []\n"
        "\n"
        '@mcp.tool(name="lookup_users")\n'
        "async def lookup():\n"
        "    return []\n",
        encoding="utf-8",
    )
    packet = _observe(tmp_path)
    assert packet["providers"][0]["state"] == "collected"
    groups = packet["declarations"]["groups"]
    assert len(groups) == 2
    observed = {row["concept"]["kind"]: row for row in groups}
    route = observed["http-route-decorator"]
    tool = observed["mcp-tool-decorator"]
    assert route["correspondence"]["state"] == "unresolved"
    assert route["coverage"]["state"] == "incomplete"
    assert route["absence"]["state"] == "unknown"
    route_fact = route["declarations"][0]
    assert route_fact["value"]["literal_argument"] == "/users"
    assert route_fact["value"]["decorator_method"] == "get"
    assert route_fact["value"]["handler_declared_name"] == "users"
    assert route_fact["evidence_state"] == "known-present"
    assert route_fact["semantic_value_authority"] == "provider-claimed"
    tool_fact = tool["declarations"][0]
    assert tool_fact["value"]["literal_argument"] == "lookup_users"
    assert tool_fact["value"]["handler_declared_name"] == "lookup"
    assert tool_fact["value"]["handler_kind"] == "async"
    assert tool_fact["evidence_state"] == "known-present"


def test_dynamic_decorator_argument_is_explicitly_unresolved_syntax(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        '@router.get(path_for("users"))\ndef handler():\n    return None\n',
        encoding="utf-8",
    )
    packet = _observe(tmp_path)
    group = packet["declarations"]["groups"][0]
    assert group["declarations"][0]["value"]["argument_state"] == (
        "dynamic-or-unsupported"
    )
    assert group["declarations"][0]["value"]["literal_argument"] is None
    assert group["correspondence"]["state"] == "unresolved"
    assert group["absence"]["state"] == "unknown"


def test_other_decorators_are_not_promoted_to_supported_interfaces(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        '@other.get("/users")\n'
        "def unrelated():\n"
        "    pass\n"
        "\n"
        '@app.add_api_route("/extra")\n'
        "def dynamic():\n"
        "    pass\n",
        encoding="utf-8",
    )
    packet = _observe(tmp_path)
    assert packet["declarations"]["groups"] == []
    assert packet["providers"][0]["state"] == "collected"


def test_missing_selected_file_does_not_prove_missing_routes(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        '@app.post("/users")\ndef create():\n    pass\n',
        encoding="utf-8",
    )
    packet = _observe(tmp_path, paths=("service.py", "unknown.py"))
    assert len(packet["declarations"]["groups"]) == 1
    assert packet["providers"][0]["provenance"]["missing_selected_paths"] == [
        "unknown.py"
    ]
    assert packet["declarations"]["groups"][0]["absence"]["state"] == "unknown"


@pytest.mark.parametrize(
    "paths",
    [(), ("service.txt",), ("../service.py",), ("x.py", "x.py")],
)
def test_invalid_selected_paths_fail_before_source_reads(
    paths: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        StaticPythonInterfaceDeclarations(paths=paths)


def test_replay_is_deterministic_and_source_mutation_changes_observation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "service.py"
    source.write_text('@app.get("/v1")\ndef handler():\n    pass\n')
    with CodeMap(tmp_path) as cm:
        cm.sync()
        provider = StaticPythonInterfaceDeclarations(paths=("service.py",))
        original = cm.discover_repository_declarations([provider])
        replay = cm.discover_repository_declarations([provider])
        assert original["observation_identity"] == replay["observation_identity"]
        source.write_text('@app.get("/v2")\ndef handler():\n    pass\n')
        cm.sync(["service.py"])
        newer = cm.discover_repository_declarations(
            [provider], previous_observation=original
        )
    assert newer["observation_identity"] != original["observation_identity"]
    assert (
        newer["declarations"]["groups"][0]["declarations"][0]["value"][
            "literal_argument"
        ]
        == "/v2"
    )
