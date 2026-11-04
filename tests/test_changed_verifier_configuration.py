"""Declared native selection cannot be mistaken for an ordinary-source verdict."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _role(native: CodeMap, path: str) -> dict[str, object]:
    packet = native.verification.changed_set((path,), limit=2)
    assert packet["negative_evidence_admissible"] is False
    changes = cast(list[dict[str, object]], packet["changes"])
    return _mapping(changes[0]["classification"])


@pytest.mark.parametrize(
    ("filename", "configuration"),
    [
        ("pyproject.toml", '[tool.pytest.ini_options]\npython_functions=["check_*"]\n'),
        ("pyproject.toml", '[tool.pytest]\npython_functions=["check_*"]\n'),
        ("pytest.toml", '[pytest]\npython_functions=["check_*"]\n'),
        (".pytest.toml", '[pytest]\npython_functions=["check_*"]\n'),
        ("pytest.ini", "[pytest]\npython_functions=check_*\n"),
        (".pytest.ini", "[pytest]\npython_functions=check_*\n"),
        ("tox.ini", "[pytest]\npython_functions=check_*\n"),
        ("setup.cfg", "[tool:pytest]\npython_functions=check_*\n"),
    ],
)
def test_custom_selection_retains_source_options_without_discovering_tests(
    tmp_path: Path, filename: str, configuration: str
) -> None:
    (tmp_path / filename).write_text(configuration)
    (tmp_path / "checks").mkdir()
    (tmp_path / "checks/behavior_cases.py").write_text(
        "def check_answer():\n assert True\n"
    )
    with CodeMap(tmp_path, state_dir=tmp_path / "state") as native:
        role = _role(native, "checks/behavior_cases.py")
    assert role["kind"] == "unknown"
    assert role["reason"] == "pytest-selection-scope-unqualified"
    selection = _mapping(role["native_selection"])
    assert selection["state"] == "declared"
    assert selection["selection_authority"] == "native-pytest"
    assert selection["collection"] == "not-observed"
    assert selection["configuration_resolution"] == "not-performed"
    assert role["native_collection"] == "not-observed"
    assert role["negative_evidence_admissible"] is False
    declarations = cast(list[dict[str, object]], selection["declarations"])
    assert declarations[0]["path"] == filename
    assert "check_*" in str(_mapping(declarations[0]["options"])["python_functions"])
    members = cast(list[dict[str, object]], role["supporting_source_members"])
    assert any(
        row["path"] == filename and row.get("member_revision") for row in members
    )


def test_nearer_unrelated_manifest_cannot_hide_parent_native_options(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npython_files=["behavior_*.py"]\n'
    )
    child = tmp_path / "nested"
    child.mkdir()
    (child / "pyproject.toml").write_text('[project]\nname="child"\nversion="1"\n')
    (child / "behavior_cases.py").write_text("def test_answer():\n assert True\n")
    with CodeMap(tmp_path, state_dir=tmp_path / "state") as native:
        role = _role(native, "nested/behavior_cases.py")
    assert role["kind"] == "unknown"
    declarations = cast(
        list[dict[str, object]], _mapping(role["native_selection"])["declarations"]
    )
    assert any(row["path"] == "pyproject.toml" for row in declarations)


def test_test_shaped_helper_flag_is_not_native_collection_absence(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_helper.py").write_text(
        "__test__ = False\ndef test_helper():\n return object()\n"
    )
    with CodeMap(tmp_path, state_dir=tmp_path / "state") as native:
        role = _role(native, "tests/test_helper.py")
    assert role["kind"] == "unknown"
    assert role["reason"] == "pytest-test-flag-not-interpreted"
    assert role["collection_authority"] == "external"


@pytest.mark.parametrize("explicit", [False, True])
def test_ini_defaults_do_not_supply_unauthored_pytest_options(
    tmp_path: Path, explicit: bool
) -> None:
    (tmp_path / "pytest.ini").write_text(
        "[DEFAULT]\npython_functions=check_*\n[pytest]\n"
        + ("python_functions=check_*\n" if explicit else "")
    )
    (tmp_path / "source.py").write_text("def ordinary():\n return 1\n")
    with CodeMap(tmp_path, state_dir=tmp_path / "state") as native:
        role = _role(native, "source.py")
    selection = _mapping(role["native_selection"])
    declarations = cast(list[dict[str, object]], selection["declarations"])
    if explicit:
        assert role["kind"] == "unknown"
        assert _mapping(declarations[0]["options"])["python_functions"] == "check_*"
    else:
        assert role["kind"] == "source"
        assert declarations == []
        assert selection["state"] == "not-observed"
    assert role["negative_evidence_admissible"] is False


def test_addopts_are_retained_without_manufacturing_native_non_test_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts="-o python_files=behavior_*.py"\n'
    )
    (tmp_path / "source.py").write_text("def ordinary():\n return 1\n")
    with CodeMap(tmp_path, state_dir=tmp_path / "state") as native:
        role = _role(native, "source.py")
    assert role["kind"] == "source"
    assert role["negative_evidence_admissible"] is False
    assert role["native_collection"] == "not-observed"
    selection = _mapping(role["native_selection"])
    assert selection["custom_name_patterns"] is False
    declaration = cast(list[dict[str, object]], selection["declarations"])[0]
    assert (
        _mapping(declaration["options"])["addopts"] == "-o python_files=behavior_*.py"
    )


def test_denied_selection_config_cannot_restore_ordinary_source_role(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npython_functions=["check_*"]\n'
    )
    (tmp_path / "source.py").write_text("def check_answer():\n assert True\n")
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern="pyproject.toml"\nindex=false\n'
    )
    with CodeMap(tmp_path, state_dir=tmp_path / "state") as native:
        role = _role(native, "source.py")
    assert role["kind"] == "unknown"
    assert _mapping(role["native_selection"])["state"] == "unknown"


@pytest.mark.parametrize(
    ("filename", "configuration"),
    [
        ("pyproject.toml", '[tool]\npytest="invalid"\n'),
        ("pytest.toml", 'pytest="invalid"\n'),
        ("pytest.ini", "[pytest\npython_functions=check_*\n"),
    ],
)
def test_invalid_native_options_do_not_restore_a_source_verdict(
    tmp_path: Path, filename: str, configuration: str
) -> None:
    (tmp_path / filename).write_text(configuration)
    (tmp_path / "source.py").write_text("def check_answer():\n assert True\n")
    with CodeMap(tmp_path, state_dir=tmp_path / "state") as native:
        role = _role(native, "source.py")
    assert role["kind"] == "unknown"
    assert _mapping(role["native_selection"])["state"] == "unknown"


def test_oversized_configuration_keeps_unavailable_member_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "source.py").write_text("def ordinary():\n return 1\n")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npython_functions=["check_*"]\n#'
        + "x" * VERIFICATION_RELEVANCE_DEFAULTS.source_member_bytes
    )
    with CodeMap(tmp_path, state_dir=tmp_path / "state") as native:
        ensure_current = native.source.ensure_current
        manifest_options = native.verification._pytest_manifest_options

        def reject_oversized_refresh(path: str) -> None:
            assert path != "pyproject.toml", (
                "oversized config reconciled before its bound"
            )
            ensure_current(path)

        def bounded_manifest_options(raw: bytes) -> object:
            assert len(raw) <= VERIFICATION_RELEVANCE_DEFAULTS.source_member_bytes
            return manifest_options(raw)

        monkeypatch.setattr(native.source, "ensure_current", reject_oversized_refresh)
        monkeypatch.setattr(
            native.verification, "_pytest_manifest_options", bounded_manifest_options
        )
        role = _role(native, "source.py")
    assert role["kind"] == "unknown"
    assert _mapping(role["native_selection"])["state"] == "unknown"
    supporting = cast(list[dict[str, object]], role["supporting_source_members"])
    assert any(
        row["path"] == "pyproject.toml"
        and row["state"] == "unknown"
        and row.get("reason") == "source-size-bound"
        for row in supporting
    )


def test_native_options_rebind_after_equal_size_source_change(tmp_path: Path) -> None:
    manifest = tmp_path / "pytest.ini"
    manifest.write_text("[pytest]\npython_functions=check_*\n")
    (tmp_path / "source.py").write_text("def check_answer():\n assert True\n")
    with CodeMap(tmp_path, state_dir=tmp_path / "state") as native:
        before = _role(native, "source.py")
        manifest.write_text("[pytest]\npython_functions=proof_*\n")
        after = _role(native, "source.py")
    assert before["evidence_identity"] != after["evidence_identity"]
    assert before["kind"] == after["kind"] == "unknown"
    assert (
        _mapping(before["native_selection"])["declarations"]
        != _mapping(after["native_selection"])["declarations"]
    )


def test_native_collector_can_find_a_case_while_repository_role_stays_unknown(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths=["checks"]\n'
        'python_files=["behavior_*.py"]\npython_functions=["check_*"]\n'
    )
    (tmp_path / "checks").mkdir()
    source = tmp_path / "checks/behavior_cases.py"
    source.write_text("def check_answer():\n assert True\n")
    with CodeMap(tmp_path, state_dir=tmp_path / "state") as native:
        role = _role(native, "checks/behavior_cases.py")
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=tmp_path,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert collected.returncode == 0, collected.stdout + collected.stderr
    assert "behavior_cases.py::check_answer" in collected.stdout
    assert role["kind"] == "unknown"
    assert _mapping(role["native_selection"])["collection"] == "not-observed"
