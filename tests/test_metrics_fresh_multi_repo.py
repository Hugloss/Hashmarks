from pathlib import Path

from scripts.agent_evaluation import metrics_fresh_multi_repo


def test_fresh_multi_repo_parser_owns_normal_defaults() -> None:
    args = metrics_fresh_multi_repo._parser().parse_args(
        ["--root", ".hashmarks/benchmarks/fresh-multi-repo"]
    )

    assert args.root == Path(".hashmarks/benchmarks/fresh-multi-repo")
    assert args.budget == 1200
    assert args.limit == 20
    assert args.output is None
    assert args.min_file_recall == 1.0
    assert args.min_symbol_recall == 1.0
    assert args.max_fallback_rate == 0.0
