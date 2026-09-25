from __future__ import annotations

import ast
from pathlib import Path

import pytest

from hashmarks import cli, repository_cli, repository_retry
from hashmarks.errors import RepositoryCliError

ROOT = Path(__file__).resolve().parents[1]


def _try_functions(path: Path) -> dict[str, list[int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: dict[str, list[int]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        lines = [child.lineno for child in ast.walk(node) if isinstance(child, ast.Try)]
        if lines:
            result[node.name] = lines
    return result


def test_repository_cli_error_translation_is_centralized() -> None:
    path = ROOT / "hashmarks" / "repository_cli.py"
    try_functions = _try_functions(path)
    assert set(try_functions) == {"_call_codemap", "_read_json_object"}


def test_top_level_cli_leaf_commands_do_not_translate_exceptions() -> None:
    path = ROOT / "hashmarks" / "cli.py"
    try_functions = _try_functions(path)
    assert set(try_functions) == {"_daemon_start", "main"}


def test_repository_cli_boundary_translates_only_expected_request_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCodeMap:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(repository_cli, "_codemap", lambda args: FakeCodeMap())

    with pytest.raises(RepositoryCliError, match="bad query"):
        repository_cli._call_codemap(
            object(), lambda codemap: (_ for _ in ()).throw(ValueError("bad query"))
        )

    with pytest.raises(RuntimeError, match="implementation bug"):
        repository_cli._call_codemap(
            object(),
            lambda codemap: (_ for _ in ()).throw(RuntimeError("implementation bug")),
        )


def test_repository_cli_boundary_retries_known_transient_races_once_centrally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCodeMap:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(repository_cli, "_codemap", lambda args: FakeCodeMap())
    monkeypatch.setattr(repository_retry, "_TRANSIENT_RETRY_DELAYS", (0.0, 0.0, 0.0))
    calls = 0

    def operation(codemap):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError(
                "CodeMap generation is incomplete (BUILDING); run sync() before querying repository intelligence"
            )
        return "ready"

    assert repository_cli._call_codemap(object(), operation) == "ready"
    assert calls == 3


def test_repository_cli_boundary_translates_exhausted_transient_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCodeMap:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(repository_cli, "_codemap", lambda args: FakeCodeMap())
    monkeypatch.setattr(repository_retry, "_TRANSIENT_RETRY_DELAYS", (0.0, 0.0))

    with pytest.raises(RepositoryCliError, match="generation is incomplete"):
        repository_cli._call_codemap(
            object(),
            lambda codemap: (_ for _ in ()).throw(
                RuntimeError(
                    "CodeMap generation is incomplete (BUILDING); run sync() before querying repository intelligence"
                )
            ),
        )


def test_mcp_and_cli_share_one_repository_retry_owner() -> None:
    source = (ROOT / "hashmarks" / "mcp_surface.py").read_text(encoding="utf-8")
    cli_source = (ROOT / "hashmarks" / "repository_cli.py").read_text(encoding="utf-8")
    assert "from .repository_retry import retry_transient_repository_race" in source
    assert "retry_transient_repository_race" in cli_source
    assert "def _retry_transient_repository_race" not in source
    assert "def _retry_transient_repository_race" not in cli_source


def test_top_level_cli_translates_user_facing_error_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(args) -> int:
        raise RepositoryCliError("caller-visible failure")

    original = cli._add_daemon_cli

    def add_one(sub) -> None:
        parser = sub.add_parser("boundary-test")
        parser.set_defaults(func=fail)

    monkeypatch.setattr(cli, "_add_daemon_cli", add_one)
    monkeypatch.setattr(cli, "_add_identity_cli", lambda sub: None)
    monkeypatch.setattr(
        "hashmarks.repository_cli.add_repository_cli",
        lambda sub, add_common_arguments: None,
    )
    try:
        with pytest.raises(SystemExit, match="caller-visible failure"):
            cli.main(["boundary-test"])
    finally:
        monkeypatch.setattr(cli, "_add_daemon_cli", original)


def test_no_catch_and_immediate_reraise_noise_in_product_python() -> None:
    violations: list[str] = []
    for path in sorted((ROOT / "hashmarks").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if (
                len(node.body) == 1
                and isinstance(node.body[0], ast.Raise)
                and node.body[0].exc is None
            ):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert violations == []


def _broad_handler_names(handler: ast.ExceptHandler) -> set[str]:
    if isinstance(handler.type, ast.Name):
        return {handler.type.id}
    if isinstance(handler.type, ast.Tuple):
        return {item.id for item in handler.type.elts if isinstance(item, ast.Name)}
    return set()


def _enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    owner = node
    while owner in parents:
        owner = parents[owner]
        if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return owner.name
    return "<module>"


def test_broad_exception_handlers_are_restricted_to_explicit_failure_boundaries() -> (
    None
):
    allowed = {
        ("hashmarks/codemap/providers.py", "auto"),
        ("hashmarks/codemap/providers.py", "_name_node"),
        ("hashmarks/codemap/providers.py", "enrich"),
        (
            "hashmarks/codemap/repository_declaration_provider.py",
            "collect_repository_declaration_providers",
        ),
        ("hashmarks/codemap/repository_index_store.py", "bulk_file_writes"),
        ("hashmarks/codemap/repository_index_store.py", "set_file"),
        ("hashmarks/ipc_boundary.py", "dispatch_json_request"),
        ("hashmarks/sqlite_boundary.py", "sqlite_transaction"),
        ("hashmarks/codemap/singleflight.py", "run"),
        ("hashmarks/merkle.py", "_run_reconciled"),
        ("hashmarks/watcher.py", "_flush_now"),
        ("hashmarks/watcher.py", "_read_loop"),
        ("hashmarks/watcher.py", "start"),
    }
    found: set[tuple[str, str]] = set()

    for path in sorted((ROOT / "hashmarks").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            names = _broad_handler_names(node)
            if not ({"Exception", "BaseException"} & names):
                continue
            found.add(
                (path.relative_to(ROOT).as_posix(), _enclosing_function(node, parents))
            )

    assert found == allowed


def test_local_ipc_request_error_serialization_has_one_owner() -> None:
    from hashmarks.ipc_boundary import dispatch_json_request

    assert dispatch_json_request(b"[]", lambda request: {"ok": True}) == {
        "ok": False,
        "error": "ValueError: request must be an object",
    }

    def broken(request: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("boom")

    assert dispatch_json_request(b"{}", broken) == {
        "ok": False,
        "error": "RuntimeError: boom",
    }
    assert dispatch_json_request(
        b'{"value":1}', lambda request: {"ok": True, **request}
    ) == {
        "ok": True,
        "value": 1,
    }
