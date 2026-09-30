from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.mcp_surface import HashmarksMcpSurface


def _fixture(root: Path, language: str) -> tuple[Path, str, str, str]:
    repo = root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    if language == "python":
        (repo / "src" / "active.py").write_text(
            "def pulse_gate():\n    return 1\n", encoding="utf-8"
        )
        (repo / "src" / "decoy.py").write_text(
            "def pulse_gate():\n    return 2\n", encoding="utf-8"
        )
        (repo / "tests" / "test_active.py").write_text(
            "from src.active import pulse_gate\n"
            "def test_pulse_gate():\n    assert pulse_gate() == 1\n",
            encoding="utf-8",
        )
        return (
            repo,
            "Change pulse_gate implementation and verify it",
            "active.py",
            "tests/test_active.py",
        )

    (repo / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
    (repo / "src" / "active.ts").write_text(
        "export function PulseGate(){return 1}\n", encoding="utf-8"
    )
    (repo / "src" / "decoy.ts").write_text(
        "export function PulseGate(){return 2}\n", encoding="utf-8"
    )
    (repo / "tests" / "active.test.ts").write_text(
        'import { PulseGate } from "../src/active.js"; void PulseGate();\n',
        encoding="utf-8",
    )
    return (
        repo,
        "Change PulseGate implementation and verify it",
        "active.ts",
        "tests/active.test.ts",
    )


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_real_owner_and_verifier_converge_across_bounds_and_mcp(
    tmp_path: Path, language: str
) -> None:
    repo, task, owner_name, verifier = _fixture(tmp_path, language)
    state = tmp_path / "state"
    owner = f"src/{owner_name}"

    with CodeMap(
        repo, state_dir=state, artifact_db=state / "artifacts.sqlite3"
    ) as codemap:
        codemap.sync()
        wide = codemap.task_action_map(task, limit=20)
        narrow = codemap.task_action_map(task, limit=1)
        evidence = codemap.task_evidence(task, limit=20, token_budget=64)
        brief = codemap.task_action_brief(task, limit=20, token_budget=64)

    assert wide["admitted_edit"]["path"] == owner
    assert wide["verify"]["path"] == verifier
    assert narrow["ownership_authority"]["resolved_owner"] == owner
    proof = wide["ownership_authority"]["authority_proof_identity"]
    assert narrow["ownership_authority"]["authority_proof_identity"] == proof
    assert evidence["ownership"]["authority_proof_identity"] == proof
    assert brief["edit"] == owner

    surface = HashmarksMcpSurface(str(repo), state_dir=str(state))
    try:
        mcp = surface.task_evidence(task, limit=20, token_budget=64)
    finally:
        surface.close()
    assert mcp["ownership"]["authority_proof_identity"] == proof
    assert mcp["ownership"]["owner"]["path"] == owner


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_removed_import_anchor_cannot_leave_a_unique_owner_after_reopen(
    tmp_path: Path, language: str
) -> None:
    repo, task, owner_name, _verifier = _fixture(tmp_path, language)
    state = tmp_path / "state"
    artifact = state / "artifacts.sqlite3"

    with CodeMap(repo, state_dir=state, artifact_db=artifact) as codemap:
        codemap.sync()
        before = codemap.task_action_map(task, limit=20)
        assert before["ownership_authority"]["resolved_owner"] == f"src/{owner_name}"

        (repo / "src" / owner_name).rename(
            repo / "src" / f"moved.{owner_name.rsplit('.', 1)[1]}"
        )
        codemap.sync()
        changed = codemap.task_action_map(task, limit=20)

    assert changed["admitted_edit"] is None
    assert changed["ownership_authority"]["owner_resolved"] is False

    with CodeMap(repo, state_dir=state, artifact_db=artifact) as reopened:
        bounded = reopened.task_action_map(task, limit=1)
    assert bounded["admitted_edit"] is None
    assert bounded["ownership_authority"]["owner_resolved"] is False


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_bounded_ambiguous_exact_symbol_stays_unresolved_in_mcp(
    tmp_path: Path, language: str
) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    if language == "python":
        name, source, task = (
            "pulse_gate.py",
            "def pulse_gate():\n    return 1\n",
            "Change pulse_gate implementation",
        )
    else:
        name, source, task = (
            "PulseGate.ts",
            "export function PulseGate(){return 1}\n",
            "Change PulseGate implementation",
        )
    for side in ("left", "right"):
        (repo / "src" / f"{side}_{name}").write_text(source, encoding="utf-8")
    state = tmp_path / "state"

    with CodeMap(repo, state_dir=state) as codemap:
        codemap.sync()
        wide = codemap.task_action_map(task, limit=20)
        narrow = codemap.task_action_map(task, limit=1)

    for action in (wide, narrow):
        assert action["admitted_edit"] is None
        assert action["ownership_authority"]["owner_resolved"] is False
        assert action["ambiguity"]["ambiguous"] is True

    surface = HashmarksMcpSurface(str(repo), state_dir=str(state))
    try:
        mcp = surface.task_evidence(task, limit=1, token_budget=64)
    finally:
        surface.close()
    assert mcp["ownership"]["status"] != "resolved"
    assert mcp["ownership"]["owner"] is None


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_wording_and_non_edit_intent_do_not_change_repository_owner_proof(
    tmp_path: Path, language: str
) -> None:
    repo, task, owner_name, _verifier = _fixture(tmp_path, language)
    symbol = "pulse_gate" if language == "python" else "PulseGate"
    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        change = codemap.task_action_map(task, limit=20)
        inspect = codemap.task_action_map(
            f"Investigate {symbol} without editing any files", limit=1
        )

    assert inspect["ownership_authority"]["resolved_owner"] == f"src/{owner_name}"
    assert (
        inspect["ownership_authority"]["authority_proof_identity"]
        == change["ownership_authority"]["authority_proof_identity"]
    )
    assert inspect["ownership_authority"]["consumer_action"] == "external"


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_exact_owner_uses_its_own_importing_test_as_verifier(
    tmp_path: Path, language: str
) -> None:
    repo, _task, owner_name, _verifier = _fixture(tmp_path, language)
    if language == "python":
        (repo / "tests" / "test_decoy.py").write_text(
            "from src.decoy import pulse_gate\n"
            "def test_pulse_gate():\n    assert pulse_gate() == 2\n",
            encoding="utf-8",
        )
        symbol = "pulse_gate"
        decoy_test = "tests/test_decoy.py"
    else:
        (repo / "tests" / "decoy.test.ts").write_text(
            'import { PulseGate } from "../src/decoy.js"; void PulseGate();\n',
            encoding="utf-8",
        )
        symbol = "PulseGate"
        decoy_test = "tests/decoy.test.ts"
    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        active = codemap.task_action_map(
            f"Change src.active.{symbol} implementation and verify it", limit=20
        )
        decoy = codemap.task_action_map(
            f"Change src.decoy.{symbol} implementation and verify it", limit=20
        )

    assert active["admitted_edit"]["path"] == f"src/{owner_name}"
    assert active["verify"]["path"].startswith("tests/")
    assert active["verify"]["path"] != decoy_test
    assert decoy["admitted_edit"]["path"].startswith("src/decoy.")
    assert decoy["verify"]["path"] == decoy_test


def test_typescript_generic_function_is_an_exact_owner(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "result.ts").write_text(
        "export function withRefreshOutcome<Value>(\n"
        "  value: Value\n"
        "): Value {\n"
        "  return value;\n"
        "}\n",
        encoding="utf-8",
    )
    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        action = codemap.task_action_map("Fix withRefreshOutcome", limit=1)

    assert action["admitted_edit"]["path"] == "src/result.ts"
    assert action["admitted_edit"]["name"] == "withRefreshOutcome"


def test_typescript_overload_signatures_share_the_implementation_owner(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "encoding.ts").write_text(
        "export function encodePayload(value: object): object;\n"
        "export function encodePayload(value: unknown): unknown;\n"
        "export function encodePayload(value: unknown): unknown {\n"
        "  return value;\n"
        "}\n",
        encoding="utf-8",
    )
    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        action = codemap.task_action_map("Fix encodePayload", limit=1)

    assert action["admitted_edit"]["path"] == "src/encoding.ts"
    assert action["admitted_edit"]["name"] == "encodePayload"


def test_typescript_overload_does_not_cross_a_scope_boundary(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "encoding.ts").write_text(
        "namespace Contract {\n"
        "  export function encodePayload(value: object): object;\n"
        "}\n"
        "export function encodePayload(value: unknown): unknown {\n"
        "  return value;\n"
        "}\n",
        encoding="utf-8",
    )
    with CodeMap(repo, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        outline = codemap.outline("src/encoding.ts")
        action = codemap.task_action_map("Fix encodePayload", limit=1)

    assert (
        len([row for row in outline["symbols"] if row["name"] == "encodePayload"]) == 2
    )
    assert action["admitted_edit"] is None
