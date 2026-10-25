"""Source consumers must not combine checked symbols with later unbound bytes."""

from pathlib import Path

import pytest
from contract_assertions import assert_records, assert_text

from hashmarks.codemap import CodeMap
from hashmarks.codemap.providers import TreeSitterRangeProvider


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


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_source_body_uses_physical_lines_and_preserves_unicode_contents(
    tmp_path: Path, newline: str
) -> None:
    source = newline.join(
        (
            "marker = 'before\u2028after'",
            "def owner():",
            "    return 'body\u0085tail'",
        )
    )
    (tmp_path / "owner.py").write_bytes(source.encode("utf-8"))
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.index.sync()
        body = codemap.source.read("owner.py::owner")
    assert body["lines"] == [2, 3]
    assert body["content"] == "def owner():\n    return 'body\u0085tail'"
    assert (tmp_path / "owner.py").read_bytes() == source.encode("utf-8")


@pytest.mark.parametrize(
    "case",
    [
        (
            "owner.py",
            "",
            "label = 'before__SEP__after'",
            "def needle_owner(): return label",
            2,
        ),
        (
            "broken.py",
            "",
            "label = 'before__SEP__after'",
            "needle_owner = (",
            2,
        ),
        (
            "owner.js",
            "",
            "const label = 'before__SEP__after';",
            "export function needle_owner() { return label; }",
            2,
        ),
        (
            "owner.ts",
            "",
            "const label = 'before__SEP__after';",
            "export function needle_owner() { return label; }",
            2,
        ),
        (
            "owner.go",
            "package sample\n",
            'var label = "before__SEP__after"',
            "func needle_owner() string { return label }",
            3,
        ),
        (
            "owner.rs",
            "",
            'const LABEL: &str = "before__SEP__after";',
            "fn needle_owner() -> &'static str { LABEL }",
            2,
        ),
        ("notes.md", "", "'before__SEP__after'", "needle_owner reference", 2),
    ],
)
@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_grep_uses_canonical_physical_lines_across_lexical_artifact_families(
    tmp_path: Path,
    case: tuple[str, str, str, str, int],
    separator: str,
    newline: str,
) -> None:
    filename, prefix, header, declaration, line = case
    header = header.replace("__SEP__", separator)
    raw = (prefix + header + "\n" + declaration).replace("\n", newline).encode("utf-8")
    (tmp_path / filename).write_bytes(raw)
    state = tmp_path / ".state"
    provider = TreeSitterRangeProvider()
    with CodeMap(
        tmp_path,
        state_dir=state,
        artifact_db=state / "artifacts.sqlite3",
        range_provider=provider,
    ) as codemap:
        codemap.index.sync()
        if filename == "broken.py":
            assert codemap.source.outline(filename)["parse_error"] is not None
        canonical = codemap.source.observe(filename, literal="needle_owner")
        first = codemap.source.grep("needle_owner", context_lines=1)
    with CodeMap(
        tmp_path,
        state_dir=state,
        artifact_db=state / "artifacts.sqlite3",
        range_provider=provider,
    ) as reopened:
        warm = reopened.index.sync()
        second = reopened.source.grep("needle_owner", context_lines=1)
    assert warm.parsed_artifacts == 0
    assert warm.reused_artifacts == 1
    assert provider.status().available is False
    assert canonical["freshness"] == "unknown"
    assert [row["line"] for row in assert_records(canonical["occurrences"])] == [line]
    for packet in (first, second):
        matches = assert_records(packet["matches"])
        assert len(matches) == 1
        assert matches[0]["line"] == line
        assert matches[0]["range"] == [line - 1, line]
        assert matches[0]["content"] == header + "\n" + declaration
    assert (tmp_path / filename).read_bytes() == raw
