"""Source-qualified verifier roles and bounded shared-support applicability.

Conftest/configuration ancestry is an applicability observation, not a claim
that every descendant consumes a fixture or is collected by a test runner.
Imports and literal file reads remain with the existing relevance owner.
"""

from __future__ import annotations

import ast
import configparser
import tomllib
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path
from hashmarks.python_ast_cache import parse_python_ast

from .repository_domains import RepositoryDomain, classify_repository_path
from .repository_observation import evidence_identity
from .verification_context import MAX_CONTEXT_ANCESTORS
from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS
from .verification_plan import _UnqualifiedNominationMember

if TYPE_CHECKING:
    from .evidence_verification import RepositoryVerification

_SUPPORT_SCAN_LIMIT = 512
_INI_CONFIG = {
    "pytest.ini": "pytest",
    ".pytest.ini": "pytest",
    "tox.ini": "pytest",
    "setup.cfg": "tool:pytest",
}
_JS_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
_PYTEST_NAME_OPTIONS = {
    "python_files",
    "python_classes",
    "python_functions",
}
_PYTEST_SELECTION_OPTIONS = _PYTEST_NAME_OPTIONS | {
    "addopts",
    "testpaths",
    "norecursedirs",
}
_PYTEST_TOML_CONFIG = {"pytest.toml", ".pytest.toml"}
_PathDetails = tuple[str, str, list[str]]


def _python_test_declarations(tree: ast.Module) -> bool:
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)
    for statement in tree.body:
        if isinstance(statement, functions) and statement.name.startswith("test_"):
            return True
        if isinstance(statement, ast.ClassDef) and statement.name.startswith("Test"):
            if any(
                isinstance(child, functions) and child.name.startswith("test_")
                for child in statement.body
            ):
                return True
    return False


def _pytest_dynamic_features(tree: ast.Module) -> list[str]:
    features: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "pytest_plugins":
            features.add("pytest-plugin-consumers-not-observed")
        if isinstance(node, ast.Name) and node.id == "__test__":
            features.add("pytest-test-flag-not-interpreted")
        if isinstance(node, ast.Attribute) and node.attr == "getfixturevalue":
            features.add("dynamic-fixture-consumers-not-observed")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "pytest_generate_tests":
                features.add("dynamic-test-generation-not-observed")
    return sorted(features)


def _python_path_details(raw: bytes, *, conftest: bool) -> _PathDetails:
    try:
        tree = parse_python_ast(raw)
    except (SyntaxError, ValueError, UnicodeError):
        return "unknown", "python-source-syntax-unqualified", []
    unsupported = _pytest_dynamic_features(tree)
    if conftest:
        return "verification-support", "pytest-conftest", unsupported
    if "pytest-test-flag-not-interpreted" in unsupported:
        return "unknown", "pytest-test-flag-not-interpreted", unsupported
    if _python_test_declarations(tree):
        return "verifier", "python-test-declaration", unsupported
    return "verification-support", "test-domain-support-source", unsupported


