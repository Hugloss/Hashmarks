from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from contract_assertions import assert_object

from hashmarks import validate_repository_intelligence_evidence
from hashmarks.codemap import CodeMap
from hashmarks.codemap.filesystem_lifecycle_contract import (
    DEFAULT_BOUNDS,
    lifecycle_identity,
    validate_lifecycle_observation,
)
from hashmarks.codemap.ownership.filesystem_lifecycle import FilesystemLifecycleAnalyzer
from hashmarks.evidence_presentation import present_repository_evidence


def _repository(root: Path, source: str) -> None:
    (root / "cleanup.py").write_text(source, encoding="utf-8")


def _observe(root: Path, source: str) -> dict:
    _repository(root, source)
    with CodeMap(root) as codemap:
        codemap.sync()
        return codemap.repository_findings(["cleanup.py"])


def test_parent_binding_is_not_child_identity_and_guards_do_not_hide_evidence(
    tmp_path: Path,
) -> None:
    result = _observe(
        tmp_path,
        """import os
def cleanup(name, parent_fd, lock):
    with lock:
        checked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if checked.st_ino:
            os.rmdir(name, dir_fd=parent_fd)
""",
    )
    packet = result["resource_lifecycle"]
    assert validate_lifecycle_observation(packet) == packet
    observation = packet["observations"][0]
    assert observation["check"]["api"] == "os.stat"
    assert observation["use"]["api"] == "os.rmdir"
    assert observation["use"]["parent_binding"] == "conditional-relative-path"
    assert observation["namespace_binding"] == "same-source-dir-fd-reference"
    assert observation["runtime_identity"] == "unverified"
    assert observation["use"]["guards"][0]["property"] == "lexical-context-only"
    findings = [
        row for row in result["findings"] if row["category"] == "resource-lifecycle"
    ]
    assert len(findings) == 1
    assert "actionability" not in findings[0]["interpretation"]
    assert packet["coverage"]["negative_evidence_admissible"] is False


@pytest.mark.parametrize(
    "source",
    [
        "import os as system\ndef cleanup(name):\n system.lstat(name)\n system.unlink(name)\n",
        "from os import stat as inspect, rmdir as remove\ndef cleanup(name):\n inspect(name)\n remove(name)\n",
        "from pathlib import Path\ndef cleanup(name):\n p=Path(name)\n p.stat()\n p.rmdir()\n",
        "import os\ndef cleanup(name):\n checked=name\n os.stat(checked)\n os.rmdir(name)\n",
    ],
)
def test_qualified_aliases_preserve_source_reference(
    tmp_path: Path, source: str
) -> None:
    packet = _observe(tmp_path, source)["resource_lifecycle"]
    assert packet["observations"]
    assert all(
        row["relationship"] == "same-source-reference" for row in packet["observations"]
    )


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef cleanup(first,second):\n os.stat(first)\n os.rmdir(second)\n",
        "import os\ndef cleanup(name):\n os.stat(name)\n name='different'\n os.rmdir(name)\n",
        "import os\ndef cleanup(os,name):\n os.stat(name)\n os.rmdir(name)\n",
        "import os\ndef cleanup(name,condition):\n if condition:\n  os.stat(name)\n else:\n  os.rmdir(name)\n",
        "import os\ndef cleanup(name):\n os.stat(name)\n return\n os.rmdir(name)\n",
        "import os\ndef cleanup(name):\n os = object()\n os.stat(name)\n os.rmdir(name)\n",
        "import os\ndef cleanup(fd,name):\n os.fstat(fd)\n os.rmdir(name)\n",
        "import os\ndef cleanup(name):\n name=os.stat(name)\n os.rmdir(name)\n",
        "import os\ndef cleanup(name):\n os.stat(name)\n for name in ['other']:\n  pass\n os.rmdir(name)\n",
        "import os\ndef cleanup(name,c):\n c and os.stat(name)\n os.rmdir(name)\n",
    ],
)
def test_near_misses_do_not_become_exact_relationships(
    tmp_path: Path, source: str
) -> None:
    assert _observe(tmp_path, source)["resource_lifecycle"]["observations"] == []


