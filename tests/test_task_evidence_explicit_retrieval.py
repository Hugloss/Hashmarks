"""Requested declarations stay visible without gaining edit authority."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_object

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_contract import (
    read_initial_projection,
    read_task_evidence,
)
from hashmarks.codemap.task_evidence_initial import decode_initial_packet
from scripts.repository_evaluation.backend_transport import capture_cli, capture_mcp

if TYPE_CHECKING:
    from pathlib import Path


_TASK = (
    "Inspect whether DeliveryStream.close nacks deliveries from another consumer "
    "subscription. Source: transport.py"
)


def _repository(root: Path) -> None:
    (root / "transport.py").write_text(
        "class DeliveryStream:\n"
        "    async def close(self):\n"
        "        return None\n"
        "    async def receive(self):\n"
        "        return None\n"
    )
    (root / "tests").mkdir()
    for index in range(12):
        (root / f"tests/test_subscription_delivery_{index:02}.py").write_text(
            "# Inspect consumer subscription delivery messages and nack close scope\n"
            f"def test_consumer_subscription_delivery_{index}(): assert True\n"
        )


@pytest.mark.parametrize("limit", [1, 3, 20])
def test_requested_declaration_precedes_weaker_hits_without_changing_ownership(
    tmp_path: Path, limit: int
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(_TASK, limit=limit)
        packet = codemap.tasks.evidence(_TASK, limit=limit)
        initial = read_initial_projection(
            decode_initial_packet(
                codemap.tasks.evidence(_TASK, limit=limit, result_mode="initial")
            )
        )
    for response in (packet, initial):
        first = response["retrieval"]["results"][0]
        assert first["path"] == "transport.py"
        assert first.get("symbol") == "DeliveryStream.close"
        assert first.get("start_line") == 2
        assert response["retrieval"]["ownership_authority"] is False
        assert len(response["retrieval"]["results"]) <= limit
        owner = response["ownership"]["owner"]
        admitted = action["admitted_edit"]
        assert owner is not None and admitted is not None
        for key in ("path", "qualname", "start_line", "end_line"):
            assert owner.get(key) == admitted.get(key)
        assert (
            response["ownership"]["authority_proof_identity"]
            == action["ownership_authority"]["authority_proof_identity"]
        )
        assert (
            response["ownership"]["ambiguity"]["ambiguous"]
            == action["ambiguity"]["ambiguous"]
        )


def test_literal_path_keeps_a_same_named_declaration_from_displacing_the_target(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    (tmp_path / "alternative.py").write_text(
        "class DeliveryStream:\n    async def close(self): return None\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(_TASK)
        packet = codemap.tasks.evidence(_TASK)
    first = packet["retrieval"]["results"][0]
    assert first["path"] == "transport.py"
    assert first.get("symbol") == "DeliveryStream.close"
    assert packet["ownership"]["owner"] == action["admitted_edit"]
    assert packet["ownership"]["ambiguity"] == action["ambiguity"]


def test_duplicate_qualified_targets_keep_both_locators_and_owner_ambiguity(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    (tmp_path / "alternative.py").write_text(
        "class DeliveryStream:\n    async def close(self): return None\n"
    )
    task = "Inspect DeliveryStream.close declarations"
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(task)
        packet = codemap.tasks.evidence(task)
    rows = packet["retrieval"]["results"][:2]
    assert {row["path"] for row in rows} == {"transport.py", "alternative.py"}
    assert all(row.get("symbol") == "DeliveryStream.close" for row in rows)
    assert packet["ownership"]["owner"] is None
    assert packet["ownership"]["ambiguity"] == action["ambiguity"]


def test_denied_requested_target_is_not_disclosed_by_ordering(tmp_path: Path) -> None:
    _repository(tmp_path)
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "transport.py"\nvisibility = "deny"\n'
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence(_TASK)
    assert all(row["path"] != "transport.py" for row in packet["retrieval"]["results"])
    assert packet["ownership"]["owner"] is None


@pytest.mark.parametrize("limit", [1, 3, 20])
def test_resolved_file_without_named_declaration_survives_saturated_retrieval(
    tmp_path: Path,
    limit: int,
) -> None:
    (tmp_path / "app.py").write_text(
        "class Dispatcher:\n    def install(self): return 1\n"
    )
    (tmp_path / "tests").mkdir()
    for index in range(30):
        (tmp_path / f"tests/test_noise_{index}.py").write_text(
            "from app import Dispatcher\n"
            "def test_handler_registration_paths(): return Dispatcher().install()\n"
        )
    task = "Handler registration hooks repeat for multiple paths in app.py."
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        action = repository.tasks.action_map(task, limit=limit)
        packet = repository.tasks.evidence(task, limit=limit)
        initial = read_initial_projection(
            decode_initial_packet(
                repository.tasks.evidence(task, limit=limit, result_mode="initial")
            )
        )
    for observed in (packet, initial):
        assert observed["explicit_target"]["status"] == "resolved"
        assert observed["explicit_target"]["path"] == "app.py"
        rows = observed["retrieval"]["results"]
        assert rows[0]["path"] == "app.py"
        assert not rows[0].get("symbol")
        assert not rows[0].get("start_line")
        assert len(rows) <= limit
        assert observed["retrieval"]["ownership_authority"] is False
        assert observed["ownership"]["owner"] == action["admitted_edit"]
        assert (
            observed["ownership"]["authority_proof_identity"]
            == action["ownership_authority"]["authority_proof_identity"]
        )
        assert observed["verification"]["selected"] is not None
        assert action["verify"] is not None
        assert observed["verification"]["selected"]["path"] == action["verify"]["path"]


@pytest.mark.parametrize("visibility", ["deny", "outline"])
def test_literal_file_fallback_respects_source_visibility(
    tmp_path: Path,
    visibility: str,
) -> None:
    (tmp_path / "app.py").write_text(
        "class Dispatcher:\n    def install(self): return 'DO_NOT_DISCLOSE_BODY'\n"
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        f"[[rule]]\npattern='app.py'\nvisibility='{visibility}'\n"
    )
    (tmp_path / "noise.py").write_text("def handler_registration_paths(): return 1\n")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence(
            "Handler registration hooks repeat for multiple paths in app.py."
        )
    assert "DO_NOT_DISCLOSE_BODY" not in str(packet)
    rows = packet["retrieval"]["results"]
    if visibility == "deny":
        assert all(row["path"] != "app.py" for row in rows)
    else:
        assert rows[0]["path"] == "app.py"
        assert rows[0].get("evidence_visibility") == "outline"
        assert not rows[0].get("symbol")


@pytest.mark.parametrize("result_mode", ["default", "initial"])
def test_literal_path_precedes_same_named_methods_without_unique_ownership(
    tmp_path: Path, result_mode: str
) -> None:
    (tmp_path / "repository").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "repository/z_async.py").write_text(
        "class BatchRepository:\n"
        "    async def delete_many(self, values): return values\n"
    )
    for index in range(12):
        (tmp_path / f"repository/other_{index:02}.py").write_text(
            f"class OtherRepository{index}:\n"
            "    def delete_many(self, values): return values\n"
        )
        (tmp_path / f"tests/test_get_session_data_async_{index:02}.py").write_text(
            "# declared chunk sizing persistence batches data repository\n"
            "def get_session_data_async(repository): return repository.delete_many([])\n"
        )
    task = (
        "Inspect declared chunk sizing for delete_many persistence batches "
        "in BatchRepository. Source: repository/z_async.py"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(task)
        packet = codemap.tasks.evidence(task, result_mode=result_mode)
    observed = (
        read_initial_projection(decode_initial_packet(packet))
        if result_mode == "initial"
        else read_task_evidence(packet)
    )
    assert observed["explicit_target"]["path"] == "repository/z_async.py"
    assert observed["retrieval"]["results"][0]["path"] == "repository/z_async.py"
    assert observed["retrieval"]["ownership_authority"] is False
    assert observed["ownership"]["owner"] is None
    assert action["admitted_edit"] is None
    assert (
        observed["ownership"]["authority_proof_identity"]
        == action["ownership_authority"]["authority_proof_identity"]
    )


def _check_initial_transport(root: Path, transport: str, ambiguous: bool) -> None:
    _repository(root)
    task = _TASK
    if ambiguous:
        (root / "alternative.py").write_text(
            "class DeliveryStream:\n    async def close(self): return None\n"
        )
        task = "Inspect DeliveryStream.close declarations"
    state = root / ".hashmarks"
    with CodeMap(root, state_dir=state) as codemap:
        codemap.index.sync()
        expected = read_initial_projection(
            decode_initial_packet(
                codemap.tasks.evidence(task, limit=3, result_mode="initial")
            )
        )
    capture = capture_cli if transport == "cli" else capture_mcp
    for row in capture(
        root,
        state,
        {
            "operation": "task_evidence",
            "inputs": {"task": task, "limit": 3, "result_mode": "initial"},
        },
    ):
        response = assert_object(row["response"])
        actual = read_initial_projection(
            decode_initial_packet(assert_object(response.get("result", response)))
        )
        assert actual["retrieval"]["results"] == expected["retrieval"]["results"]
        assert (
            actual["ownership"]["authority_proof_identity"]
            == expected["ownership"]["authority_proof_identity"]
        )
        assert actual["ownership"]["ambiguity"] == expected["ownership"]["ambiguity"]
        assert actual["retrieval"]["ownership_authority"] is False
        if ambiguous:
            assert actual["ownership"]["owner"] is None


@pytest.mark.parametrize("ambiguous", [False, True])
def test_cli_preserves_requested_locators_and_ownership_uncertainty(
    tmp_path: Path,
    ambiguous: bool,
) -> None:
    _check_initial_transport(tmp_path, "cli", ambiguous)


@pytest.mark.host_mcp_sdk
@pytest.mark.parametrize("ambiguous", [False, True])
def test_official_mcp_preserves_requested_locators_and_ownership_uncertainty(
    tmp_path: Path,
    ambiguous: bool,
) -> None:
    _check_initial_transport(tmp_path, "mcp", ambiguous)
