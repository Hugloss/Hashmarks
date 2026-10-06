from scripts.agent_evaluation import metrics_blind_worker_ab


def test_blind_worker_parser_owns_normal_query_limit() -> None:
    args = metrics_blind_worker_ab._parser().parse_args([])

    assert args.limit == 20
    assert args.root is None
    assert args.output is None
    assert args.worker is False
