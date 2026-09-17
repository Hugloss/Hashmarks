from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from scripts.qualification_environment import _version_at_least


def test_hashmarks_owns_minimum_supported_tool_versions_without_upper_caps() -> None:
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["dependency-groups"]["test"] == ["pytest>=8.4"]
    assert config["tool"]["hashmarks"]["qualification"] == {"pytest-min": "8.4"}
    assert config["tool"]["hashmarks"]["diagnostics"] == {"ruff-min": "0.12"}
    assert config["tool"]["uv"]["required-version"] == ">=0.10.0"


def test_uv_native_required_version_boundary_is_minimum_only() -> None:
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    spec = SpecifierSet(config["tool"]["uv"]["required-version"])
    assert Version("0.9.99") not in spec
    assert Version("0.10.0") in spec
    assert Version("0.12.13") in spec
    assert Version("0.13.0") in spec
    assert Version("1.0.0") in spec


def test_pytest_and_ruff_boundaries_accept_versions_above_old_ceilings() -> None:
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_requirement = config["dependency-groups"]["test"][0]
    assert pytest_requirement.startswith("pytest")
    pytest_spec = SpecifierSet(pytest_requirement.removeprefix("pytest"))
    ruff_spec = SpecifierSet(f'>={config["tool"]["hashmarks"]["diagnostics"]["ruff-min"]}')

    assert Version("8.3.99") not in pytest_spec
    assert Version("8.4.0") in pytest_spec
    assert Version("9.1.1") in pytest_spec
    assert Version("10.0.0") in pytest_spec
    assert Version("99.0.0") in pytest_spec

    assert Version("0.11.99") not in ruff_spec
    assert Version("0.12.0") in ruff_spec
    assert Version("0.16.6") in ruff_spec
    assert Version("0.17.0") in ruff_spec
    assert Version("1.0.0") in ruff_spec


def test_current_contributor_docs_do_not_reintroduce_exact_tool_admission() -> None:
    root = Path(__file__).resolve().parents[1]
    current_docs = (
        root / "AGENTS.md",
        root / "README.md",
        root / ".github/CONTRIBUTING.md",
        root / "docs/README.md",
        root / "docs/qualification/TOOL_COMPATIBILITY.md",
        root / "docs/development/PUBLISHING_CHECKLIST.md",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in current_docs)
    for forbidden in (
        "pytest **9.x** is the supported qualification runner line",
        "expected Ruff diagnostic version",
        "release lock generation requires uv 0.12.13",
        "install a side-by-side uv",
        "pytest-max-exclusive",
        "ruff-max-exclusive",
        "ruff-reference",
        "committed `uv.lock`",
        "review and commit uv.lock",
        "uv.lock is part of the release source",
    ):
        assert forbidden not in combined


def test_tool_version_contract_is_minimum_inclusive_without_upper_bound() -> None:
    assert _version_at_least("8.4.0", "8.4") is True
    assert _version_at_least("9.1.1", "8.4") is True
    assert _version_at_least("10.0.0", "8.4") is True
    assert _version_at_least("99.0.0", "8.4") is True
    assert _version_at_least("8.3.99", "8.4") is False
    assert _version_at_least("0.12.0", "0.12") is True
    assert _version_at_least("0.17.0", "0.12") is True
    assert _version_at_least("1.0.0", "0.12") is True
    assert _version_at_least("0.11.99", "0.12") is False
    assert _version_at_least("not-a-version", "0.12") is False


def test_make_uses_project_owned_test_group_without_ephemeral_tools() -> None:
    root = Path(__file__).resolve().parents[1]
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    assert "uv run --with" not in makefile.replace("$(UV)", "uv")
    assert "PYTEST_VERSION" not in makefile
    assert "RUFF_VERSION" not in makefile
    assert "UV_RELEASE_VERSION" not in makefile
    assert "python -m pytest -q" in makefile
    assert "qualification-preflight" in makefile


def test_runtime_bootstrap_consumes_local_frozen_test_supply() -> None:
    root = Path(__file__).resolve().parents[1]
    makefile = (root / "Makefile").read_text(encoding="utf-8").replace("$(UV)", "uv")
    bootstrap = makefile.split("bootstrap:\n", 1)[1].split("\nbaseline:", 1)[0]
    assert "uv sync --offline --frozen --group test" in bootstrap
    assert "run: make init" in bootstrap
    assert "ruff" not in bootstrap


def test_lock_generation_relies_on_uv_native_minimum_version_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    lock = makefile.split("lock:\n", 1)[1].split("\ninit:", 1)[0]
    assert config["tool"]["uv"]["required-version"] == ">=0.10.0"
    assert "$(UV) lock" in lock
    assert "UV_RELEASE_VERSION" not in lock
    assert "release lock generation requires uv" not in lock


def test_current_contributor_policy_matches_minimum_only_tool_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "pytest `>=8.4`" in agents
    assert "Ruff `>=0.12`" in agents
    assert "uv `>=0.10.0`" in agents
    assert "Newer releases are accepted by default" in agents
    assert "pytest **9.x**" not in agents
    assert "expected Ruff diagnostic version" not in agents
    assert "upper bound or exact-version requirement only after a concrete incompatibility" in agents


def test_uv_lock_is_local_gitignored_state_not_release_identity() -> None:
    root = Path(__file__).resolve().parents[1]
    ignore = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    makefile = (root / "Makefile").read_text(encoding="utf-8").replace("$(UV)", "uv")
    init = makefile.split("init:\n", 1)[1].split("\nsetup:", 1)[0]
    assert "uv.lock" in ignore
    assert "uv sync --group test" in init
    assert "--frozen" not in init
    assert "release source" not in init
    assert "commit uv.lock" not in makefile
    assert Path("uv.lock") not in __import__("hashmarks_build")._sdist_members()
