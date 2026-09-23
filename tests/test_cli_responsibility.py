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
