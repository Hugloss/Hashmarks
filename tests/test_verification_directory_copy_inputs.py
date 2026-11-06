"""Copied fixture inputs are positive source relationships, not test coverage."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.codemap.verification_file_reads import literal_repository_file_reads

_READER = "tests/test_flow.py"
_SOURCE = "examples/catalog/generator/renderer.py"
_PREFIX = "from pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\n"
_COPY = "shutil.copytree(ROOT / 'examples/catalog', destination)"


def _reader(imported: str = "import shutil", call: str = _COPY) -> str:
    return _PREFIX + imported + "\ndef test_flow(destination):\n    " + call + "\n"


def _repository(tmp_path: Path, target: str, reader: str) -> Path:
    root = tmp_path / "repository"
    for path, text in {
        target: "def render(): return 'synthetic'\n"
        if target.endswith(".py")
        else "synthetic\n",
        _READER: reader,
        "pyproject.toml": "[tool.pytest.ini_options]\n",
    }.items():
        member = root / path
        member.parent.mkdir(parents=True, exist_ok=True)
        member.write_text(text)
    return root


def _targets(packet: dict[str, object]) -> list[str]:
    return [str(row["path"]) for row in assert_records(packet["targets"])]


@pytest.mark.parametrize(
    ("imported", "callee"),
    [
        ("import shutil", "shutil.copytree"),
        ("import shutil as files", "files.copytree"),
        ("from shutil import copytree as copy_fixture", "copy_fixture"),
    ],
)
@pytest.mark.parametrize(
    "target",
    [
        _SOURCE,
        "examples/catalog/web/client.ts",
        "examples/catalog/input.json",
        "examples/catalog/.gitignore",
    ],
)
def test_literal_fixture_directory_nominates_descendant_input_consumer(
    tmp_path: Path, target: str, imported: str, callee: str
) -> None:
    reader = _reader(imported, _COPY.replace("shutil.copytree", callee))
    assert Path(target).name not in reader
    root = _repository(tmp_path, target, reader)
    with CodeMap(root, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        packet = repository.verification.changed_set([target])
    assert _targets(packet) == [_READER]
    change = assert_records(packet["changes"])[0]
    relation = assert_records(change["relationships"])[0]
    read = assert_records(
        assert_object(relation["reference_evidence"])["file_read_evidence"]
    )[0]
    assert read["basis"] == "unshadowed-shutil-copytree-input"
    assert read["source_directory"] == "examples/catalog"
    assert read["source_path"] == target and read["reader_path"] == _READER
    assert read["reader_revision"] and read["source_revision"]
    assert {
        row["path"] for row in assert_records(relation["supporting_source_members"])
    } >= {target, _READER}
    assert assert_object(change["consumer_scope"])["completeness"] != "complete"
    assert packet["negative_evidence_admissible"] is False
    assert packet["execution_authority"] == "external"


@pytest.mark.parametrize(
    "body",
    [
        "shutil = object()\n" + _COPY,
        "shutil.copytree = fake\n" + _COPY,
        "ROOT = Path('/tmp')\n" + _COPY,
        "__file__ = '/tmp/test.py'\n" + _COPY,
        "return\n" + _COPY,
        "assert False\n" + _COPY,
        "assert True, " + _COPY,
        "assert condition, " + _COPY,
        "if False:\n    " + _COPY,
        "if condition:\n    " + _COPY,
        "deferred = lambda: " + _COPY,
        "def deferred():\n    " + _COPY,
        "deferred = (" + _COPY + " for _ in [1])",
        "condition and " + _COPY,
        _COPY + " if condition else None",
        "[" + _COPY + " for _ in []]",
        "[" + _COPY + " for _ in [1] if condition]",
        "[" + _COPY + " for _ in supplied]",
        "try:\n    pass\nexcept Exception:\n    " + _COPY,
        "match supplied:\n    case 1:\n        " + _COPY,
        _COPY.replace("destination)", "destination, ignore=filter_inputs)"),
        _COPY.replace("destination)", "destination, copy_function=copy_file)"),
        _COPY.replace("destination)", "destination, symlinks=True)"),
        _COPY.replace("destination)", "destination, False)"),
        "shutil.copytree(*arguments)",
        "shutil.copytree(ROOT, destination)",
        _COPY.replace("ROOT / 'examples/catalog'", "ROOT / supplied"),
        _COPY.replace("ROOT / 'examples/catalog'", "Path('examples/catalog')"),
        _COPY.replace("ROOT / 'examples/catalog'", "ROOT / '../examples/catalog'"),
        _COPY.replace("ROOT / 'examples/catalog'", "ROOT / 'examples/cat'"),
        _COPY.replace(
            "ROOT / 'examples/catalog'",
            "ROOT / 'examples/catalog/generator/renderer.py'",
        ),
    ],
)
def test_unqualified_copy_input_does_not_establish_relationship(body: str) -> None:
    baseline = literal_repository_file_reads(
        ast.parse(_reader()), _READER, _SOURCE, include_directory_copies=True
    )
    assert len(baseline) == 1
    source = (
        _PREFIX
        + "import shutil\ndef test_flow(destination):\n"
        + "\n".join("    " + line for line in body.splitlines())
    )
    assert (
        literal_repository_file_reads(
            ast.parse(source), _READER, _SOURCE, include_directory_copies=True
        )
        == []
    )


@pytest.mark.parametrize(
    "expression",
    [
        "[" + _COPY + " for _ in [1]]",
        "{" + _COPY + " for _ in (1,)}",
        "{1: " + _COPY + " for _ in [1]}",
        "(item for item in " + _COPY + ")",
        _COPY + " and condition",
        _COPY + " if True else None",
        "assert False, " + _COPY,
    ],
)
def test_eager_copy_expression_retains_its_observed_input(expression: str) -> None:
    reads = literal_repository_file_reads(
        ast.parse(_reader(call=expression)),
        _READER,
        _SOURCE,
        include_directory_copies=True,
    )
    assert len(reads) == 1 and reads[0]["source_path"] == _SOURCE


def test_repository_shutil_module_does_not_inherit_standard_library_copy_authority(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path, _SOURCE, _reader())
    (root / "shutil.py").write_text(
        "def copytree(source, destination): return destination\n"
    )
    with CodeMap(root, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        assert _targets(repository.verification.changed_set([_SOURCE])) == []


@pytest.mark.parametrize("change", ["source", "rewrite-reader", "remove-reader"])
def test_warm_copy_relationship_rechecks_source_and_reader(
    tmp_path: Path, change: str
) -> None:
    root = _repository(tmp_path, _SOURCE, _reader())
    with CodeMap(root, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        before = repository.verification.changed_set([_SOURCE])
        assert _targets(before) == [_READER]
        if change == "source":
            (root / _SOURCE).write_text("def render(): return 'changed'\n")
        elif change == "rewrite-reader":
            (root / _READER).write_text(
                _reader(call=_COPY.replace("examples/catalog", "examples/other"))
            )
        else:
            (root / _READER).unlink()
        after = repository.verification.changed_set([_SOURCE])
    if change == "source":
        assert _targets(after) == [_READER]
        old = assert_records(assert_records(before["changes"])[0]["relationships"])[0]
        new = assert_records(assert_records(after["changes"])[0]["relationships"])[0]
        assert old["evidence_identity"] != new["evidence_identity"]
    else:
        assert _targets(after) == []


def test_direct_python_source_read_keeps_its_existing_unqualified_scope(
    tmp_path: Path,
) -> None:
    root = _repository(
        tmp_path,
        _SOURCE,
        _reader(
            call="assert (ROOT / 'examples/catalog/generator/renderer.py').read_bytes()"
        ),
    )
    with CodeMap(root, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        assert _targets(repository.verification.changed_set([_SOURCE])) == []


def test_changed_set_fixture_scope_does_not_redefine_legacy_symbol_reference_scope(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path, _SOURCE, _reader())
    imported = root / "tests/test_renderer.py"
    imported.write_text(
        "from examples.catalog.generator.renderer import render\n"
        "def test_renderer(): assert render() == 'synthetic'\n"
    )
    with CodeMap(root, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        legacy = repository.tasks.verification_ownership_graph(f"Change {_SOURCE}")
        changed = repository.verification.changed_set([_SOURCE])
    qualification = assert_object(legacy["verification_qualification"])
    assert qualification["completeness"] == "complete"
    assert qualification["search_bound_reasons"] == []
    assert {
        row["path"]
        for row in assert_records(legacy["verification_owners"])
        if row.get("covers_edit_candidates") == [_SOURCE]
    } == {"tests/test_renderer.py"}
    assert set(_targets(changed)) == {_READER, "tests/test_renderer.py"}
    change = assert_records(changed["changes"])[0]
    assert assert_object(change["consumer_scope"])["completeness"] == "incomplete"
    assert "literal-file-reader-syntax-scope" in assert_array(
        assert_object(change["relevance"])["search_bound_reasons"]
    )
    assert changed["negative_evidence_admissible"] is False
