from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def _build_repetitive_verification_repo(
    root: Path, distractors: int
) -> tuple[str, str]:
    (root / "packages" / "feature0042" / "tests").mkdir(parents=True)
    (root / "tests" / "regression").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    (root / "packages" / "feature0042" / "service.py").write_text(
        "def apply_policy(value):\n    return value\n"
    )
    expected = "packages/feature0042/tests/test_contract.py"
    (root / expected).write_text(
        "from packages.feature0042.service import apply_policy\n\n"
        "def test_contract():\n    assert apply_policy(1) == 1\n"
    )
    for index in range(distractors):
        path = (
            root
            / "tests"
            / "regression"
            / f"test_apply_policy_feature0042_regression_{index:04d}.py"
        )
        path.write_text(
            "from packages.feature0042.service import apply_policy\n\n"
            "def test_apply_policy_feature0042_regression():\n    assert apply_policy(1) == 1\n"
        )
    return "Fix apply_policy behavior for feature0042", expected


def test_verification_relevance_recovers_local_test_outside_canonical_top20(
    tmp_path: Path,
) -> None:
    task, expected = _build_repetitive_verification_repo(tmp_path, distractors=40)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)
        plan = codemap.verification_plan(
            action["verify"]["path"],
            symbol=action["verify"].get("verification_test_symbol"),
        )

    relevance = action["verification_relevance"]
    assert relevance["current_canonical_verify"].startswith("tests/regression/")
    assert relevance["selection_changed"] is True
    assert relevance["selected"]["path"] == expected
    assert relevance["selected"]["canonical_rank"] is None
    assert (
        relevance["selected"]["selection_reason"]
        == "unique-exact-reference-plus-namespace-locality"
    )
    assert action["verify"]["path"] == expected
    assert action["verify"]["verification_test_symbol"] == "test_contract"
    assert action["discovery_effect"] == "bounded-verification-reference-projection"
    assert plan["argv"][-1] == f"{expected}::test_contract"


def test_verification_relevance_preserves_canonical_choice_when_reference_evidence_ties(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests" / "a").mkdir(parents=True)
    (tmp_path / "tests" / "b").mkdir(parents=True)
    (tmp_path / "src" / "owner.py").write_text("def widget(value):\n    return value\n")
    for name in ("a", "b"):
        (tmp_path / "tests" / name / "test_widget.py").write_text(
            "from src.owner import widget\n\ndef test_widget():\n    assert widget(1) == 1\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("widget implementation test", limit=20)

    relevance = action["verification_relevance"]
    assert relevance["selection_changed"] is False
    assert action["verify"]["path"] == relevance["current_canonical_verify"]
    assert relevance["selection_reason"] == "canonical-verification"
    assert action["discovery_effect"] == "none"


def test_public_verification_relevance_is_bounded(tmp_path: Path) -> None:
    task, expected = _build_repetitive_verification_repo(tmp_path, distractors=30)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relevance = codemap.verification_relevance(task, limit=20, candidate_limit=3)

    assert relevance["schema"] == "hashmarks.verification-relevance.v1"
    assert relevance["selected"]["path"] == expected
    assert len(relevance["candidates"]) == 3
    assert relevance["candidate_count"] == 31
    assert relevance["bounds"]["reverse_refs_per_symbol"] == 1024
    assert relevance["secret_knowledge_used"] is False


def test_unique_indirect_active_verifier_overrides_stale_direct_legacy_decoys(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "tests/contract").mkdir(parents=True)
    (tmp_path / "legacy").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    (tmp_path / "src/case/__init__.py").write_text("")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n"
    )
    (tmp_path / "src/case/engine.py").write_text(
        "def ember_snow(v): return v + '-active'\n"
    )
    (tmp_path / "src/case/api.py").write_text(
        "from .engine import ember_snow\ndef handle(v): return ember_snow(v)\n"
    )
    (tmp_path / "tests/contract/test_public_contract.py").write_text(
        "from src.case.api import handle\ndef test_public_contract(): assert handle('x') == 'x-active'\n"
    )
    (tmp_path / "legacy/ember_snow.py").write_text(
        "def ember_snow(v): return v + '-legacy'\n"
    )
    for index in range(12):
        path = tmp_path / "tests/regression" / f"test_ember_snow_{index:02d}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "from legacy.ember_snow import ember_snow\n"
            "def test_ember_snow_regression(): assert ember_snow('x') == 'x-legacy'\n"
        )

    task = "Fix ember_snow accepted response implementation and verify behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)
        packet = codemap.task_decision_packet(task, limit=20)

    assert action["edit"]["path"] == "src/case/engine.py"
    assert action["verify"]["path"] == "tests/contract/test_public_contract.py"
    assert (
        action["verification_relevance"]["selection_reason"]
        == "unique-bounded-indirect-reference-plus-namespace-locality"
    )
    assert packet["discrimination"]["needed"] is False


