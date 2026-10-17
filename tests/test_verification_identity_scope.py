"""Verifier uncertainty and independently established edit identity stay distinct."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_object

from hashmarks.cli import main
from hashmarks.codemap import CodeMap
from hashmarks.codemap.service import CodeMapServiceClient
from hashmarks.codemap.task_evidence_contract import (
    read_initial_projection,
    read_task_action_map,
    read_task_evidence,
)
from hashmarks.codemap.task_evidence_initial import decode_initial_packet
from hashmarks.codemap.verification_relevance_model import VerificationRequest
from hashmarks.mcp_surface import HashmarksMcpSurface

if TYPE_CHECKING:
    from pathlib import Path

    from hashmarks.codemap.task_evidence_types import VerificationRelevance

_TASK = "Change EntryCatalog.entries_beneath in catalog.py"


def _repository(root: Path, *, unknown_verifier: bool = False) -> None:
    (root / "catalog.py").write_text(
        "class EntryCatalog:\n"
        "    def entries_beneath(self, prefix):\n"
        "        return [entry for entry in self.entries if entry.startswith(prefix)]\n",
        encoding="utf-8",
    )
    # These dynamic receivers cannot be qualified as calls to EntryCatalog.
    # They still limit proof of indirect verification correspondence.
    for index in range(9):
        (root / f"query_{index}.py").write_text(
            "def query(catalog, prefix):\n    return catalog.entries_beneath(prefix)\n",
            encoding="utf-8",
        )
    (root / "tests").mkdir()
    (root / "tests/test_catalog.py").write_text(
        "from catalog import EntryCatalog\n"
        "def test_catalog():\n"
        "    EntryCatalog.entries_beneath(None, 'a')\n",
        encoding="utf-8",
    )
    if unknown_verifier:
        (root / "tests/test_unknown.py").write_text(
            "def test_unknown(catalog):\n    catalog.entries_beneath('a')\n",
            encoding="utf-8",
        )


@pytest.mark.parametrize("unknown_verifier", [False, True])
def test_only_unresolved_verifiers_veto_an_independent_owner(
    tmp_path: Path, unknown_verifier: bool
) -> None:
    _repository(tmp_path, unknown_verifier=unknown_verifier)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(_TASK)
        packet = codemap.tasks.evidence(_TASK)
        graph = codemap.tasks.verification_ownership_graph(_TASK)

    relevance = action["verification_relevance"]
    assert relevance.get("qualified_identity_ambiguous") is True
    assert relevance.get("verifier_identity_ambiguous") is unknown_verifier
    assert relevance.get("negative_evidence_admissible") is False
    assert "unresolved_reference_identity_paths" in relevance
    assert "query_0.py" in relevance["unresolved_reference_identity_paths"]
    assert "unique" not in relevance["selection_reason"]
    verifier = next(
        row for row in relevance["candidates"] if row["path"] == "tests/test_catalog.py"
    )
    assert verifier.get("direct_reference") is True
    assert not any(row.get("indirect_reference") for row in relevance["candidates"])
    assert action["ambiguity"]["ambiguous"] is unknown_verifier
    assert action["edit"] is not None
    assert action["edit"]["path"] == "catalog.py"
    assert packet["ownership"]["status"] == (
        "ambiguous" if unknown_verifier else "resolved"
    )
    qualification = assert_object(graph["verification_qualification"])
    assert qualification["qualified_identity_ambiguous"] is True
    assert qualification["verifier_identity_ambiguous"] is unknown_verifier
    assert qualification["negative_evidence_admissible"] is False


@pytest.mark.parametrize("unknown_verifier", [False, True])
def test_identity_scope_is_qualified_before_path_and_candidate_projection(
    tmp_path: Path, unknown_verifier: bool
) -> None:
    _repository(tmp_path, unknown_verifier=unknown_verifier)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        narrow = codemap.tasks.verification_relevance(_TASK, candidate_limit=1)
        wide = codemap.tasks.verification_relevance(_TASK, candidate_limit=16)

    for result in (narrow, wide):
        assert result.get("qualified_identity_ambiguous") is True
        assert result.get("verifier_identity_ambiguous") is unknown_verifier
        assert result.get("negative_evidence_admissible") is False
        assert "unique" not in result["selection_reason"]
    assert "unresolved_reference_identity_paths" in narrow
    assert "unresolved_reference_identity_omitted_paths" in narrow
    assert narrow["unresolved_reference_identity_paths"] == [
        f"query_{index}.py" for index in range(8)
    ]
    assert narrow["unresolved_reference_identity_omitted_paths"] > 0
    if unknown_verifier:
        # The uncertain verifier is beyond the internal path disclosure bound,
        # yet still contributes to qualification at either candidate limit.
        assert (
            "tests/test_unknown.py" not in narrow["unresolved_reference_identity_paths"]
        )


def test_unresolved_production_references_do_not_prove_verifier_absence(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    (tmp_path / "tests/test_catalog.py").unlink()
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence(_TASK)
    relevance = packet["verification"]["relevance"]
    assert relevance["selected"] is None
    assert relevance["candidates"] == []
    assert relevance.get("qualified_identity_ambiguous") is True
    assert relevance.get("verifier_identity_ambiguous") is False
    assert relevance.get("negative_evidence_admissible") is False
    assert relevance["selection_reason"] != "no-verification-candidate"
    assert packet["ownership"]["status"] == "resolved"


def test_missing_scoped_qualification_keeps_the_aggregate_veto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        original = codemap.verification.for_owner

        def without_scope(
            request: VerificationRequest, *, limit: int
        ) -> VerificationRelevance:
            result = original(request, limit=limit)
            result.pop("verifier_identity_ambiguous")
            return result

        monkeypatch.setattr(codemap.verification, "for_owner", without_scope)
        action = codemap.tasks.action_map(_TASK)
    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "unresolved-qualified-import-identity"
    assert read_task_action_map(json.loads(json.dumps(action))) == action


def test_identity_scope_survives_python_cli_mcp_and_initial_projection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _repository(tmp_path)
    state = tmp_path / ".hashmarks"
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence(_TASK)
        initial = codemap.tasks.evidence(_TASK, result_mode="initial")
    surface = HashmarksMcpSurface(str(tmp_path), state_dir=str(state))
    try:
        mcp = surface.task_evidence(_TASK)
    finally:
        surface.close()
    assert main(["--workspace", str(tmp_path), "task-evidence", _TASK]) == 0
    cli = read_task_evidence(json.loads(capsys.readouterr().out))
    decoded = read_initial_projection(decode_initial_packet(initial))
    for result in (packet, cli, mcp, decoded):
        relevance = result["verification"]["relevance"]
        assert relevance.get("qualified_identity_ambiguous") is True
        assert relevance.get("verifier_identity_ambiguous") is False
        assert relevance.get("negative_evidence_admissible") is False
        assert result["ownership"]["status"] == "resolved"
        assert result["ownership"]["owner"] is not None
        assert result["ownership"]["owner"]["path"] == "catalog.py"
    assert cli["verification"]["relevance"] == packet["verification"]["relevance"]
    assert mcp == packet


def _competing_repository(root: Path) -> str:
    (root / "alpha.py").write_text(
        "def write_cache_block(value):\n    return value\n", encoding="utf-8"
    )
    (root / "beta.py").write_text(
        "def write_cache_entry(value):\n    return value + 1\n", encoding="utf-8"
    )
    return "Change write_cache behavior"


@pytest.mark.parametrize("limit", [3, 20])
def test_unresolved_caller_cannot_clear_competing_owner_ambiguity(
    tmp_path: Path, limit: int
) -> None:
    task = _competing_repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.tasks.action_map(task, limit=limit)
        (tmp_path / "forward.py").write_text(
            "def forward(cache, value):\n    return cache.write_cache_block(value)\n",
            encoding="utf-8",
        )
        codemap.index.sync()
        after = codemap.tasks.action_map(task, limit=limit)
        packet = codemap.tasks.evidence(task, limit=limit)
    for action in (before, after):
        assert action["ambiguity"]["ambiguous"] is True
        assert action["ambiguity"]["reason"] == "multiple-identifier-edit-owners"
        assert action["ownership_authority"]["owner_resolved"] is False
        assert action["admitted_edit"] is None
    relevance = after["verification_relevance"]
    assert relevance.get("qualified_identity_ambiguous") is True
    assert relevance.get("verifier_identity_ambiguous") is False
    assert relevance.get("negative_evidence_admissible") is False
    assert packet["ownership"]["status"] == "ambiguous"
    assert packet["ownership"]["owner"] is None
    assert packet["ownership"]["source_evidence"] is None


@pytest.mark.parametrize("limit", [1, 3, 20])
def test_unproven_candidate_never_becomes_resolved_owner_source(
    tmp_path: Path, limit: int
) -> None:
    task = _competing_repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(task, limit=limit)
        packet = codemap.tasks.evidence(task, limit=limit)
    authority = action["ownership_authority"]
    assert authority["owner_resolved"] is False
    assert authority["proof_complete"] is False
    assert authority["status"] == ("unresolved" if limit == 1 else "ambiguous")
    assert packet["ownership"]["status"] == authority["status"]
    assert packet["ownership"]["proof_scope_complete"] is False
    assert packet["ownership"]["owner"] is None
    assert packet["ownership"]["source_evidence"] is None
    assert packet["ownership"]["candidate"] is not None
    assert packet["ownership"]["candidate"]["path"] == "alpha.py"


def test_unresolved_owner_survives_all_existing_packet_delivery_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _competing_repository(tmp_path)
    state = tmp_path / ".hashmarks"
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.index.sync()
        packet = codemap.tasks.evidence(task, limit=1)
        initial = codemap.tasks.evidence(task, limit=1, result_mode="initial")
    surface = HashmarksMcpSurface(str(tmp_path), state_dir=str(state))
    try:
        mcp = surface.task_evidence(task, limit=1)
    finally:
        surface.close()
    assert (
        main(["--workspace", str(tmp_path), "task-evidence", task, "--limit", "1"]) == 0
    )
    cli = read_task_evidence(json.loads(capsys.readouterr().out))

    def request(operation: str, **payload: object) -> dict[str, object]:
        assert operation == "task_evidence"
        assert payload["limit"] == 1
        return {"task_evidence": json.loads(json.dumps(packet))}

    client = CodeMapServiceClient(tmp_path)
    monkeypatch.setattr(client, "request", request)
    service = client.task_evidence(task, limit=1)
    decoded = read_initial_projection(decode_initial_packet(initial))
    for result in (packet, cli, mcp, service, decoded):
        assert result["ownership"]["status"] == "unresolved"
        assert result["ownership"]["owner"] is None
        assert result["ownership"]["source_evidence"] is None
        assert result["ownership"]["proof_scope_complete"] is False
        assert result["ownership"]["candidate"] is not None
        assert result["ownership"]["candidate"]["path"] == "alpha.py"
    assert service == packet
    assert mcp == packet
