from scripts.agent_evaluation import metrics_worker_multistep_ab


def test_worker_multistep_parser_owns_normal_defaults() -> None:
    args = metrics_worker_multistep_ab._parser().parse_args([])

    assert args.root.as_posix() == ".hashmarks/benchmarks/worker-multistep-ab"
    assert args.limit == 20
    assert args.output is None
    assert args.worker is False
    assert args.policy is None
    assert args.workspace is None
    assert args.tasks is None


def test_worker_multistep_make_alias_delegates_normal_root() -> None:
    text = (metrics_worker_multistep_ab._REPO_ROOT / "Makefile").read_text(
        encoding="utf-8"
    )

    assert "scripts.agent_evaluation.metrics_worker_multistep_ab" in text
    assert "--output .hashmarks/metrics/worker-multistep-ab-latest.json" in text
    assert "--root .hashmarks/benchmarks/worker-multistep-ab" not in text