def test_reexported_active_symbol_keeps_exact_owner_identity(tmp_path: Path) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "tests/contract").mkdir(parents=True)
    (tmp_path / "legacy").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    (tmp_path / "src/case/__init__.py").write_text("from .engine import ember_snow\n")
    (tmp_path / "src/case/engine.py").write_text(
        "def ember_snow(v): return v + '-active'\n"
    )
    (tmp_path / "tests/contract/test_public_contract.py").write_text(
        "from src.case import ember_snow\ndef test_public_contract(): assert ember_snow('x') == 'x-active'\n"
    )
    (tmp_path / "legacy/ember_snow.py").write_text(
        "def ember_snow(v): return v + '-legacy'\n"
    )
    for index in range(8):
        path = tmp_path / "tests/regression" / f"test_ember_snow_{index:02d}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "from legacy.ember_snow import ember_snow\ndef test_old(): assert ember_snow('x') == 'x-legacy'\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix ember_snow accepted response implementation and verify behavior",
            limit=20,
        )
    assert action["edit"]["path"] == "src/case/engine.py"
    assert action["verify"]["path"] == "tests/contract/test_public_contract.py"


def test_aliased_import_preserves_underlying_owner_identity(tmp_path: Path) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    (tmp_path / "src/case/__init__.py").write_text("")
    (tmp_path / "src/case/engine.py").write_text(
        "def ember_snow(v): return v + '-active'\n"
    )
    (tmp_path / "tests/test_contract.py").write_text(
        "from src.case.engine import ember_snow as active_ember\ndef test_contract(): assert active_ember('x') == 'x-active'\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix ember_snow implementation and verify behavior", limit=20
        )
    assert action["edit"]["path"] == "src/case/engine.py"
    assert action["verify"]["path"] == "tests/test_contract.py"


def test_ambiguous_reexport_does_not_invent_qualified_owner(tmp_path: Path) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    (tmp_path / "src/case/__init__.py").write_text(
        "from .engine_a import ember_snow\nfrom .engine_b import ember_snow\n"
    )
    (tmp_path / "src/case/engine_a.py").write_text(
        "def ember_snow(v): return v + '-a'\n"
    )
    (tmp_path / "src/case/engine_b.py").write_text(
        "def ember_snow(v): return v + '-b'\n"
    )
    (tmp_path / "tests/test_contract.py").write_text(
        "from src.case import ember_snow\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        resolved = codemap._resolve_import_owner_paths(
            "tests/test_contract.py", "src.case.ember_snow"
        )
    assert resolved == ["src/case/__init__.py"]