@pytest.mark.parametrize(
    ("name", "expected"),
    [("/absolute", "ignored-absolute-path"), ("child", "relative-path")],
)
def test_literal_path_qualifies_descriptor_interpretation(
    tmp_path: Path, name: str, expected: str
) -> None:
    result = _observe(
        tmp_path,
        f"import os\ndef cleanup(parent):\n os.stat({name!r},dir_fd=parent)\n os.rmdir({name!r},dir_fd=parent)\n",
    )
    assert (
        result["resource_lifecycle"]["observations"][0]["use"]["parent_binding"]
        == expected
    )


def test_rename_destination_is_distinct_from_source(tmp_path: Path) -> None:
    result = _observe(
        tmp_path,
        "import os\ndef cleanup(source,destination):\n os.stat(destination)\n os.rename(source,destination)\n",
    )
    observations = result["resource_lifecycle"]["observations"]
    assert len(observations) == 1
    assert observations[0]["use"]["operand_role"] == "destination"


def test_cross_module_forwarding_uses_canonical_calls(tmp_path: Path) -> None:
    (tmp_path / "checks.py").write_text(
        "import os\ndef verify(name,parent):\n return os.stat(name,dir_fd=parent)\n",
        encoding="utf-8",
    )
    (tmp_path / "backend.py").write_text(
        "import os\ndef remove(name,parent):\n os.rmdir(name,dir_fd=parent)\n",
        encoding="utf-8",
    )
    result = _observe(
        tmp_path,
        "from checks import verify\nfrom backend import remove\ndef cleanup(name,parent):\n checked=verify(name,parent)\n remove(name,parent)\n",
    )
    packet = result["resource_lifecycle"]
    observation = next(
        row for row in packet["observations"] if row["check"]["path"] == "checks.py"
    )
    assert observation["use"]["path"] == "backend.py"
    assert observation["check"]["call_chain"][0]["target"] == "checks.py::verify"
    assert observation["use"]["call_chain"][0]["target"] == "backend.py::remove"
    assert set(packet["source_revisions"]) == {"cleanup.py", "checks.py", "backend.py"}


