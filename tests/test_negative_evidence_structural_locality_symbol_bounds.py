from __future__ import annotations

from pathlib import Path

from hashmarks.codemap import CodeMap

_SYMBOL_LIMIT = 64


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _codemap(root: Path) -> CodeMap:
    return CodeMap(
        root,
        state_dir=root / ".hashmarks-test-state",
        artifact_db=root / ".hashmarks-test-artifacts.sqlite3",
    )


def _install_hidden_same_name_candidate(codemap: CodeMap, monkeypatch) -> None:
    original = codemap.store.symbols_named
    actual = [dict(row) for row in original("helper", limit=10)]
    assert len(actual) >= 2
    first, hidden = actual[:2]
    noise = [
        {
            **first,
            "path": f"archive/noise_{index:04d}.py",
            "evidence_visibility": "deny",
        }
        for index in range(_SYMBOL_LIMIT - 1)
    ]
    probe = [first, *noise, hidden]
    assert len(probe) == _SYMBOL_LIMIT + 1

    def symbols_named(name: str, *, limit: int):
        if name == "helper" and limit == _SYMBOL_LIMIT + 1:
            return probe[:limit]
        return original(name, limit=limit)

    monkeypatch.setattr(codemap.store, "symbols_named", symbols_named)


def test_structural_locality_bound_cannot_manufacture_unique_call_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/core.py",
        """
def helper(value):
    return value + 1


def helper(value):
    return value - 1


def authority(value):
    return helper(value)
""".lstrip(),
    )

    with _codemap(tmp_path) as codemap:
        codemap.sync()
        _install_hidden_same_name_candidate(codemap, monkeypatch)
        packet = codemap.structural_locality(
            "pkg/core.py::authority",
            max_depth=2,
            refresh=False,
        )
        helper = codemap.structural_locality(
            "pkg/core.py::helper",
            max_depth=0,
            refresh=False,
        )

    assert [row["symbol_id"] for row in packet["nodes"]] == [
        "pkg/core.py::authority"
    ]
    assert packet["dimensions"]["unresolved_call_count"] == 1
    unresolved = packet["unresolved_calls"][0]
    assert unresolved["target_text"] == "helper"
    assert unresolved["resolved_symbol_id"] is None
    assert unresolved["candidate_search"] == {
        "completeness": "incomplete",
        "truncation": "truncated",
        "negative_evidence_admissible": False,
        "uniqueness_admissible": False,
    }
    target = helper["nodes"][0]
    assert target["exact_caller_count"] == 0
    assert target["unresolved_caller_candidates"][0]["candidate_search"] == {
        "completeness": "incomplete",
        "truncation": "truncated",
        "negative_evidence_admissible": False,
        "uniqueness_admissible": False,
    }


def test_structural_locality_complete_symbol_search_still_resolves_exact_call(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/core.py",
        """
def helper(value):
    return value + 1


def authority(value):
    return helper(value)
""".lstrip(),
    )

    with _codemap(tmp_path) as codemap:
        packet = codemap.structural_locality(
            "pkg/core.py::authority",
            max_depth=2,
        )

    assert {row["symbol_id"] for row in packet["nodes"]} == {
        "pkg/core.py::authority",
        "pkg/core.py::helper",
    }
    helper_edge = next(row for row in packet["edges"] if row["target_text"] == "helper")
    assert helper_edge["resolved_symbol_id"] == "pkg/core.py::helper"
    assert helper_edge["candidate_search"] == {
        "completeness": "complete",
        "truncation": "complete",
        "negative_evidence_admissible": True,
        "uniqueness_admissible": True,
    }


def test_structural_locality_bound_cannot_prove_qualified_root_absence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/worker.py",
        """
class Worker:
    @staticmethod
    def helper(value):
        return value + 1
""".lstrip(),
    )
    _write(
        tmp_path,
        "pkg/core.py",
        """
from pkg.worker import Worker as W


def authority(value):
    return W.helper(value)
""".lstrip(),
    )

    with _codemap(tmp_path) as codemap:
        codemap.sync()
        original = codemap.store.symbols_named
        worker_rows = [dict(row) for row in original("Worker", limit=10)]
        assert len(worker_rows) == 1
        worker = worker_rows[0]
        noise = [
            {
                **worker,
                "path": f"archive/worker_noise_{index:04d}.py",
                "evidence_visibility": "deny",
            }
            for index in range(_SYMBOL_LIMIT)
        ]
        probe = [*noise, worker]
        assert len(probe) == _SYMBOL_LIMIT + 1

        def symbols_named(name: str, *, limit: int):
            if name == "Worker" and limit == _SYMBOL_LIMIT + 1:
                return probe[:limit]
            return original(name, limit=limit)

        monkeypatch.setattr(codemap.store, "symbols_named", symbols_named)
        packet = codemap.structural_locality(
            "pkg/core.py::authority",
            max_depth=2,
            refresh=False,
        )

    assert [row["symbol_id"] for row in packet["nodes"]] == [
        "pkg/core.py::authority"
    ]
    assert packet["dimensions"]["unresolved_call_count"] == 1
    assert packet["dimensions"]["external_or_unindexed_call_count"] == 0
    unresolved = packet["unresolved_calls"][0]
    assert unresolved["target_text"] == "W.helper"
    assert unresolved["candidate_search"]["completeness"] == "incomplete"
    assert unresolved["candidate_search"]["negative_evidence_admissible"] is False