def test_two_hop_reexport_keeps_unique_underlying_owner_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "tests/contract").mkdir(parents=True)
    (tmp_path / "legacy").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    (tmp_path / "src/case/__init__.py").write_text("from .public import ember_snow\n")
    (tmp_path / "src/case/public.py").write_text("from .engine import ember_snow\n")
    (tmp_path / "src/case/engine.py").write_text(
        "def ember_snow(v): return v + '-active'\n"
    )
    (tmp_path / "tests/contract/test_public_contract.py").write_text(
        "from src.case import ember_snow\ndef test_public_contract(): assert ember_snow('x') == 'x-active'\n"
    )
    (tmp_path / "legacy/ember_snow.py").write_text(
        "def ember_snow(v): return v + '-legacy'\n"
    )
    for index in range(8):
        path = tmp_path / "tests/regression" / f"test_ember_snow_{index:02d}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "from legacy.ember_snow import ember_snow\ndef test_old(): assert ember_snow('x') == 'x-legacy'\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix ember_snow accepted response implementation and verify behavior",
            limit=20,
        )
    assert action["edit"]["path"] == "src/case/engine.py"
    assert action["verify"]["path"] == "tests/contract/test_public_contract.py"


def test_two_hop_alias_chain_keeps_unique_underlying_owner_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "tests/contract").mkdir(parents=True)
    (tmp_path / "legacy").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    (tmp_path / "src/case/__init__.py").write_text(
        "from .public import active_ember as ember_snow\n"
    )
    (tmp_path / "src/case/public.py").write_text(
        "from .engine import ember_snow as active_ember\n"
    )
    (tmp_path / "src/case/engine.py").write_text(
        "def ember_snow(v): return v + '-active'\n"
    )
    (tmp_path / "tests/contract/test_public_contract.py").write_text(
        "from src.case import ember_snow\ndef test_public_contract(): assert ember_snow('x') == 'x-active'\n"
    )
    (tmp_path / "legacy/ember_snow.py").write_text(
        "def ember_snow(v): return v + '-legacy'\n"
    )
    for index in range(8):
        path = tmp_path / "tests/regression" / f"test_ember_snow_{index:02d}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "from legacy.ember_snow import ember_snow\ndef test_old(): assert ember_snow('x') == 'x-legacy'\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix ember_snow accepted response implementation and verify behavior",
            limit=20,
        )
    assert action["edit"]["path"] == "src/case/engine.py"
    assert action["verify"]["path"] == "tests/contract/test_public_contract.py"


def test_star_reexport_keeps_name_scoped_unique_owner_identity(tmp_path: Path) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "tests/contract").mkdir(parents=True)
    (tmp_path / "legacy").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    (tmp_path / "src/case/__init__.py").write_text("from .engine import *\n")
    (tmp_path / "src/case/engine.py").write_text(
        "def ember_snow(v): return v + '-active'\n"
    )
    (tmp_path / "tests/contract/test_public_contract.py").write_text(
        "from src.case import ember_snow\ndef test_public_contract(): assert ember_snow('x') == 'x-active'\n"
    )
    (tmp_path / "legacy/ember_snow.py").write_text(
        "def ember_snow(v): return v + '-legacy'\n"
    )
    for index in range(8):
        path = tmp_path / "tests/regression" / f"test_ember_snow_{index:02d}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "from legacy.ember_snow import ember_snow\ndef test_old(): assert ember_snow('x') == 'x-legacy'\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix ember_snow accepted response implementation and verify behavior",
            limit=20,
        )
    assert action["edit"]["path"] == "src/case/engine.py"
    assert action["verify"]["path"] == "tests/contract/test_public_contract.py"


