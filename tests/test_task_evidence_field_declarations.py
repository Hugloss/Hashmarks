"""Literal source paths disclose declared defaults without runtime authority."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from contract_assertions import assert_integer, assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.static_python_backend_declarations import (
    StaticPythonBackendDeclarations,
)
from hashmarks.codemap.task_evidence_contract import (
    read_initial_projection,
    read_task_evidence,
)
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_packet,
    encode_initial_packet,
    initial_packet_identity,
)
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import FORMATS, presentation_response

TASK = "Default provider configuration in settings.py constructs a separate provider."


def _repository(root: Path, *, provider: str = "build_provider") -> None:
    (root / "settings.py").write_text(
        "from declarations import Field\n"
        "from providers import build_provider, shared_provider\n\n"
        "class Settings:\n"
        f"    provider: object = Field(default_factory={provider})\n"
    )
    (root / "providers.py").write_text(
        "def build_provider(): return object()\nshared_provider = object()\n"
    )
    (root / "declarations.py").write_text("def Field(**options): return options\n")


def _context(packet: Mapping[str, object]) -> dict[str, object]:
    if "encoding" in packet:
        packet = decode_initial_packet(packet)
    retrieval = cast("dict[str, object]", packet["retrieval"])
    rows = cast("list[dict[str, object]]", retrieval["results"])
    return cast(
        "dict[str, object]",
        next(row for row in rows if row["path"] == "settings.py")["field_declarations"],
    )


def _larger_declaration_file(root: Path) -> None:
    (root / "settings.py").write_text(
        "from declarations import Field\n"
        "from providers import build_provider\n"
        "class DeclarationRecord:\n"
        "    original: object\n    wrapped: object\n    reference: object\n"
        "class Settings:\n"
        "    enabled: bool = False\n"
        "    provider: object = Field(default_factory=build_provider)\n"
        "    serializer: object = Field(default_factory=object)\n"
        "    context: object = Field(default_factory=build_provider)\n"
        "    decorators: list = ()\n    get_dependency: object = None\n"
    )


@pytest.mark.parametrize("mode", ["default", "initial"])
@pytest.mark.parametrize("limit", [1, 3, 20])
def test_literal_file_exposes_declared_default_without_changing_authority(
    tmp_path: Path, mode: str, limit: int
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        action = repository.tasks.action_map(TASK, limit=limit)
        packet = repository.tasks.evidence(TASK, result_mode=mode, limit=limit)
    logical = (
        read_initial_projection(decode_initial_packet(packet))
        if mode == "initial"
        else read_task_evidence(packet)
    )
    context = _context(packet)
    assert context["state"] == "observed"
    assert context["ownership_authority"] is False
    assert context["negative_evidence_admissible"] is False
    assert (
        context["source_revision"]
        == hash_file(tmp_path / "settings.py", domain=FILE_DOMAIN).hash
    )
    groups = cast("list[dict[str, object]]", context["groups"])
    assert len(groups) == 1
    value = cast("dict[str, object]", groups[0]["value"])
    assert value["runtime_binding"] == "not-established"
    assert value["inherited_fields"] == "not-established"
    assert value["coverage"] == "incomplete"
    fields = cast("list[dict[str, object]]", value["fields"])
    assert fields[0]["name"] == "provider"
    assert (fields[0]["line"], fields[0]["end_line"]) == (5, 5)
    default = cast("dict[str, object]", fields[0]["default"])
    assert default["keyword_references"] == [
        {
            "keyword": "default_factory",
            "reference": {"state": "name-syntax", "name": "build_provider"},
        }
    ]
    owner = logical["ownership"]["owner"]
    admitted_owner = action["admitted_edit"]
    assert owner is not None and admitted_owner is not None
    for key in ("path", "qualname", "start_line", "end_line"):
        assert owner.get(key) == admitted_owner.get(key)
    assert (
        logical["ownership"]["authority_proof_identity"]
        == (action["ownership_authority"]["authority_proof_identity"])
    )
    assert (
        logical["ownership"]["ambiguity"]["ambiguous"]
        == (action["ambiguity"]["ambiguous"])
    )
    selected = logical["verification"]["selected"]
    admitted = action["verify"]
    assert (selected or {}).get("path") == (admitted or {}).get("path")
    for format in FORMATS:
        response = presentation_response(
            "task_evidence", packet, result_mode=mode, format=format
        )
        native = cast("dict[str, object]", response.get("result", response))
        assert _context(native) == context
        if format != "none":
            assert "default_factory" in json.dumps(response["presentation"])


@pytest.mark.parametrize("visibility", ["deny", "outline"])
def test_declared_defaults_require_source_visibility(
    tmp_path: Path, visibility: str
) -> None:
    _repository(tmp_path)
    (tmp_path / ".hashmarks-context.toml").write_text(
        f'[[rule]]\npattern = "settings.py"\nvisibility = "{visibility}"\n'
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence(TASK, result_mode="initial")
    assert "default_factory" not in json.dumps(decode_initial_packet(packet))


def test_reopened_configuration_does_not_replay_the_old_default(tmp_path: Path) -> None:
    _repository(tmp_path)
    state = tmp_path / ".hashmarks" / "state"
    with CodeMap(tmp_path, state_dir=state) as repository:
        repository.index.sync()
        before = _context(repository.tasks.evidence(TASK))
    _repository(tmp_path, provider="shared_provider")
    with CodeMap(tmp_path, state_dir=state) as repository:
        after = _context(repository.tasks.evidence(TASK, result_mode="initial"))
    assert before["source_revision"] != after["source_revision"]
    assert "build_provider" not in json.dumps(after)
    assert "shared_provider" in json.dumps(after)


def test_field_group_bound_preserves_explicit_omissions_and_unknown_absence(
    tmp_path: Path,
) -> None:
    (tmp_path / "settings.py").write_text(
        "".join(f"class Config{i}:\n    field{i}: int = {i}\n" for i in range(5))
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        context = _context(repository.tasks.evidence(TASK, result_mode="initial"))
    assert (context["observed"], context["returned"], context["omitted"]) == (5, 3, 2)
    assert context["coverage"] == "incomplete"
    assert context["negative_evidence_admissible"] is False
    assert all(
        assert_object(group["absence"])["state"] == "unknown"
        for group in assert_records(context["groups"])
    )


def test_provider_bound_failure_is_incomplete_disclosure_not_absent_fields(
    tmp_path: Path,
) -> None:
    (tmp_path / "settings.py").write_text(
        "class Settings:\n" + "".join(f"    field{i}: int = {i}\n" for i in range(25))
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence(TASK, result_mode="initial")
    context = _context(packet)
    assert context["state"] == "unavailable"
    assert context["coverage"] == "incomplete"
    assert context["negative_evidence_admissible"] is False
    assert "groups" not in context
    assert "observed" not in context


def test_empty_syntax_observation_does_not_establish_field_absence(
    tmp_path: Path,
) -> None:
    (tmp_path / "settings.py").write_text("class Settings:\n    pass\n")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence(TASK)
    assert all(
        "field_declarations" not in row for row in packet["retrieval"]["results"]
    )
    assert packet["retrieval"]["ownership_authority"] is False


def test_task_fields_retain_canonical_declaration_values_and_qualifiers(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        discovery = repository.declarations.discover(
            [
                StaticPythonBackendDeclarations(
                    paths=("settings.py",),
                    include_model_fields=False,
                    include_environment_reads=False,
                    include_class_fields=True,
                )
            ]
        )
        context = _context(repository.tasks.evidence(TASK))
    assert context["repository"] == discovery["repository"]
    assert context["discovery_identity"] == discovery["observation_identity"]
    canonical = assert_records(assert_object(discovery["declarations"])["groups"])[0]
    actual = assert_records(context["groups"])[0]
    declaration = assert_records(canonical["declarations"])[0]
    for key in (
        "value",
        "value_state",
        "semantic_value_authority",
        "evidence_state",
        "producer",
    ):
        assert actual[key] == declaration[key]
    for key in ("scope", "coverage", "correspondence", "absence"):
        assert actual[key] == canonical[key]


def test_initial_fields_preserve_target_syntax_and_account_for_other_fields(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    _larger_declaration_file(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        full = repository.tasks.evidence(TASK)
        wire = repository.tasks.evidence(TASK, result_mode="initial")
    initial = decode_initial_packet(wire)
    all_fields = [
        field
        for group in assert_records(_context(full)["groups"])
        for field in assert_records(assert_object(group["value"])["fields"])
    ]
    displayed = [
        field
        for group in assert_records(_context(wire)["groups"])
        for field in assert_records(assert_object(group["value"])["fields"])
    ]
    assert len(all_fields) == 9
    assert displayed == [field for field in all_fields if field["name"] == "provider"]
    omissions = assert_object(assert_object(initial["initial_projection"])["omissions"])
    collections = assert_object(omissions["collections"])
    field_bounds = [
        assert_object(value)
        for path, value in collections.items()
        if "/field_declarations/" in path and path.endswith("/fields")
    ]
    assert sum(assert_integer(bound["omitted"]) for bound in field_bounds) == 8
    assert _context(wire)["negative_evidence_admissible"] is False


def _pointer(value: object, pointer: str) -> object:
    for part in pointer.lstrip("/").split("/") if pointer else []:
        key = part.replace("~1", "/").replace("~0", "~")
        value = (
            value[int(key)] if isinstance(value, list) else assert_object(value)[key]
        )
    return value


def _read_field_scope(
    native: Mapping[str, object], view: Mapping[str, object], base: str
) -> dict[str, object]:
    result = deepcopy(assert_object(_pointer(native, base + str(view["metadata_ref"]))))
    for key, value in view.items():
        if key in {"metadata_ref", "metadata_ref_base"}:
            continue
        if key == "groups":
            result[key] = [
                _read_field_scope(native, group, base)
                for group in assert_records(value)
            ]
        elif key == "value":
            result[key] = _read_field_scope(native, assert_object(value), base)
        else:
            result[key] = deepcopy(value)
    return result


@pytest.mark.parametrize("format", ["compact", "text"])
def test_field_display_recovers_all_native_qualifiers_and_future_metadata(
    tmp_path: Path, format: str
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        logical = decode_initial_packet(
            repository.tasks.evidence(TASK, result_mode="initial")
        )
    context = _context(logical)
    context["future/key~"] = {"false": False, "zero": 0, "unknown": None}
    groups = assert_records(context["groups"])
    groups[0]["future_qualification"] = False
    assert_object(groups[0]["value"])["future_qualification"] = 0
    logical["evidence_packet_identity"] = initial_packet_identity(logical)
    response = presentation_response(
        "task_evidence",
        encode_initial_packet(logical),
        result_mode="initial",
        format=format,
    )
    projection = assert_object(response["presentation"])
    if format == "compact":
        group = next(
            group
            for group in assert_records(projection["groups"])
            if group["family"] == "retrieval_evidence"
        )
        finding = next(
            finding
            for finding in assert_records(group["findings"])
            if "field_declarations" in assert_object(finding["details"])
        )
        view = assert_object(assert_object(finding["details"])["field_declarations"])
    else:
        line = next(
            line
            for line in str(projection["text"]).splitlines()
            if line.startswith("Declared field syntax @ ")
        )
        view = assert_object(json.loads(line.partition(": ")[2]))
    assert _read_field_scope(logical, view, str(view["metadata_ref_base"])) == context
    assert "default_factory" in json.dumps(view)
    assert decode_initial_packet(assert_object(response["result"])) == logical


@pytest.mark.parametrize(
    "transport", ["cli", pytest.param("mcp", marks=pytest.mark.host_mcp_sdk)]
)
def test_initial_field_syntax_survives_real_transports(
    tmp_path: Path, transport: str
) -> None:
    from scripts.repository_evaluation.backend_transport import capture_cli, capture_mcp

    _repository(tmp_path)
    _larger_declaration_file(tmp_path)
    state = tmp_path / ".hashmarks"
    with CodeMap(tmp_path, state_dir=state) as repository:
        repository.index.sync()
        expected = _context(repository.tasks.evidence(TASK, result_mode="initial"))
    case = {
        "operation": "task_evidence",
        "inputs": {"task": TASK, "result_mode": "initial"},
    }
    capture = capture_cli if transport == "cli" else capture_mcp
    observations = capture(tmp_path, state, case)
    assert len(observations) == len(FORMATS)
    for observation in observations:
        response = observation["response"]
        assert _context(response.get("result", response)) == expected
        if observation["format"] != "none":
            assert "default_factory" in observation["consumer_visible_response"]
        if observation["format"] in {"compact", "text"}:
            assert observation["estimated_tokens"] <= 4000