class _AuthoredIniOptions(configparser.ConfigParser):
    """Use the stdlib parser with its supported case-preserving extension."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr


def _ini_options(name: str, raw: bytes) -> Mapping[str, object] | None:
    parser = _AuthoredIniOptions(interpolation=None, strict=True, default_section="")
    try:
        parser.read_string(raw.decode("utf-8"))
    except (UnicodeError, configparser.Error):
        raise _UnqualifiedNominationMember(
            "pytest-configuration-syntax-unqualified"
        ) from None
    # pytest.ini itself establishes the configuration location, even if empty.
    section = _INI_CONFIG[name]
    if parser.has_section(section):
        return dict(parser.items(section))
    return {} if name in {"pytest.ini", ".pytest.ini"} else None


def _ini_config_details(name: str, raw: bytes) -> _PathDetails:
    try:
        options = _ini_options(name, raw)
    except _UnqualifiedNominationMember:
        return "unknown", "pytest-configuration-syntax-unqualified", []
    return (
        ("verification-support", "pytest-configuration", [])
        if options is not None
        else ("source", "repository-source", [])
    )


def _test_filename(path: PurePosixPath) -> bool:
    return (
        ".test." in path.name
        or ".spec." in path.name
        or path.name.endswith("_test.go")
        or "__tests__" in path.parts
    )


class VerificationSupportMixin:
    """Extend the verification owner with syntax and scope observations only."""

    def _pytest_selection_options(self, filename: str, raw: bytes) -> dict[str, object]:
        """Translate only authored options; native matching is not performed."""
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        if filename == "pyproject.toml":
            options = self._pytest_manifest_options(raw)
        elif filename in _PYTEST_TOML_CONFIG:
            options = tomllib.loads(raw.decode("utf-8")).get("pytest")
            if options is not None and not isinstance(options, Mapping):
                raise _UnqualifiedNominationMember("pytest-configuration-options")
        else:
            options = _ini_options(filename, raw)
        return (
            {
                key: options[key]
                for key in sorted(_PYTEST_SELECTION_OPTIONS)
                if key in options
            }
            if isinstance(options, Mapping)
            else {}
        )

    def _pytest_selection_declarations(
        self, path: str, members: list[dict[str, object]]
    ) -> dict[str, object]:
        """Retain source declarations, never reproduce pytest's selection rules."""
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        declarations: list[dict[str, object]] = []
        try:
            parent = PurePosixPath(path).parent
            ancestors = (parent, *parent.parents)
            if len(ancestors) > MAX_CONTEXT_ANCESTORS:
                raise _UnqualifiedNominationMember("manifest-ancestor-limit")
            for ancestor in ancestors:
                for filename in (
                    "pyproject.toml",
                    *sorted(_PYTEST_TOML_CONFIG),
                    *_INI_CONFIG,
                ):
                    manifest = (ancestor / filename).as_posix()
                    raw = self._nomination_source_member(manifest, members)
                    if raw is None:
                        continue
                    selected = self._pytest_selection_options(filename, raw)
                    if selected:
                        declarations.append({"path": manifest, "options": selected})
        except (_UnqualifiedNominationMember, UnicodeError, tomllib.TOMLDecodeError):
            return {
                "state": "unknown",
                "declarations": declarations,
                "reason": "pytest-selection-configuration-unqualified",
                "collection": "not-observed",
                "selection_authority": "native-pytest",
                "configuration_resolution": "not-performed",
            }
        return {
            "state": "declared" if declarations else "not-observed",
            "declarations": declarations,
            "custom_name_patterns": any(
                _PYTEST_NAME_OPTIONS.intersection(
                    cast(Mapping[str, object], row["options"])
                )
                for row in declarations
            ),
            "collection": "not-observed",
            "selection_authority": "native-pytest",
            "configuration_resolution": "not-performed",
        }

    def _native_path_details(self, path: PurePosixPath, raw: bytes) -> _PathDetails:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        try:
            tree = self._verification_syntax(path.as_posix(), raw)
            if tree is None:
                return "unknown", "native-source-syntax-unavailable", []
            if _test_filename(path):
                return "verifier", "native-test-file-syntax", []
            if path.suffix in {".js", ".mjs", ".cjs"}:
                if self._tree_test_import(tree, raw):
                    return "verifier", "node-test-import", []
        except (ImportError, LookupError, OSError, RuntimeError, TypeError, ValueError):
            return "unknown", "native-source-syntax-unqualified", []
        return "verification-support", "test-domain-support-source", []

    def _support_path_details(self, rel: str, raw: bytes) -> _PathDetails:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        path = PurePosixPath(rel)
        if path.name == "conftest.py":
            return _python_path_details(raw, conftest=True)
        if path.name in _INI_CONFIG:
            return _ini_config_details(path.name, raw)
        if path.name == "pyproject.toml":
            try:
                if self._pytest_manifest_declaration(raw):
                    return "verification-support", "pytest-configuration", []
            except _UnqualifiedNominationMember:
                return "unknown", "pytest-configuration-syntax-unqualified", []
        return self._test_domain_details(path, raw)

    def _test_domain_details(self, path: PurePosixPath, raw: bytes) -> _PathDetails:
        if RepositoryDomain.TEST not in classify_repository_path(path.as_posix()):
            return "source", "repository-source", []
        if path.suffix == ".py":
            return _python_path_details(raw, conftest=False)
        if path.suffix in _JS_SUFFIXES or path.suffix == ".go":
            return self._native_path_details(path, raw)
        return "verification-support", "test-domain-repository-member", []

    def _verification_path_kind(
        self, path: str, *, reconcile: bool = True
    ) -> dict[str, object]:
        """Classify a qualified member, never promote a test-directory helper."""
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        rel = normalize_relative_path(path, allow_root=False)
        if reconcile:
            self.source.ensure_current(rel)
        member, raw = self.source._bounded_source_observation(
            rel, VERIFICATION_RELEVANCE_DEFAULTS.source_member_bytes
        )
        supporting = [member]
        selection = None
        if member.get("state") == "known-present" and raw is not None:
            kind, reason, unsupported = self._support_path_details(rel, raw)
            if PurePosixPath(rel).suffix == ".py":
                selection = self._pytest_selection_declarations(rel, supporting)
                if selection["state"] == "unknown" or selection.get(
                    "custom_name_patterns"
                ):
                    kind, reason = "unknown", "pytest-selection-scope-unqualified"
            if (
                kind in {"verifier", "verification-support"}
                and PurePosixPath(rel).suffix in _JS_SUFFIXES | {".go"}
                and self.source.member(rel, include_bytes=True)[0] != member
            ):
                kind, reason = "unknown", "source-changed-during-observation"
        else:
            kind = "unknown"
            reason = str(member.get("reason") or "source-evidence-unqualified")
            unsupported = []
        payload: dict[str, object] = {
            "path": rel,
            "kind": kind,
            "reason": reason,
            "source_member_revision": member.get("member_revision"),
            "supporting_source_members": supporting,
            "unsupported_features": unsupported,
            "authority": "repository-source-syntax-only",
            "collection_authority": "external",
            "native_collection": "not-observed",
            "negative_evidence_admissible": False,
            "native_selection": selection,
        }
        return {
            **payload,
            "evidence_identity": evidence_identity(
                "hashmarks.verification-path-role.v1", payload
            ),
        }

    def _support_candidate_paths(self, path: str) -> list[str]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        parent = PurePosixPath(path).parent.as_posix()
        paths = self.store.paths_under("" if parent == "." else parent)
        return sorted(
            target
            for target in paths
            if target != path
            and target.endswith(".py")
            and RepositoryDomain.TEST in classify_repository_path(target)
        )

    def _support_relationship(
        self, source: dict[str, object], target: dict[str, object]
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        relation = (
            "pytest-conftest-scope"
            if source["reason"] == "pytest-conftest"
            else "pytest-configuration-scope"
        )
        return {
            **self.relationship_evidence(
                source=str(source["path"]),
                target=str(target["path"]),
                classification="related",
                relation_kind=relation,
                provenance="qualified-source-syntax-and-directory-ancestry",
            ),
            "source_member_revision": source["source_member_revision"],
            "target_member_revision": target["source_member_revision"],
            "supporting_source_members": [
                *cast("list[dict[str, object]]", source["supporting_source_members"]),
                *cast("list[dict[str, object]]", target["supporting_source_members"]),
            ],
            "qualification": "structural-applicability-only",
            "fixture_consumption": "unknown",
            "collection": "unknown",
        }

    def _support_scope_rows(
        self, source: dict[str, object], candidates: list[str]
    ) -> tuple[list[dict[str, object]], list[str], list[str]]:
        rows: list[dict[str, object]] = []
        unresolved: list[str] = []
        unsupported: set[str] = set(cast("list[str]", source["unsupported_features"]))
        for path in candidates[:_SUPPORT_SCAN_LIMIT]:
            target = self._verification_path_kind(path)
            unsupported.update(cast("list[str]", target["unsupported_features"]))
            if target["kind"] == "verifier":
                rows.append(self._support_relationship(source, target))
            elif target["kind"] == "unknown":
                unresolved.append(path)
        return rows, unresolved, sorted(unsupported)

    def _verification_support_scope(
        self, path: str, *, limit: int
    ) -> dict[str, object]:
        """Observe bounded applicability; dynamic consumer scope stays unknown."""
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("verification support limit must be between 1 and 1000")
        source = self._verification_path_kind(path)
        applicable = source["reason"] in {"pytest-conftest", "pytest-configuration"}
        candidates = self._support_candidate_paths(path) if applicable else []
        rows, unresolved, unsupported = self._support_scope_rows(source, candidates)
        truncated = len(candidates) > _SUPPORT_SCAN_LIMIT or len(rows) > limit
        reasons = [
            "dynamic-collection-and-fixture-consumption-not-observed"
            if applicable
            else "explicit-reference-evidence-required"
        ]
        reasons.extend(unsupported)
        if unresolved:
            reasons.append("candidate-source-evidence-unqualified")
        if truncated:
            reasons.append("support-projection-bounded")
        payload: dict[str, object] = {
            "path": source["path"],
            "scope": "indexed-python-test-descendants" if applicable else "unknown",
            "scope_root": PurePosixPath(path).parent.as_posix(),
            "targets": [row["target"] for row in rows[:limit]],
            "relationships": rows[:limit],
            "supporting_source_members": source["supporting_source_members"],
            "candidate_count": len(candidates),
            "observed_candidate_count": min(len(candidates), _SUPPORT_SCAN_LIMIT),
            "unqualified_candidates": unresolved,
            "completeness": "incomplete" if truncated or unresolved else "unknown",
            "projection_completeness": "incomplete" if truncated else "complete",
            "truncated": truncated,
            "negative_evidence_admissible": False,
            "unsupported_features": unsupported,
            "reasons": reasons,
        }
        return {
            **payload,
            "evidence_identity": evidence_identity(
                "hashmarks.verification-support-scope.v1", payload
            ),
        }
