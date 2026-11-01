"""Changed-set evidence composes real source and verification owners."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import pytest
from contract_assertions import assert_integer, assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.codemap.repository_observation import evidence_identity
from hashmarks.verification_nomination_validation import (
    validate_verification_nomination,
)
from hashmarks.verification_selection import validate_verification_membership


@contextmanager
def _repository(tmp_path: Path, files: Mapping[str, str]) -> Iterator[CodeMap]:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    for path, content in files.items():
        target = workspace / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    with CodeMap(workspace, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        yield repository


def _ordinary_files() -> dict[str, str]:
    return {
        "owner.py": "def total(): return 1\n",
        "tests/test_total.py": "from owner import total\ndef test_total(): assert total() == 1\n",
        "pyproject.toml": "[tool.pytest.ini_options]\n",
    }


def _target_paths(packet: Mapping[str, object]) -> list[str]:
    return [str(row["path"]) for row in assert_records(packet["targets"])]


def _assert_no_execution(value: object) -> None:
    if isinstance(value, Mapping):
        assert {
            "argv",
            "working_directory",
            "command",
            "timeout",
            "retries",
            "workers",
        }.isdisjoint(value)
        for item in value.values():
            _assert_no_execution(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_execution(item)


def test_changed_source_has_qualified_target_membership_and_canonical_explanation(
    tmp_path: Path,
) -> None:
    with _repository(tmp_path, _ordinary_files()) as repository:
        packet = repository.verification.changed_set(["owner.py"])
        change = assert_records(packet["changes"])[0]
        expected = repository.verification.explain_relevance(
            "owner.py", assert_object(change["relevance"])
        )
        assert change["explanation"] == expected
    assert packet["schema"] == "hashmarks.changed-set-verification.v1"
    assert _target_paths(packet) == ["tests/test_total.py"]
    relation = assert_records(change["relationships"])[0]
    assert relation["classification"] == "direct"
    assert relation["relation_kind"] == "direct-reference"
    assert {
        row["path"] for row in assert_records(relation["supporting_source_members"])
    } == {"owner.py", "tests/test_total.py"}
    target = assert_records(packet["targets"])[0]
    assert validate_verification_nomination(target["nomination"])["valid"] is True
    assert (
        validate_verification_membership(assert_object(packet["membership"]))["valid"]
        is True
    )
    assert assert_object(target["member"])["test_symbol"] is None
    assert packet["negative_evidence_admissible"] is False
    assert packet["execution_authority"] == "external"
    _assert_no_execution(packet)


def test_changed_test_is_a_verifier_but_helper_is_only_support(tmp_path: Path) -> None:
    files = _ordinary_files()
    files["tests/helpers.py"] = "def make_total(): return 1\n"
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(
            ["tests/helpers.py", "tests/test_total.py"]
        )
    changes = {row["path"]: row for row in assert_records(packet["changes"])}
    assert (
        assert_object(changes["tests/helpers.py"]["classification"])["kind"]
        == "verification-support"
    )
    assert (
        assert_object(changes["tests/test_total.py"]["classification"])["kind"]
        == "verifier"
    )
    assert _target_paths(packet) == ["tests/test_total.py"]
    assert any(
        row["relation_kind"] == "changed-verifier"
        for row in assert_records(changes["tests/test_total.py"]["relationships"])
    )


def test_bounded_indirect_reference_reuses_owner_and_retains_intermediate_revision(
    tmp_path: Path,
) -> None:
    files = {
        "owner.py": "def total(): return 1\n",
        "helper.py": "from owner import total\ndef build(): return total()\n",
        "tests/test_build.py": "from helper import build\ndef test_build(): assert build() == 1\n",
    }
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["owner.py"])
    assert _target_paths(packet) == ["tests/test_build.py"]
    change = assert_records(packet["changes"])[0]
    relation = assert_records(change["relationships"])[0]
    assert relation["relation_kind"] == "bounded-indirect-reference"
    assert relation["classification"] == "related"
    assert "helper.py" in {
        row["path"] for row in assert_records(relation["supporting_source_members"])
    }


def test_imported_shared_helper_keeps_structural_consumers(tmp_path: Path) -> None:
    files = {
        "tests/__init__.py": "",
        "tests/helpers.py": "def factory(): return 1\n",
        "tests/test_build.py": "from tests.helpers import factory\ndef test_build(): assert factory() == 1\n",
    }
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["tests/helpers.py"])
    assert _target_paths(packet) == ["tests/test_build.py"]
    assert "tests/helpers.py" not in _target_paths(packet)


def test_conftest_applicability_keeps_dynamic_consumption_unknown(
    tmp_path: Path,
) -> None:
    files = {
        "tests/conftest.py": "import pytest\n@pytest.fixture\ndef value(): return 1\n",
        "tests/test_value.py": "def test_value(value): assert value == 1\n",
        "other/test_value.py": "def test_value(): pass\n",
    }
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["tests/conftest.py"])
    assert _target_paths(packet) == ["tests/test_value.py"]
    change = assert_records(packet["changes"])[0]
    assert assert_object(change["classification"])["kind"] == "verification-support"
    assert (
        assert_object(change["consumer_scope"])["negative_evidence_admissible"] is False
    )
    assert any(
        row["relation_kind"] == "pytest-conftest-scope"
        for row in assert_records(change["relationships"])
    )


def test_structural_file_read_uses_existing_reader_evidence(tmp_path: Path) -> None:
    files = {
        "settings.json": '{"enabled": true}',
        "tests/test_settings.py": 'from pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\ndef test_settings():\n    assert (ROOT / "settings.json").read_text()\n',
    }
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["settings.json"])
    assert _target_paths(packet) == ["tests/test_settings.py"]
    change = assert_records(packet["changes"])[0]
    relationship = assert_records(change["relationships"])[0]
    assert assert_object(relationship["reference_evidence"])["file_read_evidence"]
    assert packet["negative_evidence_admissible"] is False


def test_nested_frontend_target_uses_qualified_local_manifest(tmp_path: Path) -> None:
    files = {
        "package.json": '{"name":"root"}',
        "frontend/package.json": '{"name":"ui","devDependencies":{"vitest":"^3"}}',
        "frontend/src/total.test.ts": 'import { test } from "vitest";\ntest("total", () => {});\n',
    }
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["frontend/src/total.test.ts"])
    target = assert_records(packet["targets"])[0]
    nomination = assert_object(target["nomination"])
    assert nomination["available"] is True
    assert nomination["runner_evidence"] == "vitest"
    assert "frontend/package.json" in {
        row["path"] for row in assert_records(nomination["supporting_source_members"])
    }
    _assert_no_execution(packet)


def test_projection_bound_never_means_exhaustive_membership(tmp_path: Path) -> None:
    files = {"owner.py": "def total(): return 1\n"}
    files.update(
        {
            f"tests/test_{number:02}.py": "from owner import total\ndef test_total(): assert total() == 1\n"
            for number in range(20)
        }
    )
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["owner.py"], limit=2)
    assert len(_target_paths(packet)) == 2
    assert packet["truncated"] is True
    assert packet["completeness"] == "incomplete"
    scope = assert_object(assert_records(packet["changes"])[0]["consumer_scope"])
    assert assert_integer(scope["omitted_reference_candidates"]) > 0
    assert scope["negative_evidence_admissible"] is False


def test_no_verifier_missing_and_unsupported_sources_do_not_prove_negative(
    tmp_path: Path,
) -> None:
    files = {
        "owner.py": "def total(): return 1\n",
        "tests/test_bad.py": "def test_bad(:\n",
    }
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(
            ["owner.py", "missing.py", "tests/test_bad.py"]
        )
    assert packet["membership"] is None
    assert packet["targets"] == []
    assert packet["negative_evidence_admissible"] is False
    changes = {row["path"]: row for row in assert_records(packet["changes"])}
    assert (
        assert_object(changes["tests/test_bad.py"]["classification"])["kind"]
        == "unknown"
    )
    assert (
        assert_object(assert_object(changes["missing.py"]["source"])["member"])["state"]
        == "known-absent"
    )


def test_ambiguous_import_owner_is_preserved_in_changed_scope(tmp_path: Path) -> None:
    files = {
        "pkg/__init__.py": "from .left import total\nfrom .right import total\n",
        "pkg/left.py": "def total(): return 1\n",
        "pkg/right.py": "def total(): return 2\n",
        "tests/test_total.py": "from pkg import total\ndef test_total(): assert total()\n",
    }
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["pkg/left.py"])
    scope = assert_object(assert_records(packet["changes"])[0]["consumer_scope"])
    assert scope["qualified_identity_ambiguous"] is True
    assert packet["membership"] is None
    assert packet["negative_evidence_admissible"] is False


def test_source_drift_recomputes_and_retained_nomination_detects_mismatch(
    tmp_path: Path,
) -> None:
    with _repository(tmp_path, _ordinary_files()) as repository:
        before = repository.verification.changed_set(["owner.py"])
        old = assert_object(assert_records(before["targets"])[0]["nomination"])
        (repository.workspace / "tests/test_total.py").write_text(
            "def test_other(): pass\n"
        )
        after = repository.verification.changed_set(["owner.py"])
        binding = repository.verification.observe_nomination_source_binding(old)
    assert _target_paths(after) == []
    assert before["evidence_identity"] != after["evidence_identity"]
    assert binding["source_binding_state"] == "mismatch"


def test_same_question_order_and_reopen_preserve_identity(tmp_path: Path) -> None:
    with _repository(tmp_path, _ordinary_files()) as repository:
        before = repository.verification.changed_set(
            ["owner.py", "tests/test_total.py"]
        )
        again = repository.verification.changed_set(
            ["tests/test_total.py", "owner.py", "owner.py"]
        )
        assert before == again
    with CodeMap(tmp_path / "repository", state_dir=tmp_path / "state") as reopened:
        after = reopened.verification.changed_set(["owner.py", "tests/test_total.py"])
    assert before == after
    assert before["evidence_identity"] == evidence_identity(
        "hashmarks.changed-set-verification.v1",
        {key: value for key, value in before.items() if key != "evidence_identity"},
    )


@pytest.mark.parametrize(
    "paths,limit",
    [
        ("owner.py", 1),
        (["../outside.py"], 1),
        (["owner.py"], 0),
        (["owner.py"], True),
        (["owner.py"] * 257, 1),
    ],
)
def test_changed_set_rejects_invalid_paths_and_bounds(
    tmp_path: Path, paths: object, limit: object
) -> None:
    with _repository(tmp_path, _ordinary_files()) as repository:
        with pytest.raises(ValueError):
            repository.verification.changed_set(
                cast(Sequence[str], paths), limit=cast(int, limit)
            )


def test_changed_set_reuses_canonical_native_owner_and_never_legacy_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _repository(tmp_path, _ordinary_files()) as repository:
        assert repository.verification.native is repository.native

        def forbidden(*args: object, **kwargs: object) -> None:
            raise AssertionError("legacy command projection must not be consulted")

        monkeypatch.setattr(repository.verification, "plan", forbidden)
        packet = repository.verification.changed_set(["owner.py"])
    assert _target_paths(packet) == ["tests/test_total.py"]
