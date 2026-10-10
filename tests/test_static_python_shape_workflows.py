"""Real handler edits, lifecycle and agent projections without runtime imports."""

from __future__ import annotations

from copy import deepcopy
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
from hashmarks.evidence_presentation import FORMATS, presentation_response

_API_SOURCE = (
    'raise RuntimeError("café source must not execute")\n'
    "@router.get(\n"
    '    path="/användare"\n'
    ")\n"
    "async def user(payload):\n"
    "    return {\n"
    '        "id": payload["id"],\n'
    '        "name": payload["name"],\n'
    "    }\n"
)
_TOOL_SOURCE = (
    '@mcp.tool(name="lookup_user")\n'
    "def lookup(result):\n"
    "    return {\n"
    '        "user": result["name"],\n'
    "    }\n"
)


def _materialize(root: Path) -> None:
    root.mkdir()
    (root / "api.py").write_bytes(_API_SOURCE.replace("\n", "\r\n").encode("utf-8"))
    (root / "tools.py").write_text(_TOOL_SOURCE, encoding="utf-8")


def _provider(
    paths: tuple[str, ...] = ("api.py", "tools.py"), *, include: bool = True
) -> StaticPythonInterfaceDeclarations:
    return StaticPythonInterfaceDeclarations(
        paths=paths, include_literal_shape_syntax=include
    )


def _group(packet: dict[str, Any], path: str) -> dict[str, Any]:
    return next(
        group
        for group in packet["declarations"]["groups"]
        if group["scope"]["path"] == path
    )


def _body(group: dict[str, Any]) -> dict[str, Any]:
    return group["declarations"][0]["value"]["static_body_syntax"]


