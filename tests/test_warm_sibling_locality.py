from pathlib import Path

from hashmarks.codemap import CodeMap


def _build_repetitive_repo(root: Path, count: int = 25) -> list[dict[str, str]]:
    (root / "src").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "tests").mkdir()
    (root / "checks").mkdir()
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\npythonpath=['.']\n"
    )
    tasks: list[dict[str, str]] = []
    for index in range(1, count + 1):
        token = f"ember_case_{index:03d}_unique"
        ns = f"unit_{index:03d}"
        pkg = root / "src" / ns
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        active = "logic_a" if index % 2 else "logic_b"
        inactive = "logic_b" if index % 2 else "logic_a"
        fn = f"apply_case_{index:03d}"
        (pkg / f"{active}.py").write_text(
            f"def {fn}(value: str) -> str:\n    return value + '-old'\n"
        )
        (pkg / f"{inactive}.py").write_text(
            f"def {fn}(value: str) -> str:\n    return value + '-decoy'\n\n# {token} migration decoy\n"
        )
        (pkg / "route.py").write_text(
            f"from .{active} import {fn}\n\ndef handle_{token}(value: str) -> str:\n    return {fn}(value)\n"
        )
        expected_edit = f"src/{ns}/{active}.py"
        expected_verify = f"tests/{ns}/test_behavior.py"
        query = (
            f"Fix request {token}: its active accepted response must become x-new instead of x-old. "
            "Preserve the active route and verify the accepted contract."
        )
        if index % 5 == 4:
            (pkg / "policy.toml").write_text("mode = 'old'\n")
            (pkg / f"{active}.py").write_text(
                "from pathlib import Path\n\n"
                f"def {fn}(value: str) -> str:\n"
                "    text=Path(__file__).with_name('policy.toml').read_text()\n"
                "    return value + ('-new' if \"mode = 'new'\" in text else '-old')\n"
            )
            expected_edit = f"src/{ns}/policy.toml"
            query = (
                f"Fix request {token}: its active accepted response policy must produce x-new. "
                "Preserve route ownership and verify the accepted contract."
            )
        if index % 5 == 0:
            expected_verify = f"checks/{ns}/test_contract.py"
            verify_path = root / expected_verify
            verify_path.parent.mkdir(parents=True, exist_ok=True)
            verify_path.write_text(
                f"from src.{ns}.route import handle_{token}\n\n"
                f"def test_{token}_accepted_contract():\n    assert handle_{token}('x') == 'x-new'\n"
            )
            query = (
                f"Fix request {token}: its accepted response must become x-new and identify the contract "
                "check outside the default test tree."
            )
        else:
            verify_path = root / expected_verify
            verify_path.parent.mkdir(parents=True, exist_ok=True)
            verify_path.write_text(
                f"from src.{ns}.route import handle_{token}\n\n"
                f"def test_{token}_accepted():\n    assert handle_{token}('x') == 'x-new'\n"
            )
        tasks.append(
            {
                "query": query,
                "edit": expected_edit,
                "verify": expected_verify,
                "token": token,
            }
        )
    return tasks


def test_repetitive_warm_repository_keeps_edit_and_verify_in_task_namespace(
    tmp_path: Path,
) -> None:
    tasks = _build_repetitive_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        for task in tasks:
            action = codemap.task_action_map(task["query"], limit=20, per_role=3)
            assert action["edit"]["path"] == task["edit"], task["token"]
            assert action["verify"]["path"] == task["verify"], task["token"]
            brief = codemap.task_action_brief(task["query"])
            assert brief["status"] == "safe-fresh", task["token"]
            assert brief["edit"] == task["edit"], task["token"]
            assert task["verify"] in brief["verify"][-1], task["token"]
            if "contract" in brief:
                namespace = Path(task["edit"]).parent.name
                assert namespace in brief["contract"], task["token"]


def test_rare_identifier_component_is_preserved_before_generic_siblings(
    tmp_path: Path,
) -> None:
    tasks = _build_repetitive_repo(tmp_path, count=12)
    target = tasks[-1]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        hits = codemap.find_task(target["query"], limit=20)
    paths = [hit.path for hit in hits]
    assert target["verify"] in paths
    assert "src/unit_012/route.py" in paths
    assert paths.index(target["verify"]) < 6
