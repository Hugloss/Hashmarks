from __future__ import annotations

import ast
from pathlib import Path
from textwrap import indent

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.verification_file_reads import literal_repository_file_reads

_TARGET = "docs/guide.md"
_READER = "tests/test_guide.py"
_PREFIX = "from pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\n"
_READ = "(ROOT / 'docs/guide.md').read_text()"


def _source(body: str) -> str:
    return _PREFIX + "def test_commands():\n" + indent(body, "    ") + "\n"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("document = 'docs/guide.md'\nassert document", id="lexical-only"),
        pytest.param("Path = object()\n" + _READ, id="path-shadow"),
        pytest.param("ROOT = Path('/tmp')\n" + _READ, id="root-shadow"),
        pytest.param("__file__ = '/tmp/fake.py'\n" + _READ, id="file-shadow"),
        pytest.param(
            "try:\n    pass\nexcept ValueError as Path:\n    " + _READ,
            id="except-binding",
        ),
        pytest.param(
            "match object():\n    case ROOT:\n        " + _READ, id="match-binding"
        ),
        pytest.param("if 0:\n    " + _READ, id="false-zero"),
        pytest.param("if None:\n    " + _READ, id="false-none"),
        pytest.param("if '':\n    " + _READ, id="false-empty-string"),
        pytest.param(
            "from typing import TYPE_CHECKING as TC\nif TC:\n    " + _READ,
            id="type-alias",
        ),
        pytest.param("deferred = lambda: " + _READ, id="deferred-lambda"),
        pytest.param("return\n" + _READ, id="post-return"),
        pytest.param("(ROOT / '/docs/guide.md').read_text()", id="absolute"),
        pytest.param("(ROOT / '../docs/guide.md').read_text()", id="parent-escape"),
        pytest.param(
            "(ROOT / suffix / 'docs/guide.md').read_text()", id="dynamic-segment"
        ),
        pytest.param(
            "(prefix / ROOT / 'docs/guide.md').read_text()", id="unknown-prefix"
        ),
        pytest.param("Path('docs/guide.md').read_text()", id="cwd-dependent"),
        pytest.param(
            "(ROOT / r'docs\\guide.md').read_text()", id="backslash-semantics"
        ),
    ],
)
def test_unqualified_literal_reads_do_not_establish_verifier_ownership(
    body: str,
) -> None:
    baseline = literal_repository_file_reads(
        ast.parse(_source(_READ)), _READER, _TARGET
    )
    assert len(baseline) == 1 and baseline[0]["source_path"] == _TARGET
    assert (
        literal_repository_file_reads(ast.parse(_source(body)), _READER, _TARGET) == []
    )


def _document_owner(graph: dict[str, object]) -> bool:
    owners = graph["verification_owners"]
    assert isinstance(owners, list)
    return any(
        isinstance(row, dict)
        and row.get("path") == _READER
        and row.get("covers_edit_candidates") == [_TARGET]
        for row in owners
    )


def test_warm_repository_pathlib_shadow_revokes_structural_file_read(
    tmp_path: Path,
) -> None:
    document = tmp_path / _TARGET
    document.parent.mkdir()
    document.write_text("# Repository guide\n")
    reader = tmp_path / _READER
    reader.parent.mkdir()
    reader.write_text(_source(_READ))
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        assert _document_owner(
            codemap.tasks.verification_ownership_graph("Verify docs/guide.md")
        )
        (tmp_path / "pathlib.py").write_text("class Path:\n    pass\n")
        codemap.index.sync()
        assert not _document_owner(
            codemap.tasks.verification_ownership_graph("Verify docs/guide.md")
        )
