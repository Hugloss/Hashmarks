"""Source consumers must not combine checked symbols with later unbound bytes."""

import json
from pathlib import Path

import pytest
from contract_assertions import assert_records, assert_text

from hashmarks.codemap import CodeMap
from hashmarks.codemap.providers import TreeSitterRangeProvider
from hashmarks.codemap.python_ast import estimate_tokens


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_advisory_python_symbol_body_uses_the_providers_lf_rows(
    tmp_path: Path, newline: bytes
) -> None:
    provider = TreeSitterRangeProvider.auto()
    if provider.signature("python") is None:
        pytest.skip("Optional Python range provider unavailable")
    path = tmp_path / "legacy.py"
    raw = newline.join(
        [
            b"# metadata\r# continued",
            b"print 'legacy'",
            b"def target():",
            b"    return 'right'",
            b"",
        ]
    )
    path.write_bytes(raw)
    with CodeMap(tmp_path, range_provider=provider) as cm:
        outline = cm.source.outline("legacy.py")
        assert outline["parse_error"]
        source = cm.source.read("legacy.py::target")
        assert source["lines"] == [3, 4]
        assert source["content"] == "def target():\n    return 'right'"
        assert cm.source.slice("legacy.py", 3, 4) == source["content"]
        observed = cm.source.observe("legacy.py", literal="right")
        (hit,) = assert_records(observed["occurrences"])
        assert hit["line"] == 4 and hit["enclosing_symbol"] is None
        assert cm.source.bindings("legacy.py")["availability"] == "unavailable"


def test_context_uses_a_fresh_native_definition_at_its_reported_line(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    content = "    'WidgetSetting': 'a metadata value at the selected location',"
    (root / "schema.py").write_text("FIELDS = {\n" + content + "\n}\n")
    index = tmp_path / "scip.json"
    index.write_text(
        json.dumps(
            {
                "metadata": {"toolInfo": {"name": "fixture", "version": "1"}},
                "documents": [
                    {
                        "relativePath": "schema.py",
                        "occurrences": [
                            {
                                "range": [1, 5, 18],
                                "symbol": "scip-python python app 1 `schema`/WidgetSetting#",
                                "symbolRoles": 1,
                            }
                        ],
                    }
                ],
            }
        )
    )
    with CodeMap(root, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        codemap.native.import_scip(index)
        context = codemap.context.build("WidgetSetting", disclosure="source")
    assert [
        (x.symbol, x.content)
        for x in context.items
        if x.representation == "source-range"
    ] == [("WidgetSetting", content)]


def test_retained_python_qualname_cannot_read_a_replacement_method(
    tmp_path: Path,
) -> None:
    member = tmp_path / "owner.py"
    member.write_text("class Old:\n    def load(self): return 1\n")
    with CodeMap(tmp_path) as codemap:
        (retained,) = assert_records(codemap.source.symbol("Old.load")["matches"])
        member.write_text("class New:\n    def load(self): return 2\n")
        with pytest.raises(KeyError, match=r"owner\.py::Old\.load"):
            codemap.source.slice("owner.py", 2, 2, qualname="Old.load")
        assert codemap.source.slice("owner.py", 2, 2) == "    def load(self): return 2"
        assert (
            codemap.source.slice("owner.py", 1, 1, qualname="New.load")
            == "    def load(self): return 2"
        )
        item, pending = codemap.tasks._task_evidence_evidence_item(
            retained, role="owner", token_budget=1000
        )
        assert item is None and pending == {
            "role": "owner",
            "path": "owner.py",
            "symbol": "Old.load",
            "reason": "exact-source-range-unavailable",
        }


def test_direct_symbol_slice_rejects_a_publication_between_lookup_and_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    member = root / "worker.py"
    member.write_text("def target(): return 1\n")
    state = tmp_path / "state"
    with (
        CodeMap(root, state_dir=state) as reader,
        CodeMap(root, state_dir=state) as writer,
    ):
        reader.index.sync()
        lookup = reader.store.symbol_at

        def publish_after_lookup(path: str, qualname: str) -> dict[str, object] | None:
            old = lookup(path, qualname)
            member.write_text("def unrelated(): return 2\ndef target(): return 3\n")
            writer.index.sync()
            return old

        with monkeypatch.context() as patch:
            patch.setattr(reader.store, "symbol_at", publish_after_lookup)
            with pytest.raises(RuntimeError, match="generation changed"):
                reader.source.slice("worker.py", 1, 1, qualname="target")
        assert (
            reader.source.slice("worker.py", 1, 1, qualname="target")
            == "def target(): return 3"
        )


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


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_python_outline_uses_ast_lines_for_binding_signatures_and_cost(
    tmp_path: Path, newline: str
) -> None:
    marker = "marker = 'before\u2028middle\fafter'"
    binding = "retry_interval = 9"
    (tmp_path / "settings.py").write_bytes(newline.join((marker, binding)).encode())
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.index.sync()
        symbols = assert_records(codemap.source.outline("settings.py")["symbols"])
        body = codemap.source.read("settings.py::retry_interval")
        packet = codemap.tasks.evidence("Inspect retry_interval in settings.py")
    assert [row["signature"] for row in symbols] == [marker, binding]
    assert [row["body_tokens"] for row in symbols] == list(
        map(estimate_tokens, (marker, binding))
    )
    assert body["signature"] == body["content"] == binding
    source = packet["ownership"]["source_evidence"]
    assert source is not None and f"{binding}  [2-2]" in source["content"]


def test_bare_cr_task_source_range_uses_python_symbol_coordinates(
    tmp_path: Path,
) -> None:
    declaration = "def normalize_timeout(value):\n    return value"
    (tmp_path / "retry.py").write_bytes(
        ("marker = 1\n" + declaration + "\n").replace("\n", "\r").encode()
    )
    (tmp_path / "test_retry.py").write_text(
        "from retry import normalize_timeout\n"
        "def test_normalize_timeout():\n    assert normalize_timeout(1) == 1\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        source = codemap.tasks.evidence("Fix normalize_timeout")["ownership"][
            "source_evidence"
        ]
        raw = codemap.source.observe("retry.py", lines=[1, 2])
    assert source is not None
    assert (source["representation"], source.get("lines"), source["content"]) == (
        "source-range",
        [2, 3],
        declaration,
    )
    assert [anchor["state"] for anchor in assert_records(raw["line_anchors"])] == [
        "observed",
        "unknown",
    ]


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
