from pathlib import Path

from hashmarks.codemap import CodeMap
from hashmarks.file_store import UnstableFileError


def _repo(root: Path, count: int = 12) -> None:
    src = root / "src"
    src.mkdir()
    for index in range(count):
        (src / f"m{index:03d}.py").write_text(f"VALUE = {index}\n", encoding="utf-8")


def test_warm_reconciliation_preserves_exact_workspace_identity(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        first = codemap.sync()
    with CodeMap(tmp_path) as codemap:
        second = codemap.sync()
    assert second.workspace_fingerprint == first.workspace_fingerprint
    assert second.parsed_artifacts == 0
    assert second.reused_artifacts == first.indexed


def test_batched_digest_failure_falls_back_without_losing_peer_files(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        first = codemap.sync()
    with CodeMap(tmp_path) as codemap:

        def fail_batch(*args, **kwargs):
            raise UnstableFileError("synthetic batch instability")

        monkeypatch.setattr(codemap.file_store, "digest_many_info", fail_batch)
        second = codemap.sync()
    assert second.workspace_fingerprint == first.workspace_fingerprint
    assert second.skipped == 0
    assert second.parsed_artifacts == 0
    assert second.reused_artifacts == first.indexed


def test_compact_reuse_rows_match_per_path_authority(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        paths = sorted(codemap.store.paths())
        compact = codemap.store.file_reuse_rows(paths)
        for path in paths:
            row = codemap.store.file_row(path)
            assert row is not None
            assert compact[path] == (
                str(row["file_digest"]),
                str(row["artifact_key"]),
                str(row["evidence_visibility"]),
                str(row["module_name"] or ""),
                codemap.store.has_derived_nodes(path),
            )
