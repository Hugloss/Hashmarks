"""Task-retrieved tests survive broad reference discovery without gaining authority."""

from __future__ import annotations

from typing import TYPE_CHECKING

from contract_assertions import assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_contract import read_initial_projection
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_collection,
    decode_initial_packet,
)

if TYPE_CHECKING:
    from pathlib import Path


def _repository(root: Path) -> tuple[str, str]:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src/backend.py").write_text("def render(): return {'schema': 'root'}\n")
    (root / "tests/test_root_nested_schema_dto.py").write_text(
        "from src.backend import render\n"
        "def test_root_nested_schema_dto(): assert render()['schema'] == 'root'\n"
    )
    for index in range(20):
        (root / f"tests/test_smoke_{index:02}.py").write_text(
            "from src.backend import render\n"
            "def test_render(): assert isinstance(render(), dict)\n"
        )
    expected = "tests/test_client.py"
    (root / expected).write_text(
        "def test_root_nested_schema(public_client):\n"
        "    assert public_client.get('/schema').json()['schema'] == 'root'\n"
    )
    return "Fix root nested schema DTO in src/backend.py", expected


def test_task_candidate_survives_reference_fanout_without_reference_authority(
    tmp_path: Path,
) -> None:
    task, expected = _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task)
        packet = codemap.task_evidence(task)
        initial = read_initial_projection(
            decode_initial_packet(codemap.task_evidence(task, result_mode="initial"))
        )
    assert packet["ownership"]["owner"] is not None
    assert packet["ownership"]["owner"]["path"] == "src/backend.py"
    assert action["verify"] is not None
    assert action["verify"]["path"] == "tests/test_root_nested_schema_dto.py"
    relevance = packet["verification"]["relevance"]
    assert relevance["selected"] is not None
    assert relevance["selected"]["path"] == action["verify"]["path"]
    assert relevance["selection_changed"] is False
    assert len(relevance["candidates"]) == 8
    assert relevance.get("candidate_count") == 22
    row = next(row for row in relevance["candidates"] if row["path"] == expected)
    assert row.get("direct_reference") is False
    assert row.get("indirect_reference") is False
    assert row.get("reference_symbols") == []
    assert row.get("test_symbol") == "test_root_nested_schema"
    assert row.get("canonical_rank") is not None
    initial_relevance = initial["verification"]["relevance"]
    assert "candidates_encoding" in initial_relevance
    decoded = decode_initial_collection(
        initial_relevance["candidates"], initial_relevance["candidates_encoding"]
    )
    assert {row["path"] for row in decoded} == {
        row["path"] for row in relevance["candidates"]
    }


def test_disclosure_bounds_preserve_selected_verifier_and_candidate_population(
    tmp_path: Path,
) -> None:
    task, _ = _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        projections = [
            codemap.verification_relevance(task, candidate_limit=limit)
            for limit in (1, 3, 8)
        ]
    for limit, relevance in zip((1, 3, 8), projections, strict=True):
        assert len(relevance["candidates"]) == limit
        assert relevance.get("candidate_count") == 22
        assert relevance["selected"] is not None
        assert relevance["selected"]["path"] == "tests/test_root_nested_schema_dto.py"
        assert relevance["selected"]["path"] in {
            row["path"] for row in relevance["candidates"]
        }
        assert relevance["selection_changed"] is False
    assert projections[0]["selected"] == projections[-1]["selected"]


def test_short_identifier_components_remain_verification_task_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/backend.py").write_text("def field(): return None\n")
    for name in ("db", "fd"):
        (tmp_path / f"tests/test_field_{name}_options.py").write_text(
            "from src.backend import field\n"
            f"def test_{name}_options(): assert field() is None\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence("Inspect field db_type in src/backend.py")
    rows = {
        row["path"]: row for row in packet["verification"]["relevance"]["candidates"]
    }
    assert "db" in rows["tests/test_field_db_options.py"].get("task_anchor_terms", [])
    assert "db" not in rows["tests/test_field_fd_options.py"].get(
        "task_anchor_terms", []
    )


def test_production_lexical_fanout_cannot_hide_the_test_observation_scope(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/engine.py").write_text("def process(): return None\n")
    for index in range(80):
        (tmp_path / f"src/worker_{index:02}.py").write_text(
            "# Inspect cancellation scope cleanup in src engine py\n"
            "def observe(): return None\n"
        )
    (tmp_path / "src/test_cancellation.py").write_text(
        "# production module, not a test surface\n"
        "def cancellation_scope_cleanup(): return None\n"
    )
    expected = "tests/test_cancellation.py"
    (tmp_path / expected).write_text("def test_cancellation(client): client.close()\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence(
            "Inspect cancellation scope cleanup in src/engine.py"
        )
    relevance = packet["verification"]["relevance"]
    assert "task_matches" in relevance
    matches = assert_records(relevance["task_matches"].get("matches"))
    assert [row["path"] for row in matches] == [expected]
    row = next(row for row in relevance["candidates"] if row["path"] == expected)
    assert row.get("direct_reference") is False
    assert row.get("indirect_reference") is False
    assert all(
        row["path"] != "src/test_cancellation.py" for row in relevance["candidates"]
    )
