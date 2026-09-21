from __future__ import annotations

from typing import TYPE_CHECKING

from scripts import ruff_debt

if TYPE_CHECKING:
    from pathlib import Path


def _snapshot(
    *,
    excess: int,
    files: dict[str, int],
    max_python_file_lines: int = 1600,
) -> dict[str, object]:
    return {
        "schema": "hashmarks.ruff-debt.v3",
        "limits": dict(ruff_debt.LIMITS),
        "max_python_file_lines": max_python_file_lines,
        "oversized_files": {},
        "functions": len(files),
        "rule_findings": len(files),
        "excess": excess,
        "by_root": {},
        "files": {
            path: {"functions": 1, "rule_findings": 1, "excess": value}
            for path, value in files.items()
        },
        "findings": [],
    }


def test_baseline_comparison_rejects_line_ceiling_drift() -> None:
    previous = _snapshot(excess=10, files={"hashmarks/a.py": 10})
    candidate = _snapshot(
        excess=10,
        files={"hashmarks/a.py": 10},
        max_python_file_lines=1700,
    )

    failures = ruff_debt._baseline_failures(candidate, previous)

    assert any("line ceiling changed" in failure for failure in failures)


def test_baseline_mutation_rejects_new_debt_file_and_per_file_growth() -> None:
    previous = _snapshot(
        excess=20,
        files={"hashmarks/a.py": 10, "hashmarks/b.py": 10},
    )
    candidate = _snapshot(
        excess=20,
        files={"hashmarks/a.py": 11, "hashmarks/c.py": 9},
    )

    failures = ruff_debt._baseline_failures(candidate, previous)

    assert "debt increased: hashmarks/a.py 10 -> 11" in failures
    assert "new debt file: hashmarks/c.py excess=9" in failures


def test_baseline_mutation_allows_downward_ratchet_and_debt_file_removal() -> None:
    previous = _snapshot(
        excess=20,
        files={"hashmarks/a.py": 10, "hashmarks/b.py": 10},
    )
    candidate = _snapshot(excess=7, files={"hashmarks/a.py": 7})

    assert ruff_debt._baseline_failures(candidate, previous) == []


def test_ci_binds_candidate_baseline_to_previous_main(tmp_path: Path) -> None:
    del tmp_path
    root = ruff_debt.ROOT
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    script = (root / "scripts/ruff_debt.py").read_text(encoding="utf-8")

    assert "fetch-depth: 2" in workflow
    assert "Resolve previous-main Ruff debt baseline" in workflow
    assert "git show HEAD^1:ruff-debt-baseline.json" in workflow
    assert "RUFF_DEBT_PREVIOUS_BASELINE" in workflow
    assert "--previous-baseline" in makefile
    assert 'parser.add_argument("--previous-baseline"' in script
