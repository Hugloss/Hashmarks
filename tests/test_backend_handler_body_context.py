"""B11-B14: backend handler body facts are direct, bounded and revision-bound."""

from __future__ import annotations

import json
from pathlib import Path

from hashmarks.codemap import ChangeImpactOptions, CodeMap
from hashmarks.codemap.static_python_interface_declarations import (
    StaticPythonInterfaceDeclarations,
)
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation
from hashmarks.mcp_surface import HashmarksMcpSurface

PATH = "service.py"
TASK = "Change the backend handler's route declaration"


def _change(cm: CodeMap) -> dict[str, object]:
    return cm.task_change_impact(
        TASK,
        [PATH],
        options=ChangeImpactOptions(
            changed_line_spans=[{"path": PATH, "start_line": 1, "end_line": 1}]
        ),
    )


def _association(result: dict[str, object]) -> dict[str, object]:
    return result["changed_line_evidence"]["observations"][0]["decorator_associations"][
        "associations"
    ][0]


def test_body_context_reuses_existing_provider_oracle_and_exact_index(
    tmp_path: Path,
) -> None:
    (tmp_path / PATH).write_text(
        '@router.post("/items")\n'
        "async def handler(payload: dict[str, int]):\n"
        '    identifier = payload["id"]\n'
        '    return {"id": identifier, "ok": payload["ok"]}\n',
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        plain = cm.task_change_impact(TASK, [PATH])
        augmented = _change(cm)
        provider = cm.discover_repository_declarations(
            [
                StaticPythonInterfaceDeclarations(
                    paths=(PATH,), include_literal_shape_syntax=True
                )
            ]
        )
    assert "changed_line_evidence" not in plain
    assert augmented["changed"] == plain["changed"]
    assert augmented["surfaces"] == plain["surfaces"]
    assert augmented["changed_line_evidence"]["observations"][0]["symbols"] == []
    association = _association(augmented)
    assert association["subject"] == "service.py::handler"
    assert association["indexed_declaration_signature"] == {
        "state": "indexed-declaration",
        "value": "async def handler(payload: dict[str, int])",
    }
    body = association["handler_body_context"]
    assert body["state"] == "bounded-direct-handler-body-syntax"
    assert body["authority"] == "direct-static-syntax-only"
    assert body["declaration_syntax"] == "async"
    assert body["coverage"] == "incomplete"
    assert body["runtime_response_shape"] == "unknown"
    assert body["cross_artifact_correspondence"] == "unresolved"
    assert body["negative_evidence_admissible"] is False
    expected = provider["declarations"]["groups"][0]["declarations"][0]["value"][
        "static_body_syntax"
    ]
    assert body["literal_dictionary_returns"] == expected["literal_dictionary_returns"]
    assert body["literal_subscript_accesses"] == expected["literal_subscript_accesses"]
    assert body["return_sites_observed"] == 1
    assert body["subscript_sites_observed"] == 2
    assert (
        validate_evidence_presentation(
            augmented, present_repository_evidence(augmented, format="compact")
        )["valid"]
        is True
    )


def test_body_context_excludes_nested_scopes_and_preserves_dynamic_returns(
    tmp_path: Path,
) -> None:
    (tmp_path / PATH).write_text(
        "@auth.required\n"
        "def handler(payload):\n"
        "    def nested(data):\n"
        '        return {"secret": data["secret"]}\n'
        "    return nested(payload)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        body = _association(_change(cm))["handler_body_context"]
    assert body["literal_dictionary_returns"] == [
        {
            "line": 5,
            "end_line": 5,
            "syntax": "unresolved-return",
            "literal_keys_in_source_order": None,
        }
    ]
    assert body["literal_subscript_accesses"] == []
    assert body["negative_evidence_admissible"] is False


def test_body_context_bounded_sites_and_explicit_omission(
    tmp_path: Path,
) -> None:
    source = '@router.post("/items")\ndef handler(payload):\n'
    source += "".join(
        f'    if payload["k{n}"]:\n        return {{"key{n}": {n}}}\n'
        for n in range(12)
    )
    source += '    return {"fallback": True}\n'
    (tmp_path / PATH).write_text(source, encoding="utf-8")
    with CodeMap(tmp_path) as cm:
        cm.sync()
        body = _association(_change(cm))["handler_body_context"]
    assert body["state"] == "bounded-direct-handler-body-syntax"
    assert body["return_sites_observed"] == 13
    assert len(body["literal_dictionary_returns"]) == 8
    assert body["return_sites_omitted"] == 5
    assert body["subscript_sites_observed"] == 12
    assert len(body["literal_subscript_accesses"]) == 8
    assert body["subscript_sites_omitted"] == 4
    assert body["negative_evidence_admissible"] is False


def test_body_site_overflow_degrades_locally_without_dropping_handler(
    tmp_path: Path,
) -> None:
    source = "@auth.required\ndef handler(payload):\n"
    source += "".join(
        f"    if payload == {n}:\n        return {{'key': {n}}}\n" for n in range(17)
    )
    (tmp_path / PATH).write_text(source, encoding="utf-8")
    with CodeMap(tmp_path) as cm:
        cm.sync()
        association = _association(_change(cm))
    assert association["subject"] == "service.py::handler"
    assert association["decorator_context"]["state"] == (
        "bounded-current-python-ast-decorator-syntax"
    )
    assert association["handler_body_context"] == {
        "state": "unresolved",
        "reason": "handler-body-syntax-over-bound-or-unavailable",
        "coverage": "unknown",
        "negative_evidence_admissible": False,
    }


def test_decorated_class_does_not_become_a_function_response_oracle(
    tmp_path: Path,
) -> None:
    (tmp_path / PATH).write_text(
        "@register\nclass Handler:\n    def run(self):\n        return {'x': 1}\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        association = _association(_change(cm))
    assert association["subject"] == "service.py::Handler"
    assert association["handler_body_context"]["state"] == "not-a-function-declaration"
    assert association["handler_body_context"]["negative_evidence_admissible"] is False


def test_handler_body_literals_never_exposed_under_restricted_visibility(
    tmp_path: Path,
) -> None:
    (tmp_path / PATH).write_text(
        '@router.post("/private")\n'
        "def handler(payload):\n"
        '    return {"secret_return_key": payload["secret_access_key"]}\n',
        encoding="utf-8",
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "service.py"\nvisibility = "outline"\n',
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        impact = _change(cm)
    assert "secret_return_key" not in json.dumps(impact)
    assert "secret_access_key" not in json.dumps(impact)
    assert "/private" not in json.dumps(impact)
    observation = impact["changed_line_evidence"]["observations"][0]
    assert observation.get("decorator_associations", {}).get("associations", []) == []


def test_mcp_handler_body_observation_tracks_current_source_revision(
    tmp_path: Path,
) -> None:
    source = tmp_path / PATH
    source.write_text(
        '@router.post("/items")\n'
        "def handler(payload):\n"
        '    return {"before": payload["id"]}\n',
        encoding="utf-8",
    )
    surface = HashmarksMcpSurface(str(tmp_path))
    try:
        spans = [{"path": PATH, "start_line": 1, "end_line": 1}]
        before = surface.change_impact(TASK, [PATH], changed_line_spans=spans)
        replay = surface.change_impact(TASK, [PATH], changed_line_spans=spans)
        source.write_text(
            '@router.post("/items")\n'
            "def handler(payload):\n"
            '    return {"after": payload["id"]}\n',
            encoding="utf-8",
        )
        after = surface.change_impact(TASK, [PATH], changed_line_spans=spans)
    finally:
        surface.close()

    def observed_key(packet: dict[str, object]) -> str:
        return _association(packet)["handler_body_context"][
            "literal_dictionary_returns"
        ][0]["literal_keys_in_source_order"][0]

    assert observed_key(before) == "before"
    assert observed_key(replay) == "before"
    assert observed_key(after) == "after"
    assert before["changed_line_evidence"] == replay["changed_line_evidence"]
    assert (
        before["changed_line_evidence"]["observations"][0]["member_revision"]
        != after["changed_line_evidence"]["observations"][0]["member_revision"]
    )
