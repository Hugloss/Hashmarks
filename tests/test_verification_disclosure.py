"""Task-retrieved tests survive broad reference discovery without gaining authority."""

from __future__ import annotations

from typing import TYPE_CHECKING

from contract_assertions import assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_contract import read_initial_projection
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_collection,
    decode_initial_packet,
)

if TYPE_CHECKING:
    from pathlib import Path


def _repository(root: Path) -> tuple[str, str]:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src/backend.py").write_text("def render(): return {'schema': 'root'}\n")
    (root / "tests/test_root_nested_schema_dto.py").write_text(
        "from src.backend import render\n"
        "def test_root_nested_schema_dto(): assert render()['schema'] == 'root'\n"
    )
    for index in range(20):
        (root / f"tests/test_smoke_{index:02}.py").write_text(
            "from src.backend import render\n"
            "def test_render(): assert isinstance(render(), dict)\n"
        )
    expected = "tests/test_client.py"
    (root / expected).write_text(
        "def test_root_nested_schema(public_client):\n"
        "    assert public_client.get('/schema').json()['schema'] == 'root'\n"
    )
    return "Fix root nested schema DTO in src/backend.py", expected


def test_task_candidate_survives_reference_fanout_without_reference_authority(
    tmp_path: Path,
) -> None:
    task, expected = _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(task)
        packet = codemap.tasks.evidence(task)
        initial = read_initial_projection(
            decode_initial_packet(codemap.tasks.evidence(task, result_mode="initial"))
        )
    assert packet["ownership"]["owner"] is not None
    assert packet["ownership"]["owner"]["path"] == "src/backend.py"
    assert action["verify"] is not None
    assert action["verify"]["path"] == "tests/test_root_nested_schema_dto.py"
    relevance = packet["verification"]["relevance"]
    assert relevance["selected"] is not None
    assert relevance["selected"]["path"] == action["verify"]["path"]
    assert relevance["selection_changed"] is False
    assert len(relevance["candidates"]) == 8
    assert relevance.get("candidate_count") == 22
    row = next(row for row in relevance["candidates"] if row["path"] == expected)
    assert row.get("direct_reference") is False
    assert row.get("indirect_reference") is False
    assert row.get("reference_symbols") == []
    assert row.get("test_symbol") == "test_root_nested_schema"
    assert row.get("canonical_rank") is not None
    initial_relevance = initial["verification"]["relevance"]
    assert "candidates_encoding" in initial_relevance
    decoded = decode_initial_collection(
        initial_relevance["candidates"], initial_relevance["candidates_encoding"]
    )
    assert {row["path"] for row in decoded} == {
        row["path"] for row in relevance["candidates"]
    }


def test_disclosure_bounds_preserve_selected_verifier_and_candidate_population(
    tmp_path: Path,
) -> None:
    task, _ = _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        projections = [
            codemap.tasks.verification_relevance(task, candidate_limit=limit)
            for limit in (1, 3, 8)
        ]
    for limit, relevance in zip((1, 3, 8), projections, strict=True):
        assert len(relevance["candidates"]) == limit
        assert relevance.get("candidate_count") == 22
        assert relevance["selected"] is not None
        assert relevance["selected"]["path"] == "tests/test_root_nested_schema_dto.py"
        assert relevance["selected"]["path"] in {
            row["path"] for row in relevance["candidates"]
        }
        assert relevance["selection_changed"] is False
    assert projections[0]["selected"] == projections[-1]["selected"]


