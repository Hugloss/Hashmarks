"""B20-B24: selected Python schema/config syntax is source-bound, not runtime."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_declaration_provider import (
    RepositoryDeclarationProviderError,
)
from hashmarks.codemap.static_python_backend_declarations import (
    MAX_BACKEND_PATHS,
    MAX_MODEL_FIELDS,
    StaticPythonBackendDeclarations,
)

PATH = "service.py"


def _write(root: Path, source: str, *, path: str = PATH) -> None:
    (root / path).write_text(source, encoding="utf-8")


def _observe(root: Path, provider: StaticPythonBackendDeclarations) -> dict:
    with CodeMap(root) as cm:
        cm.sync()
        return cm.discover_repository_declarations([provider])


def _groups(packet: dict) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for group in packet["declarations"]["groups"]:
        groups.setdefault(group["concept"]["kind"], []).append(group)
    return groups


def _value(group: dict) -> dict:
    return group["declarations"][0]["value"]


def test_bounded_model_field_syntax_reuses_canonical_declaration_authority(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "from pydantic import BaseModel, Field\n"
        "class Payload(BaseModel):\n"
        "    id: int\n"
        "    display_name: str = Field(default='private', min_length=2)\n"
        "    enabled: bool = False\n"
        "    computed = lambda: 'not-a-field'\n"
        "class Service:\n"
        "    accidental: str = 'not-a-model'\n",
    )
    packet = _observe(tmp_path, StaticPythonBackendDeclarations(paths=(PATH,)))
    groups = _groups(packet)
    assert set(groups) == {"python-model-class-syntax"}
    group = groups["python-model-class-syntax"][0]
    assert group["correspondence"]["state"] == "unresolved"
    assert group["absence"]["state"] == "unknown"
    assert group["coverage"]["state"] == "incomplete"
    value = _value(group)
    assert value["model_identity"] == "not-established"
    assert value["field_requiredness"] == "unknown"
    assert value["schema_compatibility"] == "not-established"
    assert value["negative_evidence_admissible"] is False
    assert [row["name"] for row in value["fields"]] == ["id", "display_name", "enabled"]
    assert value["fields"][0]["annotation"]["text"] == "int"
    assert value["fields"][0]["default"]["state"] == "not-supplied"
    assert value["fields"][1]["default"]["state"] == "direct-call-syntax"
    assert value["fields"][1]["default"]["callee"] == {
        "state": "name-syntax",
        "name": "Field",
    }
    assert value["fields"][1]["default"]["keyword_names"] == ["default", "min_length"]
    assert value["fields"][2]["default"] == {
        "state": "literal-kind-only",
        "kind": "bool",
    }
    assert "private" not in str(value)
    assert group["declarations"][0]["evidence_state"] == "known-present"
    assert group["declarations"][0]["semantic_value_authority"] == ("provider-claimed")


def test_environment_key_reads_not_runtime_resolution_and_no_secret_defaults(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "import os\n"
        "ENV = os.getenv('API_TOKEN', 'NEVER_COPY_THIS_SECRET')\n"
        "timeout = os.environ.get('TIMEOUT', 30)\n"
        "flag = os.environ['FLAG']\n"
        "dynamic = os.getenv(make_key(), *extra)\n"
        "os = arbitrary_object()\n"
        "shadowed = os.getenv('SHADOWED')\n",
    )
    packet = _observe(
        tmp_path,
        StaticPythonBackendDeclarations(paths=(PATH,), include_model_fields=False),
    )
    values = [_value(group) for group in _groups(packet)["python-env-access-syntax"]]
    assert len(values) == 5
    assert [row["callee_syntax"] for row in values] == [
        "os.getenv",
        "os.environ.get",
        "os.environ[...]",
        "os.getenv",
        "os.getenv",
    ]
    assert values[0]["direct_assignment_names"] == ["ENV"]
    assert values[1]["direct_assignment_names"] == ["timeout"]
    assert values[4]["runtime_assignment_binding"] == "not-established"
    assert values[0]["key"] == {"state": "literal-key-syntax", "value": "API_TOKEN"}
    assert values[0]["default"] == {"state": "literal-kind-only", "kind": "string"}
    assert values[1]["default"] == {"state": "literal-kind-only", "kind": "integer"}
    assert values[2]["default"]["state"] == "not-supplied"
    assert values[3]["key"]["state"] == "dynamic-or-unsupported"
    assert values[3]["has_argument_expansion"] is True
    assert values[4]["runtime_binding"] == "not-established"
    assert "NEVER_COPY_THIS_SECRET" not in str(packet)
    assert all(row["negative_evidence_admissible"] is False for row in values)


def test_missing_selected_file_does_not_prove_absent_config(tmp_path: Path) -> None:
    _write(tmp_path, "import os\nvalue = os.getenv('A')\n")
    packet = _observe(
        tmp_path,
        StaticPythonBackendDeclarations(paths=(PATH, "missing.py")),
    )
    assert packet["providers"][0]["provenance"]["missing_selected_paths"] == [
        "missing.py"
    ]
    assert all(
        group["absence"]["state"] == "unknown"
        for group in packet["declarations"]["groups"]
    )


def test_selected_source_revision_edit_changes_identity_without_reinterpreting(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "import os\nvalue = os.getenv('FIRST')\n")
    provider = StaticPythonBackendDeclarations(paths=(PATH,))
    with CodeMap(tmp_path) as cm:
        cm.sync()
        before = cm.discover_repository_declarations([provider])
        same = cm.discover_repository_declarations([provider])
        assert same["observation_identity"] == before["observation_identity"]
        _write(tmp_path, "import os\nvalue = os.getenv('SECOND')\n")
        cm.sync([PATH])
        after = cm.discover_repository_declarations(
            [provider], previous_observation=before
        )
    assert before["observation_identity"] != after["observation_identity"]
    assert _value(_groups(after)["python-env-access-syntax"][0])["key"]["value"] == (
        "SECOND"
    )


@pytest.mark.parametrize(
    "paths",
    [
        (),
        ("../private.py",),
        ("settings.yaml",),
        ("backend.py", "backend.py"),
        tuple(f"p{i}.py" for i in range(MAX_BACKEND_PATHS + 1)),
    ],
)
def test_path_admission_fails_before_provider_work(paths: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        StaticPythonBackendDeclarations(paths=paths)


@pytest.mark.parametrize(
    "settings",
    [
        {"include_model_fields": 1},
        {"include_environment_reads": "yes"},
        {"include_model_fields": False, "include_environment_reads": False},
    ],
)
def test_strict_provider_modes_fail_on_construction(settings: dict) -> None:
    with pytest.raises(ValueError):
        StaticPythonBackendDeclarations(paths=(PATH,), **settings)


def test_invalid_ast_and_bound_excess_fail_closed(tmp_path: Path) -> None:
    provider = StaticPythonBackendDeclarations(paths=(PATH,))
    _write(tmp_path, "class Payload(BaseModel):\n    unfinished =\n")
    with CodeMap(tmp_path) as cm:
        cm.sync()
        with pytest.raises(
            (ValueError, SyntaxError, RepositoryDeclarationProviderError)
        ):
            cm.discover_repository_declarations([provider])
    fields = "\n".join(f"    field_{n}: int" for n in range(MAX_MODEL_FIELDS + 1))
    _write(tmp_path, f"class Payload(BaseModel):\n{fields}\n")
    with CodeMap(tmp_path) as cm:
        cm.sync()
        with pytest.raises((ValueError, RepositoryDeclarationProviderError)):
            cm.discover_repository_declarations([provider])


def test_restricted_visibility_cannot_publish_source_syntax(tmp_path: Path) -> None:
    _write(tmp_path, "import os\nsecret = os.getenv('SECRET_NAME')\n")
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "service.py"\nvisibility = "outline"\n',
        encoding="utf-8",
    )
    provider = StaticPythonBackendDeclarations(paths=(PATH,))
    with CodeMap(tmp_path) as cm:
        cm.sync()
        with pytest.raises(RepositoryDeclarationProviderError):
            cm.discover_repository_declarations([provider])


def test_provider_has_no_ambient_discovery_without_explicit_selection(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "import os\nsecret = os.getenv('ONLY_IF_SELECTED')\n")
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet = cast("dict", cm.discover_repository_declarations([]))
    assert packet["declarations"]["groups"] == []


def test_model_and_environment_modes_remain_independently_selectable(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "import os\nclass Config(BaseSettings):\n"
        "    key: str = os.getenv('CONFIG_KEY')\n",
    )
    model = _observe(
        tmp_path,
        StaticPythonBackendDeclarations(paths=(PATH,), include_environment_reads=False),
    )
    env = _observe(
        tmp_path,
        StaticPythonBackendDeclarations(paths=(PATH,), include_model_fields=False),
    )
    assert set(_groups(model)) == {"python-model-class-syntax"}
    assert set(_groups(env)) == {"python-env-access-syntax"}
    assert (
        _value(_groups(model)["python-model-class-syntax"][0])["model_identity"]
        == "not-established"
    )
    assert (
        _value(_groups(env)["python-env-access-syntax"][0])["runtime_binding"]
        == "not-established"
    )


def test_environment_keyword_default_is_syntax_not_missing_or_resolved(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "import os\nsetting = os.getenv(key='REGION', default='hidden')\n")
    rows = _groups(
        _observe(
            tmp_path,
            StaticPythonBackendDeclarations(paths=(PATH,), include_model_fields=False),
        )
    )["python-env-access-syntax"]
    value = _value(rows[0])
    assert value["key"] == {"state": "literal-key-syntax", "value": "REGION"}
    assert value["default"] == {"state": "literal-kind-only", "kind": "string"}
    assert value["direct_assignment_names"] == ["setting"]
    assert "hidden" not in str(value)
    assert value["runtime_env_read"] == "not-established"


def test_nested_model_classes_keep_distinct_source_origins(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "def first():\n"
        "    class Model(BaseModel):\n"
        "        value: str = Field(default_factory=str)\n"
        "async def second():\n"
        "    if condition:\n"
        "        class Model(library.BaseModel):\n"
        "            value: int\n",
    )
    packet = _observe(
        tmp_path,
        StaticPythonBackendDeclarations(paths=(PATH,), include_environment_reads=False),
    )
    groups = _groups(packet)["python-model-class-syntax"]
    assert [group["scope"]["class_line"] for group in groups] == [2, 6]
    assert len({group["group_id"] for group in groups}) == 2
    assert [_value(group)["fields"][0]["line"] for group in groups] == [3, 7]
    assert _value(groups[0])["fields"][0]["default"]["keyword_names"] == [
        "default_factory"
    ]
    for group in groups:
        declaration = group["declarations"][0]
        assert declaration["evidence_state"] == "known-present"
        assert group["absence"]["state"] == "unknown"
        assert _value(group)["model_identity"] == "not-established"
        assert _value(group)["runtime_binding"] == "not-established"


def test_opt_in_class_fields_do_not_infer_inheritance_or_runtime_model(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "class Parent:\n"
        "    inherited: str\n"
        "def factory():\n"
        "    class Child(Parent):\n"
        "        direct: int = Field(discriminator=select)\n"
        "        class Nested:\n"
        "            unrelated: bool\n"
        "        def method(self):\n"
        "            local: float\n",
    )
    provider = StaticPythonBackendDeclarations(
        paths=(PATH,),
        include_model_fields=False,
        include_environment_reads=False,
        include_class_fields=True,
    )
    packet = _observe(tmp_path, provider)
    groups = _groups(packet)["python-annotated-class-syntax"]
    assert [_value(group)["class_name_syntax"] for group in groups] == [
        "Parent",
        "Child",
        "Nested",
    ]
    child = _value(groups[1])
    assert [field["name"] for field in child["fields"]] == ["direct"]
    assert child["base_expressions"][0]["text"] == "Parent"
    assert child["class_identity"] == "not-established"
    assert child["inherited_fields"] == "not-established"
    assert child["runtime_field_roles"] == "unknown"
    assert child["negative_evidence_admissible"] is False
    assert "model_identity" not in child
    assert child["fields"][0]["runtime_validation"] == "not-established"
    assert packet["providers"][0]["provenance"]["class_fields"] is True


def test_nested_class_bound_fails_instead_of_claiming_complete_scope(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "def factory():\n"
        + "".join(f"    class Model_{i}(BaseModel): pass\n" for i in range(65)),
    )
    with pytest.raises(RepositoryDeclarationProviderError, match="group bound"):
        _observe(tmp_path, StaticPythonBackendDeclarations(paths=(PATH,)))


def test_generic_class_reopen_rejects_stale_source_and_does_not_replay(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "class Payload(Parent):\n    old: int\n")
    state = tmp_path / "state"
    provider = StaticPythonBackendDeclarations(
        paths=(PATH,), include_class_fields=True, include_environment_reads=False
    )
    with CodeMap(tmp_path, state_dir=state) as cm:
        cm.sync()
        before = cm.discover_repository_declarations([provider])
    _write(tmp_path, "class Payload(Parent):\n    current: str\n")
    with CodeMap(tmp_path, state_dir=state) as cm:
        with pytest.raises(RepositoryDeclarationProviderError, match="input changed"):
            cm.discover_repository_declarations([provider], previous_observation=before)
        cm.sync([PATH])
        after = cast(
            "dict",
            cm.discover_repository_declarations(
                [provider], previous_observation=before
            ),
        )
        omitted = cast(
            "dict", cm.discover_repository_declarations([], previous_observation=before)
        )
        current = cast("dict", cm.discover_repository_declarations([provider]))
    assert before["observation_identity"] != after["observation_identity"]
    assert after["observation_identity"] == current["observation_identity"]
    assert omitted["declarations"]["groups"] == []
    value = _value(_groups(current)["python-annotated-class-syntax"][0])
    assert [field["name"] for field in value["fields"]] == ["current"]
    assert value["inherited_fields"] == "not-established"
