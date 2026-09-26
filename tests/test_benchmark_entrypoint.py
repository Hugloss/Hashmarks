from pathlib import Path

import pytest

from scripts.agent_evaluation.benchmark import _load


def test_benchmark_profile_resolves_stored_module_args_and_environment(tmp_path: Path):
    config = tmp_path / "benchmark.toml"
    config.write_text(
        """
[profile.chatgpt]
module = "example.benchmark"
args = ["--budget", "1200"]
env = { HASHMARKS_CONSTRAINED_HOST = "1" }
"""
    )

    command, env = _load(config, "chatgpt")

    assert command[1:] == ["-m", "example.benchmark", "--budget", "1200"]
    assert env == {"HASHMARKS_CONSTRAINED_HOST": "1"}


def test_benchmark_profile_rejects_unknown_name(tmp_path: Path):
    config = tmp_path / "benchmark.toml"
    config.write_text('[profile.local]\nmodule = "example.benchmark"\n')

    with pytest.raises(SystemExit, match="choose: local"):
        _load(config, "missing")


def test_project_exposes_benchmark_console_entrypoint():
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text()

    assert (\n        'hashmarks-benchmark = "scripts.agent_evaluation.benchmark:main"' in pyproject\n    )
