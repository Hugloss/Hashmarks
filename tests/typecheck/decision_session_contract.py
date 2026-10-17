"""Decision decorators retain method arguments, returns, and session receivers."""

from typing import assert_type

from hashmarks.codemap import CodeMap
from hashmarks.codemap.decision_session import (
    ReadScope,
    decision_scoped,
    diagnostic_producer,
    incomplete_decision_scoped,
)
from hashmarks.codemap.task_evidence_types import TaskActionMap


@diagnostic_producer
@decision_scoped
def _complete(owner: CodeMap, *, limit: int) -> str:
    return str(limit)


@incomplete_decision_scoped
def _incomplete(owner: CodeMap, path: str) -> int:
    return len(path)


def check_contract(owner: CodeMap) -> None:
    assert_type(_complete(owner, limit=3), str)
    assert_type(_incomplete(owner, "src/owner.py"), int)
    assert_type(owner.task_action_map("inspect owner"), TaskActionMap)
    with owner.reads.session() as session:
        assert_type(session, ReadScope)
