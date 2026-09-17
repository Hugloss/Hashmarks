from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hashmarks.semantic_equivalence import verify_cold_warm_semantic_equivalence

if TYPE_CHECKING:
    from pathlib import Path


def _repository(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "engine.py").write_text(
        "def normalize_widget(value):\n    return value.strip().lower()\n"
    )
    (root / "tests" / "test_engine.py").write_text(
        "from src.engine import normalize_widget\n"
        "def test_normalize_widget():\n"
        "    assert normalize_widget(' X ') == 'x'\n"
    )


@pytest.mark.parametrize(
    "query",
    ["find_task", "task_action_map", "task_decision_packet"],
)
def test_cold_warm_semantic_equivalence_for_supported_queries(
    tmp_path: Path,
    query: str,
) -> None:
    _repository(tmp_path)
    result = verify_cold_warm_semantic_equivalence(
        tmp_path,
        query=query,
        task="normalize_widget implementation test",
        limit=20,
    )

    assert result["equivalent"] is True
    assert result["cold_semantic"] == result["warm_semantic"]


def test_equivalence_helper_rejects_invalid_inputs(tmp_path: Path) -> None:
    _repository(tmp_path)
    with pytest.raises(ValueError, match="limit"):
        verify_cold_warm_semantic_equivalence(
            tmp_path,
            query="find_task",
            task="widget",
            limit=0,
        )
    with pytest.raises(ValueError, match="task"):
        verify_cold_warm_semantic_equivalence(
            tmp_path,
            query="find_task",
            task=" ",
        )
