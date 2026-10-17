"""B25–B29: exact environment syntax direction and model field locality."""

from __future__ import annotations

from pathlib import Path

from hashmarks.codemap import CodeMap
from hashmarks.codemap.static_python_backend_declarations import (
    StaticPythonBackendDeclarations,
)
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation

PATH = "backend.py"


def _observe(repo: Path, *, source: str) -> dict:
    (repo / PATH).write_text(source, encoding="utf-8")
    with CodeMap(repo) as cm:
        cm.index.sync()
        return cm.discover_repository_declarations(
            [StaticPythonBackendDeclarations(paths=(PATH,))]
        )


def _groups(packet: dict, kind: str) -> list[dict]:
    return [
        group
        for group in packet["declarations"]["groups"]
        if group["concept"]["kind"] == kind
    ]


def _value(group: dict) -> dict:
    return group["declarations"][0]["value"]


def test_direct_model_initializer_and_environment_observation_share_exact_ast_site(
    tmp_path: Path,
) -> None:
    packet = _observe(
        tmp_path,
        source=(
            "import os\n"
            "class Settings(BaseSettings):\n"
            "    token: str = os.getenv('TOKEN', 'SECRET_DO_NOT_COPY')\n"
            "    allowed: bool = os.environ['ALLOWED']\n"
            "    lazy: str = Field(default_factory=lambda: os.getenv('LATE'))\n"
            "    calculated: str = build_env_value()\n"
        ),
    )
    models = _groups(packet, "python-model-class-syntax")
    env = [_value(group) for group in _groups(packet, "python-env-access-syntax")]
    assert len(models) == 1
    assert len(env) == 3
    fields = _value(models[0])["fields"]
    assert [field["name"] for field in fields] == [
        "token",
        "allowed",
        "lazy",
        "calculated",
    ]
    token = fields[0]["direct_environment_initializer"]
    allowed = fields[1]["direct_environment_initializer"]
    assert token["state"] == "same-direct-ast-expression"
    assert token["expression"]["key"] == {
        "state": "literal-key-syntax",
        "value": "TOKEN",
    }
    assert token["expression"]["access_role"] == "lookup-call-syntax"
    assert token["runtime_binding"] == "not-established"
    assert token["configuration_precedence"] == "unknown"
    assert allowed["expression"]["access_role"] == "load-expression-syntax"
    assert "direct_environment_initializer" not in fields[2]
    assert "direct_environment_initializer" not in fields[3]
    assert fields[0]["runtime_requiredness"] == "unknown"
    assert token["source_site"] == env[0]["source_site"]
    assert token["expression"]["key"] == env[0]["key"]
    assert allowed["source_site"] == env[1]["source_site"]
    assert env[2]["key"]["value"] == "LATE"
    assert "SECRET_DO_NOT_COPY" not in str(packet)
    assert models[0]["correspondence"]["state"] == "unresolved"
    assert models[0]["coverage"]["state"] == "incomplete"
    assert models[0]["absence"]["state"] == "unknown"
    assert (
        validate_evidence_presentation(
            packet, present_repository_evidence(packet, format="compact")
        )["valid"]
        is True
    )


def test_subscript_load_store_delete_and_augmented_target_not_collapsed(
    tmp_path: Path,
) -> None:
    packet = _observe(
        tmp_path,
        source=(
            "import os\n"
            "read = os.environ['TOKEN']\n"
            "os.environ['TOKEN'] = 'secret'\n"
            "del os.environ['TOKEN']\n"
            "os.environ['TOKEN'] += 'suffix'\n"
        ),
    )
    values = [_value(group) for group in _groups(packet, "python-env-access-syntax")]
    assert len(values) == 4
    assert [value["access_role"] for value in values] == [
        "load-expression-syntax",
        "store-target-syntax",
        "delete-target-syntax",
        "store-target-syntax",
    ]
    assert all(value["runtime_env_read"] == "not-established" for value in values)
    assert all(value["negative_evidence_admissible"] is False for value in values)
    assert values[0]["direct_assignment_names"] == ["read"]
    assert "secret" not in str(packet)
    assert "suffix" not in str(packet)


