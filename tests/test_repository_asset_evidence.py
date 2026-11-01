"""Assets retain positive consumers and never acquire repository-wide absence."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.digest import Digest

_PNG = b"\x89PNG\r\n\x1a\n"


@contextmanager
def _repository(tmp_path: Path, files: Mapping[str, str | bytes]) -> Iterator[CodeMap]:
    root = tmp_path / "repository"
    root.mkdir()
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content, str) else content)
    with CodeMap(
        root, state_dir=tmp_path / "state", artifact_db=tmp_path / "artifacts.sqlite3"
    ) as repository:
        repository.index.sync()
        yield repository


def _change(repository: CodeMap, path: str) -> dict[str, object]:
    packet = repository.verification.changed_set([path])
    return assert_records(packet["changes"])[0]


def test_documentation_asset_keeps_runtime_and_test_consumers(tmp_path: Path) -> None:
    files = {
        "docs/assets/screen.png": _PNG,
        "README.md": "![Screenshot](docs/assets/screen.png)\n",
        "runtime.py": 'from pathlib import Path\nROOT = Path(__file__).resolve().parents[0]\ndef load(): return (ROOT / "docs/assets/screen.png").read_bytes()\n',
        "tests/test_screen.py": 'from pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\ndef test_screen(): assert (ROOT / "docs/assets/screen.png").read_bytes()\n',
    }
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["docs/assets/screen.png"])
    change = assert_records(packet["changes"])[0]
    asset = assert_object(change["asset"])
    consumers = {row["path"]: row for row in assert_records(asset["consumers"])}
    assert set(consumers) == {"README.md", "runtime.py", "tests/test_screen.py"}
    assert consumers["README.md"]["relation_kind"] == "markdown-inline-image"
    assert consumers["runtime.py"]["relation_kind"] == "python-literal-file-read"
    assert consumers["runtime.py"]["reader_symbol"] == "load"
    assert consumers["tests/test_screen.py"]["qualification"] == "syntax-qualified"
    assert [row["path"] for row in assert_records(packet["targets"])] == [
        "tests/test_screen.py"
    ]
    assert asset["path_domains"] == ["doc"]
    assert (
        assert_object(asset["consumer_scope"])["negative_evidence_admissible"] is False
    )
    assert assert_object(asset["consumer_scope"])["completeness"] == "unknown"
    assert assert_object(change["source"])["content"] == asset["content"]


def test_dynamic_and_frontend_literals_remain_unqualified_consumers(
    tmp_path: Path,
) -> None:
    files = {
        "frontend/assets/icon.gif": b"GIF89a",
        "frontend/src/app.ts": 'import icon from "../assets/icon.gif";\n',
        "runtime.py": 'from pathlib import Path\nname = "icon.gif"\nblob = Path(name).read_bytes()\n',
    }
    with _repository(tmp_path, files) as repository:
        asset = assert_object(_change(repository, "frontend/assets/icon.gif")["asset"])
    consumers = assert_records(asset["consumers"])
    assert {row["path"] for row in consumers} == {"frontend/src/app.ts", "runtime.py"}
    assert all(row["qualification"] == "literal-only" for row in consumers)
    assert asset["path_domains"] == []
    assert (
        assert_object(asset["consumer_scope"])["negative_evidence_admissible"] is False
    )


@pytest.mark.parametrize(
    "document",
    [
        "```md\n![screen](screen.png)\n```\n",
        "````md\n```\n![screen](screen.png)\n````\n",
        "~~~md\n~~~ still code\n![screen](screen.png)\n~~~\n",
        "<!-- ![screen](screen.png) -->\n",
        "`![screen](screen.png)`\n",
        "![screen](https://example.invalid/screen.png)\n",
        "![screen](../other/screen.png)\n",
        "    ![screen](screen.png)\n",
        '<script>const example = "![screen](screen.png)";</script>\n',
        "<pre>![screen](screen.png)</pre>\n",
        '<SCRIPT type="text/javascript">\n\n![screen](screen.png)\n</SCRIPT>\n',
        "<style>\n![screen](screen.png)\n</style>\n",
        "<textarea>\n![screen](screen.png)\n</textarea>\n",
        "<div>\n![screen](screen.png)\n</div>\n",
        "`example\n![screen](screen.png)\nexample`\n",
        "``example\n`\n![screen](screen.png)\nexample``\n",
    ],
)
def test_document_examples_and_unresolved_destinations_do_not_prove_consumption(
    tmp_path: Path, document: str
) -> None:
    with _repository(
        tmp_path, {"docs/screen.png": _PNG, "docs/page.md": document}
    ) as repository:
        asset = assert_object(_change(repository, "docs/screen.png")["asset"])
    assert all(
        row["qualification"] == "literal-only"
        for row in assert_records(asset["consumers"])
    )


def test_relative_and_encoded_document_destinations_bind_the_target(
    tmp_path: Path,
) -> None:
    files = {
        "docs/assets/screen shot.png": _PNG,
        "docs/guide/page.md": '![screen](../assets/screen%20shot.png "Caption")\n',
    }
    with _repository(tmp_path, files) as repository:
        asset = assert_object(
            _change(repository, "docs/assets/screen shot.png")["asset"]
        )
    rows = assert_records(asset["consumers"])
    assert len(rows) == 1
    assert rows[0]["path"] == "docs/guide/page.md"
    assert rows[0]["qualification"] == "syntax-qualified"


def test_absent_asset_has_no_content_claim_but_retains_current_document_reference(
    tmp_path: Path,
) -> None:
    with _repository(tmp_path, {"README.md": "![gone](gone.png)\n"}) as repository:
        change = _change(repository, "gone.png")
    asset = assert_object(change["asset"])
    assert assert_object(asset["content"])["state"] == "unavailable"
    assert assert_object(asset["content"])["media_type"] is None
    assert (
        assert_object(assert_object(change["source"])["member"])["state"]
        == "known-absent"
    )
    assert assert_records(asset["consumers"])[0]["qualification"] == "syntax-qualified"


def test_known_candidate_source_gap_is_incomplete(tmp_path: Path) -> None:
    files = {
        "docs/screen.png": _PNG,
        "README.md": "![screen](docs/screen.png)\n",
        "runtime.py": 'asset = "docs/screen.png"\n',
        ".hashmarks-context.toml": '[[rule]]\npattern = "runtime.py"\nvisibility = "outline"\n',
    }
    with _repository(tmp_path, files) as repository:
        change = _change(repository, "docs/screen.png")
    scope = assert_object(assert_object(change["asset"])["consumer_scope"])
    assert scope["source_coverage"] == "incomplete"
    assert scope["completeness"] == "incomplete"
    assert scope["negative_evidence_admissible"] is False
    assert assert_object(change["consumer_scope"])["completeness"] == "incomplete"


def test_candidate_bound_never_becomes_no_consumer_evidence(tmp_path: Path) -> None:
    files: dict[str, str | bytes] = {"docs/screen.png": _PNG}
    files.update(
        {
            f"docs/page_{number:03d}.md": "![screen](screen.png)\n"
            for number in range(70)
        }
    )
    with _repository(tmp_path, files) as repository:
        packet = repository.verification.changed_set(["docs/screen.png"])
    change = assert_records(packet["changes"])[0]
    asset = assert_object(change["asset"])
    assert len(assert_records(asset["consumers"])) == 64
    scope = assert_object(asset["consumer_scope"])
    assert scope["truncated"] is True
    assert scope["completeness"] == "incomplete"
    assert scope["negative_evidence_admissible"] is False
    assert packet["truncated"] is True


def test_incidental_basename_tokens_do_not_exhaust_full_literal_candidates(
    tmp_path: Path,
) -> None:
    files: dict[str, str | bytes] = {
        "docs/game-tape-screen.png": _PNG,
        "README.md": "![screen](docs/game-tape-screen.png)\n",
    }
    files.update(
        {
            f"docs/other_{number:03d}.md": "A game tape discussion.\n"
            for number in range(70)
        }
    )
    with _repository(tmp_path, files) as repository:
        asset = assert_object(_change(repository, "docs/game-tape-screen.png")["asset"])
    assert [row["path"] for row in assert_records(asset["consumers"])] == ["README.md"]
    assert assert_object(asset["consumer_scope"])["truncated"] is False


def test_large_unindexed_asset_never_falls_through_to_unbounded_member_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {
        "docs/large.png": _PNG + b"x" * 1_048_576,
        "README.md": "![large](docs/large.png)\n",
    }
    with _repository(tmp_path, files) as repository:
        native_read = repository.source.file_store.read_bytes_stable
        native_digest = repository.source.file_store.digest

        def read(path: Path) -> tuple[bytes, Digest]:
            assert path.name != "large.png", "oversized image bytes were read"
            return native_read(path)

        def digest(
            path: Path,
            *,
            workspace: str | Path,
            relative_path: str,
            force: bool = False,
        ) -> Digest:
            assert path.name != "large.png", "oversized image bytes were hashed"
            return native_digest(
                path, workspace=workspace, relative_path=relative_path, force=force
            )

        monkeypatch.setattr(repository.source.file_store, "read_bytes_stable", read)
        monkeypatch.setattr(repository.source.file_store, "digest", digest)
        change = _change(repository, "docs/large.png")
    assert assert_object(change["classification"])["kind"] == "unknown"
    assert (
        assert_object(assert_object(change["asset"])["content"])["state"]
        == "unavailable"
    )
    assert (
        assert_object(change["consumer_scope"])["negative_evidence_admissible"] is False
    )


def test_asset_reader_change_during_projection_is_reconciled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {"docs/screen.png": _PNG, "README.md": "![screen](docs/screen.png)\n"}
    with _repository(tmp_path, files) as repository:
        native = repository.verification._asset_consumer
        changed = False

        def observe(
            reader: str, target: str, max_bytes: int
        ) -> tuple[list[dict[str, object]], dict[str, object], int, str]:
            nonlocal changed
            result = native(reader, target, max_bytes)
            if reader == "README.md" and not changed:
                changed = True
                (repository.source.workspace / reader).write_text(
                    "No image declaration.\n"
                )
            return result

        monkeypatch.setattr(repository.verification, "_asset_consumer", observe)
        asset = assert_object(_change(repository, "docs/screen.png")["asset"])
    assert changed
    assert asset["consumers"] == []
    assert (
        assert_object(asset["consumer_scope"])["negative_evidence_admissible"] is False
    )


def test_literal_examples_remain_visible_beside_a_qualified_image(
    tmp_path: Path,
) -> None:
    files = {
        "docs/screen.png": _PNG,
        "README.md": "![screen](docs/screen.png)\n\n```python\nload('docs/screen.png')\n```\n",
    }
    with _repository(tmp_path, files) as repository:
        asset = assert_object(_change(repository, "docs/screen.png")["asset"])
    assert {row["qualification"] for row in assert_records(asset["consumers"])} == {
        "syntax-qualified",
        "literal-only",
    }


def test_many_references_in_one_reader_preserve_result_bound(tmp_path: Path) -> None:
    files = {"docs/screen.png": _PNG, "README.md": "![screen](docs/screen.png)\n" * 70}
    with _repository(tmp_path, files) as repository:
        asset = assert_object(_change(repository, "docs/screen.png")["asset"])
    assert len(assert_records(asset["consumers"])) == 64
    scope = assert_object(asset["consumer_scope"])
    assert scope["truncated"] is True
    assert "asset-reference-result-bound" in assert_array(scope["reasons"])


def test_oversized_reader_is_not_reconciled_before_its_source_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {"docs/screen.png": _PNG, "guide.md": "![screen](docs/screen.png)\n"}
    with _repository(tmp_path, files) as repository:
        (repository.source.workspace / "guide.md").write_text(
            "![screen](docs/screen.png)\n" + "x" * 1_048_576
        )
        native = repository.source.file_store.read_bytes_stable

        def read(path: Path) -> tuple[bytes, Digest]:
            assert path.name != "guide.md", "oversized reader was read before its bound"
            return native(path)

        monkeypatch.setattr(repository.source.file_store, "read_bytes_stable", read)
        asset = assert_object(_change(repository, "docs/screen.png")["asset"])
    assert asset["consumers"] == []
    assert assert_object(asset["consumer_scope"])["source_coverage"] == "incomplete"
    assert assert_object(asset["consumer_scope"])["completeness"] == "incomplete"


def test_reopened_observer_preserves_asset_projection_identity(tmp_path: Path) -> None:
    files = {"docs/screen.png": _PNG, "README.md": "![screen](docs/screen.png)\n"}
    with _repository(tmp_path, files) as repository:
        first = assert_object(_change(repository, "docs/screen.png")["asset"])
    with CodeMap(
        tmp_path / "repository",
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as repository:
        repository.index.sync()
        second = assert_object(_change(repository, "docs/screen.png")["asset"])
    assert first == second


@pytest.mark.parametrize(
    "document",
    [
        '![screen](docs/screen.png) <img src="docs/screen.png">\n',
        "![screen](docs/screen.png) and a literal docs/screen.png\n",
        "![screen](docs/screen.png) <!-- docs/screen.png -->\n",
    ],
)
def test_qualified_use_never_hides_an_unsupported_same_line_use(
    tmp_path: Path, document: str
) -> None:
    with _repository(
        tmp_path, {"docs/screen.png": _PNG, "README.md": document}
    ) as repository:
        asset = assert_object(_change(repository, "docs/screen.png")["asset"])
    assert any(
        row["qualification"] == "literal-only"
        for row in assert_records(asset["consumers"])
    )


def test_qualified_utf8_destinations_do_not_create_duplicate_literal_uses(
    tmp_path: Path,
) -> None:
    files = {
        "docs/screen.png": _PNG,
        "README.md": "A café: ![screen](docs/screen.png) [other](docs/screen.png)\n",
    }
    with _repository(tmp_path, files) as repository:
        asset = assert_object(_change(repository, "docs/screen.png")["asset"])
    rows = assert_records(asset["consumers"])
    assert len(rows) == 2
    assert all(row["qualification"] == "syntax-qualified" for row in rows)


def test_python_read_does_not_hide_a_same_line_dynamic_use(tmp_path: Path) -> None:
    files = {
        "docs/screen.png": _PNG,
        "runtime.py": 'from pathlib import Path\nROOT = Path(__file__).resolve().parents[0]\ndef load(): return (ROOT / "docs/screen.png").read_bytes(), other("docs/screen.png")\n',
    }
    with _repository(tmp_path, files) as repository:
        asset = assert_object(_change(repository, "docs/screen.png")["asset"])
    assert {row["qualification"] for row in assert_records(asset["consumers"])} == {
        "syntax-qualified",
        "literal-only",
    }


def test_native_sync_discovers_a_new_reader_in_a_reopened_observer(
    tmp_path: Path,
) -> None:
    files = {"docs/screen.png": _PNG, "README.md": "![screen](docs/screen.png)\n"}
    with _repository(tmp_path, files) as repository:
        first = assert_object(_change(repository, "docs/screen.png")["asset"])
    (tmp_path / "repository" / "runtime.py").write_text(
        'from pathlib import Path\nROOT = Path(__file__).resolve().parents[0]\ndef load(): return (ROOT / "docs/screen.png").read_bytes()\n'
    )
    with CodeMap(
        tmp_path / "repository",
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as repository:
        repository.index.sync()
        second = assert_object(_change(repository, "docs/screen.png")["asset"])
    assert [row["path"] for row in assert_records(first["consumers"])] == ["README.md"]
    assert {row["path"] for row in assert_records(second["consumers"])} == {
        "README.md",
        "runtime.py",
    }
    assert second["evidence_identity"] != first["evidence_identity"]
