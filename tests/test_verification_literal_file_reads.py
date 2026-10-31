import os
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks.codemap import CodeMap


def _fixture(tmp_path: Path, reader: str) -> Path:
    document = tmp_path / "docs/guide.md"
    document.parent.mkdir()
    document.write_text("# Commands\n\n```sh\ntool inspect\n```\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    path = tests / "test_guide.py"
    path.write_text(
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "def test_commands():\n" + reader
    )
    return path


def _linked(graph: dict[str, object]) -> list[dict[str, object]]:
    return [
        row
        for row in assert_records(graph["verification_owners"])
        if row["path"] == "tests/test_guide.py"
        and row["covers_edit_candidates"] == ["docs/guide.md"]
        and row["coverage_evidence"] == "direct-reference"
    ]


@pytest.mark.parametrize(
    "expression", ["ROOT / 'docs/guide.md'", "Path(ROOT / 'docs/guide.md')"]
)
@pytest.mark.parametrize(
    ("method", "value"),
    [("read_text", "'tool inspect'"), ("read_bytes", "b'tool inspect'")],
)
def test_literal_repository_document_reader_is_a_structural_verifier(
    tmp_path: Path, expression: str, method: str, value: str
) -> None:
    _fixture(
        tmp_path,
        f"    document = ({expression}).{method}()\n    assert {value} in document\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        graph = codemap.tasks.verification_ownership_graph("Verify docs/guide.md")
    assert graph["edit_candidates"] == ["docs/guide.md"]
    (owner,) = _linked(graph)
    assert assert_object(owner["plan"])["scope"] == "test-file"
    (read,) = assert_records(owner["file_read_evidence"])
    assert read["source_path"] == "docs/guide.md"
    assert read["reader_path"] == "tests/test_guide.py"
    assert read["test_symbol"] == "test_commands"
    assert read["basis"] == "unshadowed-pathlib-literal-read"
    assert read["reader_revision"] and read["source_revision"]
    qualification = assert_object(graph["verification_qualification"])
    assert qualification["negative_evidence_admissible"] is False
    assert qualification["completeness"] == "incomplete"


@pytest.mark.parametrize("change", ["rewrite", "delete", "branch-return"])
def test_warm_document_relation_does_not_survive_reader_change(
    tmp_path: Path, change: str
) -> None:
    reader = _fixture(tmp_path, "    assert (ROOT / 'docs/guide.md').read_text()\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        assert _linked(
            codemap.tasks.verification_ownership_graph("Verify docs/guide.md")
        )
        if change == "rewrite":
            reader.write_text(reader.read_text().replace(".read_text()", ".as_posix()"))
        elif change == "branch-return":
            reader.write_text(
                reader.read_text().replace(
                    "    assert", "    if True:\n        return\n    assert"
                )
            )
        else:
            reader.unlink()
        assert not _linked(
            codemap.tasks.verification_ownership_graph("Verify docs/guide.md")
        )


@pytest.mark.skipif(
    os.name == "nt" or getattr(os, "geteuid", lambda: -1)() == 0,
    reason="native non-root POSIX read denial required",
)
def test_warm_document_relation_refuses_unavailable_reader(tmp_path: Path) -> None:
    reader = _fixture(tmp_path, "    assert (ROOT / 'docs/guide.md').read_text()\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        assert _linked(
            codemap.tasks.verification_ownership_graph("Verify docs/guide.md")
        )
        reader.chmod(0o000)
        try:
            with pytest.raises(PermissionError):
                reader.read_text()
            with pytest.raises(PermissionError, match="test_guide.py"):
                codemap.tasks.verification_ownership_graph("Verify docs/guide.md")
        finally:
            reader.chmod(0o600)