def test_competing_key_and_default_arguments_do_not_select_first_candidate(
    tmp_path: Path,
) -> None:
    packet = _observe(
        tmp_path,
        source=(
            "import os\n"
            "x = os.getenv('A', key='B')\n"
            "y = os.getenv('C', 'first', default='second')\n"
            "z = os.getenv('D', **kwargs)\n"
            "w = os.getenv(default='not-revealed')\n"
        ),
    )
    values = [_value(group) for group in _groups(packet, "python-env-access-syntax")]
    assert values[0]["key"] == {"state": "ambiguous-explicit-syntax"}
    assert values[0]["argument_binding"] == "unresolved-ambiguous-or-expanded"
    assert values[1]["default"] == {"state": "ambiguous-explicit-syntax"}
    assert values[1]["key"]["value"] == "C"
    assert values[2]["key"]["value"] == "D"
    assert values[2]["has_argument_expansion"] is True
    assert values[2]["argument_binding"] == "unresolved-ambiguous-or-expanded"
    assert values[3]["key"] == {"state": "not-supplied"}
    assert values[3]["default"] == {"state": "literal-kind-only", "kind": "string"}
    assert "not-revealed" not in str(packet)
    assert "first" not in str(packet)
    assert "second" not in str(packet)


def test_same_line_separate_expressions_have_distinct_source_site(
    tmp_path: Path,
) -> None:
    packet = _observe(
        tmp_path,
        source="import os\na = os.getenv('K'); b = os.getenv('K')\n",
    )
    groups = _groups(packet, "python-env-access-syntax")
    values = [_value(group) for group in groups]
    assert len(groups) == 2
    assert groups[0]["group_id"] != groups[1]["group_id"]
    assert values[0]["source_site"]["start_line"] == 2
    assert values[1]["source_site"]["start_line"] == 2
    assert (
        values[0]["source_site"]["start_column"]
        != (values[1]["source_site"]["start_column"])
    )
    assert values[0]["key"]["value"] == values[1]["key"]["value"] == "K"


def test_source_mutation_changes_direct_initializer_correspondence(
    tmp_path: Path,
) -> None:
    source = tmp_path / PATH
    source.write_text(
        "import os\nclass Settings(BaseSettings):\n    key: str = os.getenv('ONE')\n",
        encoding="utf-8",
    )
    provider = StaticPythonBackendDeclarations(paths=(PATH,))
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        before = cm.discover_repository_declarations([provider])
        source.write_text(
            "import os\nclass Settings(BaseSettings):\n"
            "    key: str = os.getenv('TWO')\n",
            encoding="utf-8",
        )
        cm.index.sync([PATH])
        after = cm.discover_repository_declarations(
            [provider], previous_observation=before
        )
    first = _value(_groups(before, "python-model-class-syntax")[0])["fields"][0]
    second = _value(_groups(after, "python-model-class-syntax")[0])["fields"][0]
    assert (
        first["direct_environment_initializer"]["expression"]["key"]["value"] == "ONE"
    )
    assert (
        second["direct_environment_initializer"]["expression"]["key"]["value"] == "TWO"
    )
    assert before["observation_identity"] != after["observation_identity"]


def test_explicit_opt_in_observation_modes_still_independent(tmp_path: Path) -> None:
    source = tmp_path / PATH
    source.write_text(
        "import os\nclass Settings(BaseSettings):\n    token: str = os.getenv('K')\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        model = cm.discover_repository_declarations(
            [
                StaticPythonBackendDeclarations(
                    paths=(PATH,), include_environment_reads=False
                )
            ]
        )
        env = cm.discover_repository_declarations(
            [StaticPythonBackendDeclarations(paths=(PATH,), include_model_fields=False)]
        )
    assert len(_groups(model, "python-model-class-syntax")) == 1
    assert _groups(model, "python-env-access-syntax") == []
    assert _groups(env, "python-model-class-syntax") == []
    assert len(_groups(env, "python-env-access-syntax")) == 1
    field = _value(_groups(model, "python-model-class-syntax")[0])["fields"][0]
    assert field["direct_environment_initializer"]["expression"]["key"]["value"] == "K"
    assert _value(_groups(env, "python-env-access-syntax")[0])["key"]["value"] == "K"
