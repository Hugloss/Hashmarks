from pathlib import Path

from scripts.agent_evaluation import codex_agent_economics


def test_codex_agent_economics_parser_owns_default_root() -> None:
    args = codex_agent_economics._parser().parse_args([])

    assert args.root == Path(".hashmarks/benchmarks/codex-agent-economics")
    assert args.output is None
    assert args.preflight is False
