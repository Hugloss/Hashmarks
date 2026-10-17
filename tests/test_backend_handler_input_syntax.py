"""B15-B19: qualified, request-local backend handler parameter evidence."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks.codemap import ChangeImpactOptions, CodeMap
from hashmarks.codemap.handler_input_syntax import MAX_HANDLER_PARAMETERS
from hashmarks.codemap.repository_declaration_provider import (
    RepositoryDeclarationProviderError,
)
from hashmarks.codemap.static_python_interface_declarations import (
    StaticPythonInterfaceDeclarations,
)
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation
from hashmarks.mcp_surface import HashmarksMcpSurface

PATH = "service.py"
TASK = "Change request handling for the backend route"


def _write(root: Path, content: str) -> None:
    (root / PATH).write_text(content, encoding="utf-8")


def _input(result: dict[str, object]) -> dict[str, object]:
    evidence = assert_object(result["changed_line_evidence"])
    observation = assert_records(evidence["observations"])[0]
    decorators = assert_object(observation["decorator_associations"])
    association = assert_records(decorators["associations"])[0]
    return assert_object(association["handler_input_context"])


def _declaration_value(result: dict[str, object]) -> dict[str, object]:
    declarations = assert_object(result["declarations"])
    group = assert_records(declarations["groups"])[0]
    return assert_object(assert_records(group["declarations"])[0]["value"])


def _change(cm: CodeMap) -> dict[str, object]:
    return cm.task_change_impact(
        TASK,
        [PATH],
        options=ChangeImpactOptions(
            changed_line_spans=[{"path": PATH, "start_line": 1, "end_line": 1}]
        ),
    )


def _provider(cm: CodeMap, *, enabled: bool) -> dict[str, object]:
    return cm.discover_repository_declarations(
        [
            StaticPythonInterfaceDeclarations(
                paths=(PATH,), include_input_contract_syntax=enabled
            )
        ]
    )


def _fixture() -> str:
    return (
        '@router.post("/items")\n'
        "async def handler(\n"
        "    payload: Payload,\n"
        "    actor: Annotated[str, Depends(authorize)],\n"
        "    *,\n"
        "    limit: int = Query(3, ge=1),\n"
        "    token: str | None = Header(default=None),\n"
        ") -> dict[str, int]:\n"
        "    return {'id': payload['id']}\n"
    )


def test_shared_input_oracle_and_default_declaration_identity(tmp_path: Path) -> None:
    _write(tmp_path, _fixture())
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        default = _provider(cm, enabled=False)
        explicit = _provider(cm, enabled=True)
        changed = _change(cm)
        plain = cm.task_change_impact(TASK, [PATH])
    base_value = _declaration_value(default)
    with_input = _declaration_value(explicit)
    assert "static_input_syntax" not in base_value
    assert with_input["static_input_syntax"] == _input(changed)
    assert "changed_line_evidence" not in plain
    assert changed["surfaces"] == plain["surfaces"]
    assert changed["changed"] == plain["changed"]
    input_syntax = _input(changed)
    assert input_syntax["state"] == "bounded-direct-handler-input-syntax"
    assert input_syntax["authority"] == "direct-static-syntax-only"
    assert input_syntax["coverage"] == "incomplete"
    assert input_syntax["parameters_observed"] == 4
    assert input_syntax["signature_source_range"] == {"start_line": 2, "end_line": 8}
    assert input_syntax["runtime_request_validation"] == "unknown"
    assert input_syntax["cross_artifact_correspondence"] == "unresolved"
    assert input_syntax["dependency_resolution"] == "not-established"
    assert input_syntax["negative_evidence_admissible"] is False
    params = assert_records(input_syntax["parameters"])
    assert [p["name"] for p in params] == ["payload", "actor", "limit", "token"]
    assert [p["kind"] for p in params] == [
        "positional-or-keyword",
        "positional-or-keyword",
        "keyword-only",
        "keyword-only",
    ]
    assert assert_object(params[0]["annotation"])["text"] == "Payload"
    assert (
        assert_object(params[1]["annotation"])["text"]
        == "Annotated[str, Depends(authorize)]"
    )
    meta = assert_object(params[1]["annotated_metadata"])
    assert meta["state"] == "direct-annotated-metadata-syntax"
    assert assert_records(meta["sites"])[0]["callee"] == {
        "state": "name-syntax",
        "name": "Depends",
    }
    assert assert_records(meta["sites"])[0]["first_argument_reference"] == {
        "state": "name-syntax",
        "name": "authorize",
    }
    assert assert_object(params[2]["default"])["callee"] == {
        "state": "name-syntax",
        "name": "Query",
    }
    assert assert_object(params[2]["default"])["keyword_names"] == ["ge"]
    assert assert_object(params[3]["default"])["callee"] == {
        "state": "name-syntax",
        "name": "Header",
    }
    assert assert_object(params[3]["default"])["keyword_names"] == ["default"]
    assert assert_object(input_syntax["return_annotation"])["text"] == "dict[str, int]"
    assert (
        validate_evidence_presentation(
            changed,
            present_repository_evidence(changed, format="compact"),
        )["valid"]
        is True
    )


def test_positional_defaults_and_keyword_kinds_are_not_inferred(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "@router.get('/items')\n"
        "def handler(a: str, /, b: int = 4, *items: str, "
        "flag: bool = False, **kwargs: object):\n"
        "    return None\n",
    )
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        result = _input(_change(cm))
    params = assert_records(result["parameters"])
    assert [x["kind"] for x in params] == [
        "positional-only",
        "positional-or-keyword",
        "variadic-positional",
        "keyword-only",
        "variadic-keyword",
    ]
    assert [assert_object(x["default"])["state"] for x in params] == [
        "not-supplied",
        "literal-kind-only",
        "not-supplied",
        "literal-kind-only",
        "not-supplied",
    ]
    assert assert_object(params[1]["default"])["kind"] == "integer"
    assert assert_object(params[3]["default"])["kind"] == "bool"
    assert result["negative_evidence_admissible"] is False


def test_default_literals_never_disclose_values_and_dynamic_stays_unknown(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "@router.get('/items')\n"
        "def handler(token: str = 'UNIQUE_SECRET_VALUE', "
        "service = resolver().service, "
        "actor = factory(*args, **kwargs)):\n"
        "    return None\n",
    )
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        result = _input(_change(cm))
    params = assert_records(result["parameters"])
    assert params[0]["default"] == {
        "state": "literal-kind-only",
        "kind": "string",
    }
    assert params[1]["default"] == {"state": "dynamic-or-unsupported"}
    assert assert_object(params[2]["default"])["state"] == "direct-call-syntax"
    assert assert_object(params[2]["default"])["has_argument_expansion"] is True
    assert "UNIQUE_SECRET_VALUE" not in str(result)


def test_annotated_unknown_metadata_keeps_scope_unresolved(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "@router.get('/items')\n"
        "def handler(value: Annotated[int, Depends(make_provider()), "
        "source, Unknown(3), Other(4), Extra(5)]):\n"
        "    return value\n",
    )
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        result = _input(_change(cm))
    sites = assert_object(assert_records(result["parameters"])[0]["annotated_metadata"])
    assert sites["observed_count"] == 5
    assert sites["omitted_count"] == 1
    assert assert_object(assert_records(sites["sites"])[0]["first_argument_reference"])[
        "state"
    ] == ("dynamic-or-unsupported")
    assert assert_records(sites["sites"])[1]["state"] == "dynamic-or-unsupported"
    assert sites["dependency_resolution"] == "not-established"


def test_overbound_signature_fails_selected_provider_but_not_change_impact(
    tmp_path: Path,
) -> None:
    parameters = ", ".join(f"p{i}: int" for i in range(MAX_HANDLER_PARAMETERS + 1))
    _write(
        tmp_path,
        f"@router.get('/items')\ndef handler({parameters}):\n    return None\n",
    )
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        with pytest.raises((ValueError, RepositoryDeclarationProviderError)):
            _provider(cm, enabled=True)
        result = _input(_change(cm))
    assert result["state"] == "unresolved"
    assert result["negative_evidence_admissible"] is False
    assert result["coverage"] == "unknown"


@pytest.mark.parametrize("flag", [None, 1, "true", [], {}])
def test_strict_opt_in_flag_rejected_before_source_reads(flag: object) -> None:
    with pytest.raises(ValueError, match="include_input_contract_syntax"):
        replace(
            StaticPythonInterfaceDeclarations(paths=(PATH,)),
            include_input_contract_syntax=flag,
        )


def test_decorated_class_cannot_claim_handler_parameters(tmp_path: Path) -> None:
    _write(tmp_path, "@router.get('/items')\nclass Handler:\n    pass\n")
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        result = _input(_change(cm))
    assert result["state"] == "not-a-function-declaration"
    assert result["coverage"] == "unknown"


def test_source_visibility_prevents_signature_literal_disclosure(
    tmp_path: Path,
) -> None:
    _write(tmp_path, _fixture())
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "service.py"\nvisibility = "outline"\n',
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        result = _change(cm)
    row = assert_records(
        assert_object(result["changed_line_evidence"])["observations"]
    )[0]
    assert row["state"] == "unresolved"
    assert "Annotated[str" not in str(row)


def test_mcp_full_packet_includes_input_syntax_without_new_tool(tmp_path: Path) -> None:
    _write(tmp_path, _fixture())
    surface = HashmarksMcpSurface(str(tmp_path))
    try:
        packet = surface.change_impact(
            TASK,
            [PATH],
            changed_line_spans=[{"path": PATH, "start_line": 1, "end_line": 1}],
        )
    finally:
        surface.close()
    parameters = assert_records(_input(packet)["parameters"])
    assert assert_object(parameters[1]["annotated_metadata"])["state"] == (
        "direct-annotated-metadata-syntax"
    )
