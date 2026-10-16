"""Verifier uncertainty and independently established edit identity stay distinct."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_object

from hashmarks.cli import main
from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_contract import (
    read_initial_projection,
    read_task_action_map,
    read_task_evidence,
)
from hashmarks.codemap.task_evidence_initial import decode_initial_packet
from hashmarks.mcp_surface import HashmarksMcpSurface

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
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
        codemap.sync()
        action = codemap.task_action_map(_TASK)
        packet = codemap.task_evidence(_TASK)
        graph = codemap.verification_ownership_graph(_TASK)

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
        codemap.sync()
        narrow = codemap.verification_relevance(_TASK, candidate_limit=1)
        wide = codemap.verification_relevance(_TASK, candidate_limit=16)

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
        codemap.sync()
        packet = codemap.task_evidence(_TASK)
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
        codemap.sync()
        original = codemap._verification_relevance

        def without_scope(
            task: str,
            *,
            edit: Mapping[str, object] | None,
            current_verify: Mapping[str, object] | None,
            rows: Sequence[Mapping[str, object]],
            limit: int,
        ) -> VerificationRelevance:
            result = original(
                task, edit=edit, current_verify=current_verify, rows=rows, limit=limit
            )
            result.pop("verifier_identity_ambiguous")
            return result

        monkeypatch.setattr(codemap, "_verification_relevance", without_scope)
        action = codemap.task_action_map(_TASK)
    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "unresolved-qualified-import-identity"
    assert read_task_action_map(json.loads(json.dumps(action))) == action


def test_identity_scope_survives_python_cli_mcp_and_initial_projection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _repository(tmp_path)
    state = tmp_path / ".hashmarks"
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.sync()
        packet = codemap.task_evidence(_TASK)
        initial = codemap.task_evidence(_TASK, result_mode="initial")
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