def test_same_symbol_across_multiple_live_packages_fails_closed_instead_of_archive_fallback(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "src/other").mkdir(parents=True)
    (tmp_path / "tests/case").mkdir(parents=True)
    (tmp_path / "tests/other").mkdir(parents=True)
    (tmp_path / "legacy").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    for package, suffix in (("case", "active"), ("other", "other")):
        (tmp_path / f"src/{package}/__init__.py").write_text(
            "from .engine import ember_snow\n"
        )
        (tmp_path / f"src/{package}/engine.py").write_text(
            f"def ember_snow(v): return v + '-{suffix}'\n"
        )
        (tmp_path / f"tests/{package}/test_contract.py").write_text(
            f"from src.{package} import ember_snow\ndef test_contract(): assert ember_snow('x') == 'x-{suffix}'\n"
        )
    (tmp_path / "legacy/ember_snow.py").write_text(
        "def ember_snow(v): return v + '-legacy'\n"
    )
    for index in range(8):
        path = tmp_path / "tests/regression" / f"test_ember_snow_{index:02d}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "from legacy.ember_snow import ember_snow\ndef test_old(): assert ember_snow('x') == 'x-legacy'\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix ember_snow accepted response implementation and verify behavior",
            limit=20,
        )
        packet = codemap.task_decision_packet(
            "Fix ember_snow accepted response implementation and verify behavior",
            limit=20,
        )
    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] in {
        "multiple-live-owners-behind-archive-hit",
        "multiple-task-local-structural-owners",
    }
    assert packet["discrimination"]["needed"] is True


def test_reexport_chain_beyond_bound_fails_closed_instead_of_stale_verifier(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "tests/contract").mkdir(parents=True)
    (tmp_path / "legacy").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    layers = [f"layer{i}" for i in range(8)]
    (tmp_path / "src/case/__init__.py").write_text(
        f"from .{layers[0]} import ember_snow\n"
    )
    for index, layer in enumerate(layers):
        nxt = layers[index + 1] if index + 1 < len(layers) else "engine"
        (tmp_path / f"src/case/{layer}.py").write_text(
            f"from .{nxt} import ember_snow\n"
        )
    (tmp_path / "src/case/engine.py").write_text(
        "def ember_snow(v): return v + '-active'\n"
    )
    (tmp_path / "tests/contract/test_public_contract.py").write_text(
        "from src.case import ember_snow\ndef test_public_contract(): assert ember_snow('x') == 'x-active'\n"
    )
    (tmp_path / "legacy/ember_snow.py").write_text(
        "def ember_snow(v): return v + '-legacy'\n"
    )
    for index in range(4):
        path = tmp_path / "tests/regression" / f"test_ember_snow_{index:02d}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "from legacy.ember_snow import ember_snow\ndef test_old(): assert ember_snow('x') == 'x-legacy'\n"
        )
    task = "Fix ember_snow accepted response implementation and verify behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)
        packet = codemap.task_decision_packet(task, limit=20)
    assert action["edit"]["path"] == "src/case/engine.py"
    assert action["verification_relevance"]["qualified_identity_ambiguous"] is True
    assert action["ambiguity"]["reason"] == "unresolved-qualified-import-identity"
    assert packet["discrimination"]["needed"] is True


def test_multiple_star_reexports_do_not_invent_unique_owner(tmp_path: Path) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    (tmp_path / "src/case/__init__.py").write_text(
        "from .engine_a import *\nfrom .engine_b import *\n"
    )
    (tmp_path / "src/case/engine_a.py").write_text(
        "def ember_snow(v): return v + '-a'\n"
    )
    (tmp_path / "src/case/engine_b.py").write_text(
        "def ember_snow(v): return v + '-b'\n"
    )
    (tmp_path / "tests/test_contract.py").write_text(
        "from src.case import ember_snow\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        resolved, unresolved = codemap._resolve_import_owner_evidence(
            "tests/test_contract.py", "src.case.ember_snow"
        )
    assert resolved == ["src/case/__init__.py"]
    assert unresolved is True


def _verification_reference_case(
    tmp_path: Path, verifier_source: str
) -> dict[str, object]:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "owner.py").write_text(
        "def ember_snow(value):\n    return value\n"
    )
    (tmp_path / "tests" / "test_owner.py").write_text(verifier_source)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relevance = codemap.verification_relevance(
            "Fix ember_snow implementation and verify behavior", limit=20
        )
    return next(
        row for row in relevance["candidates"] if row["path"] == "tests/test_owner.py"
    )


