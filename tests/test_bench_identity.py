from __future__ import annotations

import json
import sys

import pytest


@pytest.mark.parametrize("manifest", ["directory", "files"])
def test_identity_benchmark_reports_each_identity_scenario(
    manifest: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from benchmarks import bench_identity

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bench_identity.py",
            "--files",
            "6",
            "--files-per-dir",
            "2",
            "--manifest",
            manifest,
        ],
    )

    bench_identity.main()

    result = json.loads(capsys.readouterr().out)
    assert result["manifest"] == manifest
    assert result["files"] == 6
    assert set(result["seconds"]) == {
        "cold",
        "hot_unchanged",
        "warm_scan_hot_cache_dropped",
        "one_file_edit",
        "up_to_100_file_edit",
        "strong_verify",
        "fresh_process_warm_cache",
    }
    assert result["identity_checks"] == {
        "cold_equals_hot": True,
        "cold_equals_warm_scan": True,
        "one_edit_changes_identity": True,
        "batch_edit_changes_identity": True,
    }
    assert result["workspace"] is None
