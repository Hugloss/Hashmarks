import pytest


def test_repository_cli_registers_structural_locality_commands() -> None:
    import argparse

    from hashmarks.repository_cli import add_repository_cli

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_repository_cli(sub, add_common_arguments=lambda *_args, **_kwargs: None)

    for command, handler in (
        ("symbol", "_symbol_code"),
        ("deps", "_deps_code"),
        ("refs", "_refs_code"),
    ):
        parsed = parser.parse_args([command, "Widget.run"])
        assert parsed.query == "Widget.run"
        assert parsed.func.__name__ == handler
        assert parsed.func.__module__ == "hashmarks.repository_cli"

    locality = parser.parse_args(["structural-locality", "pkg/core.py::Worker.run"])
    assert locality.target == "pkg/core.py::Worker.run"
    assert locality.max_depth == 2
    assert locality.call_limit == 64
    assert locality.ref_limit == 256
    assert locality.func.__module__ == "hashmarks.repository_cli"

    delta = parser.parse_args(
        [
            "structural-locality-delta",
            "--before",
            "before.json",
            "--after",
            "after.json",
        ]
    )
    assert delta.before == "before.json"
    assert delta.after == "after.json"
    assert delta.func.__module__ == "hashmarks.repository_cli"


def test_top_level_cli_delegates_repository_command_family(
    tmp_path, monkeypatch
) -> None:
    import hashmarks.cli as cli
    import hashmarks.repository_cli as repository_cli

    seen: dict[str, object] = {}

    def fake_symbol(args) -> int:
        seen["query"] = args.query
        seen["workspace"] = args.workspace
        return 0

    monkeypatch.setattr(repository_cli, "_symbol_code", fake_symbol)

    assert cli.main(["--workspace", str(tmp_path), "symbol", "Widget.run"]) == 0
    assert seen == {"query": "Widget.run", "workspace": tmp_path.resolve()}


@pytest.mark.parametrize("command", ["root", "map"])
def test_removed_cli_shortcuts_are_not_callable(command: str) -> None:
    from hashmarks.cli import main

    with pytest.raises(SystemExit) as exc:
        main([command])
    assert exc.value.code == 2


def test_repository_cli_operation_projection_validates_before_print(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hashmarks.repository_cli as repository_cli

    printed: list[object] = []
    monkeypatch.setattr(repository_cli, "_print", printed.append)

    packet = {"schema": "hashmarks.find.v2", "results": []}
    repository_cli._print_operation("find", packet)
    assert printed == [packet]

    with pytest.raises(RuntimeError, match="operation response schema drift"):
        repository_cli._print_operation(
            "find",
            {"schema": "hashmarks.repository-capsule.v1"},
        )
    assert printed == [packet]


def test_repository_cli_projects_all_canonical_cli_operations_through_one_guard() -> None:
    from pathlib import Path

    import hashmarks.repository_cli as repository_cli

    source = Path(repository_cli.__file__).read_text(encoding="utf-8")
    expected = {
        '_print_operation("repository_context", value)',
        '_print_operation("find", value)',
        '_print_operation("task_evidence", value)',
        '_print_operation("change_impact", value)',
        '_print_operation("post_change", value)',
    }
    assert all(call in source for call in expected)

    for function_name in (
        "_map_orient",
        "_find_code",
        "_task_evidence_code",
        "_change_impact_code",
        "_post_change_code",
    ):
        start = source.index(f"def {function_name}(")
        next_def = source.find("\ndef ", start + 1)
        body = source[start:] if next_def < 0 else source[start:next_def]
        assert "_print_operation(" in body
        assert "_print(value)" not in body
