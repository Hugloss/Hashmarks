from pathlib import Path

from scripts.metrics_codemap_concurrency import probe


def test_shared_service_pressure_keeps_one_generation_and_one_sync(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(); (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "adapter.py").write_text("class Adapter:\n    pass\n")
    (tmp_path / "tests" / "test_adapter.py").write_text("from src.adapter import Adapter\n")
    result = probe(tmp_path, concurrencies=(1, 2, 4, 8), requests_per_worker=1)
    assert result["ownership"] == "single-warm-codemap"
    assert result["one_time_sync"] is True
    assert result["all_generations_consistent"] is True
    assert result["all_deterministic"] is True
    assert [row["concurrency"] for row in result["rows"]] == [1, 2, 4, 8]
    assert all(row["requests"] == row["concurrency"] for row in result["rows"])
    assert all(row["p99_ms"] >= row["p50_ms"] >= 0 for row in result["rows"])
