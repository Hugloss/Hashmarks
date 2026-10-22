"""Cross-owner authority semantics must survive confusingly similar names."""

from __future__ import annotations

from pathlib import Path

from hashmarks import RepositoryIdentity
from hashmarks import test_shards as legacy_shards
from hashmarks._development import test_shards as developer_shards
from hashmarks.codemap import CodeMap


def test_developer_shard_compatibility_is_one_module_object(tmp_path: Path) -> None:
    assert legacy_shards is developer_shards
    assert legacy_shards.plan is developer_shards.plan
    assert (
        legacy_shards.repository_content_identity
        is developer_shards.developer_selection_source_identity
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_demo.py").write_text("def test_demo(): pass\n", encoding="utf-8")
    assert legacy_shards.plan(tmp_path, 1) == developer_shards.plan(tmp_path, 1)


def test_developer_identity_keeps_its_explicit_source_scope(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    authored = tests / "test_demo.py"
    authored.write_text("def test_demo(): pass\n", encoding="utf-8")
    generated = tmp_path / "generated-state"
    generated.mkdir()
    cache = generated / "untrusted.cache"
    cache.write_text("first", encoding="utf-8")
    identity = developer_shards.developer_selection_source_identity(
        tmp_path, excluded_paths=(generated,)
    )
    cache.write_text("second", encoding="utf-8")
    assert (
        developer_shards.developer_selection_source_identity(
            tmp_path, excluded_paths=(generated,)
        )
        == identity
    )
    authored.write_text("def test_demo(): assert True\n", encoding="utf-8")
    assert (
        developer_shards.developer_selection_source_identity(
            tmp_path, excluded_paths=(generated,)
        )
        != identity
    )
    # Native repository identity and this developer v2 selection identity
    # intentionally have distinct domains; don't pretend that hashes coincide.
    with RepositoryIdentity(
        tmp_path, mode="local", state_dir=tmp_path / ".identity-test"
    ) as native:
        observation = native.observe_directory(
            exclude_paths=("generated-state", ".identity-test")
        )
    assert observation.inputs.snapshot.hash
    assert identity.startswith("sha256:")


def test_verification_target_is_evidence_not_command_authority(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_demo.py").write_text("def test_demo(): pass\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['tests']\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        nomination = codemap.verification.plan("tests/test_demo.py", symbol="test_demo")
    assert nomination["available"] is True
    assert nomination["verification_target"] == {
        "path": "tests/test_demo.py",
        "test_symbol": "test_demo",
    }
    assert nomination["command_intent_authority"] == "advisory-only"
    assert nomination["execution_authority"] == "external"
    # Preserve existing callers during migration, without promoting argv.
    assert nomination["argv"] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_demo.py::test_demo",
    ]


def test_legacy_brief_safety_words_are_scoped_to_evidence(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "engine.py").write_text(
        "def widget(): return 'old'\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_engine.py").write_text(
        "from src.engine import widget\ndef test_widget(): assert widget() == 'new'\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        decision = codemap.tasks.decision_brief("widget implementation test")
        action = codemap.tasks.action_brief("widget implementation test")
    assert decision["status_scope"] == "evidence-role-coverage"
    assert action["status_scope"] == "evidence-role-coverage"
    assert action["status"] in {
        "unsafe",
        "safe-stale",
        "safe-fresh",
        "safe-unknown",
    }
