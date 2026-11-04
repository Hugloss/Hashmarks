from __future__ import annotations

import ast
from pathlib import Path
from textwrap import indent

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS
from hashmarks.codemap.verification_file_reads import literal_repository_file_reads

_TARGET = "docs/guide.md"
_READER = "tests/test_guide.py"
_PREFIX = "from pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\n"
_READ = "(ROOT / 'docs/guide.md').read_text()"
_FINITE_BINDING = "documents = [ROOT / 'docs/other.md', ROOT / 'docs/guide.md']\n"
_FINITE_LOOP = "for document in documents:\n    assert document.read_text()"


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


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            _FINITE_BINDING + "alias = documents\nalias.clear()\n" + _FINITE_LOOP,
            id="mutated-list-alias",
        ),
        pytest.param(
            _FINITE_BINDING + "documents[1] = ROOT / 'docs/other.md'\n" + _FINITE_LOOP,
            id="mutated-list-member",
        ),
        pytest.param(
            _FINITE_BINDING + "mutate(documents)\n" + _FINITE_LOOP,
            id="escaped-list",
        ),
        pytest.param(
            _FINITE_BINDING
            + "for document in documents:\n"
            + "    document = ROOT / 'docs/other.md'\n"
            + "    assert document.read_text()",
            id="rebound-loop-target",
        ),
        pytest.param(
            "ROOT = Path('/tmp')\n" + _FINITE_BINDING + _FINITE_LOOP,
            id="shadowed-root",
        ),
        pytest.param(
            "documents = [ROOT / 'docs/guide.md', caller_path]\n" + _FINITE_LOOP,
            id="dynamic-member",
        ),
        pytest.param(
            "documents = [ROOT / name for name in ['docs/guide.md']]\n" + _FINITE_LOOP,
            id="comprehension",
        ),
        pytest.param(
            _FINITE_LOOP + "\n" + _FINITE_BINDING,
            id="read-before-collection-binding",
        ),
        pytest.param(
            "documents = [ROOT / 'docs/guide.md', ROOT / 'docs/other.md']\n"
            "for document in documents:\n    pass\n"
            "assert document.read_text()",
            id="target-escapes-loop",
        ),
        pytest.param(
            _FINITE_BINDING + _FINITE_LOOP + "\n    return",
            id="return-before-later-member",
        ),
        pytest.param(
            _FINITE_BINDING + _FINITE_LOOP + "\n    break",
            id="break-before-later-member",
        ),
        pytest.param(
            _FINITE_BINDING
            + "for document in documents:\n"
            + "    continue\n    assert document.read_text()",
            id="continue-before-read",
        ),
        pytest.param(
            _FINITE_BINDING + _FINITE_LOOP + "\n    raise RuntimeError()",
            id="raise-before-later-member",
        ),
        pytest.param(
            _FINITE_BINDING + _FINITE_LOOP + "\n    assert False",
            id="assert-before-later-member",
        ),
        pytest.param(
            "for document in []:\n    assert " + _READ,
            id="empty-iteration",
        ),
        pytest.param(
            "documents = ["
            + ", ".join(
                ["ROOT / 'docs/guide.md'"]
                + [
                    f"ROOT / 'docs/member-{index}.md'"
                    for index in range(
                        VERIFICATION_RELEVANCE_DEFAULTS.literal_file_read_sites
                    )
                ]
            )
            + "]\n"
            + _FINITE_LOOP,
            id="collection-bound",
        ),
    ],
)
def test_unqualified_finite_iteration_does_not_establish_file_read(
    body: str,
) -> None:
    baseline = literal_repository_file_reads(
        ast.parse(_source(_FINITE_BINDING + _FINITE_LOOP)), _READER, _TARGET
    )
    assert len(baseline) == 1 and baseline[0]["source_path"] == _TARGET
    assert (
        literal_repository_file_reads(ast.parse(_source(body)), _READER, _TARGET) == []
    )


@pytest.mark.parametrize("tests_only", [True, False])
def test_module_iteration_does_not_bind_a_deferred_function_reader(
    tests_only: bool,
) -> None:
    baseline = literal_repository_file_reads(
        ast.parse(_source(_FINITE_BINDING + _FINITE_LOOP)),
        _READER,
        _TARGET,
        tests_only=tests_only,
    )
    assert len(baseline) == 1 and baseline[0]["source_path"] == _TARGET
    source = (
        _PREFIX
        + "for document in (ROOT / 'docs/guide.md', ROOT / 'docs/other.md'):\n"
        + "    def test_commands():\n"
        + "        return document.read_text()\n"
    )
    assert (
        literal_repository_file_reads(
            ast.parse(source), _READER, _TARGET, tests_only=tests_only
        )
        == []
    )


@pytest.mark.parametrize("tests_only", [True, False])
def test_iteration_does_not_bind_a_deferred_generator_reader(
    tests_only: bool,
) -> None:
    baseline = literal_repository_file_reads(
        ast.parse(_source(_FINITE_BINDING + _FINITE_LOOP)),
        _READER,
        _TARGET,
        tests_only=tests_only,
    )
    assert len(baseline) == 1 and baseline[0]["source_path"] == _TARGET
    body = (
        "documents = [ROOT / 'docs/guide.md', ROOT / 'docs/other.md']\n"
        "for document in documents:\n"
        "    pending = (document.read_text() for _ in (0,))\n"
        "assert next(pending)\n"
    )
    assert (
        literal_repository_file_reads(
            ast.parse(_source(body)), _READER, _TARGET, tests_only=tests_only
        )
        == []
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
