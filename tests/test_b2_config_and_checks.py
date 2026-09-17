from pathlib import Path

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_domains import RepositoryDomain, classify_repository_path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_checks_python_spec_is_verification_domain() -> None:
    domains = set(classify_repository_path("checks/widget/contract_spec.py"))
    assert RepositoryDomain.TEST in domains
    assert RepositoryDomain.CONTRACT in domains
    assert RepositoryDomain.SOURCE in domains
    assert RepositoryDomain.TEST not in set(classify_repository_path("checks/widget/helper.py"))


def test_explicit_config_task_uses_verification_backed_active_locality(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[tool.pytest.ini_options]\ntestpaths=['tests']\n")
    _write(tmp_path / "src/__init__.py", "")
    _write(tmp_path / "src/widget/__init__.py", "")
    _write(tmp_path / "src/widget/policy.toml", "mode = 'active'\n")
    _write(tmp_path / "src/widget/engine.py", "from pathlib import Path\ndef transform(value: str) -> str:\n    policy = Path(__file__).with_name('policy.toml').read_text()\n    return value + ('-active' if 'active' in policy else '-legacy')\n")
    _write(tmp_path / "src/widget/api.py", "from .engine import transform\ndef handle_quartz_config(value: str) -> str:\n    return transform(value)\n")
    _write(tmp_path / "tests/test_widget.py", "from src.widget.api import handle_quartz_config\ndef test_quartz_config():\n    assert handle_quartz_config('x') == 'x-active'\n")
    _write(tmp_path / "legacy/compat.py", "# Change the quartz_config accepted-response policy; behavior is configuration-controlled\ndef handle_quartz_config(value: str) -> str:\n    return value + '-legacy'\n")

    task = "Change the quartz_config accepted-response policy; behavior is configuration-controlled"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task)

    assert action["edit"]["path"] == "src/widget/policy.toml"


def test_checks_spec_can_be_selected_as_verification(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[tool.pytest.ini_options]\ntestpaths=['tests']\n")
    _write(tmp_path / "src/__init__.py", "")
    _write(tmp_path / "src/widget/__init__.py", "")
    _write(tmp_path / "src/widget/engine.py", "def transform(value: str) -> str:\n    return value + '-active'\n")
    _write(tmp_path / "src/widget/api.py", "from .engine import transform\ndef handle_quartz_checks(value: str) -> str:\n    return transform(value)\n")
    _write(tmp_path / "checks/widget/contract_spec.py", "from src.widget.api import handle_quartz_checks\ndef test_quartz_checks_contract():\n    assert handle_quartz_checks('x') == 'x-active'\n")

    task = "Repair quartz_checks behavior and locate its verification outside the default tests tree"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task)

    assert action["edit"]["path"] == "src/widget/engine.py"
    assert action["verify"]["path"] == "checks/widget/contract_spec.py"


def test_test_prefixed_python_module_under_src_is_not_test_domain() -> None:
    domains = set(classify_repository_path("src/oh_goon/repository_tooling/test_batches.py"))
    assert RepositoryDomain.SOURCE in domains
    assert RepositoryDomain.TEST not in domains
    assert RepositoryDomain.TEST in set(classify_repository_path("tests/unit/test_batches.py"))
