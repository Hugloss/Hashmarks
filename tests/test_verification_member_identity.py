"""A shared method spelling does not prove correspondence to its edit owner."""

from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.query_router import normalize_task_query
from hashmarks.codemap.verification_relevance_model import VerificationRequest


def _repository(root: Path, verifier: str) -> None:
    (root / "alpha.py").write_text(
        "class Message:\n    def nack(self): return 'alpha'\n"
        "class Other:\n    def nack(self): return 'other'\n"
    )
    (root / "beta.py").write_text("class Message:\n    def nack(self): return 'beta'\n")
    (root / "tests").mkdir()
    (root / "tests/test_delivery.py").write_text(verifier)


@pytest.mark.parametrize(
    "verifier",
    [
        "from beta import Message as Foreign\n"
        "def test_delivery():\n    Foreign().nack()\n",
        "def test_delivery(message):\n    message.nack()\n",
        "import alpha as repository\n"
        "def test_delivery():\n    repository.Other.nack(None)\n",
        "import alpha as repository\nfrom beta import Message\n"
        "repository = Message\n"
        "def test_delivery():\n    repository.nack(None)\n",
        "import alpha as repository\nimport beta as repository\n"
        "def test_delivery():\n    repository.Message.nack(None)\n",
    ],
)
def test_unqualified_or_conflicting_method_receiver_is_not_direct_evidence(
    tmp_path: Path, verifier: str
) -> None:
    _repository(tmp_path, verifier)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        relevance = codemap.tasks.verification_relevance(
            "Inspect Message.nack in alpha.py"
        )
    candidate = next(
        row
        for row in relevance["candidates"]
        if row["path"] == "tests/test_delivery.py"
    )
    assert candidate.get("direct_reference") is False
    assert candidate.get("indirect_reference") is False
    assert candidate.get("reference_symbols") == []
    assert relevance.get("negative_evidence_admissible") is False


@pytest.mark.parametrize(
    "verifier",
    [
        "import alpha as repository\n"
        "def test_delivery():\n    repository.Message.nack(None)\n",
        "from alpha import Message as Actual\n"
        "def test_delivery():\n    Actual.nack(None)\n",
    ],
)
def test_explicit_import_and_member_scope_qualify_the_static_reference(
    tmp_path: Path, verifier: str
) -> None:
    _repository(tmp_path, verifier)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        relevance = codemap.tasks.verification_relevance(
            "Inspect Message.nack in alpha.py"
        )
    candidate = next(
        row
        for row in relevance["candidates"]
        if row["path"] == "tests/test_delivery.py"
    )
    assert candidate.get("direct_reference") is True
    assert candidate.get("reference_symbols") == ["nack"]


def test_unknown_method_receivers_cannot_make_a_known_verifier_unique(
    tmp_path: Path,
) -> None:
    _repository(
        tmp_path,
        "import alpha as repository\n"
        "def test_delivery():\n    repository.Message.nack(None)\n",
    )
    (tmp_path / "tests/test_unknown.py").write_text(
        "def test_unresolved(message):\n    message.nack()\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        relevance = codemap.tasks.verification_relevance(
            "Inspect Message.nack in alpha.py"
        )
    assert relevance.get("negative_evidence_admissible") is False
    assert relevance.get("qualified_identity_ambiguous") is True
    assert "unique" not in relevance["selection_reason"]


@pytest.mark.parametrize(
    "verifier",
    [
        "def test_delivery(client):\n    client.emit()\n",
        "from alpha import emit\ndef test_delivery(client):\n    client.emit()\n",
        "from alpha import emit\ndef test_delivery(emit):\n    emit()\n",
        "from alpha import emit as actual\ndef test_delivery(actual):\n    actual()\n",
        "import alpha as repository\nfrom beta import Other as repository\n"
        "def test_delivery():\n    repository.emit()\n",
        "import alpha as repository\ndef test_delivery():\n    repository.Other.emit()\n",
    ],
)
def test_instance_method_spelling_does_not_reference_an_unrelated_module_function(
    tmp_path: Path,
    verifier: str,
) -> None:
    (tmp_path / "alpha.py").write_text(
        "def emit(): return 'alpha'\nclass Other:\n    def emit(): return 'other'\n"
    )
    (tmp_path / "beta.py").write_text("class Other:\n    def emit(): return 'beta'\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_delivery.py").write_text(verifier)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with codemap.reads.session() as _task_read_scope:
            relevance = codemap.verification.for_owner(
                VerificationRequest(
                    _task_read_scope,
                    normalize_task_query("Inspect emit in alpha.py"),
                    "nominated",
                    {"path": "alpha.py", "name": "emit", "qualname": "emit"},
                    None,
                    tuple([]),
                )
            )
    candidate = next(
        row
        for row in relevance["candidates"]
        if row["path"] == "tests/test_delivery.py"
    )
    assert candidate.get("direct_reference") is False
    assert candidate.get("indirect_reference") is False
    assert relevance.get("negative_evidence_admissible") is False


@pytest.mark.parametrize(
    "binding, call",
    [
        ("from alpha import emit as actual", "actual()"),
        ("import alpha as repository", "repository.emit()"),
    ],
)
def test_explicit_module_function_reference_retains_its_authority(
    tmp_path: Path,
    binding: str,
    call: str,
) -> None:
    (tmp_path / "alpha.py").write_text("def emit(): return 'alpha'\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_delivery.py").write_text(
        f"{binding}\ndef test_delivery():\n    {call}\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        relevance = codemap.tasks.verification_relevance("Inspect emit in alpha.py")
    candidate = next(
        row
        for row in relevance["candidates"]
        if row["path"] == "tests/test_delivery.py"
    )
    assert candidate.get("direct_reference") is True
    assert candidate.get("reference_symbols") == ["emit"]


def test_indirect_member_proof_cannot_strengthen_an_unused_direct_import(
    tmp_path: Path,
) -> None:
    (tmp_path / "alpha.py").write_text("def emit(): return 'alpha'\n")
    (tmp_path / "beta.py").write_text(
        "from alpha import emit as imported\n"
        "class Other:\n    def emit(): return 'other'\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_delivery.py").write_text(
        "from alpha import emit\nimport beta\n"
        "def test_delivery():\n    beta.Other.emit()\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        relevance = codemap.tasks.verification_relevance("Inspect emit in alpha.py")
    candidate = next(
        row
        for row in relevance["candidates"]
        if row["path"] == "tests/test_delivery.py"
    )
    assert candidate.get("direct_reference") is False
    assert candidate.get("indirect_reference") is True
    assert candidate.get("reference_strength") == "reachable-import"
