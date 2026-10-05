from pathlib import Path

from scripts.agent_evaluation import metrics_worker_inspection_ab


def test_worker_inspection_parser_owns_normal_defaults() -> None:
    args = metrics_worker_inspection_ab._parser().parse_args([])

    assert args.root == Path(".hashmarks/benchmarks/worker-inspection-ab")
    assert args.limit == 20
    assert args.output is None
    assert args.worker is False
    assert args.policy is None
    assert args.workspace is None
    assert args.tasks is None
