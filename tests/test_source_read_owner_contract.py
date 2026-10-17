"""Source consumers must not combine checked symbols with later unbound bytes."""

from pathlib import Path

import pytest
from contract_assertions import assert_records, assert_text

from hashmarks.codemap import CodeMap


def _move_after_check(
    codemap: CodeMap, source: Path, transition: str, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    ensure = codemap.source.ensure_current
    checked: list[str] = []

    def move(path: str) -> None:
        ensure(path)
        if path != "owner.py":
            return
        row = codemap.store.symbol_at(path, "owner")
        if row is None:
            return
        signature = str(row["signature"])
        checked.append(signature)
        if transition == "modify":
            name = "needle_bravo" if "needle_alpha" in signature else "needle_alpha"
            source.write_text(f"def owner({name}):\n    return {name}\n")
        elif source.is_file() and not source.is_symlink():
            source.unlink()
            if transition == "symlink":
                source.symlink_to(source.parent.parent / "outside.py")

    monkeypatch.setattr(codemap.source, "ensure_current", move)
    return checked


def _read_surface(
    codemap: CodeMap, surface: str, checked: list[str]
) -> tuple[str, str] | None:
    if surface == "source":
        result = codemap.source.read("owner.py::owner")
        return assert_text(result["content"]), assert_text(result["signature"])
    if surface == "slice":
        return codemap.source.slice("owner.py", 1, 2, qualname="owner"), checked[-1]
    matches = assert_records(codemap.source.grep("owner", context_lines=1)["matches"])
    return (assert_text(matches[0]["content"]), checked[-1]) if matches else None


@pytest.mark.parametrize("surface", ["source", "slice", "grep"])
@pytest.mark.parametrize("transition", ["modify", "delete", "symlink"])
def test_source_read_requalifies_bytes_after_currentness_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    transition: str,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    source = workspace / "owner.py"
    original = "def owner(needle_alpha):\n    return needle_alpha\n"
    source.write_text(original)
    outside = tmp_path / "outside.py"
    outside.write_text("def owner(needle_external):\n    return needle_external\n")
    with CodeMap(
        workspace,
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        checked = _move_after_check(codemap, source, transition, monkeypatch)
        try:
            observation = _read_surface(codemap, surface, checked)
        except (OSError, KeyError, RuntimeError):
            # Explicit unavailable/drifting state is acceptable; mixed evidence is not.
            assert checked
            return
        assert checked
        if observation is None:
            return
        content, signature = observation
        assert transition == "modify", "deleted or foreign source must not be disclosed"
        assert "needle_external" not in content
        assert ("needle_alpha" in signature) == ("needle_alpha" in content)
