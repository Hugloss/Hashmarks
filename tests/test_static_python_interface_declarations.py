"""Adversarial static interface discovery without runtime-route claims."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from contract_assertions import assert_object

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_declaration_provider import (
    RepositoryDeclarationProviderError,
)
from hashmarks.codemap.static_python_interface_declarations import (
    StaticPythonInterfaceDeclarations,
)
from hashmarks.evidence_presentation import FORMATS, presentation_response


def _observe(repo: Path, *, paths: tuple[str, ...] = ("service.py",)) -> dict:
    with CodeMap(repo) as cm:
        cm.index.sync()
        return cm.declarations.discover(
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


def test_explicit_curried_route_call_preserves_syntax_and_runtime_unknowns(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        "def configure():\n"
        "    async def handle(request):\n"
        "        return request\n"
        "    if enabled:\n"
        '        app.post(f"{prefix}/items", include_in_schema=False)(handle)\n',
        encoding="utf-8",
    )
    packet = _observe(tmp_path)
    groups = packet["declarations"]["groups"]
    registration = next(
        row for row in groups if row["concept"]["kind"] == "http-route-call"
    )
    value = registration["declarations"][0]["value"]
    assert value["object_name"] == "app"
    assert value["method_syntax"] == "post"
    assert value["argument_state"] == "dynamic-or-unsupported"
    assert value["literal_argument"] is None
    assert value["handler_argument_syntax"] == "handle"
    assert value["runtime_registration"] == "not-established"
    assert value["handler_resolution"] == "unresolved"
    assert registration["scope"]["path"] == "service.py"
    assert registration["scope"]["call_line"] == 5
    assert registration["declarations"][0]["evidence_state"] == "known-present"
    assert registration["absence"]["state"] == "unknown"
    assert registration["coverage"]["state"] == "incomplete"
    assert registration["correspondence"]["state"] == "unresolved"


def test_curried_route_syntax_does_not_resolve_rebound_or_missing_handlers(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        'app.get("/one")(missing)\n'
        "def handler(): return 1\n"
        "handler = replacement\n"
        'app.post("/two")(handler)\n'
        'other.get("/foreign")(handler)\n',
        encoding="utf-8",
    )
    groups = _observe(tmp_path)["declarations"]["groups"]
    values = [row["declarations"][0]["value"] for row in groups]
    assert [row["literal_argument"] for row in values] == ["/one", "/two"]
    assert [row["handler_argument_syntax"] for row in values] == ["missing", "handler"]
    assert all(row["handler_resolution"] == "unresolved" for row in values)
    assert all(row["runtime_registration"] == "not-established" for row in values)


def test_curried_route_dynamic_handler_and_expansion_remain_unresolved(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        "raise RuntimeError('source must not execute')\n"
        "app.get(**options)(build_handler())\n"
        'app.post("/literal", **options)(*handlers)\n',
        encoding="utf-8",
    )
    values = _interface_values(_observe(tmp_path))
    assert values[0]["argument_state"] == "dynamic-or-unsupported"
    assert values[0]["literal_argument"] is None
    assert values[1]["literal_argument"] == "/literal"
    assert all(row["has_argument_expansion"] is True for row in values)
    assert all(row["handler_argument_syntax"] is None for row in values)
    assert all(
        row["handler_argument_state"] == "dynamic-or-unsupported" for row in values
    )
    assert all(row["handler_resolution"] == "unresolved" for row in values)


def test_curried_route_expression_in_decorator_is_not_a_call_registration(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        '@app.get("/factory")(factory)\ndef handler(): return 1\n',
        encoding="utf-8",
    )
    assert _observe(tmp_path)["declarations"]["groups"] == []


def test_curried_route_calls_share_the_existing_provider_group_bound(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        "".join(f'app.get("/{index}")(handler)\n' for index in range(129)),
        encoding="utf-8",
    )
    with pytest.raises(RepositoryDeclarationProviderError, match="group bound"):
        _observe(tmp_path)


@pytest.mark.parametrize("format", FORMATS)
def test_curried_route_formats_preserve_source_claim_and_uncertainty(
    tmp_path: Path, format: str
) -> None:
    (tmp_path / "service.py").write_text('app.post("/items")(handler)\n')
    native = _observe(tmp_path)["declarations"]
    response = presentation_response(
        "repository_declarations", native, format=format, result_mode="observation"
    )
    if format == "none":
        assert response == native
    else:
        assert response["result"] == native
        projection: Any = response["presentation"]
        claims = [
            finding
            for group in projection["groups"]
            for finding in group["findings"]
            if finding["source_refs"] == ["/groups/0"]
        ]
        assert len(claims) == 1
        assert claims[0]["details"] == native["groups"][0]
        assert claims[0]["assertion"] == "producer_claim"
        if format == "text":
            assert '"handler_resolution":"unresolved"' in projection["text"]
            assert '"runtime_registration":"not-established"' in projection["text"]


def test_curried_route_edit_requires_refresh_and_previous_packet_cannot_replay_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "service.py"
    path.write_text('app.get("/before")(handler)\n')
    state = tmp_path / "state"
    provider = StaticPythonInterfaceDeclarations(paths=("service.py",))
    with CodeMap(tmp_path, state_dir=state) as repo:
        repo.index.sync()
        before = repo.declarations.discover([provider])
        path.write_text('app.post("/after")(replacement)\n')
        with pytest.raises(RepositoryDeclarationProviderError, match="input changed"):
            repo.declarations.discover([provider], previous_observation=before)
        repo.index.sync(["service.py"])
        after = repo.declarations.discover([provider], previous_observation=before)
        assert _interface_values(after)[0]["literal_argument"] == "/after"
        assert _interface_values(after)[0]["handler_argument_syntax"] == "replacement"
        assert before["observation_identity"] != after["observation_identity"]
    with CodeMap(tmp_path, state_dir=state) as reopened:
        unselected = reopened.declarations.discover([], previous_observation=before)
        assert assert_object(unselected["declarations"])["groups"] == []
        assert unselected["providers"] == []


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
        cm.index.sync()
        provider = StaticPythonInterfaceDeclarations(paths=("service.py",))
        original = cm.declarations.discover([provider])
        replay = cm.declarations.discover([provider])
        assert original["observation_identity"] == replay["observation_identity"]
        source.write_text('@app.get("/v2")\ndef handler():\n    pass\n')
        cm.index.sync(["service.py"])
        newer: Any = cm.declarations.discover([provider], previous_observation=original)
    assert newer["observation_identity"] != original["observation_identity"]
    assert (
        newer["declarations"]["groups"][0]["declarations"][0]["value"][
            "literal_argument"
        ]
        == "/v2"
    )


@pytest.mark.parametrize(
    ("decorator", "state", "literal"),
    [
        ("@router.get(**route_options)", "dynamic-or-unsupported", None),
        ("@mcp.tool(**tool_options)", "dynamic-or-unsupported", None),
        ('@mcp.tool("positional_name")', "dynamic-or-unsupported", None),
        ("@mcp.tool(*tool_arguments)", "dynamic-or-unsupported", None),
        ("@router.get(*route_arguments)", "dynamic-or-unsupported", None),
        ('@router.get(path="/explicit", **options)', "literal", "/explicit"),
        ('@mcp.tool(name="explicit", **options)', "literal", "explicit"),
        ("@mcp.tool()", "not-supplied", None),
        ("@mcp.tool", "not-supplied", None),
    ],
)
def test_expanded_and_unsupported_arguments_preserve_syntactic_uncertainty(
    tmp_path: Path,
    decorator: str,
    state: str,
    literal: str | None,
) -> None:
    (tmp_path / "service.py").write_text(
        f"{decorator}\nasync def lookup():\n    return []\n"
    )
    packet = _observe(tmp_path)
    (group,) = packet["declarations"]["groups"]
    value = group["declarations"][0]["value"]
    assert value["argument_state"] == state
    assert value["literal_argument"] == literal
    assert group["coverage"]["state"] == "incomplete"
    assert group["correspondence"]["state"] == "unresolved"
    assert group["absence"]["state"] == "unknown"


def _interface_values(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        group["declarations"][0]["value"] for group in packet["declarations"]["groups"]
    ]


def test_multifile_interfaces_edit_rename_delete_and_reopen_without_replay(
    tmp_path: Path,
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    root.mkdir()
    api = root / "api.py"
    api.write_text(
        'raise RuntimeError("source must never execute")\n'
        '@router.get(\n    path="/räknare"\n)\n'
        '@router.post("/räknare")\n'
        "async def counters():\n    return []\n",
        encoding="utf-8",
    )
    (root / "tools.py").write_text(
        '@mcp.tool(name="lookup_counters")\ndef lookup():\n    return []\n'
    )
    provider = StaticPythonInterfaceDeclarations(paths=("api.py", "tools.py"))
    with CodeMap(root, state_dir=state) as cm:
        cm.index.sync()
        before: Any = cm.declarations.discover([provider])
        assert len(_interface_values(before)) == 3
        assert {row["literal_argument"] for row in _interface_values(before)} == {
            "/räknare",
            "lookup_counters",
        }
        binding_id = before["declarations"]["groups"][0]["declarations"][0][
            "binding_id"
        ]
        binding = next(
            row
            for row in before["declarations"]["repository_evidence"]["bindings"]
            if row["binding_id"] == binding_id
        )
        evidence = binding["evidence"][0]
        assert evidence["start_line"] == 2
        assert evidence["end_line"] == 6
        api.write_text(api.read_text().replace("/räknare", "/räknare/v2"))
        with pytest.raises(
            RepositoryDeclarationProviderError, match="input changed while reading"
        ):
            cm.declarations.discover([provider], previous_observation=before)
        cm.index.sync(["api.py"])
        changed: Any = cm.declarations.discover([provider], previous_observation=before)
        assert changed["observation_identity"] != before["observation_identity"]
        assert {row["literal_argument"] for row in _interface_values(changed)} == {
            "/räknare/v2",
            "lookup_counters",
        }
        assert changed["delta_from_previous"]["declarations"]["changed_groups"]
        api.rename(root / "routes.py")
        cm.index.sync(["api.py", "routes.py"])
        renamed: Any = cm.declarations.discover(
            [
                StaticPythonInterfaceDeclarations(
                    paths=("api.py", "routes.py", "tools.py")
                )
            ],
            previous_observation=changed,
        )
        assert renamed["providers"][0]["provenance"]["missing_selected_paths"] == [
            "api.py"
        ]
        assert len(_interface_values(renamed)) == 3
    with CodeMap(root, state_dir=state) as cm:
        tools: Any = cm.declarations.discover(
            [StaticPythonInterfaceDeclarations(paths=("tools.py",))],
            previous_observation=renamed,
        )
        assert [row["literal_argument"] for row in _interface_values(tools)] == [
            "lookup_counters"
        ]
        assert _interface_values(cm.declarations.discover([])) == []
        (root / "tools.py").unlink()
        cm.index.sync(["tools.py"])
        deleted: Any = cm.declarations.discover([provider], previous_observation=tools)
        assert _interface_values(deleted) == []
    with CodeMap(root, state_dir=state) as cm:
        assert _interface_values(cm.declarations.discover([provider])) == []


def test_actual_nested_hashmarks_handlers_are_unsupported_not_missing_tools(
    tmp_path: Path,
) -> None:
    import hashmarks.mcp_server as mcp_server

    assert mcp_server.__file__ is not None
    (tmp_path / "server.py").write_bytes(Path(mcp_server.__file__).read_bytes())
    packet = _observe(tmp_path, paths=("server.py",))
    assert packet["providers"][0]["state"] == "collected"
    assert packet["declarations"]["groups"] == []
    assert packet["authority"] == "repository-intelligence-only"


def test_selected_denied_source_does_not_leak_decorator_literals(
    tmp_path: Path,
) -> None:
    import json

    (tmp_path / "service.py").write_text(
        '@router.get("/private-route")\ndef hidden():\n    pass\n'
    )
    (tmp_path / "tools.py").write_text(
        '@mcp.tool(name="public_tool")\ndef public():\n    pass\n'
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "service.py"\nvisibility = "deny"\n'
    )
    with pytest.raises(RepositoryDeclarationProviderError) as failure:
        _observe(tmp_path, paths=("service.py", "tools.py"))
    assert "/private-route" not in str(failure.value)
    packet = _observe(tmp_path, paths=("tools.py",))
    assert [row["literal_argument"] for row in _interface_values(packet)] == [
        "public_tool"
    ]
    assert "/private-route" not in json.dumps(packet)


@pytest.mark.parametrize("boundary", ["groups", "source", "syntax"])
def test_interface_input_bounds_and_invalid_syntax_fail_without_publishing(
    tmp_path: Path,
    boundary: str,
) -> None:
    source = {
        "groups": "".join(
            f'@router.get("/{index}")\ndef handler_{index}():\n    pass\n'
            for index in range(129)
        ),
        "source": "#" + "x" * 262144,
        "syntax": '@router.get("/broken")\ndef handler(:\n',
    }[boundary]
    (tmp_path / "service.py").write_text(source)
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        with pytest.raises(RepositoryDeclarationProviderError):
            cm.declarations.discover(
                [StaticPythonInterfaceDeclarations(paths=("service.py",))]
            )
        packet: Any = cm.declarations.discover([])
        assert packet["declarations"]["groups"] == []
