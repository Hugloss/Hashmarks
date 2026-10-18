from contract_assertions import assert_integer, assert_object

from scripts.agent_evaluation import metrics_agent
from scripts.agent_evaluation.metrics_agent import SCHEMA, collect


def test_agent_metrics_measure_sync_retrieval_and_bounded_context() -> None:
    result = collect(files=8, budget=256)

    assert result["schema"] == SCHEMA
    assert result["parameters"] == {"files": 8, "budget": 256}
    assert assert_object(result["index"])["cold_parsed"] == 8
    assert assert_object(result["index"])["hot_parsed"] == 0
    assert assert_object(result["index"])["hot_reused"] == 8
    assert assert_object(result["index"])["edit_parsed"] == 1
    assert assert_object(result["retrieval"])["target_present_top10"] is True
    assert assert_integer(assert_object(result["tokens"])["context_estimate"]) <= 256
    assert set(assert_object(result["seconds"])) == {
        "cold_sync",
        "hot_sync",
        "find",
        "context",
        "one_file_reindex",
    }


def test_metrics_agent_parser_owns_normal_defaults() -> None:
    args = metrics_agent._parser().parse_args([])

    assert args.files == 1000
    assert args.budget == 1000
