from pathlib import Path

from scripts.agent_evaluation import metrics_agent_corpus


def test_metrics_agent_corpus_parser_owns_normal_defaults() -> None:
    args = metrics_agent_corpus._parser().parse_args([])

    assert args.workspace == Path(".")
    assert args.corpus == Path("benchmarks/agent_tasks.json")
    assert args.budget == 1200
    assert args.limit == 20
    assert args.output is None