def _binding(packet: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    binding_id = group["declarations"][0]["binding_id"]
    return next(
        row
        for row in packet["declarations"]["repository_evidence"]["bindings"]
        if row["binding_id"] == binding_id
    )


def _assert_unknown(packet: dict[str, Any]) -> None:
    assert len(packet["declarations"]["groups"]) == 2
    for group in packet["declarations"]["groups"]:
        body = _body(group)
        assert body["authority"] == "direct-static-syntax-only"
        assert body["coverage"] == "incomplete"
        assert body["runtime_response_shape"] == "unknown"
        assert body["cross_artifact_correspondence"] == "unresolved"
        assert group["coverage"]["state"] == "incomplete"
        assert group["correspondence"]["state"] == "unresolved"
        assert group["absence"]["state"] == "unknown"


def _assert_source_bound(
    packet: dict[str, Any], path: str, spans: set[tuple[int, int]]
) -> None:
    group = _group(packet, path)
    assert group["declarations"][0]["evidence_state"] == "known-present"
    evidence = _binding(packet, group)["evidence"]
    input_row = next(
        row for row in packet["providers"][0]["inputs"] if row["path"] == path
    )
    assert input_row["state"] == "known-present"
    assert input_row["member_revision"]
    assert {(row["start_line"], row["end_line"]) for row in evidence} == spans
    assert all(row["path"] == path for row in evidence)
    assert all(
        row["member_revision"] == input_row["member_revision"] for row in evidence
    )


@pytest.fixture
def handler_repository(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    _materialize(root)
    return root, tmp_path / "state"


@pytest.fixture(scope="module")
def handler_packet(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    fixture = tmp_path_factory.mktemp("handler-projection")
    root = fixture / "repo"
    _materialize(root)
    with CodeMap(root, state_dir=fixture / "state") as cm:
        cm.sync()
        return cm.discover_repository_declarations([_provider()])


def test_body_only_edit_has_exact_value_and_revision_deltas(
    handler_repository: tuple[Path, Path],
) -> None:
    root, state = handler_repository
    source = root / "api.py"
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        before: dict[str, Any] = cm.discover_repository_declarations([_provider()])
        snapshot = deepcopy(before)
        _assert_source_bound(before, "api.py", {(2, 5), (6, 9), (7, 7), (8, 8)})
        source.write_bytes(source.read_bytes().replace(b'"name":', b'"display_name":'))
        with pytest.raises(RepositoryDeclarationProviderError, match="input changed"):
            cm.discover_repository_declarations(
                [_provider()], previous_observation=before
            )
        cm.sync(["api.py"])
        after: dict[str, Any] = cm.discover_repository_declarations(
            [_provider()], previous_observation=before
        )
    old, new = _group(before, "api.py"), _group(after, "api.py")
    assert old["semantic_subject_identity"] == new["semantic_subject_identity"]
    assert (
        old["declarations"][0]["semantic_declaration_identity"]
        == new["declarations"][0]["semantic_declaration_identity"]
    )
    assert _body(new)["literal_dictionary_returns"][0][
        "literal_keys_in_source_order"
    ] == ["id", "display_name"]
    assert (
        _body(new)["literal_subscript_accesses"]
        == _body(old)["literal_subscript_accesses"]
    )
    assert _body(_group(before, "tools.py")) == _body(_group(after, "tools.py"))
    _assert_source_bound(after, "api.py", {(2, 5), (6, 9), (7, 7), (8, 8)})
    assert (
        _binding(before, old)["evidence"][0]["member_revision"]
        != _binding(after, new)["evidence"][0]["member_revision"]
    )
    delta = after["delta_from_previous"]["declarations"]
    changed = next(
        row for row in delta["changed_groups"] if row["group_id"] == new["group_id"]
    )
    assert changed["value_changed_declaration_ids"] == ["direct-decorator"]
    semantic = next(
        row
        for row in delta["semantic_subjects"]["changed"]
        if row["semantic_subject_identity"] == new["semantic_subject_identity"]
    )
    (transition,) = semantic["semantic_declarations"]["changed"]
    assert (
        transition["value_transition"]["before"]["value"]
        == old["declarations"][0]["value"]
    )
    assert (
        transition["value_transition"]["after"]["value"]
        == new["declarations"][0]["value"]
    )
    _assert_unknown(after)
    assert before == snapshot


def test_dynamic_return_cannot_reuse_previous_literal_keys(
    handler_repository: tuple[Path, Path],
) -> None:
    root, state = handler_repository
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        before: dict[str, Any] = cm.discover_repository_declarations([_provider()])
        snapshot = deepcopy(before)
        (root / "api.py").write_text(
            _API_SOURCE.split("    return {")[0]
            + '    return {**build_response(payload), "ok": True}\n',
            encoding="utf-8",
        )
        with pytest.raises(RepositoryDeclarationProviderError, match="input changed"):
            cm.discover_repository_declarations(
                [_provider()], previous_observation=before
            )
        cm.sync(["api.py"])
        after: dict[str, Any] = cm.discover_repository_declarations(
            [_provider()], previous_observation=before
        )
    assert _body(_group(after, "api.py"))["literal_dictionary_returns"] == [
        {
            "line": 6,
            "end_line": 6,
            "syntax": "unresolved-return",
            "literal_keys_in_source_order": None,
        }
    ]
    assert _body(_group(after, "api.py"))["literal_subscript_accesses"] == []
    _assert_source_bound(after, "api.py", {(2, 5), (6, 6)})
    _assert_unknown(after)
    assert before == snapshot


def test_rename_delete_reopen_and_opt_out_do_not_replay_handler_facts(
    handler_repository: tuple[Path, Path],
) -> None:
    root, state = handler_repository
    selected = _provider(paths=("routes.py", "tools.py"))
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        before: dict[str, Any] = cm.discover_repository_declarations([_provider()])
        (root / "api.py").rename(root / "routes.py")
        cm.sync(["api.py", "routes.py"])
        renamed: dict[str, Any] = cm.discover_repository_declarations(
            [_provider(paths=("api.py", "routes.py", "tools.py"))],
            previous_observation=before,
        )
        assert renamed["providers"][0]["provenance"]["missing_selected_paths"] == [
            "api.py"
        ]
        assert {row["scope"]["path"] for row in renamed["declarations"]["groups"]} == {
            "routes.py",
            "tools.py",
        }
        _assert_source_bound(renamed, "routes.py", {(2, 5), (6, 9), (7, 7), (8, 8)})
    with CodeMap(root, state_dir=state) as cm:
        reopened: dict[str, Any] = cm.discover_repository_declarations(
            [selected], previous_observation=before
        )
        current: dict[str, Any] = cm.discover_repository_declarations([selected])
        assert current["observation_identity"] == reopened["observation_identity"]
        assert _body(_group(current, "routes.py")) == _body(_group(before, "api.py"))
        _assert_unknown(current)
        empty: dict[str, Any] = cm.discover_repository_declarations(
            [], previous_observation=before
        )
        assert empty["declarations"]["groups"] == []
        default: dict[str, Any] = cm.discover_repository_declarations(
            [_provider(paths=("routes.py", "tools.py"), include=False)],
            previous_observation=before,
        )
        assert all(
            "static_body_syntax" not in group["declarations"][0]["value"]
            for group in default["declarations"]["groups"]
        )
        assert (
            cm.discover_repository_declarations([selected])["observation_identity"]
            == current["observation_identity"]
        )
        (root / "routes.py").unlink()
        (root / "tools.py").unlink()
        cm.sync(["routes.py", "tools.py"])
        deleted: dict[str, Any] = cm.discover_repository_declarations(
            [selected], previous_observation=before
        )
        assert deleted["declarations"]["groups"] == []
        assert all(
            row["state"] == "known-absent" for row in deleted["providers"][0]["inputs"]
        )
    with CodeMap(root, state_dir=state) as cm:
        final: dict[str, Any] = cm.discover_repository_declarations([selected])
        assert final["declarations"]["groups"] == []


@pytest.mark.parametrize("format", FORMATS)
def test_handler_agent_formats_preserve_exact_claims_and_uncertainty(
    handler_packet: dict[str, Any], format: str
) -> None:
    snapshot = deepcopy(handler_packet)
    _assert_unknown(handler_packet)
    native = handler_packet["declarations"]
    response: dict[str, Any] = presentation_response(
        "repository_declarations", native, format=format, result_mode="observation"
    )
    if format == "none":
        assert response == native
    else:
        assert response["result"] == native
        projection = response["presentation"]
        assert projection["coverage"] == "projection-only"
        findings = [row for group in projection["groups"] for row in group["findings"]]
        claims = [
            row
            for row in findings
            if row["source_refs"] in [["/groups/0"], ["/groups/1"]]
        ]
        assert len(claims) == 2
        for claim in claims:
            index = int(claim["source_refs"][0].rsplit("/", 1)[1])
            assert claim["details"] == native["groups"][index]
            assert claim["assertion"] == "producer_claim"
            assert _body(claim["details"])["runtime_response_shape"] == "unknown"
            assert (
                _body(claim["details"])["cross_artifact_correspondence"] == "unresolved"
            )
        if format == "text":
            for detail in (
                '"runtime_response_shape":"unknown"',
                '"cross_artifact_correspondence":"unresolved"',
                '"coverage":"incomplete"',
                "/användare",
                "lookup_user",
            ):
                assert detail in projection["text"]
    assert handler_packet == snapshot
