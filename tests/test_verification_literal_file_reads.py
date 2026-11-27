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


@pytest.mark.parametrize("collection", ["tuple", "list"])
def test_finite_repository_document_iteration_is_a_structural_verifier(
    tmp_path: Path, collection: str
) -> None:
    opening, closing = ("(", ")") if collection == "tuple" else ("[", "]")
    _fixture(
        tmp_path,
        f"    documents = {opening}ROOT / 'docs/guide.md', ROOT / 'README.md'{closing}\n"
        "    for document in documents:\n"
        "        text = document.read_text(encoding='utf-8')\n"
        "        assert text\n",
    )
    (tmp_path / "README.md").write_text("# Repository\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        graph = codemap.tasks.verification_ownership_graph("Verify docs/guide.md")
        changed = codemap.verification.changed_set(["docs/guide.md"])
    (owner,) = _linked(graph)
    (read,) = assert_records(owner["file_read_evidence"])
    assert read["test_symbol"] == "test_commands"
    assert read["reader_revision"] and read["source_revision"]
    qualification = assert_object(graph["verification_qualification"])
    assert qualification["completeness"] == "incomplete"
    assert qualification["negative_evidence_admissible"] is False
    (target,) = assert_records(changed["targets"])
    assert target["path"] == "tests/test_guide.py"
    assert assert_object(target["nomination"])["available"] is True
    assert changed["negative_evidence_admissible"] is False
    assert changed["execution_authority"] == "external"


@pytest.mark.parametrize("change", ["method", "mutation", "receiver-rebound"])
def test_warm_document_iteration_does_not_survive_reader_change(
    tmp_path: Path, change: str
) -> None:
    reader = _fixture(
        tmp_path,
        "    documents = [ROOT / 'docs/guide.md']\n"
        "    for document in documents:\n"
        "        assert document.read_text()\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        assert _linked(
            codemap.tasks.verification_ownership_graph("Verify docs/guide.md")
        )
        before = reader.read_text()
        if change == "method":
            after = before.replace(".read_text()", ".as_posix()")
        elif change == "mutation":
            after = before.replace(
                "    for document", "    documents.clear()\n    for document"
            )
        else:
            after = before.replace(
                "        assert",
                "        document = Path('/tmp/other')\n        assert",
            )
        reader.write_text(after)
        assert not _linked(
            codemap.tasks.verification_ownership_graph("Verify docs/guide.md")
        )


def test_module_iteration_does_not_bind_a_deferred_test_reader(tmp_path: Path) -> None:
    reader = _fixture(
        tmp_path,
        "    for document in (ROOT / 'docs/guide.md', ROOT / 'docs/other.md'):\n"
        "        assert document.read_text()\n",
    )
    (tmp_path / "docs/other.md").write_text("# Other\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        assert _linked(
            codemap.tasks.verification_ownership_graph("Verify docs/guide.md")
        )
        reader.write_text(
            "from pathlib import Path\n"
            "ROOT = Path(__file__).resolve().parents[1]\n"
            "for document in (ROOT / 'docs/guide.md', ROOT / 'docs/other.md'):\n"
            "    def test_commands():\n"
            "        return document.read_text()\n"
        )
        assert not _linked(
            codemap.tasks.verification_ownership_graph("Verify docs/guide.md")
        )


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


@pytest.mark.parametrize(
    ("condition", "observed"),
    [("True or", False), ("False and", False), ("False or", True), ("True and", True)],
)
def test_literal_read_relationship_obeys_boolean_short_circuit(
    tmp_path: Path, condition: str, observed: bool
) -> None:
    _fixture(tmp_path, f"    assert {condition} (ROOT / 'docs/guide.md').read_text()\n")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.verification.changed_set(["docs/guide.md"])
    assert bool(packet["targets"]) is observed
    assert packet["negative_evidence_admissible"] is False


@pytest.mark.parametrize(
    ("expression", "observed"),
    [
        ("READ if not True else 1", False),
        ("1 if not False else READ", False),
        ("READ if not False else 1", True),
        ("1 if not True else READ", True),
        ("1 if READ else 2", True),
    ],
)
def test_literal_reads_follow_the_possible_conditional_arm(
    tmp_path: Path, expression: str, observed: bool
) -> None:
    read = "(ROOT / 'docs/guide.md').read_text()"
    _fixture(tmp_path, "    value = " + expression.replace("READ", read) + "\n")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        changed = repository.verification.changed_set(["docs/guide.md"])
    assert bool(changed["targets"]) is observed
    assert changed["negative_evidence_admissible"] is False


@pytest.mark.parametrize(
    ("body", "observed"),
    [
        ("for item in ():\n        pass\n    else:\n        READ", True),
        ("for item in []:\n        READ\n    else:\n        pass", False),
        (
            "for item in '':\n        pass\n    else:\n        return\n        READ",
            False,
        ),
        (
            "try:\n        for _ in ():\n            pass\n        else:\n            return\n    finally:\n        READ",
            True,
        ),
        (
            "try:\n        for _ in ():\n            pass\n        else:\n            raise RuntimeError\n    except RuntimeError:\n        READ",
            True,
        ),
    ],
)
def test_empty_for_preserves_qualified_literal_read_in_loop_else(
    tmp_path: Path, body: str, observed: bool
) -> None:
    _fixture(
        tmp_path,
        "    " + body.replace("READ", "(ROOT / 'docs/guide.md').read_text()") + "\n",
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        changed = repository.verification.changed_set(["docs/guide.md"])
    assert bool(changed["targets"]) is observed
    assert changed["negative_evidence_admissible"] is False


@pytest.mark.parametrize(
    ("suites", "observed"),
    [
        ("while not True: pass\n    else: READ", True),
        ("while False: READ\n    else: pass", False),
        ("while 0: pass\n    else: return\n    READ", False),
        (
            "try:\n        while False: pass\n        else: return\n    finally: READ",
            True,
        ),
        (
            "try:\n        while False: pass\n        else: raise ValueError\n    except ValueError: READ",
            True,
        ),
    ],
)
def test_zero_iteration_while_retains_only_possible_literal_read(
    tmp_path: Path, suites: str, observed: bool
) -> None:
    _fixture(
        tmp_path,
        "    " + suites.replace("READ", "(ROOT / 'docs/guide.md').read_text()") + "\n",
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        changed = repository.verification.changed_set(["docs/guide.md"])
    assert bool(changed["targets"]) is observed
    assert changed["negative_evidence_admissible"] is False


@pytest.mark.parametrize(
    ("condition", "observed"),
    [
        ("not False", False),
        ("(lambda: READ)", False),
        ("(lambda value=READ: value)", True),
        ("(READ for item in (1,))", False),
        ("(item for item in READ)", True),
        ("False", True),
        ("flag", True),
    ],
)
def test_assertion_reads_preserve_eager_inputs_and_skip_impossible_messages(
    tmp_path: Path, condition: str, observed: bool
) -> None:
    read = "(ROOT / 'docs/guide.md').read_text()"
    _fixture(
        tmp_path,
        "    flag = (ROOT / 'enabled').exists()\n    assert "
        + condition.replace("READ", read)
        + ", "
        + read
        + "\n",
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        changed = repository.verification.changed_set(["docs/guide.md"])
    assert bool(changed["targets"]) is observed
    assert changed["negative_evidence_admissible"] is False


@pytest.mark.parametrize(
    ("expression", "observed"),
    [
        ("[READ for item in ()]", False),
        ("{item: READ for item in ''}", False),
        ("[item for item in (1,) if False if READ]", False),
        ("[item for _ in READ for item in []]", True),
        ("[item for item in (1,) if READ if False]", True),
        ("[READ for _ in (1,)]", True),
    ],
)
def test_literal_read_comprehensions_retain_only_possible_inputs(
    tmp_path: Path, expression: str, observed: bool
) -> None:
    _fixture(
        tmp_path,
        "    rows = "
        + expression.replace("READ", "(ROOT / 'docs/guide.md').read_text()")
        + "\n",
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        changed = repository.verification.changed_set(["docs/guide.md"])
    assert bool(changed["targets"]) is observed
    assert changed["negative_evidence_admissible"] is False
