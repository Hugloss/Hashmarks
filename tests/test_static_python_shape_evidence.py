"""Opt-in H09/H10 handler syntax remains producer evidence, not API truth."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_declaration_provider import (
    RepositoryDeclarationProviderError,
)
from hashmarks.codemap.static_python_interface_declarations import (
    StaticPythonInterfaceDeclarations,
)


def _observe(root: Path, *, include: bool = True) -> dict:
    provider = StaticPythonInterfaceDeclarations(
        paths=("service.py",),
        include_literal_shape_syntax=include,
    )
    with CodeMap(root) as cm:
        cm.sync()
        return cm.discover_repository_declarations([provider])


def _group(packet: dict) -> dict:
    return packet["declarations"]["groups"][0]


def _value(packet: dict) -> dict:
    return _group(packet)["declarations"][0]["value"]


@pytest.mark.parametrize(
    ("expression", "expected_keys", "expected_lines"),
    [
        (
            "    return {\n"
            '        payload["key1"]: payload["value1"],\n'
            '        payload["key2"]: payload["value2"],\n'
            "    }\n",
            ["key1", "value1", "key2", "value2"],
            [4, 4, 5, 5],
        ),
        (
            '    return {payload["key1"]: payload["value1"], '
            'payload["key2"]: payload["value2"]}\n',
            ["key1", "value1", "key2", "value2"],
            [3, 3, 3, 3],
        ),
        (
            "    return await build(\n"
            '        answer=payload["first"],\n'
            '        *payload["second"],\n'
            "    )\n",
            ["first", "second"],
            [4, 5],
        ),
        (
            '    return await build(answer=payload["first"], *payload["second"])\n',
            ["first", "second"],
            [3, 3],
        ),
    ],
    ids=["multiline-dict", "same-line-dict", "multiline-call", "same-line-call"],
)
def test_literal_reads_follow_physical_source_order(
    tmp_path: Path,
    expression: str,
    expected_keys: list[str],
    expected_lines: list[int],
) -> None:
    (tmp_path / "service.py").write_text(
        '@router.get("/values")\nasync def values(payload):\n' + expression,
        encoding="utf-8",
    )
    body = _value(_observe(tmp_path))["static_body_syntax"]
    sites = body["literal_subscript_accesses"]
    assert [site["literal_key"] for site in sites] == expected_keys
    assert [site["line"] for site in sites] == expected_lines
    assert all(
        set(site) == {"line", "end_line", "receiver_syntax", "literal_key"}
        for site in sites
    )
    assert body["literal_dictionary_returns"][0]["syntax"] == "unresolved-return"
    assert body["coverage"] == "incomplete"


def test_selected_handler_syntax_is_source_bound_and_unresolved(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text(
        'raise RuntimeError("do not execute")\n'
        '@router.get("/users")\n'
        "def users(payload):\n"
        '    user_id = payload["id"]\n'
        "    if user_id:\n"
        '        return {"id": user_id, "ok": True}\n'
        "    return build_response()\n",
        encoding="utf-8",
    )
    packet = _observe(tmp_path)
    body = _value(packet)["static_body_syntax"]
    assert _value(packet)["literal_argument"] == "/users"
    assert body["authority"] == "direct-static-syntax-only"
    assert body["coverage"] == "incomplete"
    assert body["runtime_response_shape"] == "unknown"
    assert body["cross_artifact_correspondence"] == "unresolved"
    assert body["literal_dictionary_returns"] == [
        {
            "line": 6,
            "end_line": 6,
            "syntax": "literal-dict-return",
            "literal_keys_in_source_order": ["id", "ok"],
        },
        {
            "line": 7,
            "end_line": 7,
            "syntax": "unresolved-return",
            "literal_keys_in_source_order": None,
        },
    ]
    assert body["literal_subscript_accesses"] == [
        {
            "line": 4,
            "end_line": 4,
            "receiver_syntax": "payload",
            "literal_key": "id",
        }
    ]
    declaration = _group(packet)["declarations"][0]
    assert declaration["evidence_state"] == "known-present"
    binding = next(
        row
        for row in packet["declarations"]["repository_evidence"]["bindings"]
        if row["binding_id"] == declaration["binding_id"]
    )
    assert {(row["start_line"], row["end_line"]) for row in binding["evidence"]} == {
        (2, 3),
        (4, 4),
        (6, 6),
        (7, 7),
    }
    assert _group(packet)["correspondence"]["state"] == "unresolved"
    assert _group(packet)["absence"]["state"] == "unknown"


def test_default_contract_is_unchanged_by_opt_in(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text(
        '@mcp.tool(name="search")\n'
        "def search(data):\n"
        '    return {"answer": data["query"]}\n'
    )
    native = _observe(tmp_path, include=False)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        default = cm.discover_repository_declarations(
            [StaticPythonInterfaceDeclarations(paths=("service.py",))]
        )
    assert native["observation_identity"] == default["observation_identity"]
    assert "static_body_syntax" not in _value(native)
    opt_in = _observe(tmp_path)
    assert opt_in["observation_identity"] != native["observation_identity"]


def test_nested_scopes_dynamic_returns_and_unsupported_keys_are_unknown(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        '@app.post("/x")\n'
        "def handler(payload):\n"
        "    def nested():\n"
        '        return {"not_handler": 1}\n'
        '    obj = lambda value: value["not_handler"]\n'
        "    if flag:\n"
        '        return {**payload, "known": 1}\n'
        '    return {42: "numeric", "key": 3}\n'
    )
    body = _value(_observe(tmp_path))["static_body_syntax"]
    assert [row["syntax"] for row in body["literal_dictionary_returns"]] == [
        "unresolved-return",
        "unresolved-return",
    ]
    assert all(
        row["literal_keys_in_source_order"] is None
        for row in body["literal_dictionary_returns"]
    )
    assert body["literal_subscript_accesses"] == []
    assert body["coverage"] == "incomplete"


def test_literal_writes_and_deletes_are_not_consumer_reads(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text(
        '@app.post("/values")\n'
        "def values(payload):\n"
        '    payload["write"] = 1\n'
        '    del payload["delete"]\n'
        '    value = payload["read"]\n'
        '    return {"ok": value}\n'
    )
    body = _value(_observe(tmp_path))["static_body_syntax"]
    assert [site["literal_key"] for site in body["literal_subscript_accesses"]] == [
        "read"
    ]
    assert body["coverage"] == "incomplete"


def test_multiple_selected_decorators_preserve_distinct_route_scopes(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.py").write_text(
        '@app.get("/first")\n'
        '@router.post("/second")\n'
        "def handler():\n"
        '    return {"ok": True}\n'
    )
    packet = _observe(tmp_path)
    groups = packet["declarations"]["groups"]
    assert len(groups) == 2
    assert all(
        group["declarations"][0]["value"]["static_body_syntax"][
            "literal_dictionary_returns"
        ][0]["literal_keys_in_source_order"]
        == ["ok"]
        for group in groups
    )
    assert all(group["correspondence"]["state"] == "unresolved" for group in groups)


def test_site_limit_fails_before_provider_publication(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text(
        '@router.get("/many")\n'
        "def many(payload):\n" + "".join(f'    payload["key_{n}"]\n' for n in range(17))
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        with pytest.raises(RepositoryDeclarationProviderError, match="site bound"):
            cm.discover_repository_declarations(
                [
                    StaticPythonInterfaceDeclarations(
                        paths=("service.py",),
                        include_literal_shape_syntax=True,
                    )
                ]
            )
        assert cm.discover_repository_declarations([])["declarations"]["groups"] == []


@pytest.mark.parametrize("kind", ["returns", "reads"])
def test_site_bound_accepts_sixteen_and_rejects_seventeen(
    tmp_path: Path, kind: str
) -> None:
    def handler(count: int) -> str:
        statements = (
            f'    if payload:\n        return {{"key_{n}": {n}}}\n'
            if kind == "returns"
            else f'    payload["key_{n}"]\n'
            for n in range(count)
        )
        return '@router.get("/values")\ndef values(payload):\n' + "".join(statements)

    source = tmp_path / "service.py"
    source.write_text(handler(16), encoding="utf-8")
    provider = StaticPythonInterfaceDeclarations(
        paths=("service.py",), include_literal_shape_syntax=True
    )
    field = (
        "literal_dictionary_returns"
        if kind == "returns"
        else "literal_subscript_accesses"
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        before = cm.discover_repository_declarations([provider])
        assert len(_value(before)["static_body_syntax"][field]) == 16
        source.write_text(handler(17), encoding="utf-8")
        cm.sync(["service.py"])
        with pytest.raises(RepositoryDeclarationProviderError, match="site bound"):
            cm.discover_repository_declarations([provider], previous_observation=before)
        empty: dict[str, Any] = cm.discover_repository_declarations([])
        assert empty["declarations"]["groups"] == []
        source.write_text(handler(16), encoding="utf-8")
        cm.sync(["service.py"])
        repaired = cm.discover_repository_declarations(
            [provider], previous_observation=before
        )
        assert _value(repaired) == _value(before)


@pytest.mark.parametrize("key_count", [32, 33])
@pytest.mark.parametrize("key_chars", [128, 129])
def test_large_dictionary_never_publishes_a_partial_key_set(
    tmp_path: Path, key_count: int, key_chars: int
) -> None:
    keys = ["é" * key_chars, *(f"field_{n}" for n in range(key_count - 1))]
    expression = ", ".join(f"{key!r}: 1" for key in keys)
    (tmp_path / "service.py").write_text(
        '@router.get("/values")\ndef values():\n    return {' + expression + "}\n",
        encoding="utf-8",
    )
    packet = _observe(tmp_path)
    body = _value(packet)["static_body_syntax"]
    (site,) = body["literal_dictionary_returns"]
    if key_count == 32 and key_chars == 128:
        assert site["syntax"] == "literal-dict-return"
        assert site["literal_keys_in_source_order"] == keys
    else:
        assert site["syntax"] == "unresolved-return"
        assert site["literal_keys_in_source_order"] is None
    assert body["runtime_response_shape"] == "unknown"
    assert body["coverage"] == "incomplete"
    assert _group(packet)["absence"]["state"] == "unknown"


def test_stale_source_cannot_reuse_old_literal_facts(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text('@app.get("/x")\ndef x():\n    return {"old": 1}\n')
    provider = StaticPythonInterfaceDeclarations(
        paths=("service.py",),
        include_literal_shape_syntax=True,
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        first = cm.discover_repository_declarations([provider])
        source.write_text('@app.get("/x")\ndef x():\n    return {"new": 1}\n')
        with pytest.raises(RepositoryDeclarationProviderError, match="input changed"):
            cm.discover_repository_declarations([provider], previous_observation=first)
        cm.sync(["service.py"])
        second = cm.discover_repository_declarations(
            [provider],
            previous_observation=first,
        )
    assert first["observation_identity"] != second["observation_identity"]
    assert _value(second)["static_body_syntax"]["literal_dictionary_returns"][0][
        "literal_keys_in_source_order"
    ] == ["new"]


def test_denied_input_never_leaks_literal_keys(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text(
        '@app.get("/private")\ndef secret():\n    return {"SECRET_PRIVATE_KEY": 1}\n'
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "service.py"\nvisibility = "deny"\n'
    )
    with pytest.raises(RepositoryDeclarationProviderError) as failure:
        _observe(tmp_path)
    assert "SECRET_PRIVATE_KEY" not in str(failure.value)


@pytest.mark.parametrize("bad", [1, "yes", None])
def test_shape_opt_in_requires_boolean(bad: object) -> None:
    with pytest.raises(ValueError, match="boolean"):
        StaticPythonInterfaceDeclarations(
            paths=("service.py",),
            include_literal_shape_syntax=bad,  # type: ignore[arg-type]
        )
