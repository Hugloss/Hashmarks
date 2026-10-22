from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.native_vitest import local_vitest
from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.paths import normalize_relative_path

from .repository_domains import RepositoryDomain, classify_repository_path

if TYPE_CHECKING:
    from .evidence_verification import RepositoryVerification
    from .task_evidence_types import TaskVerificationPlan


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

    def _vitest_declared(self) -> bool:
        """Look at authored package metadata, never installed executable paths."""
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        manifest = self.workspace / "package.json"
        if not self.files.is_admitted("package.json") or not manifest.is_file():
            return False
        try:
            package = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            return False
        if not isinstance(package, Mapping):
            return False
        return any(
            isinstance(dependencies, Mapping) and "vitest" in dependencies
            for key in ("dependencies", "devDependencies", "optionalDependencies")
            if (dependencies := package.get(key)) is not None
        )

    @staticmethod
    def _source_test_import(source: str) -> bool:
        """Recognize explicit node:test source evidence, not a runtime install."""
        return "node:test" in source or "node:test/" in source

    def _python_surface_nomination(
        self, *, symbol: str | None, qualname: str | None
    ) -> tuple[str, str, str, str, str | None]:
        declared = self._pytest_declared()
        test_symbol = self._verification_test_symbol(symbol, qualname)
        return (
            "pytest",
            "test-node" if test_symbol else "test-file",
            "pyproject-pytest-config" if declared else "python-test-domain",
            "high" if declared else "medium",
            test_symbol,
        )

    def _go_surface_nomination(
        self, rel: str
    ) -> tuple[str, str, str, str, str | None] | None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        if (
            Path(rel).name.endswith("_test.go")
            and (self.workspace / "go.mod").is_file()
        ):
            return ("go-test", "go-package", "go-mod-plus-test-file", "high", None)
        return None

    def _ecmascript_surface_nomination(
        self, rel: str
    ) -> tuple[str, str, str, str, str | None] | None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        suffix = Path(rel).suffix.lower()
        if self._vitest_declared():
            return (
                "vitest",
                "test-file",
                "package-manifest-vitest-declaration",
                "high",
                None,
            )
        if suffix in {".js", ".mjs", ".cjs"}:
            try:
                source = (self.workspace / rel).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                source = ""
            if self._source_test_import(source):
                return (
                    "node-test",
                    "test-file",
                    "node-test-import-plus-test-file",
                    "high",
                    None,
                )
        if (
            suffix in {".ts", ".tsx", ".mts", ".cts"}
            and (self.workspace / "tsconfig.json").is_file()
        ):
            return (
                "typescript-compiler",
                "typescript-project",
                "tsconfig-plus-typescript-test-file",
                "medium",
                None,
            )
        return None

    def _test_surface_nomination(
        self, rel: str, *, symbol: str | None, qualname: str | None
    ) -> tuple[str, str, str, str, str | None] | None:
        """One repository-derived nomination dispatcher, not an executable selector."""
        suffix = Path(rel).suffix.lower()
        if suffix == ".py":
            return self._python_surface_nomination(symbol=symbol, qualname=qualname)
        if suffix == ".go":
            return self._go_surface_nomination(rel)
        if suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}:
            return self._ecmascript_surface_nomination(rel)
        return None

    @operation_response("verification_nomination")
    def nomination(
        self, path: str, *, symbol: str | None = None, qualname: str | None = None
    ) -> dict[str, object]:
        """Nominate a repository-verifiable target without resolving native tools.

        This independent observer cut reads only repository evidence. It does
        not call the legacy command-producing Plan, inspect node_modules/.bin,
        discover ambient executables, or authorize execution. Plan's historical
        argv remains an advisory compatibility projection with different
        command-availability semantics.
        """
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
            self.source.ensure_current(rel)
            observed, _ = self.source.member(rel)
            if (
                observed.get("state") != "known-present"
                or not observed.get("member_revision")
            ):
                reason = "source-evidence-unqualified"
            else:
                nomination = self._test_surface_nomination(
                    rel, symbol=symbol, qualname=qualname
                )
                if nomination is not None:
                    runner, scope, evidence, confidence, test_symbol = nomination
                    return {
                        "schema": operation_schema("verification_nomination"),
                        "available": True,
                        "verification_target": {
                            "path": rel,
                            "test_symbol": test_symbol,
                        },
                        "source_member_revision": observed["member_revision"],
                        "scope": scope,
                        "runner_evidence": runner,
                        "source_evidence": evidence,
                        "confidence": confidence,
                        "authority": "repository-evidence-only",
                        "execution_authority": "external",
                    }
                reason = "unsupported-repository-verification-source"
        return {
            "schema": operation_schema("verification_nomination"),
            "available": False,
            "path": rel,
            "reason": reason,
            "authority": "repository-evidence-only",
            "execution_authority": "external",
        }

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
