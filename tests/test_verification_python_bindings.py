"""Verification observes authored Python data and configured test import context."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records
from test_changed_set_verification import _repository, _target_paths


@pytest.mark.parametrize(
    ("source", "consumer"),
    [
        ("VALUE = object()\n", "assert VALUE is not None"),
        ("VALUE: str = 'selected'\n", "assert VALUE == 'selected'"),
    ],
)
def test_module_data_import_and_use_is_a_source_relationship(
    tmp_path: Path, source: str, consumer: str
) -> None:
    with _repository(
        tmp_path,
        {
            "owner.py": source,
            "tests/test_data.py": "from owner import VALUE\ndef test_data(): "
            + consumer
            + "\n",
        },
    ) as repository:
        packet = repository.verification.changed_set(["owner.py"])
    assert _target_paths(packet) == ["tests/test_data.py"]
    relation = assert_records(assert_records(packet["changes"])[0]["relationships"])[0]
    assert relation["relation_kind"] == "direct-reference"
    assert packet["negative_evidence_admissible"] is False


def test_module_data_reaches_a_verifier_through_an_existing_source_consumer(
    tmp_path: Path,
) -> None:
    with _repository(
        tmp_path,
        {
            "schema.py": "SCHEMA = 'create table sample(value)'\n",
            "database.py": "from schema import SCHEMA\ndef initialize(): return SCHEMA\n",
            "tests/test_database.py": "from database import initialize\ndef test_database(): assert initialize()\n",
        },
    ) as repository:
        packet = repository.verification.changed_set(["schema.py"])
    assert _target_paths(packet) == ["tests/test_database.py"]
    relation = assert_records(assert_records(packet["changes"])[0]["relationships"])[0]
    assert relation["relation_kind"] == "bounded-indirect-reference"


@pytest.mark.parametrize("configuration", [True, False])
def test_nested_test_helper_requires_explicit_pytest_import_context(
    tmp_path: Path, configuration: bool
) -> None:
    files = {
        "component/pyproject.toml": (
            '[tool.setuptools.package-dir]\n""="src"\n'
            '[tool.pytest.ini_options]\ntestpaths=["tests"]\n'
            + ('pythonpath=["."]\n' if configuration else "")
        ),
        "component/src/sample/__init__.py": "",
        "component/tests/__init__.py": "",
        "component/tests/factories/__init__.py": "",
        "component/tests/factories/data.py": "def build(): return 1\n",
        "component/tests/test_data.py": "from tests.factories.data import build\ndef test_data(): assert build() == 1\n",
    }
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(
            ["component/tests/factories/data.py"]
        )
    assert _target_paths(packet) == (
        ["component/tests/test_data.py"] if configuration else []
    )
    if configuration:
        relationship = assert_records(
            assert_records(packet["changes"])[0]["relationships"]
        )[0]
        assert "component/pyproject.toml" in {
            member["path"]
            for member in assert_records(relationship["supporting_source_members"])
        }


@pytest.mark.skipif(
    sys.version_info < (3, 12), reason="PEP695 requires the native Python grammar"
)
def test_pep695_type_alias_is_an_authored_source_binding(tmp_path: Path) -> None:
    with _repository(
        tmp_path,
        {
            "owner.py": "type Choice = str | int\n",
            "tests/test_choice.py": "from owner import Choice\ndef test_choice(): assert Choice is not None\n",
        },
    ) as repository:
        packet = repository.verification.changed_set(["owner.py"])
        binding = repository.source.bindings("owner.py")
    assert _target_paths(packet) == ["tests/test_choice.py"]
    declarations = [
        row for row in assert_records(binding["facts"]) if row["kind"] == "declaration"
    ]
    assert len(declarations) == 1
    assert declarations[0]["declaration_kind"] == "type-alias"
    assert declarations[0]["runtime_target"] == "not-established"
    assert assert_object(declarations[0]["target"])["name"] == "Choice"


@pytest.mark.skipif(
    sys.version_info >= (3, 12), reason="This runtime admits PEP695 syntax"
)
def test_pep695_source_remains_unavailable_without_native_python_grammar(
    tmp_path: Path,
) -> None:
    with _repository(
        tmp_path,
        {
            "owner.py": "type Choice = str | int\n",
            "tests/test_choice.py": "from owner import Choice\ndef test_choice(): assert Choice is not None\n",
        },
    ) as repository:
        packet = repository.verification.changed_set(["owner.py"])
        binding = repository.source.bindings("owner.py")
    assert _target_paths(packet) == []
    assert binding["availability"] != "observed"
    assert binding["facts"] == []
    assert binding["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize(
    "source", ["if configured:\n VALUE = object()\n", "VALUE = 1\ndel VALUE\n"]
)
def test_lexical_data_index_cannot_repair_unknown_export_binding(
    tmp_path: Path, source: str
) -> None:
    with _repository(
        tmp_path,
        {
            "owner.py": source,
            "tests/test_data.py": "from owner import VALUE\ndef test_data(): assert VALUE\n",
        },
    ) as repository:
        packet = repository.verification.changed_set(["owner.py"])
    assert _target_paths(packet) == []
    assert packet["negative_evidence_admissible"] is False


def test_data_reference_shadowing_withdraws_a_previous_positive(tmp_path: Path) -> None:
    with _repository(
        tmp_path,
        {
            "owner.py": "VALUE = 1\n",
            "tests/test_data.py": "from owner import VALUE\ndef test_data(): assert VALUE == 1\n",
        },
    ) as repository:
        assert _target_paths(repository.verification.changed_set(["owner.py"])) == [
            "tests/test_data.py"
        ]
        (repository.workspace / "tests/test_data.py").write_text(
            "from owner import VALUE\ndef test_data(VALUE): assert VALUE == 1\n"
        )
        packet = repository.verification.changed_set(["owner.py"])
    assert _target_paths(packet) == []


def _configured_helper_files() -> dict[str, str]:
    return {
        "component/pyproject.toml": '[tool.pytest.ini_options]\npythonpath=["."]\n',
        "component/tests/__init__.py": "",
        "component/tests/factories/__init__.py": "",
        "component/tests/factories/data.py": "def build(): return 1\n",
        "component/tests/test_data.py": "from tests.factories.data import build\ndef test_data(): assert build() == 1\n",
    }


def test_pytest_import_context_does_not_rewrite_production_import_identity(
    tmp_path: Path,
) -> None:
    files = _configured_helper_files()
    files["component/pyproject.toml"] += '[tool.setuptools.package-dir]\n""="src"\n'
    files["component/src/sample/__init__.py"] = ""
    files["component/src/sample/client.py"] = (
        "from tests.factories.data import build\ndef selected(): return build()\n"
    )
    files["component/tests/test_data.py"] = (
        "from sample.client import selected\ndef test_data(): assert selected() == 1\n"
    )
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(
            ["component/tests/factories/data.py"]
        )
    assert _target_paths(packet) == []


def test_explicit_repository_root_context_keeps_its_native_declaration(
    tmp_path: Path,
) -> None:
    with _repository(
        tmp_path,
        {
            "pyproject.toml": '[tool.pytest.ini_options]\npythonpath=["."]\n',
            "tests/__init__.py": "",
            "tests/helpers.py": "def build(): return 1\n",
            "tests/test_data.py": "from tests.helpers import build\ndef test_data(): assert build() == 1\n",
        },
    ) as repository:
        packet = repository.verification.changed_set(["tests/helpers.py"])
    assert _target_paths(packet) == ["tests/test_data.py"]
    relationship = assert_records(
        assert_records(packet["changes"])[0]["relationships"]
    )[0]
    context = assert_object(
        assert_object(relationship["reference_evidence"])["import_context"]
    )
    assert context["roots"] == [""]
    assert context["runtime_import"] == "not-established"


def test_declared_pytest_roots_do_not_choose_between_duplicate_module_owners(
    tmp_path: Path,
) -> None:
    files = _configured_helper_files()
    files["component/pyproject.toml"] = (
        '[tool.pytest.ini_options]\npythonpath=[".", "other"]\n'
    )
    files["component/other/tests/factories/data.py"] = "def build(): return 2\n"
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(
            ["component/tests/factories/data.py"]
        )
    assert _target_paths(packet) == []
    change = assert_records(packet["changes"])[0]
    assert (
        assert_object(change["consumer_scope"])["qualified_identity_ambiguous"] is True
    )


def test_new_nearer_config_reconciles_the_retained_absence_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _repository(tmp_path, _configured_helper_files()) as repository:
        source = "component/tests/factories/data.py"
        baseline = repository.verification.changed_set([source])
        assert _target_paths(baseline) == ["component/tests/test_data.py"]
        relationship = assert_records(
            assert_records(baseline["changes"])[0]["relationships"]
        )[0]
        absent = {
            member["path"]
            for member in assert_records(relationship["supporting_source_members"])
            if member["state"] == "known-absent"
        }
        assert "component/tests/pytest.ini" in absent
        recheck = repository.verification._changed_recheck
        changed = False

        def introduce(
            changes: Sequence[Mapping[str, object]],
            targets: Sequence[Mapping[str, object]],
        ) -> None:
            nonlocal changed
            if not changed:
                changed = True
                (repository.workspace / "component/tests/pytest.ini").write_text(
                    "[pytest]\npythonpath=.\n"
                )
            recheck(changes, targets)

        monkeypatch.setattr(repository.verification, "_changed_recheck", introduce)
        packet = repository.verification.changed_set([source])
    assert changed
    assert _target_paths(packet) == []


def test_indirect_test_helper_retains_each_explicit_import_context(
    tmp_path: Path,
) -> None:
    with _repository(
        tmp_path,
        {
            "pyproject.toml": '[tool.pytest.ini_options]\npythonpath=["."]\n',
            "owner.py": "VALUE = 1\n",
            "tests/__init__.py": "",
            "tests/helpers/__init__.py": "",
            "tests/helpers/bridge.py": "from owner import VALUE\ndef observed(): return VALUE\n",
            "tests/test_data.py": "from tests.helpers.bridge import observed\ndef test_data(): assert observed() == 1\n",
        },
    ) as repository:
        packet = repository.verification.changed_set(["owner.py"])
    assert _target_paths(packet) == ["tests/test_data.py"]
    relationship = assert_records(
        assert_records(packet["changes"])[0]["relationships"]
    )[0]
    context = assert_object(
        assert_object(relationship["reference_evidence"])["import_context"]
    )
    assert set(assert_object(context["contributing_contexts"])) == {
        "tests/helpers/bridge.py",
        "tests/test_data.py",
    }
    assert {
        member["path"]
        for member in assert_records(context["supporting_source_members"])
    } >= {
        "tests/helpers/pytest.ini",
        "tests/pytest.ini",
        "pyproject.toml",
    }
