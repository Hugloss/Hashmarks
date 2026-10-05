from __future__ import annotations

from scripts import metrics


def test_metrics_parser_owns_normal_baseline_defaults() -> None:
    args = metrics._parser().parse_args([])

    assert args.workspace == "."
    assert args.files == 10_000
    assert args.files_per_dir == 250
    assert args.hot_requests == 20
    assert args.skip_daemon is False
    assert args.output is None
