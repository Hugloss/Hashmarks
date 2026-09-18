from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hashmarks.codemap.structural_search import AstGrepSearchProvider


def test_structural_search_reports_unavailable_binary(tmp_path: Path) -> None:
    provider = AstGrepSearchProvider(tmp_path)
    provider.executable = None
    assert provider.search(tmp_path, "call($A)") == (
        [],
        ("ast-grep executable unavailable",),
    )


def test_structural_search_parses_stream_with_bounded_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    provider = AstGrepSearchProvider(tmp_path)
    provider.executable = "ast-grep"

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args[0] == [
            "ast-grep",
            "run",
            "--pattern",
            "call($A)",
            "--json=stream",
            "--lang",
            "python",
            ".",
        ]
        assert kwargs["cwd"] == tmp_path
        return subprocess.CompletedProcess(
            args[0],
            0,
            stdout='\ninvalid\n{"path":"first.py"}\n{"path":"second.py"}\n',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    results, warnings = provider.search(
        tmp_path, "call($A)", language="python", limit=1
    )
    assert results == [{"path": "first.py"}]
    assert warnings == ("ast-grep emitted non-JSON output",)


@pytest.mark.parametrize(
    ("returncode", "stderr", "warning"),
    [
        (2, "first\nlast\n", "ast-grep search failed: last"),
        (2, "", "ast-grep search failed: exit 2"),
    ],
)
def test_structural_search_reports_command_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    returncode: int,
    stderr: str,
    warning: str,
) -> None:
    provider = AstGrepSearchProvider(tmp_path)
    provider.executable = "ast-grep"
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], returncode, stdout="", stderr=stderr
        ),
    )
    assert provider.search(tmp_path, "call($A)") == ([], (warning,))


def test_structural_search_reports_process_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    provider = AstGrepSearchProvider(tmp_path)
    provider.executable = "ast-grep"

    def fail(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("cannot start")

    monkeypatch.setattr(subprocess, "run", fail)
    assert provider.search(tmp_path, "call($A)") == (
        [],
        ("ast-grep search failed: cannot start",),
    )
