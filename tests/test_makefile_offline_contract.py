from pathlib import Path


def test_offline_bootstrap_keeps_runtime_sync_offline_and_reuses_doctor_owner() -> None:
    makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text()
    normalized = makefile.replace("$(UV)", "uv").replace("$(MAKE)", "make")
    bootstrap = normalized.split("bootstrap:\n", 1)[1].split("\nbaseline:", 1)[0]
    assert "uv sync --offline --frozen --group test" in bootstrap
    assert "make --no-print-directory doctor >/dev/null" in bootstrap
    assert "hashmarks doctor" not in bootstrap


def test_test_owner_consumes_project_owned_pytest_group() -> None:
    makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text()
    assert "python -m pytest -q" in makefile
    assert "--group test" in makefile
    assert "uv run --with" not in makefile.replace("$(UV)", "uv")
    assert "uv add pytest" not in makefile
    assert "uv pip install pytest" not in makefile



def test_profile_is_the_single_full_qualification_owner() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")
    assert "test-fast:" not in makefile
    profile = makefile.split("test-profile: qualification-preflight", 1)[1].split("\ntest-shard-plan:", 1)[0]
    assert "python -m pytest -q --durations=25 --durations-min=1.0" in profile
    assert "--offline --frozen --no-sync --group test" in profile


def test_profile_warns_about_windows_mounted_wsl_timing_surface() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")
    profile = makefile.split("test-profile: qualification-preflight", 1)[1].split("\ntest-shard-plan:", 1)[0]
    assert "python scripts/qualification_filesystem.py" in profile
    assert "--offline --frozen --no-sync --group test" in profile
