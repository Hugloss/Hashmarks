"""Caller-nominated Python interface pairing never invents runtime compatibility."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.repository_declaration_provider import (
    RepositoryDeclarationProviderError,
)
from hashmarks.codemap.static_python_interface_declarations import (
    StaticPythonInterfaceDeclarations,
)
from hashmarks.evidence_presentation import present_repository_evidence

PAIR = ("api.py", "serve", "client.py", "render", "response")


def _repo(root: Path) -> None:
    (root / "api.py").write_text(
        '@app.get("/users")\n'
        "def serve():\n"
        '    if flag:\n'
        '        return {"id": 1}\n'
        '    return {"name": "Sam", "age": 2}\n',
        encoding="utf-8",
    )
    (root / "client.py").write_text(
        "def render(response):\n"
        '    a = response["name"]\n'
        '    response["id"] = 7\n'
        '    other = payload["other"]\n'
        '    def nested():\n'
        '        return response["nested"]\n'
        '    return a\n',
        encoding="utf-8",
    )


def _provider(
    pairs: tuple[tuple[str, str, str, str, str], ...] = (PAIR,),
) -> StaticPythonInterfaceDeclarations:
    return StaticPythonInterfaceDeclarations(
        paths=("api.py", "client.py"), consumer_pairs=pairs
    )


def _observe(root: Path, provider: StaticPythonInterfaceDeclarations) -> dict:
    with CodeMap(root) as codemap:
        codemap.sync()
        return codemap.discover_repository_declarations([provider])


def _pair(packet: dict) -> dict:
    (group,) = [
        row for row in packet["declarations"]["groups"]
        if row["concept"]["kind"] == "nominated-python-interface-syntax-pair"
    ]
    return group


def test_b15_b18_pair_has_two_exact_bindings_but_no_compatibility_claim(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    packet = _observe(tmp_path, _provider())
    group = _pair(packet)
    assert group["correspondence"]["state"] == "unresolved"
    assert group["comparison"]["state"] == "ambiguous"
    assert group["absence"]["state"] == "unknown"
    assert group["coverage"]["state"] == "incomplete"
    assert group["scope"] == {
        "producer_path": "api.py",
        "producer_function": "serve",
        "consumer_path": "client.py",
        "consumer_function": "render",
        "consumer_receiver_syntax": "response",
    }
    roles = {
        row["semantic_role"]["kind"]: row for row in group["declarations"]
    }
    producer = roles["producer-return-syntax"]
    consumer = roles["consumer-subscript-read-syntax"]
    returns = producer["value"]["literal_dictionary_returns"]
    assert [row["literal_keys_in_source_order"] for row in returns] == [
        ["id"], ["name", "age"]
    ]
    reads = consumer["value"]["literal_subscript_reads"]
    assert [(row["receiver_syntax"], row["literal_key"]) for row in reads] == [
        ("response", "name")
    ]
    assert consumer["value"]["runtime_consumer_binding"] == "unknown"
    assert producer["value"]["runtime_response_shape"] == "unknown"
    assert all(row["evidence_state"] == "known-present" for row in roles.values())
    assert all(
        row["semantic_value_authority"] == "provider-claimed"
        for row in roles.values()
    )
    assert packet["execution_effect"]["hashmarks"] == "none"
    projected = present_repository_evidence(
        packet["declarations"], format="compact"
    )
    assert projected["supported"] is True


def test_consumer_alias_is_not_inferred_from_other_receiver(tmp_path: Path) -> None:
    _repo(tmp_path)
    packet = _observe(
        tmp_path,
        _provider((("api.py", "serve", "client.py", "render", "alias"),)),
    )
    group = _pair(packet)
    consumer = next(
        row for row in group["declarations"]
        if row["declaration_id"] == "consumer-subscript-read-syntax"
    )
    assert consumer["value"]["literal_subscript_reads"] == []
    assert group["comparison"]["state"] == "ambiguous"
    assert group["absence"]["state"] == "unknown"


def test_missing_consumer_never_creates_a_pair_or_negative_claim(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    packet = _observe(
        tmp_path,
        _provider((("api.py", "serve", "client.py", "missing", "response"),)),
    )
    assert not [
        group for group in packet["declarations"]["groups"]
        if group["concept"]["kind"] == "nominated-python-interface-syntax-pair"
    ]
    unresolved = packet["providers"][0]["provenance"]["unresolved_consumer_pairs"]
    assert unresolved == [
        {
            "pair": ["api.py", "serve", "client.py", "missing", "response"],
            "reason": "source-or-subject-unresolved",
        }
    ]


def test_duplicate_consumer_function_is_ambiguous_not_first_match(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with (tmp_path / "client.py").open("a", encoding="utf-8") as out:
        out.write("\ndef render(response):\n    return response['id']\n")
    packet = _observe(tmp_path, _provider())
    assert packet["providers"][0]["provenance"]["unresolved_consumer_pairs"]
    assert not [
        g for g in packet["declarations"]["groups"]
        if g["concept"]["kind"] == "nominated-python-interface-syntax-pair"
    ]


def test_undecorated_producer_does_not_masquerade_as_route(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    (tmp_path / "api.py").write_text(
        'def serve():\n    return {"name": "Sam"}\n', encoding="utf-8"
    )
    packet = _observe(tmp_path, _provider())
    assert packet["providers"][0]["provenance"]["unresolved_consumer_pairs"][
        0
    ]["reason"] == "producer-decorator-unresolved"


def test_opt_out_preserves_existing_declaration_evidence(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        default = cm.discover_repository_declarations(
            [StaticPythonInterfaceDeclarations(paths=("api.py", "client.py"))]
        )
        explicitly_empty = cm.discover_repository_declarations(
            [_provider(())]
        )
    assert default == explicitly_empty
    assert "consumer_pairs" not in default["providers"][0]["provenance"]


def test_order_does_not_change_pair_identity_and_mutation_changes_observation(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    pairs = (
        PAIR,
        ("api.py", "serve", "client.py", "render", "payload"),
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        first = cm.discover_repository_declarations([_provider(pairs)])
        second = cm.discover_repository_declarations([_provider(tuple(reversed(pairs)))])
        assert first["observation_identity"] == second["observation_identity"]
        source = tmp_path / "client.py"
        source.write_text(source.read_text().replace('response["name"]', 'response["age"]'))
        cm.sync(["client.py"])
        changed = cm.discover_repository_declarations(
            [_provider(pairs)], previous_observation=first
        )
    assert changed["observation_identity"] != first["observation_identity"]
    groups = [
        row for row in changed["declarations"]["groups"]
        if row["concept"]["kind"] == "nominated-python-interface-syntax-pair"
    ]
    consumer = next(
        row for row in groups[1]["declarations"]
        if row["declaration_id"] == "consumer-subscript-read-syntax"
    )
    assert consumer["value"]["literal_subscript_reads"][0]["literal_key"] == "age"


@pytest.mark.parametrize(
    "pairs",
    [
        (("unselected.py", "serve", "client.py", "render", "response"),),
        (("api.py", "serve", "client.py", "render", "not valid"),),
        (("api.py", "serve", "client.py", "render"),),
        (PAIR, PAIR),
        tuple(
            ("api.py", "serve", "client.py", f"render_{i}", "response")
            for i in range(17)
        ),
        (["api.py", "serve", "client.py", "render", "response"],),
    ],
)
def test_invalid_nominations_fail_before_provider_reads(pairs: object) -> None:
    with pytest.raises(ValueError, match="consumer_pairs"):
        StaticPythonInterfaceDeclarations(
            paths=("api.py", "client.py"),
            consumer_pairs=pairs,  # type: ignore[arg-type]
        )


def test_bounded_consumer_syntax_fails_closed_instead_of_false_empty(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    (tmp_path / "client.py").write_text(
        "def render(response):\n"
        + "".join(f'    response["field_{i}"]\n' for i in range(17)),
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        with pytest.raises(RepositoryDeclarationProviderError, match="bound"):
            cm.discover_repository_declarations([_provider()])
