"""Direct verification consumes source-bound owner facts, never a task service."""

import subprocess
import sys
from pathlib import Path

import pytest
from test_repository_index_component import index as index
from test_repository_source_component import _source

from hashmarks.codemap.evidence_verification import RepositoryVerification
from hashmarks.codemap.import_resolution import RepositoryImports
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.query_router import normalize_task_query
from hashmarks.codemap.verification_relevance_model import VerificationRequest


def _verification(index: RepositoryIndex) -> RepositoryVerification:
    source = _source(index)
    imports = RepositoryImports(source)
    return RepositoryVerification(imports)


def test_direct_verifier_selects_reference_backed_test_and_rejects_expired_binding(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.py").write_text("def calculate_total(): return 1\n")
    (index.workspace / "tests").mkdir()
    (index.workspace / "tests/test_total.py").write_text(
        "from owner import calculate_total\ndef test_total(): assert calculate_total() == 1\n"
    )
    index.sync()
    verification = _verification(index)
    with verification.reads.session() as scope:
        request = VerificationRequest(
            scope,
            normalize_task_query("Change calculate_total"),
            "nominated",
            {"path": "owner.py", "name": "calculate_total"},
            None,
            (),
        )
        packet = verification.for_owner(request)
        assert packet["selected"] is not None
        assert packet["selected"]["path"] == "tests/test_total.py"
        assert packet["selected"].get("direct_reference") is True
    with pytest.raises(RuntimeError, match="different read scope"):
        verification.for_owner(request)


def test_unresolved_request_cannot_supply_an_admitted_edit(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "owner.py").write_text("def owner(): return 1\n")
    index.sync()
    verification = _verification(index)
    with verification.reads.session() as scope:
        request = VerificationRequest(
            scope,
            normalize_task_query("owner"),
            "unresolved",
            {"path": "owner.py"},
            None,
            (),
        )
        with pytest.raises(ValueError, match="unresolved ownership"):
            verification.for_owner(request)


def test_verification_import_observation_cannot_survive_a_changed_source_scope(
    index: RepositoryIndex,
) -> None:
    (index.workspace / "pkg").mkdir()
    (index.workspace / "pkg/__init__.py").write_text("")
    for module in ("left", "right"):
        (index.workspace / f"pkg/{module}.py").write_text(
            "class Worker:\n    def run(self): return 1\n"
        )
    facade = index.workspace / "pkg/facade.py"
    facade.write_text("from .left import Worker\n")
    (index.workspace / "tests").mkdir()
    (index.workspace / "tests/test_result.py").write_text(
        "from pkg.facade import Worker\ndef test_result(): assert Worker().run() == 1\n"
    )
    index.sync()
    verification = _verification(index)
    packets = []
    for module in ("left", "right"):
        facade.write_text(f"from .{module} import Worker\n")
        index.sync(["pkg/facade.py"])
        with verification.reads.session() as scope:
            packets.append(
                verification.for_owner(
                    VerificationRequest(
                        scope,
                        normalize_task_query("Inspect Worker in pkg/left.py"),
                        "nominated",
                        {"path": "pkg/left.py", "name": "Worker"},
                        None,
                        (),
                    )
                )
            )
    assert any(row.get("direct_reference") is True for row in packets[0]["candidates"])
    assert all(row.get("direct_reference") is False for row in packets[1]["candidates"])
    assert verification.reads.depth == 0


@pytest.mark.parametrize("shadowed", [False, True])
def test_source_reference_fanout_cannot_hide_a_qualified_test(
    index: RepositoryIndex, shadowed: bool
) -> None:
    (index.workspace / "pkg").mkdir()
    (index.workspace / "pkg/__init__.py").write_text("from .impl import Worker\n")
    (index.workspace / "pkg/impl.py").write_text(
        "class Worker:\n    def run(self): return 1\n"
    )
    (index.workspace / "a_callers.py").write_text(
        "from pkg import Worker\n" + "Worker()\n" * 1030
    )
    (index.workspace / "tests").mkdir()
    test_path = "tests/test_result.py"
    (index.workspace / test_path).write_text(
        "from pkg import Worker\n"
        + ("Worker = object\n" if shadowed else "")
        + "def test_result(): assert Worker().run() == 1\n"
    )
    index.sync()
    verification = _verification(index)
    with verification.reads.session() as scope:
        packet = verification.for_owner(
            VerificationRequest(
                scope,
                normalize_task_query("Inspect Worker"),
                "nominated",
                {"path": "pkg/impl.py", "name": "Worker"},
                None,
                (),
            )
        )
    candidate = next(row for row in packet["candidates"] if row["path"] == test_path)
    assert candidate.get("direct_reference") is not shadowed
    if not shadowed:
        assert candidate.get("reference_symbols") == ["Worker"]
    assert packet.get("completeness") == "incomplete"
    assert packet.get("negative_evidence_admissible") is False
    assert not str(packet["selection_reason"]).startswith("unique")


@pytest.mark.parametrize("shadowed", [False, True])
@pytest.mark.parametrize("other_owner", [False, True])
def test_test_reference_fanout_keeps_module_local_import_evidence(
    index: RepositoryIndex, shadowed: bool, other_owner: bool
) -> None:
    (index.workspace / "pkg").mkdir()
    (index.workspace / "pkg/__init__.py").write_text("from .app import Worker\n")
    (index.workspace / "pkg/app.py").write_text(
        "class Worker:\n    def run(self): return 1\n"
    )
    (index.workspace / "pkg/other.py").write_text(
        "class Worker:\n    def run(self): return 1\n"
    )
    (index.workspace / "tests/zzz").mkdir(parents=True)
    (index.workspace / "tests/test_noise.py").write_text(
        "from pkg import Worker\n" + "Worker()\n" * 1030
    )
    test_path = "tests/zzz/test_app.py"
    (index.workspace / test_path).write_text(
        (
            "from pkg.other import Worker\n"
            if other_owner
            else "from pkg import Worker\n"
        )
        + ("Worker = object\n" if shadowed else "")
        + "def test_response(): assert Worker().run() == 1\n"
    )
    index.sync()
    verification = _verification(index)
    with verification.reads.session() as scope:
        packet = verification.for_owner(
            VerificationRequest(
                scope,
                normalize_task_query("Inspect Worker"),
                "nominated",
                {"path": "pkg/app.py", "name": "Worker"},
                None,
                (),
            )
        )
    candidate = next(row for row in packet["candidates"] if row["path"] == test_path)
    assert candidate.get("direct_reference") is (not shadowed and not other_owner)
    assert packet.get("completeness") == "incomplete"
    assert packet.get("negative_evidence_admissible") is False
    assert not str(packet["selection_reason"]).startswith("unique")


@pytest.mark.parametrize("visibility", ["deny", "outline"])
def test_hidden_module_name_matches_do_not_consume_source_reference_slots(
    index: RepositoryIndex, visibility: str
) -> None:
    (index.workspace / ".hashmarks-context.toml").write_text(
        f"[[rule]]\npattern='tests/hidden/**'\nvisibility='{visibility}'\n"
    )
    (index.workspace / "pkg").mkdir()
    (index.workspace / "pkg/__init__.py").write_text("from .app import Worker\n")
    (index.workspace / "pkg/app.py").write_text(
        "class Worker:\n    def run(self): return 1\n"
    )
    for n in range(65):
        folder = index.workspace / f"tests/hidden/{n:03}"
        folder.mkdir(parents=True)
        (folder / "test_app.py").write_text(
            "from pkg import Worker\ndef test_hidden(): Worker()\n"
        )
    (index.workspace / "tests/zzz").mkdir()
    path = "tests/zzz/test_app.py"
    (index.workspace / path).write_text(
        "from pkg import Worker\ndef test_visible(): Worker()\n"
    )
    index.sync()
    verification = _verification(index)
    with verification.reads.session() as scope:
        packet = verification.for_owner(
            VerificationRequest(
                scope,
                normalize_task_query("Inspect Worker"),
                "nominated",
                {"path": "pkg/app.py", "name": "Worker"},
                None,
                (),
            )
        )
    assert "module-test-path-limit" not in packet.get("search_bound_reasons", [])
    assert any(
        row["path"] == path and row.get("direct_reference") is True
        for row in packet["candidates"]
    )


def test_verifier_import_does_not_load_tasks_ownership_or_facade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.evidence_verification import RepositoryVerification; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.repository_tasks' not in sys.modules; assert 'hashmarks.codemap.ownership_graph' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
