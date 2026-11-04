from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import packaging
import pytest

from hashmarks.codemap.dependency_version_predicates import (
    normalize_version_predicate,
    prepare_version_predicate,
)


@pytest.mark.parametrize(
    ("version", "expression", "expected"),
    [
        ("1.2.3", ">=1.0,<2.0", "match"),
        ("2.0", ">=1.0,<2.0", "nonmatch"),
        ("1.2", "==1.2.0", "match"),
        ("1.2.3", "~=1.2", "match"),
        ("2.0", "~=1.2", "nonmatch"),
        ("1!1.2", ">=1!1.0,<2!0", "match"),
        ("1.0.post1", ">1.0", "nonmatch"),
        ("1.0.post1", ">=1.0.post1", "match"),
        ("1.0+vendor.2", "==1.0", "match"),
        ("1.0+vendor.2", "==1.0+vendor.1", "nonmatch"),
        ("1.0+vendor.2", "==1.0+vendor.2", "match"),
        ("unknown", ">=1", "unclassified"),
        ("1.2.3.unknown", ">=1", "unclassified"),
    ],
)
def test_python_versions_use_native_pep440(
    version: str, expression: str, expected: str
) -> None:
    prepared = prepare_version_predicate(
        "pypi", {"dialect": "pep440", "expression": expression}
    )
    assert prepared.classify(version)["state"] == expected
    assert prepared.evidence["availability"] == "supported"


def test_python_prerelease_choice_is_explicit_and_changes_identity() -> None:
    request = {"dialect": "pep440", "expression": ">=1.0,<2.0"}
    excluded = prepare_version_predicate("pypi", request)
    included = prepare_version_predicate("pypi", {**request, "prereleases": True})
    assert excluded.request["prereleases"] is False
    assert excluded.classify("1.1a1")["state"] == "nonmatch"
    assert included.classify("1.1a1")["state"] == "match"
    assert (
        excluded.evidence["predicate_identity"]
        != included.evidence["predicate_identity"]
    )


def test_python_arbitrary_legacy_versions_are_unclassified() -> None:
    prepared = prepare_version_predicate(
        "pypi", {"dialect": "pep440", "expression": "===private-build"}
    )
    assert prepared.classify("private-build") == {
        "state": "unclassified",
        "reason": "unsupported-version",
    }


def test_same_range_text_keeps_its_ecosystem_dialect() -> None:
    python = prepare_version_predicate(
        "pypi", {"dialect": "pep440", "expression": "~=1.0"}
    )
    npm = prepare_version_predicate(
        "npm", {"dialect": "npm-semver", "expression": "~=1.0"}
    )
    assert python.classify("1.2.3")["state"] == "match"
    assert npm.classify("1.2.3")["state"] == "nonmatch"
    assert npm.classify("1.0.1")["state"] == "match"
    assert python.evidence["predicate_identity"] != npm.evidence["predicate_identity"]


def test_native_interpreter_version_changes_predicate_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = {"dialect": "pep440", "expression": ">=1.0"}
    before = prepare_version_predicate("pypi", request)
    monkeypatch.setattr(packaging, "__version__", packaging.__version__ + ".different")
    after = prepare_version_predicate("pypi", request)
    assert before.request == after.request
    assert before.evidence["predicate_identity"] != after.evidence["predicate_identity"]


@pytest.mark.parametrize(
    ("version", "expression", "expected"),
    [
        ("1.5.0", "^1.2.3", "match"),
        ("2.0.0", "^1.2.3", "nonmatch"),
        ("0.2.9", "^0.2.3", "match"),
        ("0.3.0", "^0.2.3", "nonmatch"),
        ("1.2.9", "~1.2.3", "match"),
        ("1.3.0", "~1.2.3", "nonmatch"),
        ("3.2.1", "1.x || >=3.0.0", "match"),
        ("2.0.0", "1.x || >=3.0.0", "nonmatch"),
        ("2.3.4", "1.2.3 - 2.3.4", "match"),
        ("2.3.5", "1.2.3 - 2.3.4", "nonmatch"),
        ("1.3.0-beta.1", "^1.2.3", "nonmatch"),
        ("1.2.3-beta.2", ">=1.2.3-beta.1 <2.0.0", "match"),
        ("1.3.0-beta.1", ">=1.2.3-beta.1 <2.0.0", "nonmatch"),
        ("1.2.3+build.7", "1.2.3", "match"),
        ("1.2.3+build.7", "=1.2.3+other", "match"),
        ("v1.2.3", "^1.2.0", "match"),
        ("1.2", "^1.2.0", "unclassified"),
        ("9007199254740992.0.0", "*", "unclassified"),
        ("1.2.3+" + "x" * 256, "*", "unclassified"),
        ("1.2.3-9007199254740993", "*", "unclassified"),
        ("1!1.2.3", "*", "unclassified"),
        ("unknown", "*", "unclassified"),
    ],
)
def test_npm_versions_use_native_npm_ranges(
    version: str, expression: str, expected: str
) -> None:
    prepared = prepare_version_predicate(
        "npm", {"dialect": "npm-semver", "expression": expression}
    )
    assert prepared.classify(version)["state"] == expected
    assert prepared.evidence["availability"] == "supported"


