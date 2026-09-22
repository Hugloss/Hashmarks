from pathlib import Path

from hashmarks.codemap import CodeMap


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base(repo: Path) -> None:
    _write(repo / "pyproject.toml", "[tool.pytest.ini_options]\ntestpaths=['tests']\n")
    _write(repo / "src/__init__.py", "")
    _write(repo / "src/feature/__init__.py", "")


def test_dual_live_task_local_owners_require_discrimination(tmp_path: Path) -> None:
    _base(tmp_path)
    _write(
        tmp_path / "src/feature/engine_a.py",
        "def transform(value: str) -> str:\n    return value + '-a'\n",
    )
    _write(
        tmp_path / "src/feature/engine_b.py",
        "def transform(value: str) -> str:\n    return value + '-b'\n",
    )
    _write(
        tmp_path / "src/feature/api_a.py",
        "from .engine_a import transform\ndef handle_quartz_dual(value: str) -> str:\n    return transform(value)\n",
    )
    _write(
        tmp_path / "src/feature/api_b.py",
        "from .engine_b import transform\ndef handle_quartz_dual_b(value: str) -> str:\n    return transform(value)\n",
    )
    _write(
        tmp_path / "tests/test_a.py",
        "from src.feature.api_a import handle_quartz_dual\ndef test_quartz_dual_a():\n    assert handle_quartz_dual('x') == 'x-a'\n",
    )
    _write(
        tmp_path / "tests/test_b.py",
        "from src.feature.api_b import handle_quartz_dual_b\ndef test_quartz_dual_b():\n    assert handle_quartz_dual_b('x') == 'x-b'\n",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix quartz_dual transform behavior across both active product paths"
        )
        packet = codemap.task_decision_packet(
            "Fix quartz_dual transform behavior across both active product paths"
        )

    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "multiple-task-local-structural-owners"
    assert len(action["ambiguity"]["task_local_structural_owners"]) == 2
    assert action["ownership_authority"]["owner_resolved"] is False
    assert packet["discrimination"]["needed"] is True
    assert packet["discrimination"]["reason"] == "competing-action-roles"


def test_multiple_task_local_tests_for_same_candidate_remain_unproven(
    tmp_path: Path,
) -> None:
    _base(tmp_path)
    _write(
        tmp_path / "src/feature/engine.py",
        "def transform(value: str) -> str:\n    return value + '-ok'\n",
    )
    _write(
        tmp_path / "src/feature/api.py",
        "from .engine import transform\ndef handle_quartz_single(value: str) -> str:\n    return transform(value)\n",
    )
    for name in ("a", "b"):
        _write(
            tmp_path / f"tests/test_{name}.py",
            f"from src.feature.api import handle_quartz_single\ndef test_quartz_single_{name}():\n    assert handle_quartz_single('x') == 'x-ok'\n",
        )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("Fix quartz_single transform behavior")
        packet = codemap.task_decision_packet("Fix quartz_single transform behavior")

    assert action["ambiguity"]["ambiguous"] is False
    assert action["ambiguity"]["task_local_structural_owners"] == [
        "src/feature/engine.py"
    ]
    assert action["ownership_authority"]["owner_resolved"] is False
    assert action["ownership_authority"]["candidate_owner"] == "src/feature/engine.py"
    assert packet["edit"]["path"] == "src/feature/engine.py"
    assert packet["discrimination"]["needed"] is True
    assert packet["discrimination"]["reason"] == "ownership-unresolved"
