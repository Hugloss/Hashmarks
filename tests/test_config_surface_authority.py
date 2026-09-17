from pathlib import Path

from hashmarks.codemap import CodeMap


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base_repo(root: Path) -> None:
    _write(root / "src/case/__init__.py", "")
    _write(
        root / "src/case/policy.py",
        "from pathlib import Path\n\n"
        "def accepted_suffix() -> str:\n"
        "    text = Path(__file__).with_name('policy.toml').read_text()\n"
        "    return '-old' if '-old' in text else '-new'\n",
    )
    _write(
        root / "src/case/route.py",
        "from .policy import accepted_suffix\n\n"
        "def handle_flare001(value: str) -> str:\n"
        "    return value + accepted_suffix()\n",
    )
    _write(
        root / "tests/case/test_behavior.py",
        "from src.case.route import handle_flare001\n\n"
        "def test_flare001_contract():\n"
        "    assert handle_flare001('x') == 'x-new'\n",
    )


def test_explicit_config_surface_beats_same_stem_contract_source(
    tmp_path: Path,
) -> None:
    _base_repo(tmp_path)
    _write(tmp_path / "src/case/policy.toml", "suffix = '-old'\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Change flare001 policy.toml from x-old to x-new"
        )

    assert action["edit"]["path"] == "src/case/policy.toml"
    assert action["verify"]["path"] == "tests/case/test_behavior.py"


def test_multiple_concrete_configs_use_unique_task_specificity(tmp_path: Path) -> None:
    _base_repo(tmp_path)
    _write(tmp_path / "src/case/policy.toml", "suffix = '-old'\n")
    _write(tmp_path / "src/case/policy.yaml", "suffix: '-old'\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        toml = codemap.task_action_map("Change flare001 policy.toml to x-new")
        yaml = codemap.task_action_map("Change flare001 policy.yaml to x-new")

    assert toml["edit"]["path"] == "src/case/policy.toml"
    assert yaml["edit"]["path"] == "src/case/policy.yaml"


def test_multiple_concrete_configs_do_not_invent_generic_winner(tmp_path: Path) -> None:
    _base_repo(tmp_path)
    _write(tmp_path / "src/case/policy.toml", "suffix = '-old'\n")
    _write(tmp_path / "src/case/policy.yaml", "suffix: '-old'\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        generic = codemap.task_action_map(
            "Repair flare001 accepted response contract to x-new"
        )

    assert generic["edit"]["path"] == "src/case/policy.py"