@pytest.mark.parametrize(
    ("ecosystem", "predicate", "reason"),
    [
        ("maven", {"dialect": "pep440", "expression": ">=1"}, "unsupported-ecosystem"),
        (
            "pypi",
            {"dialect": "npm-semver", "expression": "^1.0.0"},
            "dialect-ecosystem-mismatch",
        ),
        (
            "npm",
            {"dialect": "pep440", "expression": ">=1"},
            "dialect-ecosystem-mismatch",
        ),
        ("pypi", {"dialect": "future", "expression": ">=1"}, "unsupported-dialect"),
        ("pypi", {"dialect": "pep440", "expression": "^1.0"}, "unsupported-expression"),
        (
            "npm",
            {"dialect": "npm-semver", "expression": "not-a-range"},
            "unsupported-expression",
        ),
        (
            "npm",
            {"dialect": "npm-semver", "expression": ">=9007199254740992.0.0"},
            "unsupported-expression",
        ),
        (
            "npm",
            {"dialect": "npm-semver", "expression": ">1.2.3-9007199254740992"},
            "unsupported-expression",
        ),
        (
            "npm",
            {"dialect": "npm-semver", "expression": "1.2.3+" + "x" * 256},
            "unsupported-expression",
        ),
    ],
)
def test_unqualified_predicates_do_not_become_nonmatches(
    ecosystem: str, predicate: Mapping[str, object], reason: str
) -> None:
    prepared = prepare_version_predicate(ecosystem, predicate)
    assert prepared.evidence["availability"] == "unsupported"
    assert prepared.classify("1.2.3") == {"state": "unclassified", "reason": reason}


@pytest.mark.parametrize(
    "predicate_input",
    [
        None,
        [],
        {},
        {"dialect": "pep440", "expression": 123},
        {"dialect": "pep440", "expression": False},
        {"dialect": "pep440", "expression": ">=1", "extra": True},
        {"dialect": "pep440", "expression": ">=1", "prereleases": 1},
        {"dialect": "npm-semver", "expression": "*", "prereleases": False},
        {"dialect": "pep440", "expression": " " * 4096 + ">=1"},
    ],
)
def test_invalid_request_shapes_refuse_before_interpretation(
    predicate_input: object,
) -> None:
    with pytest.raises(ValueError):
        prepare_version_predicate("pypi", predicate_input)


@pytest.mark.parametrize(
    "ecosystem,dialect", [("pypi", "pep440"), ("npm", "npm-semver")]
)
def test_explicit_empty_native_predicates_mean_any_stable_version(
    ecosystem: str, dialect: str
) -> None:
    prepared = prepare_version_predicate(
        ecosystem, {"dialect": dialect, "expression": ""}
    )
    assert prepared.classify("1.2.3")["state"] == "match"
    assert prepared.classify("1.2.3-alpha.1")["state"] == "nonmatch"


def test_predicate_evidence_binds_engine_and_caller_text_without_aliasing() -> None:
    original = {"dialect": "pep440", "expression": " >=1.0, <2.0 "}
    prepared = prepare_version_predicate("pypi", original)
    original["expression"] = "<1"
    request = prepared.request
    evidence = prepared.evidence
    request["expression"] = "<1"
    cast("dict[str, object]", evidence["engine"])["version"] = "different"
    assert prepared.request["expression"] == " >=1.0, <2.0 "
    assert prepared.classify("1.5.0")["state"] == "match"
    assert prepared.evidence != evidence
    engine = cast("Mapping[str, object]", prepared.evidence["engine"])
    assert engine["name"] == "packaging"
    assert isinstance(engine["version"], str)
    assert prepared.evidence["predicate_identity"]
    assert normalize_version_predicate(prepared.request) == prepared.request
