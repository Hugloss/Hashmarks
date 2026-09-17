from pathlib import Path


def test_watcher_readiness_failure_never_reads_live_stderr_unbounded() -> None:
    source = Path(__file__).with_name("test_codemap.py").read_text(encoding="utf-8")
    marker = "CodeMap watcher did not become ready"
    prefix = source[: source.index(marker)]
    failure_branch = prefix[prefix.rfind("else:") :]
    assert "proc.wait(timeout=2)" in failure_branch
    assert "proc.kill()" in failure_branch
    assert "proc.stderr.read()" not in failure_branch
    assert "proc.communicate(" not in failure_branch
