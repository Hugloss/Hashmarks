from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient

if TYPE_CHECKING:
    from pathlib import Path


def _repo(root: Path) -> tuple[Path, str]:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    source = root / "src" / "owner.py"
    source.write_text("def widget(): return 'old'\n", encoding="utf-8")
    (root / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\ndef test_widget(): assert widget() == 'new'\n",
        encoding="utf-8",
    )
    return source, "change widget behavior and verify widget test"


def _apply(previous: dict[str, object], delta: dict[str, object]) -> dict[str, object]:
    out = json.loads(json.dumps(previous))
    for change in delta["changes"]:
        path = change["path"]
        current = out
        for part in path[:-1]:
            current = current[part]
        key = path[-1]
        if change.get("delete"):
            del current[key]
        else:
            current[key] = change["value"]
    out["snapshot_identity"] = delta["to"]["snapshot_identity"]
    return out


def test_snapshot_contains_path_symbols_dependencies_and_repository_evidence(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        snapshot = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])
    assert snapshot["schema"] == "hashmarks.repository-intelligence-snapshot.v1"
    assert "src/owner.py" in snapshot["paths"]
    assert any(
        row.get("name") == "widget"
        for row in snapshot["paths"]["src/owner.py"]["symbols"]
    )
    assert isinstance(snapshot["paths"]["src/owner.py"]["dependencies"], list)
    assert snapshot["verification"]["member"] == "tests/test_owner.py"
    assert snapshot["freshness"]
    assert snapshot["storage"] == "derived-not-persisted"


def test_repository_delta_is_smaller_and_exactly_reconstructs_current_snapshot(
    tmp_path: Path,
) -> None:
    source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])
        source.write_text("def widget(): return 'new'\n", encoding="utf-8")
        codemap.sync(["src/owner.py"])
        delta = codemap.repository_intelligence_delta(
            task, ["src/owner.py"], previous_snapshot=previous
        )
        current = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])

    assert delta["schema"] == "hashmarks.repository-intelligence-delta.v1"
    assert delta["storage"] == "derived-not-persisted"
    assert delta["authority"] == "repository-intelligence-only"
    assert delta["execution_effect"] == "none"
    assert _apply(previous, delta) == current
    assert len(json.dumps(delta, sort_keys=True)) < len(
        json.dumps(current, sort_keys=True)
    )
    assert "paths" in delta["changed_sections"]
    assert "impact_changed" not in delta["semantic"]
    assert "verification_changed" not in delta["semantic"]
    assert delta["semantic"]["freshness_changed"] is True


def test_repository_delta_reports_dependency_change(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "a.py").write_text(
        "def widget(): return 'a'\n", encoding="utf-8"
    )
    (tmp_path / "src" / "b.py").write_text(
        "def widget(): return 'b'\n", encoding="utf-8"
    )
    route = tmp_path / "src" / "route.py"
    route.write_text(
        "from src.a import widget\ndef route(): return widget()\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_route.py").write_text(
        "from src.route import route\ndef test_route(): assert route() == 'b'\n",
        encoding="utf-8",
    )
    task = "change route widget behavior and verify route test"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.repository_intelligence_snapshot(task, ["src/route.py"])
        route.write_text(
            "from src.b import widget\ndef route(): return widget()\n", encoding="utf-8"
        )
        codemap.sync(["src/route.py"])
        delta = codemap.repository_intelligence_delta(
            task, ["src/route.py"], previous_snapshot=previous
        )
        current = codemap.repository_intelligence_snapshot(task, ["src/route.py"])
    assert _apply(previous, delta) == current
    assert any(
        row.get("target") == "src.b.widget"
        for row in delta["semantic"]["dependencies_added"]
    )
    assert any(
        row.get("target") == "src.a.widget"
        for row in delta["semantic"]["dependencies_removed"]
    )


def test_repository_delta_reports_symbol_add_remove_and_move(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    left = tmp_path / "src" / "left.py"
    right = tmp_path / "src" / "right.py"
    left.write_text("def widget(): return 1\n", encoding="utf-8")
    right.write_text("def helper(): return 2\n", encoding="utf-8")
    (tmp_path / "tests" / "test_left.py").write_text(
        "from src.left import widget\ndef test_widget(): assert widget()==1\n",
        encoding="utf-8",
    )
    task = "change widget and verify widget test"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.repository_intelligence_snapshot(
            task, ["src/left.py", "src/right.py"]
        )
        left.write_text("", encoding="utf-8")
        right.write_text(
            "def helper(): return 2\ndef widget(): return 1\n", encoding="utf-8"
        )
        codemap.sync(["src/left.py", "src/right.py"])
        delta = codemap.repository_intelligence_delta(
            task, ["src/left.py", "src/right.py"], previous_snapshot=previous
        )
    assert any(
        row.get("name") == "widget" and row["path"] == "src/right.py"
        for row in delta["semantic"]["symbols_added"]
    )
    assert any(
        row.get("name") == "widget" and row["path"] == "src/left.py"
        for row in delta["semantic"]["symbols_removed"]
    )
    assert any(
        row.get("name") == "widget"
        and row["from"] == "src/left.py"
        and row["to"] == "src/right.py"
        for row in delta["semantic"]["symbols_moved"]
    )


def test_repository_delta_rejects_foreign_repository_other_task_and_wrong_schema(
    tmp_path: Path,
) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _source_a, task = _repo(a)
    _source_b, _ = _repo(b)
    with CodeMap(a) as ca:
        ca.sync()
        previous = ca.repository_intelligence_snapshot(task, ["src/owner.py"])
    with CodeMap(b) as cb:
        cb.sync()
        with pytest.raises(ValueError, match="repository-mismatch"):
            cb.repository_intelligence_delta(
                task, ["src/owner.py"], previous_snapshot=previous
            )
    with CodeMap(a) as ca:
        ca.sync()
        with pytest.raises(ValueError, match="task-mismatch"):
            ca.repository_intelligence_delta(
                "different task", ["src/owner.py"], previous_snapshot=previous
            )
        with pytest.raises(ValueError, match="repository-intelligence-snapshot"):
            ca.repository_intelligence_delta(
                task, ["src/owner.py"], previous_snapshot={"schema": "wrong"}
            )


def _wait(client: CodeMapServiceClient) -> None:
    for _ in range(100):
        try:
            client.status()
            return
        except OSError:
            time.sleep(0.01)
    raise AssertionError("service did not start")


def test_repository_snapshot_and_delta_service_surface(tmp_path: Path) -> None:
    source, task = _repo(tmp_path)
    socket = tmp_path / "delta.sock"
    service = CodeMapService(tmp_path, socket_path=socket)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket)
    _wait(client)
    try:
        client.sync()
        previous = client.repository_intelligence_query(
            "snapshot", task, ["src/owner.py"]
        )["result"]
        source.write_text("def widget(): return 'new'\n", encoding="utf-8")
        client.sync()
        delta = client.repository_intelligence_query(
            "delta", task, ["src/owner.py"], previous_snapshot=previous
        )["result"]
        assert delta["schema"] == "hashmarks.repository-intelligence-delta.v1"
        assert delta["execution_effect"] == "none"
    finally:
        client.stop()
        thread.join(timeout=5)
