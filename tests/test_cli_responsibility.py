from pathlib import Path


def test_repository_cli_registers_structural_locality_commands() -> None:
    import argparse

    from hashmarks.repository_cli import add_repository_cli

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_repository_cli(sub, add_common_arguments=lambda *_args, **_kwargs: None)

    for command, handler in (
        ("symbol", "_symbol_code"),
        ("deps", "_deps_code"),
        ("refs", "_refs_code"),
    ):
        parsed = parser.parse_args([command, "Widget.run"])
        assert parsed.query == "Widget.run"
        assert parsed.func.__name__ == handler

    locality = parser.parse_args(["structural-locality", "pkg/core.py::Worker.run"])
    assert locality.target == "pkg/core.py::Worker.run"
    assert locality.max_depth == 2
    assert locality.call_limit == 64
    assert locality.ref_limit == 256

    delta = parser.parse_args(
        [
            "structural-locality-delta",
            "--before",
            "before.json",
            "--after",
            "after.json",
        ]
    )
    assert delta.before == "before.json"
    assert delta.after == "after.json"


def test_top_level_cli_delegates_repository_command_family() -> None:
    import hashmarks.cli as cli

    source = Path(cli.__file__).read_text(encoding="utf-8")
    assert "from .repository_cli import add_repository_cli" in source
    assert "def _map_sync(" not in source
    assert "def _find_code(" not in source
    assert "def _task_evidence_code(" not in source


def test_repository_cli_does_not_acquire_execution_or_daemon_ownership() -> None:
    import hashmarks.repository_cli as repository_cli

    source = Path(repository_cli.__file__).read_text(encoding="utf-8")
    assert "IdentityDaemon" not in source
    assert "subprocess" not in source
    assert "ImpactTrustPolicy" not in source
    assert "benchmark_shards" not in source
