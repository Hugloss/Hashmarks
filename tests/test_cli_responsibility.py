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

    with pytest.raises(ValueError, match="unknown Hashmarks operation"):
        repository_cli._print_operation(
            "unregistered_operation",
            {"schema": "hashmarks.unregistered.v1"},
        )
    assert printed == [packet]


@pytest.mark.parametrize(
    ("command", "operation"),
    [
        (("orient",), "repository_context"),
        (("find", "Widget.run"), "find"),
        (("task-evidence", "Change Widget.run"), "task_evidence"),
        (
            ("change-impact", "Change Widget.run", "--changed", "widget.py"),
            "change_impact",
        ),
        (("post-change", "Change Widget.run", "--changed", "widget.py"), "post_change"),
    ],
)
def test_repository_cli_projects_all_canonical_cli_operations_through_one_guard(
    command: tuple[str, ...], operation: str, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse

    import hashmarks.repository_cli as repository_cli
    from hashmarks.operation_contract import operation_schema

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    repository_cli.add_repository_cli(
        sub, add_common_arguments=lambda *_args, **_kwargs: None
    )
    if operation == "post_change":
        previous = tmp_path / "previous.json"
        previous.write_text("{}", encoding="utf-8")
        command = (*command, "--previous-evidence", str(previous))
    parsed = parser.parse_args(command)

    packet = {"schema": operation_schema(operation)}
    printed: list[object] = []
    monkeypatch.setattr(repository_cli, "_call_codemap", lambda *_args: packet)
    monkeypatch.setattr(repository_cli, "_print", printed.append)
    assert parsed.func(parsed) == 0
    assert printed == [packet]

    printed.clear()
    packet["schema"] = "hashmarks.invalid-response.v1"
    with pytest.raises(RuntimeError, match="operation response schema drift"):
        parsed.func(parsed)
    assert printed == []


def test_repository_context_defaults_have_one_owner() -> None:
    import argparse
    import inspect

    from hashmarks.codemap.context_defaults import REPOSITORY_CONTEXT_DEFAULTS
    from hashmarks.codemap.repository_context import ContextPlanningMixin
    from hashmarks.repository_cli import add_repository_cli

    signature = inspect.signature(ContextPlanningMixin.context)
    assert (
        signature.parameters["token_budget"].default
        == REPOSITORY_CONTEXT_DEFAULTS.token_budget
    )
    assert signature.parameters["limit"].default == REPOSITORY_CONTEXT_DEFAULTS.limit
    assert (
        signature.parameters["disclosure"].default
        == REPOSITORY_CONTEXT_DEFAULTS.disclosure
    )

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_repository_cli(sub, add_common_arguments=lambda *_args, **_kwargs: None)
    parsed = parser.parse_args(["context", "Widget.run"])
    assert parsed.budget == REPOSITORY_CONTEXT_DEFAULTS.token_budget
    assert parsed.limit == REPOSITORY_CONTEXT_DEFAULTS.limit
    assert parsed.level == REPOSITORY_CONTEXT_DEFAULTS.disclosure.value

    source = inspect.getsource(__import__("hashmarks.repository_cli", fromlist=["_"]))
    context_registration = source.split("def _add_context_cli", 1)[1].split(
        "def _add_task_evidence_cli", 1
    )[0]
    assert "default=4000" not in context_registration
    assert "default=30" not in context_registration
    assert 'default="source"' not in context_registration
