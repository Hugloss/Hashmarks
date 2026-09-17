from pathlib import Path

from hashmarks.codemap import CodeMap


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _configuration_siblings(root: Path, *, count: int = 6) -> list[dict[str, str]]:
    _write(root / "pyproject.toml", "[tool.pytest.ini_options]\ntestpaths=['tests']\n")
    _write(root / "src/__init__.py", "")
    tasks: list[dict[str, str]] = []
    for index in range(1, count + 1):
        token = f"flare{index:03d}"
        namespace = f"case_{index:03d}"
        package = root / "src" / namespace
        _write(package / "__init__.py", "")
        _write(
            package / "legacy.py",
            f"def old_{token}(value: str) -> str:\n    return value + '-legacy'\n",
        )
        _write(
            package / "route.py",
            "from pathlib import Path\n\n"
            f"def handle_{token}(value: str) -> str:\n"
            "    text = Path(__file__).with_name('policy.toml').read_text()\n"
            "    return value + ('-new' if \"mode = 'new'\" in text else '-old')\n",
        )
        _write(package / "policy.toml", "mode = 'old'\n")
        verify = f"tests/{namespace}/test_behavior.py"
        _write(
            root / verify,
            f"from src.{namespace}.route import handle_{token}\n\n"
            f"def test_{token}_accepted():\n"
            f"    assert handle_{token}('x') == 'x-new'\n",
        )
        tasks.append(
            {
                "token": token,
                "edit": f"src/{namespace}/policy.toml",
                "verify": verify,
            }
        )
    return tasks


def _configuration_query(token: str, *, prefix: str = "") -> str:
    return (
        f"Fix request {prefix} {token}: its active accepted response policy must produce x-new. "
        "Preserve route ownership and verify the accepted contract."
    )


def test_omitted_lowercase_alnum_identifier_recovers_task_local_action(
    tmp_path: Path,
) -> None:
    tasks = _configuration_siblings(tmp_path)
    target = tasks[-1]
    query = _configuration_query(target["token"])
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        views = codemap.task_query_views(query)
        action = codemap.task_action_map(query, limit=20, per_role=3)

    assert all(
        target["token"] not in views[key].split()
        for key in ("base", "governance", "evidence")
    )
    assert action["edit"]["path"] == target["edit"]
    assert action["verify"]["path"] == target["verify"]


def test_omitted_identifier_probe_survives_leading_version_protocol_tokens(
    tmp_path: Path,
) -> None:
    tasks = _configuration_siblings(tmp_path)
    target = tasks[-1]
    distractors = "python3 http2 sha256 ipv6 x86 utf8 tls13 utf16 http3 sha512 arm64 utf32 tls12 ipv4 python2 x64"
    query = _configuration_query(target["token"], prefix=distractors)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(query, limit=20, per_role=3)

    assert action["edit"]["path"] == target["edit"]
    assert action["verify"]["path"] == target["verify"]


def test_omitted_identifiers_preserve_existing_multi_owner_ambiguity(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "pyproject.toml", "[tool.pytest.ini_options]\ntestpaths=['tests']\n"
    )
    _write(tmp_path / "src/__init__.py", "")
    tokens = ("flare001", "flare002")
    for index, token in enumerate(tokens, start=1):
        namespace = f"feature_{index:03d}"
        _write(tmp_path / f"src/{namespace}/__init__.py", "")
        _write(
            tmp_path / f"src/{namespace}/engine.py",
            f"def transform_{token}(value: str) -> str:\n    return value + '-{index}'\n",
        )
        _write(
            tmp_path / f"src/{namespace}/api.py",
            f"from .engine import transform_{token}\n"
            f"def handle_{token}(value: str) -> str:\n    return transform_{token}(value)\n",
        )
        _write(
            tmp_path / f"tests/{namespace}/test_behavior.py",
            f"from src.{namespace}.api import handle_{token}\n"
            f"def test_{token}():\n    assert handle_{token}('x') == 'x-{index}'\n",
        )

    task = "Fix behavior for flare001 and flare002 across all active product paths and verify each contract."
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20, per_role=3)
        packet = codemap.task_decision_packet(task)

    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "multiple-task-local-structural-owners"
    assert packet["discrimination"]["needed"] is True
    assert packet["discrimination"]["reason"] == "competing-action-roles"
