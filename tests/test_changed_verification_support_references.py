"""Test support participates in the existing bounded reference traversal."""

from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records
from test_changed_set_verification import _repository, _target_paths


def test_changed_source_reaches_verifier_through_shared_test_factory(
    tmp_path: Path,
) -> None:
    files = {
        "owner.py": "def total(): return 1\n",
        "tests/__init__.py": "",
        "tests/helpers.py": "from owner import total\ndef build(): return total()\n",
        "tests/test_build.py": "from tests.helpers import build\ndef test_build(): assert build() == 1\n",
    }
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["owner.py"])
    assert _target_paths(packet) == ["tests/test_build.py"]
    change = assert_records(packet["changes"])[0]
    relation = assert_records(change["relationships"])[0]
    assert relation["relation_kind"] == "bounded-indirect-reference"
    assert assert_object(relation["reference_evidence"])["indirect_via_paths"] == [
        "tests/helpers.py"
    ]
    assert {
        member["path"]
        for member in assert_records(relation["supporting_source_members"])
    } == {"owner.py", "tests/helpers.py", "tests/test_build.py"}
    assert "tests/helpers.py" not in _target_paths(packet)


def test_test_helper_hop_keeps_qualified_import_owner_identity(tmp_path: Path) -> None:
    files = {
        "owner.py": "def total(): return 1\n",
        "tests/__init__.py": "",
        "tests/helpers.py": "from owner import total\ndef build(): return total()\n",
        "tests/unrelated.py": "def build(): return 2\n",
        "tests/test_right.py": "from tests.helpers import build\ndef test_right(): assert build() == 1\n",
        "tests/test_wrong.py": "from tests.unrelated import build\ndef test_wrong(): assert build() == 2\n",
    }
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["owner.py"])
    assert _target_paths(packet) == ["tests/test_right.py"]
    change = assert_records(packet["changes"])[0]
    assert {row["target"] for row in assert_records(change["relationships"])} == {
        "tests/test_right.py"
    }


def test_shared_support_does_not_extend_the_existing_indirect_depth(
    tmp_path: Path,
) -> None:
    files = {
        "owner.py": "def total(): return 1\n",
        "tests/__init__.py": "",
        "tests/first.py": "from owner import total\ndef first(): return total()\n",
        "tests/second.py": "from tests.first import first\ndef second(): return first()\n",
        "tests/test_second.py": "from tests.second import second\ndef test_second(): assert second() == 1\n",
    }
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["owner.py"])
    assert _target_paths(packet) == []
    assert packet["negative_evidence_admissible"] is False
    assert packet["completeness"] != "complete"


def test_support_path_roles_are_reused_only_within_one_reference_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {
        "owner.py": "def left(): return 1\ndef right(): return 2\n",
        "tests/__init__.py": "",
        "tests/helpers.py": (
            "from owner import left, right\ndef build(): return left() + right()\n"
        ),
        "tests/test_build.py": "from tests.helpers import build\ndef test_build(): assert build() == 3\n",
    }
    with _repository(tmp_path, files) as repository:
        original = repository.verification._verification_path_kind
        observed: list[str] = []

        def observe(path: str, *, reconcile: bool = True) -> dict[str, object]:
            observed.append(path)
            return original(path, reconcile=reconcile)

        monkeypatch.setattr(repository.verification, "_verification_path_kind", observe)
        with repository.reads.session():
            repository.verification._changed_relevance("owner.py", 16)
        assert observed.count("tests/helpers.py") == 1
        with repository.reads.session():
            repository.verification._changed_relevance("owner.py", 16)
        assert observed.count("tests/helpers.py") == 2


def test_shared_support_paths_preserve_existing_intermediate_bound(
    tmp_path: Path,
) -> None:
    files = {"owner.py": "def total(): return 1\n", "tests/__init__.py": ""}
    files.update(
        {
            f"tests/helper_{number:02}.py": (
                f"from owner import total\ndef build_{number:02}(): return total()\n"
            )
            for number in range(65)
        }
    )
    files["tests/test_omitted.py"] = (
        "from tests.helper_64 import build_64\n"
        "def test_omitted(): assert build_64() == 1\n"
    )
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["owner.py"])
    change = assert_records(packet["changes"])[0]
    relevance = assert_object(change["relevance"])
    assert "indirect-source-path-limit" in assert_array(
        relevance["search_bound_reasons"]
    )
    assert packet["truncated"] is True
    assert packet["negative_evidence_admissible"] is False
    assert "tests/test_omitted.py" not in _target_paths(packet)
