from pathlib import Path

from hashmarks.codemap import CodeMap


def _repo(root: Path) -> None:
    (root / 'src').mkdir()
    (root / 'tests').mkdir()
    (root / 'src' / 'engine.py').write_text("def widget(value: str) -> str:\n    return value + '-old'\n")
    (root / 'tests' / 'test_engine.py').write_text(
        "from src.engine import widget\n\ndef test_widget():\n    assert widget('x') == 'x-new'\n"
    )


def test_decision_brief_budget_sweep_finds_smallest_safe_agent_budget(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        sweep = codemap.task_decision_brief_budget_sweep(
            'change widget behavior implementation test', budgets=(1, 32, 64, 128, 256, 512)
        )
    assert sweep['schema'] == 'hashmarks.task-decision-brief-budget-sweep.v1'
    rows = sweep['rows']
    assert [row['budget'] for row in rows] == [1, 32, 64, 128, 256, 512]
    safe = [row for row in rows if row['safe']]
    assert safe
    assert sweep['smallest_safe_budget'] == safe[0]['budget']
    assert sweep['smallest_safe_visible_brief_bytes'] == safe[0]['visible_brief_bytes']
    assert all(row['visible_brief_bytes'] > 0 for row in rows)
    assert all(row['edit_available'] for row in safe)
    assert all(row['verify_available'] for row in safe)
    assert sweep['optimization_target'] == 'minimum-safe-agent-visible-evidence'


def test_unsafe_budget_exposes_missing_roles_instead_of_false_qualification(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        sweep = codemap.task_decision_brief_budget_sweep('widget implementation test', budgets=(1, 512))
    assert sweep['rows'][0]['safe'] is False
    assert sweep['rows'][0]['missing_roles']
    assert sweep['rows'][-1]['safe'] is True
