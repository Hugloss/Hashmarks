import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

from hashmarks.codemap import CodeMap


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _dependency_path(root: Path) -> Path:
    return (
        root / ".venv" / "lib" / "python3.13" / "site-packages" / "demo_dep" / "core.py"
    )


def _simulate_historical_dependency_row(
    codemap: CodeMap, rel: str, monkeypatch
) -> None:
    original = codemap._path_admitted_for_analysis
    monkeypatch.setattr(codemap, "_path_admitted_for_analysis", lambda _rel: True)
    assert codemap.outline(rel)["path"] == rel
    monkeypatch.setattr(codemap, "_path_admitted_for_analysis", original)
    codemap.store.set_meta(
        "analysis_scope_conformance_identity", "historical-pre-hm303"
    )


def test_global_queries_retire_historical_pruned_rows_before_returning_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = tmp_path / "src" / "app.py"
    dependency = _dependency_path(tmp_path)
    _write(owned, "def owned():\n    return 1\n")
    _write(dependency, "def dependency_impl():\n    return 2\n")
    rel = dependency.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        _simulate_historical_dependency_row(codemap, rel, monkeypatch)
        assert rel in codemap.store.paths()

        assert codemap.find("dependency_impl") == ()
        assert rel not in codemap.store.paths()
        with pytest.raises(KeyError, match="symbol not found"):
            codemap.symbol("dependency_impl")
        assert codemap.derived_graph(rel)["nodes"] == []
        assert {hit.path for hit in codemap.find("owned")} == {"src/app.py"}


def test_stable_scope_identity_avoids_repeated_repository_map_scan(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "src" / "app.py", "def owned():\n    return 1\n")
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        identity = codemap.store.meta("analysis_scope_conformance_identity")
        assert identity and identity.startswith("sha256:")
        with patch.object(
            codemap.store,
            "paths",
            side_effect=AssertionError("stable scope must not rescan persisted paths"),
        ):
            assert {hit.path for hit in codemap.find("owned")} == {"src/app.py"}
            assert codemap.symbol("owned")["matches"][0]["path"] == "src/app.py"


def test_context_policy_change_retires_historical_rows_on_reopen(
    tmp_path: Path,
) -> None:
    hidden = tmp_path / "private" / "hidden.py"
    owned = tmp_path / "src" / "node_modules_adapter.py"
    _write(hidden, "def hidden():\n    return 2\n")
    _write(owned, "def adapter():\n    return 3\n")
    state_dir = tmp_path / ".state"
    artifact_db = tmp_path / "artifacts.sqlite3"

    with CodeMap(tmp_path, state_dir=state_dir, artifact_db=artifact_db) as codemap:
        codemap.sync()
        assert "private/hidden.py" in codemap.store.paths()
        assert "src/node_modules_adapter.py" in codemap.store.paths()

    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "private/**"\nindex = false\n',
        encoding="utf-8",
    )

    with CodeMap(tmp_path, state_dir=state_dir, artifact_db=artifact_db) as codemap:
        assert codemap.find("hidden") == ()
        assert "private/hidden.py" not in codemap.store.paths()
        assert {hit.path for hit in codemap.find("adapter")} == {
            "src/node_modules_adapter.py"
        }


def test_live_context_policy_deny_converges_without_reopening_codemap(
    tmp_path: Path,
) -> None:
    hidden = tmp_path / "private" / "hidden.py"
    _write(hidden, "def hidden_owner():\n    return 2\n")

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        assert (
            codemap.symbol("hidden_owner")["matches"][0]["path"] == "private/hidden.py"
        )
        (tmp_path / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern = "private/**"\nindex = false\n',
            encoding="utf-8",
        )
        with pytest.raises(KeyError, match="symbol not found"):
            codemap.symbol("hidden_owner")
        assert "private/hidden.py" not in codemap.store.paths()


def test_live_context_policy_reallow_discovers_newly_admitted_paths(
    tmp_path: Path,
) -> None:
    hidden = tmp_path / "private" / "hidden.py"
    _write(hidden, "def hidden_owner():\n    return 2\n")
    policy = tmp_path / ".hashmarks-context.toml"
    policy.write_text(
        '[[rule]]\npattern = "private/**"\nindex = false\n',
        encoding="utf-8",
    )

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        with pytest.raises(KeyError, match="symbol not found"):
            codemap.symbol("hidden_owner")
        policy.unlink()
        assert (
            codemap.symbol("hidden_owner")["matches"][0]["path"] == "private/hidden.py"
        )


def test_live_custom_context_policy_path_is_authority_not_construction_snapshot(
    tmp_path: Path,
) -> None:
    hidden = tmp_path / "private" / "hidden.py"
    policy = tmp_path / "config" / "context.toml"
    _write(hidden, "def hidden_owner():\n    return 2\n")
    _write(policy, "")

    with CodeMap(
        tmp_path,
        policy_path=policy,
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.sync()
        assert codemap.symbol("hidden_owner")["matches"]
        policy.write_text(
            '[[rule]]\npattern = "private/**"\nindex = false\n',
            encoding="utf-8",
        )
        with pytest.raises(KeyError, match="symbol not found"):
            codemap.symbol("hidden_owner")


def test_invalid_live_context_policy_fails_closed_before_persisted_evidence(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "src" / "app.py", "def owned():\n    return 1\n")
    policy = tmp_path / ".hashmarks-context.toml"
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        assert codemap.symbol("owned")["matches"]
        policy.write_text("[[rule]\n", encoding="utf-8")
        with pytest.raises(tomllib.TOMLDecodeError):
            codemap.symbol("owned")
