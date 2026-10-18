"""Qualified call evidence is independent of unrelated same-name declarations."""

from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.decision_session import DecisionRefreshRequired


def _write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _noise(root: Path) -> None:
    for index in range(70):
        _write(
            root,
            f"unrelated/noise_{index:03}.py",
            "def helper(value): return value\n"
            "class Worker:\n"
            "    def helper(self, value): return value\n",
        )


@pytest.mark.parametrize(
    ("source", "target", "callee"),
    [
        (
            "class Worker:\n"
            "    @staticmethod\n"
            "    def helper(value): return value + 1\n"
            "def authority(value): return Worker.helper(value)\n",
            "authority",
            "pkg/core.py::Worker.helper",
        ),
        (
            "from .worker import Worker as W\n"
            "def authority(value): return W.helper(value)\n",
            "authority",
            "pkg/worker.py::Worker.helper",
        ),
        (
            "class Worker:\n"
            "    def helper(self, value): return value + 1\n"
            "    def authority(self, value): return self.helper(value)\n",
            "Worker.authority",
            "pkg/core.py::Worker.helper",
        ),
        (
            "from .worker import helper as selected\n"
            "def authority(value): return selected(value)\n",
            "authority",
            "pkg/worker.py::helper",
        ),
        (
            "from .facade import PublicWorker as W\n"
            "def authority(value): return W.helper(value)\n",
            "authority",
            "pkg/worker.py::Worker.helper",
        ),
    ],
    ids=[
        "local-class",
        "imported-class",
        "self",
        "imported-function",
        "class-reexport",
    ],
)
def test_unrelated_name_crowding_preserves_qualified_call_and_caller(
    tmp_path: Path, source: str, target: str, callee: str
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/core.py", source)
    _write(
        tmp_path,
        "pkg/worker.py",
        "def helper(value): return value + 1\n"
        "class Worker:\n"
        "    @staticmethod\n"
        "    def helper(value): return value + 1\n",
    )
    _write(tmp_path, "pkg/facade.py", "from .worker import Worker as PublicWorker\n")
    selected = f"pkg/core.py::{target}"
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as repo:
        for crowded in (False, True):
            if crowded:
                _noise(tmp_path)
            repo.index.sync()
            packet = repo.structure.locality(selected, refresh=False)
            assert {row["symbol_id"] for row in assert_records(packet["nodes"])} == {
                selected,
                callee,
            }
            assert {
                (row["source_symbol_id"], row["resolved_symbol_id"])
                for row in assert_records(packet["edges"])
                if row["resolved_symbol_id"]
            } == {(selected, callee)}
            reverse = repo.structure.locality(callee, max_depth=0, refresh=False)
            node = assert_records(reverse["nodes"])[0]
            assert node["exact_caller_count"] == 1
            assert {
                (row["path"], row["source"])
                for row in assert_records(node["exact_callers"])
            } == {("pkg/core.py", target)}


@pytest.mark.parametrize(
    ("source", "target", "call"),
    [
        (
            "from .worker import Worker as W\n"
            "def authority(value, W): return W.helper(value)\n",
            "authority",
            "W.helper",
        ),
        (
            "from .worker import Worker as W\n"
            "from .other import Worker as W\n"
            "def authority(value): return W.helper(value)\n",
            "authority",
            "W.helper",
        ),
        (
            "from .worker import Worker as W\n"
            "if runtime_flag: W = unknown\n"
            "def authority(value): return W.helper(value)\n",
            "authority",
            "W.helper",
        ),
        (
            "class Worker:\n"
            "    def helper(self, value): return value\n"
            "    if runtime_flag:\n"
            "        def helper(self, value): return value + 1\n"
            "    def authority(self, value): return self.helper(value)\n",
            "Worker.authority",
            "self.helper",
        ),
        (
            "class Worker:\n"
            "    def helper(self, value): return value\n"
            "    def authority(self, value):\n"
            "        self = unknown\n"
            "        return self.helper(value)\n",
            "Worker.authority",
            "self.helper",
        ),
        (
            "class Worker:\n"
            "    def helper(self, value): return value\n"
            "    @classmethod\n"
            "    def authority(cls, value):\n"
            "        cls = unknown\n"
            "        return cls.helper(value)\n",
            "Worker.authority",
            "cls.helper",
        ),
        (
            "def factory():\n"
            "    def helper(value): return value\n"
            "    return helper\n"
            "def authority(value): return factory.helper(value)\n",
            "authority",
            "factory.helper",
        ),
    ],
    ids=[
        "parameter-shadow",
        "duplicate-import",
        "conditional-shadow",
        "conditional-method",
        "self-rebound",
        "cls-rebound",
        "function-attribute",
    ],
)
@pytest.mark.parametrize("crowded", [False, True], ids=["small", "crowded"])
def test_source_binding_uncertainty_survives_name_crowding(
    tmp_path: Path, source: str, target: str, call: str, crowded: bool
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    for path in ("pkg/worker.py", "pkg/other.py"):
        _write(
            tmp_path,
            path,
            "class Worker:\n    @staticmethod\n    def helper(value): return value\n",
        )
    _write(tmp_path, "pkg/core.py", source)
    if crowded:
        _noise(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as repo:
        packet = repo.structure.locality(f"pkg/core.py::{target}")
    edge = next(
        row for row in assert_records(packet["edges"]) if row["target_text"] == call
    )
    assert edge["resolved_symbol_id"] is None
    if call in {"self.helper", "cls.helper"}:
        assert any(
            row["target_text"] == call
            for row in assert_records(packet["unresolved_calls"])
        )
    assert {row["symbol_id"] for row in assert_records(packet["nodes"])} == {
        f"pkg/core.py::{target}"
    }


def test_changed_reexport_cannot_mix_current_ast_with_old_repository_binding(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    for path in ("pkg/worker.py", "pkg/other.py"):
        _write(
            tmp_path,
            path,
            "class Worker:\n    @staticmethod\n    def helper(value): return value\n",
        )
    _write(tmp_path, "pkg/facade.py", "from .worker import Worker as PublicWorker\n")
    _write(
        tmp_path,
        "pkg/core.py",
        "from .facade import PublicWorker as W\ndef authority(value): return W.helper(value)\n",
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as repo:
        repo.index.sync()
        repo.structure.locality("pkg/core.py::authority", refresh=False)
        generation = repo.store.generation()
        _write(tmp_path, "pkg/facade.py", "from .other import Worker as PublicWorker\n")
        with pytest.raises(DecisionRefreshRequired):
            repo.structure.locality("pkg/core.py::authority", refresh=False)
        assert repo.store.generation() == generation
        repo.index.sync()
        packet = repo.structure.locality("pkg/core.py::authority", refresh=False)
    assert {row["symbol_id"] for row in assert_records(packet["nodes"])} == {
        "pkg/core.py::authority",
        "pkg/other.py::Worker.helper",
    }


def test_member_binding_rejects_an_indexed_range_for_another_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(
        tmp_path,
        "owner.py",
        "class Worker:\n"
        "    @staticmethod\n"
        "    def helper(value): return value\n"
        "def authority(value): return Worker.helper(value)\n",
    )
    _noise(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as repo:
        repo.index.sync()
        original = repo.reads.symbols_for_path

        def wrong_range(path: str) -> list[dict[str, object]]:
            return [
                {**row, "start_line": 1, "end_line": 1}
                if row["qualname"] == "Worker.helper"
                else row
                for row in original(path)
            ]

        monkeypatch.setattr(repo.reads, "symbols_for_path", wrong_range)
        packet = repo.structure.locality("owner.py::authority", refresh=False)
    edge = next(
        row
        for row in assert_records(packet["edges"])
        if row["target_text"] == "Worker.helper"
    )
    assert edge["resolved_symbol_id"] is None
    assert {row["symbol_id"] for row in assert_records(packet["nodes"])} == {
        "owner.py::authority"
    }
