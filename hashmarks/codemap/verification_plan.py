from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.native_vitest import local_vitest
from hashmarks.paths import normalize_relative_path

from .repository_domains import RepositoryDomain, classify_repository_path

if TYPE_CHECKING:
    from .engine import CodeMap


class VerificationPlanMixin:
    """Repository-owned bounded verification plan projection."""

    def _pytest_declared(self) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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
    ) -> dict[str, object]:
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

    def _go_verification_plan(self, rel: str, target: Path) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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

    def _polyglot_verification_plan(self, rel: str, target: Path) -> dict[str, object]:
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

    def verification_plan(
        self, path: str, *, symbol: str | None = None, qualname: str | None = None
    ) -> dict[str, object]:
        """Derive a bounded argv for a known verification surface."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rel = normalize_relative_path(path, allow_root=False)
        if not self._path_admitted_for_analysis(rel):
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
            return self._python_verification_plan(rel, symbol, qualname)
        return self._polyglot_verification_plan(rel, target)
