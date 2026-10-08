from __future__ import annotations

from collections import Counter
from pathlib import Path

from hashmarks.codemap.engine import CodeMap
from hashmarks.codemap.task_action_evidence import TaskActionEvidenceMixin
from hashmarks.codemap.task_action_types import _TaskActionConfigState


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_config_specificity_reuses_positive_and_zero_scores() -> None:
    reads: Counter[int] = Counter()

    class RowText(dict[int, str]):
        def __getitem__(self, row_id: int) -> str:
            reads[row_id] += 1
            return super().__getitem__(row_id)

    rows: list[dict[str, object]] = [
        {"path": "src/timeout.py", "domains": ["source"], "canonical_rank": 1},
        {"path": "src/unrelated.py", "domains": ["source"], "canonical_rank": 2},
    ]
    state = _TaskActionConfigState(
        task_terms=["timeout"],
        row_text=RowText({id(row): str(row["path"]) for row in rows}),
        term_rows={"timeout": 1},
    )

    assert TaskActionEvidenceMixin._task_action_config_anchor(rows, state) is rows[0]
    assert (
        TaskActionEvidenceMixin._task_action_fallback_config_source_anchor(rows, state)
        is rows[0]
    )
    assert reads == {id(row): 1 for row in rows}


def test_equal_config_specificity_preserves_nonunique_result() -> None:
    rows: list[dict[str, object]] = [{"path": "a.toml"}, {"path": "b.toml"}]
    state = _TaskActionConfigState(
        task_terms=["timeout"],
        row_text={id(row): "timeout" for row in rows},
        term_rows={"timeout": 2},
    )

    assert TaskActionEvidenceMixin._unique_best_concrete_config(rows, state) is None


def test_config_request_selects_config_edit_surface(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", "[tool.demo]\ntimeout = 30\n")
    _write(tmp_path, "src/main.py", "DEFAULT_TIMEOUT = 30\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        result = codemap.task_action_map("update timeout config")

    edit, ambiguity = result["edit"], result["ambiguity"]
    assert isinstance(edit, dict)
    assert isinstance(ambiguity, dict)
    assert edit["path"] == "pyproject.toml"
    assert ambiguity["ambiguous"] is False


def test_config_source_fallback_preserves_test_verification_role(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/config_manager.py", "DEFAULT_TIMEOUT = 30\n")
    _write(tmp_path, "tests/test_config.py", "def test_timeout(): pass\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        result = codemap.task_action_map("change the timeout setting")

    edit, verify = result["edit"], result["verify"]
    assert isinstance(edit, dict)
    assert isinstance(verify, dict)
    assert edit["path"] == "src/config_manager.py"
    assert verify["path"] == "tests/test_config.py"


def test_locally_admitted_config_siblings_have_scoring_evidence(tmp_path: Path) -> None:
    _write(tmp_path, "service/timeout_manager.py", "DEFAULT_TIMEOUT = 30\n")
    _write(tmp_path, "service/a.toml", "[opaque]\nvalue = 1\n")
    _write(tmp_path, "service/b.toml", "[opaque]\nvalue = 2\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        result = codemap.task_action_map("update timeout config", limit=5)

    edit = result["edit"]
    assert isinstance(edit, dict)
    assert edit["path"] == "service/a.toml"
    assert edit["locality_projection"] is True
