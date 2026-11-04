"""Qualified ecosystem predicates over supplied versions, without resolution."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from importlib.metadata import version as distribution_version
from typing import cast

import nodesemver
import packaging
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .dependency_resolution_contract import normalized_text
from .repository_observation import evidence_identity

PREDICATE_SCHEMA = "hashmarks.dependency-version-predicate.v1"
PREDICATE_SEMANTICS = "hashmarks.dependency-version-predicate-semantics.v1"
_MAX_EXPRESSION_CHARS = 4096
_FIELDS = frozenset({"dialect", "expression", "prereleases"})
_NPM_MAX_VERSION_CHARS = 256
_NPM_MAX_NUMERIC_IDENTIFIER = 9_007_199_254_740_991


def normalize_version_predicate(value: object) -> dict[str, object]:
    """Validate caller syntax without interpreting or weakening its predicate."""
    if not isinstance(value, Mapping) or set(value) - _FIELDS:
        raise ValueError("version predicate must contain only declared fields")
    dialect = normalized_text(
        value.get("dialect"), label="version predicate dialect", required=True
    )
    expression = value.get("expression")
    if not isinstance(expression, str) or len(expression) > _MAX_EXPRESSION_CHARS:
        raise ValueError("version predicate expression requires bounded text")
    request: dict[str, object] = {"dialect": dialect, "expression": expression}
    if "prereleases" in value and dialect != "pep440":
        raise ValueError("prereleases is valid only for a pep440 predicate")
    if dialect == "pep440":
        prereleases = value.get("prereleases", False)
        if type(prereleases) is not bool:
            raise ValueError("version predicate prereleases must be a boolean")
        request["prereleases"] = prereleases
    return request


def _engine(dialect: str) -> dict[str, object]:
    if dialect == "pep440":
        return {
            "name": "packaging",
            "version": packaging.__version__,
            "operation": "SpecifierSet.contains",
        }
    if dialect == "npm-semver":
        return {
            "name": "node-semver",
            "version": distribution_version("node-semver"),
            "operation": "Range.test",
            "profile": {
                "name": "node-semver-parsed-bounds.v1",
                "max_version_chars": _NPM_MAX_VERSION_CHARS,
                "max_numeric_identifier": _NPM_MAX_NUMERIC_IDENTIFIER,
                "micro_versions": "unsupported",
            },
        }
    return {"name": "unsupported", "version": None, "operation": None}


def _unsupported_predicate_reason(ecosystem: str, dialect: str) -> str | None:
    expected = {"pypi": "pep440", "npm": "npm-semver"}
    if ecosystem not in expected:
        return "unsupported-ecosystem"
    if dialect not in {"pep440", "npm-semver"}:
        return "unsupported-dialect"
    if dialect != expected[ecosystem]:
        return "dialect-ecosystem-mismatch"
    return None


def _native_matcher(
    ecosystem: str, request: Mapping[str, object]
) -> tuple[SpecifierSet | nodesemver.Range | None, str | None]:
    dialect = str(request["dialect"])
    unsupported = _unsupported_predicate_reason(ecosystem, dialect)
    if unsupported is not None:
        return None, unsupported
    expression = str(request["expression"])
    if dialect == "pep440":
        try:
            return SpecifierSet(expression), None
        except InvalidSpecifier:
            return None, "unsupported-expression"
    try:
        matcher = nodesemver.Range(expression, loose=False)
    except ValueError:
        return None, "unsupported-expression"
    if not matcher.set or not all(
        term.semver is nodesemver.ANY or _npm_version_supported(term.semver)
        for terms in matcher.set
        for term in terms
    ):
        return None, "unsupported-expression"
    return matcher, None


def _npm_identifier_supported(identifier: object) -> bool:
    if isinstance(identifier, str):
        return (
            not identifier.isdecimal() or int(identifier) <= _NPM_MAX_NUMERIC_IDENTIFIER
        )
    return type(identifier) is int and 0 <= identifier <= _NPM_MAX_NUMERIC_IDENTIFIER


def _npm_version_supported(observed: object) -> bool:
    if not isinstance(observed, nodesemver.SemVer):
        return False
    return (
        len(observed.raw) <= _NPM_MAX_VERSION_CHARS
        and not observed.micro_versions
        and all(
            _npm_identifier_supported(part)
            for part in (
                observed.major,
                observed.minor,
                observed.patch,
                *observed.prerelease,
            )
        )
    )


def _npm_contains(matcher: nodesemver.Range, version: str) -> bool | None:
    if len(version) > _NPM_MAX_VERSION_CHARS:
        return None
    try:
        observed = nodesemver.valid(version, loose=False)
    except ValueError:
        return None
    if not _npm_version_supported(observed):
        return None
    return matcher.test(observed, include_prerelease=False)


@dataclass(frozen=True)
class PreparedVersionPredicate:
    """One operation-local native interpretation and its detached evidence."""

    _request: dict[str, object]
    _evidence: dict[str, object]
    _matcher: SpecifierSet | nodesemver.Range | None
    _reason: str | None

    @property
    def request(self) -> dict[str, object]:
        return deepcopy(self._request)

    @property
    def evidence(self) -> dict[str, object]:
        return deepcopy(self._evidence)

    def classify(self, version: object) -> dict[str, object]:
        if self._reason is not None:
            return {"state": "unclassified", "reason": self._reason}
        if not isinstance(version, str) or not version or len(version) > 4096:
            return {"state": "unclassified", "reason": "unsupported-version"}
        matched = self._contains(version)
        if matched is None:
            return {"state": "unclassified", "reason": "unsupported-version"}
        return {
            "state": "match" if matched else "nonmatch",
            "reason": "version-satisfies-predicate"
            if matched
            else "version-does-not-satisfy-predicate",
        }

    def _contains(self, version: str) -> bool | None:
        if isinstance(self._matcher, SpecifierSet):
            try:
                observed = Version(version)
            except InvalidVersion:
                return None
            return self._matcher.contains(
                observed, prereleases=cast("bool", self._request["prereleases"])
            )
        if self._matcher is not None:
            return _npm_contains(self._matcher, version)
        return None


def prepare_version_predicate(
    ecosystem: str, value: object
) -> PreparedVersionPredicate:
    request = normalize_version_predicate(value)
    selected_ecosystem = normalized_text(
        ecosystem, label="version predicate ecosystem", required=True
    )
    matcher, reason = _native_matcher(selected_ecosystem, request)
    evidence: dict[str, object] = {
        "schema": PREDICATE_SCHEMA,
        "ecosystem": selected_ecosystem,
        "predicate": request,
        "semantics": PREDICATE_SEMANTICS,
        "engine": _engine(str(request["dialect"])),
        "availability": "supported" if reason is None else "unsupported",
        "reason": reason or "native-predicate",
    }
    evidence["predicate_identity"] = evidence_identity(PREDICATE_SCHEMA, evidence)
    return PreparedVersionPredicate(request, evidence, matcher, reason)
