from scripts.agent_evaluation import metrics_agent_economics


def test_agent_economics_parser_owns_default_mode() -> None:
    args = metrics_agent_economics._parser().parse_args(["--root", "."])

    assert args.mode == "paired"
    assert args.limit == 20
    assert args.output is None
