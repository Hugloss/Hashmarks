from pathlib import Path


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
