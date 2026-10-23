from __future__ import annotations

import ast
import json
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.native_vitest import local_vitest
from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.paths import normalize_relative_path

from .decision_session import decision_scoped, reconcile_decision
from .repository_domains import RepositoryDomain, classify_repository_path
from .repository_observation import evidence_identity

if TYPE_CHECKING:
    from .evidence_verification import RepositoryVerification
    from .task_evidence_types import TaskVerificationPlan


class _UnqualifiedNominationMember(RuntimeError):
    """A supporting source could not be qualified by the canonical observer."""


class VerificationPlanMixin:
    """Repository-owned verification *nomination*, never execution authority.

    A legacy argv remains for existing consumers but is only an advisory
    candidate; native tool selection and executable command authority belong
    to the consuming agent or execution system.
    """

    def _pytest_declared(self) -> bool:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        pyproject = self.workspace / "pyproject.toml"
        if not pyproject.is_file():
            return False
        try:
            return "[tool.pytest." in pyproject.read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            return False

    @staticmethod
    def _verification_test_symbol(
        symbol: str | None, qualname: str | None
    ) -> str | None:
        if isinstance(symbol, str) and symbol.startswith("test_"):
            return symbol
        if not isinstance(qualname, str):
            return None
        root_symbol = qualname.split(".", 1)[0]
        return root_symbol if root_symbol.startswith("test_") else None

    def _python_verification_plan(
        self,
        rel: str,
        symbol: str | None,
        qualname: str | None,
        *,
        pytest_declared: bool | None = None,
    ) -> TaskVerificationPlan:
        if pytest_declared is None:
            pytest_declared = self._pytest_declared()
        test_symbol = self._verification_test_symbol(symbol, qualname)
        target_arg = f"{rel}::{test_symbol}" if test_symbol else rel
        return {
            "schema": "hashmarks.verification-plan.v1",
            "path": rel,
            "available": True,
            "runner": "pytest",
            "argv": ["python", "-m", "pytest", "-q", target_arg],
            "working_directory": ".",
            "confidence": "high" if pytest_declared else "medium",
            "evidence": "pyproject-pytest-config"
            if pytest_declared
            else "python-test-domain",
            "scope": "test-node" if test_symbol else "test-file",
            "test_symbol": test_symbol,
        }

    def _go_verification_plan(
        self, rel: str, target: Path
    ) -> TaskVerificationPlan | None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        if (
            not target.name.endswith("_test.go")
            or not (self.workspace / "go.mod").is_file()
        ):
            return None
        package = target.parent.as_posix()
        package_arg = "." if package == "." else f"./{package}"
        return {
            "schema": "hashmarks.verification-plan.v1",
            "path": rel,
            "available": True,
            "runner": "go-test",
            "argv": ["go", "test", package_arg],
            "working_directory": ".",
            "confidence": "high",
            "evidence": "go-mod-plus-test-file",
        }

    @staticmethod
    def _vitest_runner(workspace: Path) -> str | None:
        vitest = local_vitest(workspace)
        if vitest is None:
            return None
        try:
            return vitest.relative_to(workspace).as_posix()
        except ValueError:
            return str(vitest)

    def _javascript_verification_plan(
        self, rel: str, target: Path
    ) -> TaskVerificationPlan | None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        runner = self._vitest_runner(self.workspace)
        if runner is not None:
            return {
                "schema": "hashmarks.verification-plan.v1",
                "path": rel,
                "available": True,
                "runner": "vitest",
                "argv": [runner, "run", rel],
                "working_directory": ".",
                "confidence": "high",
                "evidence": "local-vitest-plus-test-file",
                "scope": "test-file",
            }
        if target.suffix.lower() not in {".js", ".mjs", ".cjs"}:
            return None
        try:
            source = (self.workspace / rel).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            source = ""
        if "node:test" not in source and "node:test/" not in source:
            return None
        return {
            "schema": "hashmarks.verification-plan.v1",
            "path": rel,
            "available": True,
            "runner": "node-test",
            "argv": ["node", "--test", rel],
            "working_directory": ".",
            "confidence": "high",
            "evidence": "node-test-import-plus-test-file",
            "scope": "test-file",
        }

    def _typescript_verification_plan(
        self, rel: str, target: Path
    ) -> TaskVerificationPlan | None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        if target.suffix.lower() not in {".ts", ".tsx", ".mts", ".cts"}:
            return None
        if not (self.workspace / "tsconfig.json").is_file():
            return None
        return {
            "schema": "hashmarks.verification-plan.v1",
            "path": rel,
            "available": True,
            "runner": "typescript-compiler",
            "argv": ["tsc", "--noEmit", "-p", "tsconfig.json"],
            "working_directory": ".",
            "confidence": "medium",
            "evidence": "tsconfig-plus-typescript-test-file",
            "scope": "typescript-project",
        }

    def _polyglot_verification_plan(
        self, rel: str, target: Path
    ) -> TaskVerificationPlan:
        plan = self._go_verification_plan(rel, target)
        if plan is not None:
            return plan
        js_exts = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
        if target.suffix.lower() in js_exts:
            plan = self._javascript_verification_plan(rel, target)
            if plan is not None:
                return plan
            plan = self._typescript_verification_plan(rel, target)
            if plan is not None:
                return plan
        return {
            "schema": "hashmarks.verification-plan.v1",
            "path": rel,
            "available": False,
            "reason": "unsupported-test-runner",
        }

    def _nomination_source_member(
        self, rel: str, members: list[dict[str, object]]
    ) -> bytes | None:
        """Read one current supporting input through the canonical source owner."""
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        self.source.ensure_current(rel)
        observation, raw = self.source.member(rel, include_bytes=True)
        state = observation.get("state")
        if state == "known-absent":
            members.append({"path": rel, "state": "known-absent"})
            return None
        revision = observation.get("member_revision")
        if (
            state != "known-present"
            or not isinstance(revision, str)
            or not revision
            or raw is None
        ):
            raise _UnqualifiedNominationMember(rel)
        members.append(
            {"path": rel, "state": "known-present", "member_revision": revision}
        )
        return raw

    @staticmethod
    def _unique_package_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        """Reject ambiguous JSON keys without creating a second JSON parser."""
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise _UnqualifiedNominationMember("package.json")
            result[key] = value
        return result

    @classmethod
    def _vitest_package_declaration(cls, raw: bytes) -> bool:
        """Qualify an authored, nonblank Vitest spec; never infer installation."""
        try:
            package = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=cls._unique_package_object,
            )
        except (UnicodeError, ValueError) as exc:
            raise _UnqualifiedNominationMember("package.json") from exc
        if not isinstance(package, Mapping):
            raise _UnqualifiedNominationMember("package.json")
        declared = False
        for key in ("dependencies", "devDependencies", "optionalDependencies"):
            if key not in package:
                continue
            dependencies = package[key]
            if not isinstance(dependencies, Mapping):
                raise _UnqualifiedNominationMember("package.json")
            if "vitest" in dependencies:
                value = dependencies["vitest"]
                if not isinstance(value, str) or not value.strip():
                    raise _UnqualifiedNominationMember("package.json")
                declared = True
        return declared

    def _vitest_declared(self, members: list[dict[str, object]]) -> bool:
        """Interpret qualified authored package metadata, not installed tools."""
        raw = self._nomination_source_member("package.json", members)
        return raw is not None and self._vitest_package_declaration(raw)

    @staticmethod
    def _source_test_import(source: str) -> bool:
        """Recognize explicit node:test source evidence, not a runtime install."""
        return "node:test" in source or "node:test/" in source

    @staticmethod
    def _pytest_manifest_declaration(raw: bytes) -> bool:
        """Qualify authored pytest configuration by TOML syntax, not text hints."""
        try:
            manifest = tomllib.loads(raw.decode("utf-8"))
        except (UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise _UnqualifiedNominationMember("pyproject.toml") from exc
        tool = manifest.get("tool")
        if not isinstance(tool, Mapping):
            return False
        pytest = tool.get("pytest")
        return isinstance(pytest, Mapping) and isinstance(
            pytest.get("ini_options"), Mapping
        )

    @staticmethod
    def _qualify_python_test_node(source: bytes, name: str) -> None:
        """Accept only one top-level declaration found in qualified test bytes.

        A class method or nested function cannot be represented by the current
        file::function target; a caller must not promote one to test-node.
        """
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, UnicodeError) as exc:
            raise _UnqualifiedNominationMember("python-test-syntax") from exc
        matches = sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
            for node in tree.body
        )
        if matches != 1:
            raise _UnqualifiedNominationMember("python-test-node-unqualified")

    @classmethod
    def _qualified_python_test_symbol(
        cls, symbol: str | None, qualname: str | None
    ) -> str | None:
        """Refuse to flatten nested or contradictory requested source identities.

        The current nomination target can represent a flat file::function only.
        Preserve the legacy planner's historical symbol resolution separately.
        """
        if isinstance(symbol, str) and "." in symbol:
            raise _UnqualifiedNominationMember("python-test-symbol-not-flat")
        if isinstance(qualname, str) and "." in qualname:
            raise _UnqualifiedNominationMember("python-test-qualname-not-flat")
        for selector in (symbol, qualname):
            if selector is not None and (
                not isinstance(selector, str)
                or not selector.startswith("test_")
                or not selector.isidentifier()
            ):
                raise _UnqualifiedNominationMember("python-test-selector-unqualified")
        if symbol is not None and qualname is not None and symbol != qualname:
            raise _UnqualifiedNominationMember("python-test-selection-conflict")
        return cls._verification_test_symbol(symbol, qualname)

    def _python_surface_nomination(
        self,
        source: bytes,
        members: list[dict[str, object]],
        *,
        symbol: str | None,
        qualname: str | None,
    ) -> tuple[str, str, str, str, str | None]:
        test_symbol = self._qualified_python_test_symbol(symbol, qualname)
        if test_symbol:
            self._qualify_python_test_node(source, test_symbol)
        raw = self._nomination_source_member("pyproject.toml", members)
        declared = raw is not None and self._pytest_manifest_declaration(raw)
        return (
            "pytest",
            "test-node" if test_symbol else "test-file",
            "pyproject-pytest-config" if declared else "python-test-domain",
            "high" if declared else "medium",
            test_symbol,
        )

    def _go_surface_nomination(
        self, rel: str, members: list[dict[str, object]]
    ) -> tuple[str, str, str, str, str | None] | None:
        if not Path(rel).name.endswith("_test.go"):
            return None
        if self._nomination_source_member("go.mod", members) is not None:
            return ("go-test", "go-package", "go-mod-plus-test-file", "high", None)
        return None

    def _ecmascript_surface_nomination(
        self, rel: str, source: bytes, members: list[dict[str, object]]
    ) -> tuple[str, str, str, str, str | None] | None:
        suffix = Path(rel).suffix.lower()
        if self._vitest_declared(members):
            return (
                "vitest",
                "test-file",
                "package-manifest-vitest-declaration",
                "high",
                None,
            )
        if suffix in {".js", ".mjs", ".cjs"}:
            try:
                source_text = source.decode("utf-8")
            except UnicodeError as exc:
                raise _UnqualifiedNominationMember(rel) from exc
            if self._source_test_import(source_text):
                return (
                    "node-test",
                    "test-file",
                    "node-test-import-plus-test-file",
                    "high",
                    None,
                )
        if suffix in {".ts", ".tsx", ".mts", ".cts"}:
            if self._nomination_source_member("tsconfig.json", members) is not None:
                return (
                    "typescript-compiler",
                    "typescript-project",
                    "tsconfig-plus-typescript-test-file",
                    "medium",
                    None,
                )
        return None

    def _test_surface_nomination(
        self,
        rel: str,
        source: bytes,
        members: list[dict[str, object]],
        *,
        symbol: str | None,
        qualname: str | None,
    ) -> tuple[str, str, str, str, str | None] | None:
        """Dispatch one source-qualified repository nomination, without tool lookup."""
        suffix = Path(rel).suffix.lower()
        if suffix == ".py":
            return self._python_surface_nomination(
                source, members, symbol=symbol, qualname=qualname
            )
        if suffix == ".go":
            return self._go_surface_nomination(rel, members)
        if suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}:
            return self._ecmascript_surface_nomination(rel, source, members)
        return None

    @staticmethod
    def _bound_nomination(payload: dict[str, object]) -> dict[str, object]:
        """Bind this evidence projection without creating execution authority."""
        return {
            **payload,
            "nomination_identity": evidence_identity(
                operation_schema("verification_nomination"), payload
            ),
        }

    def _qualified_nomination(
        self, rel: str, *, symbol: str | None, qualname: str | None
    ) -> dict[str, object] | None:
        members: list[dict[str, object]] = []
        source = self._nomination_source_member(rel, members)
        if source is None:
            raise _UnqualifiedNominationMember(rel)
        nominated = self._test_surface_nomination(
            rel, source, members, symbol=symbol, qualname=qualname
        )
        if nominated is None:
            return None
        runner, scope, evidence, confidence, test_symbol = nominated
        return self._bound_nomination(
            {
                "schema": operation_schema("verification_nomination"),
                "available": True,
                "verification_target": {
                    "path": rel,
                    "test_symbol": test_symbol,
                },
                "source_member_revision": members[0]["member_revision"],
                "supporting_source_members": members,
                "scope": scope,
                "runner_evidence": runner,
                "source_evidence": evidence,
                "confidence": confidence,
                "authority": "repository-evidence-only",
                "execution_authority": "external",
            }
        )

    @operation_response("verification_nomination")
    @reconcile_decision
    @decision_scoped
    def nomination(
        self, path: str, *, symbol: str | None = None, qualname: str | None = None
    ) -> dict[str, object]:
        """Observe one generation-bound verifier nomination with input revisions."""
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        rel = normalize_relative_path(path, allow_root=False)
        reason: str | None = None
        if not self.files.is_admitted(rel):
            reason = "path-outside-analysis-scope"
        elif (
            not (self.workspace / rel).is_file() or (self.workspace / rel).is_symlink()
        ):
            reason = "source-file-unavailable"
        elif RepositoryDomain.TEST not in set(classify_repository_path(rel)):
            reason = "path-is-not-test-domain"
        else:
            try:
                nomination = self._qualified_nomination(
                    rel, symbol=symbol, qualname=qualname
                )
            except _UnqualifiedNominationMember:
                reason = "source-evidence-unqualified"
            else:
                if nomination is not None:
                    return nomination
                reason = "unsupported-repository-verification-source"
        return self._bound_nomination(
            {
                "schema": operation_schema("verification_nomination"),
                "available": False,
                "path": rel,
                "reason": reason,
                "authority": "repository-evidence-only",
                "execution_authority": "external",
            }
        )

    def plan(
        self, path: str, *, symbol: str | None = None, qualname: str | None = None
    ) -> TaskVerificationPlan:
        """Derive a bounded argv for a known verification surface."""
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        rel = normalize_relative_path(path, allow_root=False)
        if not self.files.is_admitted(rel):
            return {
                "schema": "hashmarks.verification-plan.v1",
                "path": rel,
                "available": False,
                "reason": "path-outside-analysis-scope",
            }
        target = Path(rel)
        domains = set(classify_repository_path(rel))
        if RepositoryDomain.TEST not in domains:
            return {
                "schema": "hashmarks.verification-plan.v1",
                "path": rel,
                "available": False,
                "reason": "path-is-not-test-domain",
            }
        if target.suffix.lower() == ".py":
            nominated = self._python_verification_plan(rel, symbol, qualname)
        else:
            nominated = self._polyglot_verification_plan(rel, target)
        if not nominated["available"]:
            return nominated
        # The repository-derived test target is the observer's result. The
        # historical argv/runner fields are advisory compatibility projections:
        # consumers must resolve their own executable and execution policy.
        return {
            **nominated,
            "verification_target": {
                "path": rel,
                "test_symbol": nominated.get("test_symbol"),
            },
            "command_intent_authority": "advisory-only",
            "execution_authority": "external",
        }
