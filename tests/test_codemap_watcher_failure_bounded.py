from pathlib import Path


def test_watcher_readiness_failure_never_reads_live_stderr_unbounded() -> None:
    source = Path(__file__).with_name("test_codemap.py").read_text(encoding="utf-8")
    start = source.index("def _stop_watcher")
    end = source.index("def test_codemap_watcher_keeps_map_hot", start)
    cleanup_helper = source[start:end]
    assert "proc.wait(timeout=" in cleanup_helper
    assert "proc.kill()" in cleanup_helper
    assert "proc.stderr.read()" not in cleanup_helper
    assert "proc.communicate(" not in cleanup_helper
