from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import TYPE_CHECKING, Any

from .providers import ProviderStatus

if TYPE_CHECKING:
    from pathlib import Path


def _parse_ast_grep_stream(
    stdout: str, limit: int
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """Retain bounded JSON object matches and deduplicated format warnings."""
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            warnings.append("ast-grep emitted non-JSON output")
            continue
        if isinstance(value, dict):
            out.append(value)
        if len(out) >= limit:
            break
    return out, tuple(dict.fromkeys(warnings))


class AstGrepSearchProvider:
    """Optional structural-search delegation to ast-grep.

    Hashmarks never installs ast-grep and never treats it as identity authority.
    If a repository-local or PATH ``ast-grep`` binary exists, this adapter can
    answer syntax-aware queries without sending repository contents anywhere.
    """

    def __init__(self, workspace: Path) -> None:
        local = (
            workspace
            / "node_modules"
            / ".bin"
            / ("ast-grep.cmd" if os.name == "nt" else "ast-grep")
        )
        if local.is_file():
            self.executable = str(local)
        else:
            self.executable = shutil.which("ast-grep")
        self._version: str | None = None

    @property
    def available(self) -> bool:
        return self.executable is not None

    def version(self) -> str | None:
        if not self.available:
            return None
        if self._version is not None:
            return self._version
        try:
            completed = subprocess.run(
                [str(self.executable), "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        self._version = completed.stdout.strip() or None
        return self._version

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name="ast-grep-structural-search",
            available=self.available,
            version=self.version(),
            detail=None if self.available else "ast-grep executable not found",
        )

    def search(
        self,
        workspace: Path,
        pattern: str,
        *,
        language: str | None = None,
        limit: int = 100,
        timeout: float = 10.0,
    ) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
        if not self.available:
            return [], ("ast-grep executable unavailable",)
        command = [str(self.executable), "run", "--pattern", pattern, "--json=stream"]
        if language:
            command.extend(["--lang", language])
        command.append(".")
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return [], (f"ast-grep search failed: {exc}",)
        if completed.returncode not in {0, 1}:  # 1 may mean no matches in some releases
            detail = (
                completed.stderr.strip().splitlines()[-1]
                if completed.stderr.strip()
                else f"exit {completed.returncode}"
            )
            return [], (f"ast-grep search failed: {detail}",)
        return _parse_ast_grep_stream(completed.stdout, limit)