def test_short_identifier_components_remain_verification_task_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/backend.py").write_text("def field(): return None\n")
    for name in ("db", "fd"):
        (tmp_path / f"tests/test_field_{name}_options.py").write_text(
            "from src.backend import field\n"
            f"def test_{name}_options(): assert field() is None\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence("Inspect field db_type in src/backend.py")
    rows = {
        row["path"]: row for row in packet["verification"]["relevance"]["candidates"]
    }
    assert "db" in rows["tests/test_field_db_options.py"].get("task_anchor_terms", [])
    assert "db" not in rows["tests/test_field_fd_options.py"].get(
        "task_anchor_terms", []
    )


def test_production_lexical_fanout_cannot_hide_the_test_observation_scope(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/engine.py").write_text("def process(): return None\n")
    for index in range(80):
        (tmp_path / f"src/worker_{index:02}.py").write_text(
            "# Inspect cancellation scope cleanup in src engine py\n"
            "def observe(): return None\n"
        )
    (tmp_path / "src/test_cancellation.py").write_text(
        "# production module, not a test surface\n"
        "def cancellation_scope_cleanup(): return None\n"
    )
    expected = "tests/test_cancellation.py"
    (tmp_path / expected).write_text("def test_cancellation(client): client.close()\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence(
            "Inspect cancellation scope cleanup in src/engine.py"
        )
    relevance = packet["verification"]["relevance"]
    assert "task_matches" in relevance
    matches = assert_records(relevance["task_matches"].get("matches"))
    assert [row["path"] for row in matches] == [expected]
    row = next(row for row in relevance["candidates"] if row["path"] == expected)
    assert row.get("direct_reference") is False
    assert row.get("indirect_reference") is False
    assert all(
        row["path"] != "src/test_cancellation.py" for row in relevance["candidates"]
    )


def test_tied_test_names_remain_visible_without_selecting_one(tmp_path: Path) -> None:
    (tmp_path / "backend.py").write_text("def execute(): return 1\n")
    (tmp_path / "tests").mkdir()
    names = ["test_stateful_sync_cleanup", "test_stateful_async_cleanup"]
    (tmp_path / "tests/test_backend.py").write_text(
        "from backend import execute\n"
        + "\n".join(f"def {name}(): assert execute() == 1" for name in names)
        + "\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        task = "Inspect stateful cleanup in backend.py"
        baseline = codemap.tasks.verification_relevance(task)
        packet = codemap.tasks.evidence(task)
    row = assert_object(
        next(
            row
            for row in packet["verification"]["relevance"]["candidates"]
            if row["path"] == "tests/test_backend.py"
        )
    )
    assert row["test_symbol"] is None
    context = assert_object(row.get("test_declarations"))
    declarations = assert_records(context["declarations"])
    assert {item["symbol"] for item in declarations} == set(names)
    assert context["source_revision"] == row["test_revision"]
    assert context["coverage"] == "incomplete"
    assert context["verification_selection_authority"] is False
    assert context["negative_evidence_admissible"] is False
    assert packet["verification"]["relevance"]["selected"] == baseline["selected"]
    assert packet["verification"]["relevance"]["selection_changed"] is False


def test_declared_test_scouts_preserve_the_bound_and_omitted_ties(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend.py").write_text("def execute(): return 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_backend.py").write_text(
        "from backend import execute\n"
        + "".join(
            f"def test_stateful_cleanup_{index}(): assert execute() == 1\n"
            for index in range(8)
        )
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence("Inspect stateful cleanup in backend.py")
        initial = decode_initial_packet(
            codemap.tasks.evidence(
                "Inspect stateful cleanup in backend.py", result_mode="initial"
            )
        )
    row = assert_object(packet["verification"]["relevance"]["candidates"][0])
    context = assert_object(row.get("test_declarations"))
    assert row["test_symbol"] is None
    assert context["observed"] == 8
    assert context["returned"] == context["bound"] == 3
    assert context["omitted"] == 5
    assert context["coverage"] == "incomplete"
    relevance = initial["verification"]["relevance"]
    rows = decode_initial_collection(
        relevance["candidates"], relevance["candidates_encoding"]
    )
    assert rows[0]["test_symbol"] is None
    assert rows[0]["test_declarations"] == context


def test_common_name_families_cannot_hide_more_specific_late_test_declarations(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend.py").write_text("def execute(): return 1\n")
    (tmp_path / "tests").mkdir()
    expected = {"test_bound_async_method", "test_bound_sync_method"}
    (tmp_path / "tests/test_backend.py").write_text(
        "from backend import execute\n"
        + "".join(
            f"def test_callable_instance_{index}(): assert execute() == 1\n"
            for index in range(8)
        )
        + "".join(f"def {name}(): assert execute() == 1\n" for name in sorted(expected))
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence(
            "Inspect bound methods classified as callable instances in backend.py"
        )
    row = assert_object(packet["verification"]["relevance"]["candidates"][0])
    context = assert_object(row.get("test_declarations"))
    assert expected <= {
        item["symbol"] for item in assert_records(context["declarations"])
    }
    assert row["test_symbol"] is None
    assert context["observed"] == 10
    assert context["returned"] == 3
    assert context["omitted"] == 7
    assert context["verification_selection_authority"] is False


def test_denied_test_declarations_are_not_disclosed(tmp_path: Path) -> None:
    (tmp_path / "backend.py").write_text("def execute(): return 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_backend.py").write_text(
        "from backend import execute\n"
        "def test_stateful_cleanup_secret_a(): assert execute() == 1\n"
        "def test_stateful_cleanup_secret_b(): assert execute() == 1\n"
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "tests/**"\nvisibility = "deny"\n'
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence("Inspect stateful cleanup in backend.py")
    assert "test_stateful_cleanup_secret" not in str(packet)


def test_reopened_test_declarations_bind_the_new_file_revision(tmp_path: Path) -> None:
    from hashmarks.digest import FILE_DOMAIN, hash_file

    (tmp_path / "backend.py").write_text("def execute(): return 1\n")
    (tmp_path / "tests").mkdir()
    file = tmp_path / "tests/test_backend.py"
    file.write_text(
        "from backend import execute\n"
        "def test_stateful_cleanup_a(): assert execute() == 1\n"
        "def test_stateful_cleanup_b(): assert execute() == 1\n"
    )
    task = "Inspect stateful cleanup in backend.py"
    state = tmp_path / ".hashmarks/state"
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.index.sync()
        before = codemap.tasks.evidence(task)
    old_revision = hash_file(file, domain=FILE_DOMAIN).hash
    file.write_text(file.read_text().replace("cleanup_a", "cleanup_new"))
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.index.sync()
        after = codemap.tasks.evidence(task)
    old_row = assert_object(before["verification"]["relevance"]["candidates"][0])
    new_row = assert_object(after["verification"]["relevance"]["candidates"][0])
    assert (
        assert_object(old_row["test_declarations"])["source_revision"] == old_revision
    )
    context = assert_object(new_row["test_declarations"])
    assert context["source_revision"] == hash_file(file, domain=FILE_DOMAIN).hash
    assert context["source_revision"] != old_revision
    assert {item["symbol"] for item in assert_records(context["declarations"])} == {
        "test_stateful_cleanup_new",
        "test_stateful_cleanup_b",
    }


def test_selected_name_does_not_hide_a_distinct_problem_test_declaration(
    tmp_path: Path,
) -> None:
    (tmp_path / "engine.py").write_text("def encode(value): return value\n")
    (tmp_path / "tests").mkdir()
    path = "tests/test_engine.py"
    (tmp_path / path).write_text(
        "from engine import encode\n"
        "def test_engine_response_message_options(): assert encode(1) == 1\n"
        "def test_null_tombstone(): assert encode(None) is None\n"
    )
    task = "A null tombstone loses response message options. Inspect engine.py."
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        baseline = repository.tasks.verification_relevance(task)
        packet = repository.tasks.evidence(task)
        initial = decode_initial_packet(
            repository.tasks.evidence(task, result_mode="initial")
        )
    relevance = packet["verification"]["relevance"]
    candidate = next(row for row in relevance["candidates"] if row["path"] == path)
    assert candidate.get("test_symbol") == "test_engine_response_message_options"
    context = assert_object(candidate.get("test_declarations"))
    assert "test_null_tombstone" in {
        row["symbol"] for row in assert_records(context["declarations"])
    }
    assert context["coverage"] == "incomplete"
    assert context["verification_selection_authority"] is False
    assert context["negative_evidence_admissible"] is False
    assert relevance["selected"] == baseline["selected"]
    assert relevance["selection_changed"] is False
    initial_relevance = initial["verification"]["relevance"]
    rows = decode_initial_collection(
        initial_relevance["candidates"], initial_relevance["candidates_encoding"]
    )
    assert (
        next(row for row in rows if row["path"] == path)["test_declarations"] == context
    )