def test_bounded_discovery_retains_accounting_without_negative_evidence(
    tmp_path: Path,
) -> None:
    _repository(
        tmp_path, "import os\ndef cleanup(name):\n os.stat(name)\n os.rmdir(name)\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        bounds = replace(DEFAULT_BOUNDS, observations=0)
        packet = FilesystemLifecycleAnalyzer(codemap, bounds).analyze(["cleanup.py"])
    assert packet["observations"] == []
    assert packet["accounting"]["omitted"] == 1
    assert packet["coverage"]["truncated"] is True
    assert packet["coverage"]["negative_evidence_admissible"] is False


def test_invalid_and_missing_sources_are_accounted_for(tmp_path: Path) -> None:
    _repository(tmp_path, "def invalid(:\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = FilesystemLifecycleAnalyzer(codemap).analyze(
            ["cleanup.py", "missing.py"]
        )
    assert packet["coverage"]["completeness"] == "incomplete"
    assert packet["accounting"]["failed_paths"] == 2
    assert {row["path"] for row in packet["unresolved"]} == {"cleanup.py", "missing.py"}


def test_consumer_validator_rejects_tamper_and_authority_escalation(
    tmp_path: Path,
) -> None:
    packet = _observe(
        tmp_path, "import os\ndef cleanup(name):\n os.stat(name)\n os.rmdir(name)\n"
    )["resource_lifecycle"]
    assert (
        validate_repository_intelligence_evidence(json.loads(json.dumps(packet)))[
            "valid"
        ]
        is True
    )
    tampered = deepcopy(packet)
    tampered["observations"][0]["runtime_identity"] = "proven"
    tampered["observation_identity"] = lifecycle_identity(tampered)
    assert validate_repository_intelligence_evidence(tampered)["valid"] is False
    tampered = deepcopy(packet)
    tampered["operations"][0]["member_revision"] = "different"
    tampered["observation_identity"] = lifecycle_identity(tampered)
    assert validate_repository_intelligence_evidence(tampered)["valid"] is False


def test_public_surfaces_preserve_lifecycle_and_freshness(tmp_path: Path) -> None:
    source = "import os\ndef cleanup(name):\n os.stat(name)\n os.rmdir(name)\n"
    _repository(tmp_path, source)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        findings = codemap.repository_findings(["cleanup.py"])
        locality = codemap.structural_locality("cleanup.py::cleanup")
        task = codemap.task_evidence("inspect cleanup.py cleanup")
        assert assert_object(locality["resource_lifecycle"])["observations"]
        assert assert_object(task["related"].get("resource_lifecycle"))["observations"]
        packet = assert_object(findings["resource_lifecycle"])
        assert (
            codemap.repository_findings(["cleanup.py"])["resource_lifecycle"] == packet
        )
        _repository(tmp_path, "def cleanup(name):\n return name\n")
        changed = assert_object(
            codemap.repository_findings(["cleanup.py"])["resource_lifecycle"]
        )
        assert changed["observations"] == []
        assert changed["observation_identity"] != packet["observation_identity"]
    projection = present_repository_evidence(findings)
    assert "unverified" in json.dumps(projection)
    assert "resource_lifecycle" in json.dumps(projection)


def test_reopen_uses_current_source_not_prior_observations(tmp_path: Path) -> None:
    _repository(
        tmp_path, "import os\ndef cleanup(name):\n os.stat(name)\n os.rmdir(name)\n"
    )
    state = tmp_path / ".state"
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.sync()
        assert assert_object(codemap.repository_findings()["resource_lifecycle"])[
            "observations"
        ]
    _repository(tmp_path, "def cleanup(name):\n return name\n")
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.sync()
        assert (
            assert_object(codemap.repository_findings()["resource_lifecycle"])[
                "observations"
            ]
            == []
        )


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef cleanup(name,other):\n os.stat(name)\n os.rmdir=other\n os.rmdir(name)\n",
        "import os\ndef cleanup(name,other):\n os.stat(name)\n setattr(os,'rmdir',other)\n os.rmdir(name)\n",
        "import os\nasync def verify(name):\n os.stat(name)\ndef cleanup(name):\n verify(name)\n os.rmdir(name)\n",
        "import os\ndef verify(a,b):\n os.stat(a)\ndef cleanup(name):\n verify(name)\n os.rmdir(name)\n",
        "import os\ndef verify(a,b):\n os.stat(b)\ndef cleanup(args,name):\n verify(*args,name)\n os.rmdir(name)\n",
        "import os\ndef cleanup(name):\n def mutate():\n  nonlocal name\n  name='other'\n os.stat(name)\n mutate()\n os.rmdir(name)\n",
    ],
)
def test_dynamic_api_and_forwarding_uncertainty_is_preserved(
    tmp_path: Path, source: str
) -> None:
    packet = _observe(tmp_path, source)["resource_lifecycle"]
    assert packet["observations"] == []
    assert packet["coverage"]["completeness"] == "incomplete"


def test_module_level_operations_and_local_import_aliases(tmp_path: Path) -> None:
    source = "import os\nname='child'\nos.stat(name)\nos.rmdir(name)\ndef cleanup(name):\n from os import stat as inspect, rmdir as remove\n inspect(name)\n remove(name)\n"
    packet = _observe(tmp_path, source)["resource_lifecycle"]
    assert {row["use"]["symbol"] for row in packet["observations"]} == {
        "<module>",
        "cleanup",
    }


def test_unsupported_exception_paths_retain_operations_without_fabricated_sequence(
    tmp_path: Path,
) -> None:
    packet = _observe(
        tmp_path,
        "import os\ndef cleanup(name):\n try:\n  os.stat(name)\n except OSError:\n  os.rmdir(name)\n",
    )["resource_lifecycle"]
    assert {row["api"] for row in packet["operations"]} == {"os.stat", "os.rmdir"}
    assert packet["observations"] == []
    assert packet["coverage"]["completeness"] == "incomplete"


def test_visibility_denied_support_never_leaks_into_lifecycle(tmp_path: Path) -> None:
    (tmp_path / "hidden").mkdir()
    (tmp_path / "hidden" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "hidden" / "backend.py").write_text(
        "import os\ndef remove(name):\n os.rmdir(name)\n", encoding="utf-8"
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "hidden/**"\nvisibility = "deny"\n', encoding="utf-8"
    )
    result = _observe(
        tmp_path,
        "import os\nfrom hidden.backend import remove\ndef cleanup(name):\n os.stat(name)\n remove(name)\n",
    )
    assert "hidden/backend.py" not in json.dumps(result["resource_lifecycle"])
    assert result["resource_lifecycle"]["observations"] == []


