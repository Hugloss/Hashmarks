from pathlib import Path

from hashmarks.codemap import CodeMap


def _repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "engine.py").write_text(
        "def widget(value: str) -> str:\n    return value + '-old'\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_engine.py").write_text(
        "from src.engine import widget\n\n"
        "def test_widget():\n"
        "    assert widget('x') == 'x-new'\n",
        encoding="utf-8",
    )


def test_unknown_freshness_converges_across_decision_surfaces(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    task = "widget implementation test"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        generation = codemap.store.generation()

        def unknown_status(observation=None):
            del observation
            return generation, generation, None

        monkeypatch.setattr(codemap, "_generation_status", unknown_status)

        packet = codemap.task_decision_packet(task, token_budget=256)
        decision = codemap.task_decision_brief(task, token_budget=256)
        action = codemap.task_action_brief(task, token_budget=256)

    assert packet["identity"]["stale"] is True
    assert packet["identity"]["codemap_complete"] is True
    assert packet["evidence_receipt"]["stale"] is None

    assert decision["stale"] is True
    assert decision["evidence_receipt"]["stale"] is None

    assert action["status"] == "safe-unknown"
    assert action["evidence_receipt"]["stale"] is None


def test_codemap_completeness_does_not_redefine_freshness(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    task = "widget implementation test"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        generation = codemap.store.generation()

        def current_status(observation=None):
            del observation
            return generation, generation, False

        monkeypatch.setattr(codemap, "_generation_status", current_status)
        monkeypatch.setattr(
            codemap,
            "_codemap_build_state",
            lambda: {"state": "BUILDING", "complete": False},
        )

        packet = codemap.task_decision_packet(task, token_budget=256)

    assert packet["identity"]["stale"] is False
    assert packet["identity"]["codemap_complete"] is False
    assert packet["identity"]["codemap_build_state"] == "BUILDING"

def test_action_brief_status_consumes_receipt_freshness_once(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    task = "widget implementation test"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        generation = codemap.store.generation()
        action = codemap.task_action_map(task)
        reads = 0

        def one_freshness_read(observation=None):
            nonlocal reads
            del observation
            reads += 1
            if reads > 1:
                raise AssertionError(
                    "task action brief re-read freshness after assembling its receipt"
                )
            return generation, generation, False

        monkeypatch.setattr(codemap, "_generation_status", one_freshness_read)
        brief = codemap._task_action_brief_from_action(
            action,
            task=task,
            token_budget=256,
            limit=20,
        )

    assert reads == 1
    assert brief["status"] == "safe-fresh"
    assert brief["evidence_receipt"]["stale"] is False

