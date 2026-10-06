from scripts.agent_evaluation import metrics_worker_behavior_ab


def test_worker_behavior_parser_owns_normal_query_limit() -> None:
    args = metrics_worker_behavior_ab._parser().parse_args([])

    assert args.limit == 20
    assert args.root is None
    assert args.output is None
    assert args.worker is False
    assert args.policy is None