def test_mutator_and_verifier_evidence_remains_positive_relevance(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_cleanup.py").write_text(
        "from cleanup import cleanup\ndef test_cleanup():\n cleanup('child')\n",
        encoding="utf-8",
    )
    packet = _observe(
        tmp_path,
        "import os\ndef cleanup(name):\n os.stat(name)\n os.mkdir(name)\n os.rmdir(name)\n",
    )["resource_lifecycle"]
    observation = packet["observations"][0]
    assert observation["mutation_evidence"][0]["api"] == "os.mkdir"
    assert "tests/test_cleanup.py" in observation["verification"]["paths"]
    assert observation["verification"]["completeness"] == "not-claimed"


def test_bounds_cannot_be_relabelled_complete(tmp_path: Path) -> None:
    _repository(
        tmp_path, "import os\ndef cleanup(name):\n os.stat(name)\n os.rmdir(name)\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = FilesystemLifecycleAnalyzer(
            codemap, replace(DEFAULT_BOUNDS, observations=0)
        ).analyze(["cleanup.py"])
    packet["coverage"]["completeness"] = "complete-within-supported-scope"
    packet["observation_identity"] = lifecycle_identity(packet)
    assert validate_repository_intelligence_evidence(packet)["valid"] is False


def test_call_budget_covers_repeated_helper_contexts(tmp_path: Path) -> None:
    _repository(
        tmp_path,
        "from helper import remove\ndef cleanup():\n remove('first')\n remove('second')\n",
    )
    (tmp_path / "helper.py").write_text(
        "import os\ndef remove(name):\n os.stat(name)\n os.rmdir(name)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = FilesystemLifecycleAnalyzer(
            codemap, replace(DEFAULT_BOUNDS, calls_per_symbol=2)
        ).analyze(["cleanup.py"])
    assert len(packet["observations"]) == 1
    assert (
        assert_object(packet["observations"][0]["use"])["reference"]
        == "literal:'first'"
    )
    assert any(row["reason"] == "call-limit" for row in packet["unresolved"])
    assert packet["coverage"]["truncated"] is True
    assert packet["coverage"]["completeness"] == "incomplete"
    assert packet["coverage"]["negative_evidence_admissible"] is False


def test_distinct_factory_invocations_do_not_share_resource_identity(
    tmp_path: Path,
) -> None:
    packet = _observe(
        tmp_path,
        "from pathlib import Path\ndef make(name):\n return Path(name)\ndef cleanup(first,second):\n a=make(first)\n b=make(second)\n a.stat()\n b.rmdir()\n",
    )["resource_lifecycle"]
    assert packet["observations"] == []


def test_cyclic_reexport_remains_unresolved(tmp_path: Path) -> None:
    (tmp_path / "first.py").write_text("from second import remove\n", encoding="utf-8")
    (tmp_path / "second.py").write_text("from first import remove\n", encoding="utf-8")
    packet = _observe(
        tmp_path,
        "import os\nfrom first import remove\ndef cleanup(name):\n os.stat(name)\n remove(name)\n",
    )["resource_lifecycle"]
    assert packet["observations"] == []
    assert packet["unresolved"]


def test_explicit_metadata_comparison_is_source_evidence_not_atomic_child_binding(
    tmp_path: Path,
) -> None:
    packet = _observe(
        tmp_path,
        "import os\ndef cleanup(name,parent,child_fd):\n checked=os.stat(name,dir_fd=parent)\n expected=os.fstat(child_fd)\n if (checked.st_dev,checked.st_ino)==(expected.st_dev,expected.st_ino):\n  os.rmdir(name,dir_fd=parent)\n",
    )["resource_lifecycle"]
    observation = packet["observations"][0]
    assert (
        observation["identity_comparisons"][0]["qualification"] == "source-syntax-only"
    )
    assert observation["identity_comparisons"][0]["operators"] == ["Eq"]
    assert observation["runtime_identity"] == "unverified"


def test_explicit_stdlib_reexport_uses_current_facade_evidence(tmp_path: Path) -> None:
    (tmp_path / "facade.py").write_text(
        "from os import stat, rmdir\n", encoding="utf-8"
    )
    packet = _observe(
        tmp_path,
        "from facade import stat, rmdir\ndef cleanup(name):\n stat(name)\n rmdir(name)\n",
    )["resource_lifecycle"]
    assert packet["observations"]
    assert "facade.py" in packet["source_revisions"]