def test_type_checking_only_import_is_not_authoritative_direct_reference(
    tmp_path: Path,
) -> None:
    row = _verification_reference_case(
        tmp_path,
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from src.owner import ember_snow\n\ndef test_owner():\n    assert True\n",
    )
    assert row["syntactic_reference"] is True
    assert row["reference_strength"] == "type-checking-only"
    assert row["direct_reference"] is False


def test_statically_dead_import_is_not_authoritative_direct_reference(
    tmp_path: Path,
) -> None:
    row = _verification_reference_case(
        tmp_path,
        "if False:\n    from src.owner import ember_snow\n\ndef test_owner():\n    assert True\n",
    )
    assert row["syntactic_reference"] is True
    assert row["reference_strength"] == "statically-dead"
    assert row["direct_reference"] is False


def test_reachable_unused_import_is_weaker_than_symbol_use(tmp_path: Path) -> None:
    row = _verification_reference_case(
        tmp_path,
        "from src.owner import ember_snow\n\ndef test_owner():\n    assert True\n",
    )
    assert row["syntactic_reference"] is True
    assert row["reachable_import"] is True
    assert row["reachable_symbol_use"] is False
    assert row["reference_strength"] == "reachable-import"
    assert row["direct_reference"] is False


def test_reachable_aliased_symbol_use_is_authoritative_direct_reference(
    tmp_path: Path,
) -> None:
    row = _verification_reference_case(
        tmp_path,
        "from src.owner import ember_snow as active_ember\n\ndef test_owner():\n    assert active_ember('x') == 'x'\n",
    )
    assert row["syntactic_reference"] is True
    assert row["reachable_import"] is True
    assert row["reachable_symbol_use"] is True
    assert row["reference_strength"] == "reachable-symbol-use"
    assert row["direct_reference"] is True


def test_verification_reference_index_invalidates_when_source_changes(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "owner.py").write_text(
        "def ember_snow(value):\n    return value\n"
    )
    verifier = tmp_path / "tests" / "test_owner.py"
    verifier.write_text(
        "from src.owner import ember_snow\n\ndef test_owner():\n    assert ember_snow('x') == 'x'\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.verification_relevance(
            "Fix ember_snow implementation and verify behavior", limit=20
        )
        first_row = next(
            row for row in first["candidates"] if row["path"] == "tests/test_owner.py"
        )
        assert first_row["reference_strength"] == "reachable-symbol-use"

        verifier.write_text(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from src.owner import ember_snow\n\n"
            "def test_owner():\n"
            "    assert True\n"
        )
        second = codemap.verification_relevance(
            "Fix ember_snow implementation and verify behavior", limit=20
        )
        second_row = next(
            row for row in second["candidates"] if row["path"] == "tests/test_owner.py"
        )
        assert second_row["reference_strength"] == "type-checking-only"
        assert second_row["direct_reference"] is False


def test_verification_candidate_projection_samples_pytest_config_once(
    tmp_path: Path, monkeypatch
) -> None:
    task, _ = _build_repetitive_verification_repo(tmp_path, distractors=80)
    calls = 0
    original = CodeMap._pytest_declared

    def counted(self):
        nonlocal calls
        calls += 1
        return original(self)

    monkeypatch.setattr(CodeMap, "_pytest_declared", counted)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)

    assert action["verification_relevance"]["candidate_count"] == 81
    assert calls == 1


def test_verification_reference_projection_reads_each_candidate_snapshot_once(
    tmp_path: Path, monkeypatch
) -> None:
    task, _ = _build_repetitive_verification_repo(tmp_path, distractors=80)
    import hashmarks.codemap.evidence_verification as verification_module

    calls = 0
    original = verification_module.read_python_ast

    def counted(path, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(path, *args, **kwargs)

    monkeypatch.setattr(verification_module, "read_python_ast", counted)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task, limit=20)

    candidate_count = action["verification_relevance"]["candidate_count"]
    assert candidate_count == 81
    assert calls == candidate_count
